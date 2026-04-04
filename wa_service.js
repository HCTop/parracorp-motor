/**
 * wa_service.js - Servicio WhatsApp Web local
 *
 * Usa whatsapp-web.js con Chromium headless.
 * Expone API HTTP interna (solo localhost) para que Python envie mensajes.
 * Sesion persistente en /data/wa_session (Railway Volume).
 *
 * Endpoints:
 *   GET  /wa/status  - Estado de conexion
 *   GET  /wa/qr      - QR code como imagen (para escanear desde navegador)
 *   GET  /wa/qr/text - QR code como texto (para logs)
 *   POST /wa/send    - Enviar mensaje { group_name, message }
 *   GET  /wa/groups  - Lista de grupos disponibles
 */

const { Client, LocalAuth } = require('whatsapp-web.js');
const express = require('express');
const QRCode = require('qrcode');
const qrcodeTerminal = require('qrcode-terminal');
const path = require('path');
const fs = require('fs');

const app = express();
app.use(express.json());

const PORT = 3001;  // Internal only, not exposed
const DATA_DIR = fs.existsSync('/data') ? '/data' : __dirname;
const SESSION_DIR = path.join(DATA_DIR, 'wa_session');

// State
let currentQR = null;
let isReady = false;
let clientInfo = null;
let groupCache = {};  // name -> chatId
let lastError = null;

// Ensure session dir exists + clean stale locks
if (!fs.existsSync(SESSION_DIR)) {
    fs.mkdirSync(SESSION_DIR, { recursive: true });
}
// Remove Chromium lock files from previous crashed sessions
const lockFiles = ['SingletonLock', 'SingletonSocket', 'SingletonCookie'];
function cleanLocks(dir) {
    try {
        const entries = fs.readdirSync(dir, { withFileTypes: true });
        for (const e of entries) {
            const full = path.join(dir, e.name);
            if (lockFiles.includes(e.name)) {
                fs.unlinkSync(full);
                console.log(`[WA] Removed stale lock: ${full}`);
            } else if (e.isDirectory()) {
                cleanLocks(full);
            }
        }
    } catch (_) {}
}
cleanLocks(SESSION_DIR);

console.log('[WA] Iniciando whatsapp-web.js...');
console.log('[WA] Sesion en:', SESSION_DIR);

// Create WhatsApp client
const client = new Client({
    authStrategy: new LocalAuth({
        dataPath: SESSION_DIR,
    }),
    puppeteer: {
        headless: true,
        args: [
            '--no-sandbox',
            '--disable-setuid-sandbox',
            '--disable-dev-shm-usage',
            '--disable-accelerated-2d-canvas',
            '--no-first-run',
            '--no-zygote',
            '--disable-gpu',
            '--single-process',
        ],
        executablePath: process.env.CHROMIUM_PATH || undefined,
    },
});

// Events
client.on('qr', (qr) => {
    currentQR = qr;
    console.log('[WA] QR recibido - escanea con tu telefono:');
    qrcodeTerminal.generate(qr, { small: true });
    console.log('[WA] O abre: /wa/qr en el navegador');
});

client.on('ready', async () => {
    isReady = true;
    currentQR = null;
    clientInfo = client.info;
    console.log(`[WA] Conectado como: ${clientInfo.pushname} (${clientInfo.wid.user})`);

    // Cache groups
    try {
        const chats = await client.getChats();
        const groups = chats.filter(c => c.isGroup);
        groups.forEach(g => {
            groupCache[g.name] = g.id._serialized;
        });
        console.log(`[WA] ${groups.length} grupos encontrados`);
        groups.forEach(g => console.log(`  - ${g.name}`));
    } catch (e) {
        console.log('[WA] Error cargando grupos:', e.message);
    }
});

client.on('authenticated', () => {
    console.log('[WA] Sesion autenticada (guardada para proximas veces)');
});

client.on('auth_failure', (msg) => {
    lastError = `Auth failed: ${msg}`;
    console.log('[WA] Error de autenticacion:', msg);
});

client.on('disconnected', (reason) => {
    isReady = false;
    lastError = `Disconnected: ${reason}`;
    console.log('[WA] Desconectado:', reason);
    // Reconnect
    setTimeout(() => {
        console.log('[WA] Reconectando...');
        client.initialize();
    }, 5000);
});

// Initialize
client.initialize();

// === HTTP API ===

app.get('/wa/status', (req, res) => {
    res.json({
        connected: isReady,
        user: clientInfo ? clientInfo.pushname : null,
        phone: clientInfo ? clientInfo.wid.user : null,
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
    try {
        const chats = await client.getChats();
        const groups = chats.filter(c => c.isGroup);
        groupCache = {};
        groups.forEach(g => {
            groupCache[g.name] = g.id._serialized;
        });
        console.log(`[WA] ${groups.length} grupos encontrados`);
        res.json({
            connected: true,
            groups: groups.map(g => g.name),
        });
    } catch (e) {
        res.json({ connected: isReady, groups: Object.keys(groupCache), error: e.message });
    }
});

app.post('/wa/send', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ ok: false, error: 'WhatsApp no conectado' });
    }

    const { group_name, message, chat_id } = req.body;
    if (!message) {
        return res.status(400).json({ ok: false, error: 'message requerido' });
    }

    try {
        let targetId = chat_id;

        // Find group by name if no chat_id
        if (!targetId && group_name) {
            targetId = groupCache[group_name];

            // If not cached, search again
            if (!targetId) {
                const chats = await client.getChats();
                const group = chats.find(c => c.isGroup && c.name === group_name);
                if (group) {
                    targetId = group.id._serialized;
                    groupCache[group_name] = targetId;
                }
            }
        }

        if (!targetId) {
            return res.status(404).json({
                ok: false,
                error: `Grupo "${group_name}" no encontrado`,
                available: Object.keys(groupCache),
            });
        }

        await client.sendMessage(targetId, message);
        console.log(`[WA] Mensaje enviado a "${group_name || targetId}"`);
        res.json({ ok: true });

    } catch (e) {
        console.log('[WA] Error enviando:', e.message);
        res.status(500).json({ ok: false, error: e.message });
    }
});

// Send image with caption
app.post('/wa/send-image', async (req, res) => {
    if (!isReady) {
        return res.status(503).json({ ok: false, error: 'WhatsApp no conectado' });
    }

    const { group_name, image_path, caption, chat_id } = req.body;
    if (!image_path) {
        return res.status(400).json({ ok: false, error: 'image_path requerido' });
    }

    try {
        let targetId = chat_id;
        if (!targetId && group_name) {
            targetId = groupCache[group_name];
            if (!targetId) {
                const chats = await client.getChats();
                const group = chats.find(c => c.isGroup && c.name === group_name);
                if (group) {
                    targetId = group.id._serialized;
                    groupCache[group_name] = targetId;
                }
            }
        }

        if (!targetId) {
            return res.status(404).json({ ok: false, error: `Grupo "${group_name}" no encontrado` });
        }

        const { MessageMedia } = require('whatsapp-web.js');
        const media = MessageMedia.fromFilePath(image_path);
        await client.sendMessage(targetId, media, { caption: caption || '' });
        console.log(`[WA] Imagen enviada a "${group_name || targetId}"`);
        res.json({ ok: true });

    } catch (e) {
        console.log('[WA] Error enviando imagen:', e.message);
        res.status(500).json({ ok: false, error: e.message });
    }
});

// Start server
app.listen(PORT, '127.0.0.1', () => {
    console.log(`[WA] API HTTP en http://127.0.0.1:${PORT}`);
});
