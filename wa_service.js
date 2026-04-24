/**
 * wa_service.js - Servicio WhatsApp via Baileys (WebSocket directo)
 *
 * Reemplazo de whatsapp-web.js (Chromium + scraping) por
 * @whiskeysockets/baileys (WebSocket a WhatsApp). Mas estable,
 * mas ligero (no usa Chromium) y mas resistente a cambios del
 * frontend de WhatsApp Web.
 *
 * API HTTP identica a la version anterior para no tocar Python:
 *   GET  /wa/status       - Estado
 *   GET  /wa/qr           - QR como pagina HTML
 *   GET  /wa/qr/text      - QR como JSON
 *   GET  /wa/groups       - Lista de grupos
 *   POST /wa/send         - { group_name | chat_id, message }
 *   POST /wa/send-image   - { group_name | chat_id, image_path, caption }
 */
const {
    default: makeWASocket,
    useMultiFileAuthState,
    DisconnectReason,
    Browsers,
    fetchLatestBaileysVersion,
} = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const express = require('express');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = 3001;
const DATA_DIR = fs.existsSync('/data') ? '/data' : __dirname;
const SESSION_DIR = path.join(DATA_DIR, 'wa_session');

if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
}

// Logger compatible con baileys (evita dep de pino).
// Nivel 'warn' para no spamear pero ver problemas reales.
function makeLogger(level) {
    const logger = {
        level: level,
        trace: () => {},
        debug: () => {},
        info: (...args) => console.log('[WA-baileys]', ...args.map(a => typeof a === 'object' ? JSON.stringify(a).slice(0, 300) : a)),
        warn: (...args) => console.log('[WA-baileys-warn]', ...args.map(a => typeof a === 'object' ? JSON.stringify(a).slice(0, 300) : a)),
        error: (...args) => console.error('[WA-baileys-error]', ...args.map(a => typeof a === 'object' ? JSON.stringify(a).slice(0, 500) : a)),
        fatal: (...args) => console.error('[WA-baileys-fatal]', ...args.map(a => typeof a === 'object' ? JSON.stringify(a).slice(0, 500) : a)),
        child() { return logger; },
    };
    return logger;
}
const logger = makeLogger('warn');

// State
let sock = null;
let currentQR = null;
let isReady = false;
let me = null;
let groupCache = {};  // name -> jid
let lastError = null;

console.log('[WA] Iniciando Baileys...');
console.log('[WA] Sesion en:', SESSION_DIR);

async function refreshGroups() {
    if (!sock) return;
    try {
        const groups = await sock.groupFetchAllParticipating();
        groupCache = {};
        for (const jid of Object.keys(groups)) {
            const info = groups[jid];
            if (info && info.subject) {
                groupCache[info.subject] = jid;
            }
        }
        console.log(`[WA] ${Object.keys(groupCache).length} grupos encontrados`);
        Object.keys(groupCache).forEach(n => console.log(`  - ${n}`));
    } catch (e) {
        console.log('[WA] Error cargando grupos:', e.message);
    }
}

async function startBaileys() {
    try {
        const { state, saveCreds } = await useMultiFileAuthState(SESSION_DIR);

        // Pide a la API de Baileys la version vigente del protocolo WhatsApp Web,
        // evita rechazos del servidor (Connection Failure 405) por appVersion obsoleta.
        let waVersion;
        try {
            const v = await fetchLatestBaileysVersion();
            waVersion = v.version;
            console.log(`[WA] Usando WA Web version ${waVersion.join('.')} (latest=${v.isLatest})`);
        } catch (e) {
            console.log('[WA] No pude obtener version latest:', e.message, '- uso default de la lib');
        }

        sock = makeWASocket({
            version: waVersion,
            auth: state,
            logger: logger,
            printQRInTerminal: false,
            browser: Browsers.ubuntu('ParraCorp'),
            markOnlineOnConnect: false,
            syncFullHistory: false,
        });

        sock.ev.on('creds.update', saveCreds);

        sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                currentQR = qr;
                console.log('[WA] QR recibido - escanea con tu telefono:');
                qrcodeTerminal.generate(qr, { small: true });
                console.log('[WA] O abre /wa/qr en el navegador');
            }

            if (connection === 'open') {
                isReady = true;
                currentQR = null;
                lastError = null;
                me = sock.user;
                console.log(`[WA] Conectado como: ${me?.name || me?.id}`);
                // Pequena espera para que el store se estabilice
                setTimeout(() => refreshGroups(), 2000);
            }

            if (connection === 'close') {
                isReady = false;
                const statusCode = (lastDisconnect?.error instanceof Boom)
                    ? lastDisconnect.error.output.statusCode
                    : (lastDisconnect?.error?.output?.statusCode || 0);
                const loggedOut = statusCode === DisconnectReason.loggedOut;

                console.log(`[WA] Desconectado (code=${statusCode}, loggedOut=${loggedOut})`);

                if (loggedOut) {
                    lastError = 'Sesion cerrada - hace falta nuevo QR';
                    // Limpiar credenciales para forzar nuevo QR
                    try {
                        fs.rmSync(SESSION_DIR, { recursive: true, force: true });
                        fs.mkdirSync(SESSION_DIR, { recursive: true });
                    } catch (_) {}
                    setTimeout(() => startBaileys(), 3000);
                } else {
                    lastError = `Disconnected (${statusCode})`;
                    setTimeout(() => startBaileys(), 5000);
                }
            }
        });

    } catch (e) {
        console.log('[WA] Error iniciando Baileys:', e.message);
        lastError = e.message;
        setTimeout(() => startBaileys(), 10000);
    }
}

// === HTTP API ===

app.get('/wa/status', (req, res) => {
    res.json({
        connected: isReady,
        user: me?.name || null,
        phone: me?.id ? String(me.id).split(':')[0].split('@')[0] : null,
        groups: Object.keys(groupCache).length,
        qr_pending: currentQR !== null,
        error: lastError,
    });
});

app.get('/wa/qr', async (req, res) => {
    if (!currentQR) {
        if (isReady) {
            return res.send('<h2>WhatsApp ya esta conectado!</h2>');
        }
        return res.send('<h2>Esperando QR... recarga en unos segundos</h2><meta http-equiv="refresh" content="3">');
    }
    try {
        const qrImage = await QRCode.toDataURL(currentQR, { width: 300 });
        res.send(`
            <html>
            <body style="display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;background:#1a1a2e;color:white;font-family:sans-serif;">
                <h2>Escanea con WhatsApp</h2>
                <p>WhatsApp > Menu > Dispositivos vinculados > Vincular</p>
                <img src="${qrImage}" style="margin:20px;border-radius:10px;" />
                <p style="color:#888;">Se recarga automaticamente</p>
                <meta http-equiv="refresh" content="5">
            </body>
            </html>
        `);
    } catch (e) {
        res.status(500).send('Error generando QR');
    }
});

app.get('/wa/qr/text', (req, res) => {
    if (!currentQR) {
        return res.json({ qr: null, connected: isReady });
    }
    res.json({ qr: currentQR, connected: false });
});

app.get('/wa/groups', async (req, res) => {
    if (!isReady) {
        return res.json({ connected: false, groups: [] });
    }
    await refreshGroups();
    res.json({
        connected: true,
        groups: Object.keys(groupCache),
    });
});

async function resolveJid(group_name, chat_id) {
    if (chat_id) return chat_id;
    if (!group_name) return null;
    let jid = groupCache[group_name];
    if (!jid) {
        await refreshGroups();
        jid = groupCache[group_name];
    }
    return jid;
}

app.post('/wa/send', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ ok: false, error: 'WhatsApp no conectado' });
    }
    const { group_name, message, chat_id } = req.body;
    if (!message) {
        return res.status(400).json({ ok: false, error: 'message requerido' });
    }
    try {
        const jid = await resolveJid(group_name, chat_id);
        if (!jid) {
            return res.status(404).json({
                ok: false,
                error: `Grupo "${group_name}" no encontrado`,
                available: Object.keys(groupCache),
            });
        }
        await sock.sendMessage(jid, { text: message });
        console.log(`[WA] Mensaje enviado a "${group_name || jid}"`);
        res.json({ ok: true });
    } catch (e) {
        console.log('[WA] Error enviando:', e.message);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.post('/wa/send-image', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ ok: false, error: 'WhatsApp no conectado' });
    }
    const { group_name, image_path, caption, chat_id } = req.body;
    if (!image_path) {
        return res.status(400).json({ ok: false, error: 'image_path requerido' });
    }
    try {
        const jid = await resolveJid(group_name, chat_id);
        if (!jid) {
            return res.status(404).json({ ok: false, error: `Grupo "${group_name}" no encontrado` });
        }
        const buffer = fs.readFileSync(image_path);
        await sock.sendMessage(jid, { image: buffer, caption: caption || '' });
        console.log(`[WA] Imagen enviada a "${group_name || jid}"`);
        res.json({ ok: true });
    } catch (e) {
        console.log('[WA] Error enviando imagen:', e.message);
        res.status(500).json({ ok: false, error: e.message });
    }
});

app.listen(PORT, '127.0.0.1', () => {
    console.log(`[WA] API HTTP en http://127.0.0.1:${PORT}`);
});

startBaileys();
