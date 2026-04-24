# -*- coding: utf-8 -*-
"""
whatsapp_bot.py - Envio de senales a WhatsApp

Se comunica con wa_service.js (Node.js local) via HTTP.
Mismo formato que telegram_bot.py.
"""
import requests
import threading
from config import log as mlog

_WA_URL = "http://127.0.0.1:3001"
_GROUP_NAME = ""


def configure(group_name):
    """Configura el nombre del grupo de WhatsApp."""
    global _GROUP_NAME
    _GROUP_NAME = group_name
    if _GROUP_NAME:
        mlog("WA", f"Grupo configurado: {_GROUP_NAME}")


def is_ready():
    """Verifica si WhatsApp Web esta conectado."""
    try:
        r = requests.get(f"{_WA_URL}/wa/status", timeout=3)
        return r.json().get("connected", False)
    except Exception:
        return False


def is_configured():
    return bool(_GROUP_NAME)


def _send(message):
    """Envia mensaje al grupo configurado."""
    if not _GROUP_NAME:
        return False
    try:
        r = requests.post(f"{_WA_URL}/wa/send", json={
            "group_name": _GROUP_NAME,
            "message": message,
        }, timeout=15)
        if r.status_code == 200:
            return True
        else:
            mlog("WA", f"Error {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        mlog("WA", f"Error enviando: {e}")
        return False


def _send_async(message):
    """Envia en hilo separado."""
    threading.Thread(target=_send, args=(message,), daemon=True).start()


def _send_image(image_path, caption=""):
    """Envia imagen al grupo configurado."""
    if not _GROUP_NAME:
        return False
    try:
        r = requests.post(f"{_WA_URL}/wa/send-image", json={
            "group_name": _GROUP_NAME,
            "image_path": image_path,
            "caption": caption,
        }, timeout=30)
        if r.status_code == 200:
            return True
        else:
            mlog("WA", f"Error imagen {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        mlog("WA", f"Error enviando imagen: {e}")
        return False


def _send_image_async(image_path, caption=""):
    """Envia imagen en hilo separado."""
    threading.Thread(target=_send_image, args=(image_path, caption), daemon=True).start()


# === Formateo ================================================================

def _fmt_price(price):
    try:
        price = float(price or 0)
    except (ValueError, TypeError):
        return "0"
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    return f"{price:.6f}"


def _tf_label(tf):
    _map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "240": "4h", "1D": "1D"}
    return _map.get(str(tf), str(tf))


def send_signal_open(signal, chart_path=None):
    """Envia senal de apertura, con grafico si disponible."""
    if not is_configured():
        return

    sym = signal.get("symbol", "")
    action = signal.get("action", "")
    entry = float(signal.get("entry_price", 0) or 0)
    sl = float(signal.get("sl", 0) or 0)
    tp = float(signal.get("tp", 0) or 0)
    conf = int(signal.get("confidence", 0) or 0)
    reason = signal.get("reason", "") or ""
    rr = float(signal.get("risk_reward", 0) or 0)
    tf = _tf_label(signal.get("timeframe", "60"))
    lote = float(signal.get("lote", 0) or 0)
    unidades = float(signal.get("unidades", 0) or 0)
    lote_std = float(signal.get("lote_std", 0) or 0)
    sig_id = signal.get("id", "")

    emoji = "\U0001F7E2" if action == "BUY" else "\U0001F534"
    arrow = "\u2B06" if action == "BUY" else "\u2B07"
    dir_text = "COMPRA" if action == "BUY" else "VENTA"

    text = (
        f"{emoji} *SENAL {dir_text}* {arrow}\n"
        f"\n"
        f"\U0001F4B9 *{sym}* | {tf}\n"
        f"\n"
        f"\u2022 Entrada: `{_fmt_price(entry)}`\n"
        f"\u2022 Stop Loss: `{_fmt_price(sl)}`\n"
        f"\u2022 Take Profit: `{_fmt_price(tp)}`\n"
        f"\u2022 R:R: *{rr:.1f}:1* | Conf: {conf}%\n"
    )
    lote_txt = f"{lote_std:.2f}" if lote_std >= 0.01 else "0.01"
    min_lot = signal.get("min_lot_applied", False)
    text += f"\u2022 Lote: *{lote_txt}*"
    if unidades > 0:
        text += f" ({unidades:.0f} uds)"
    if min_lot:
        text += " ⚠️ lote minimo broker"
    text += "\n"
    trailing = signal.get("trailing_stop", "none")
    if trailing != "none":
        ts_map = {
            "breakeven": "Breakeven (SL a entrada al 50% del TP)",
            "atr1": "ATR Trail (SL sigue al precio a 1 ATR)",
            "atr2": "ATR Agresivo (SL sigue cada +0.5 ATR)",
        }
        ts_label = ts_map.get(trailing, trailing)
        text += f"\u2022 Trailing: *{ts_label}*\n"
    text += f"\n\U0001F916 By ParraCorp-V2 | {sig_id}"

    # Enviar con grafico si disponible
    import os
    if chart_path and os.path.exists(chart_path):
        _send_image_async(chart_path, caption=text)
    else:
        _send_async(text)
    mlog("WA", f"Senal {sig_id} {action} {sym} enviada")


def send_signal_close(signal):
    """Envia cierre de senal."""
    if not is_configured():
        return

    sym = signal.get("symbol", "")
    status = signal.get("status", "")
    entry = float(signal.get("entry_price", 0) or 0)
    exit_price = float(signal.get("exit_price", 0) or 0)
    pnl_pct = float(signal.get("pnl_pct", 0) or 0)
    pnl_usd = float(signal.get("pnl_usd", 0) or 0)
    sig_id = signal.get("id", "")
    tf = _tf_label(signal.get("timeframe", "60"))

    result = "TP ALCANZADO" if status == "HIT_TP" else "SL ALCANZADO"
    if status == "TRAILING_CLOSE":
        result = "TRAILING STOP (profit protegido)"
    elif status == "CANCELLED":
        result = "CANCELADA"
    elif status == "SWAP_CLOSE":
        pnl_sign = f"+{pnl_usd:.2f}\u20ac" if pnl_usd >= 0 else f"{pnl_usd:.2f}\u20ac"
        result = f"SWAP PROTECT ({pnl_sign})"
    elif status == "TREND_PROTECT":
        pnl_sign = f"+{pnl_usd:.2f}\u20ac" if pnl_usd >= 0 else f"{pnl_usd:.2f}\u20ac"
        result = f"TREND PROTECT ({pnl_sign})"
    emoji = "\u2705" if status in ("HIT_TP", "TRAILING_CLOSE") else "\u274C"
    if status == "TRAILING_CLOSE":
        emoji = "\U0001F3AF"
    elif status in ("SWAP_CLOSE", "TREND_PROTECT"):
        emoji = "\U0001F6E1" if pnl_usd >= 0 else "\u26A0"
    sign = "+" if pnl_pct >= 0 else ""

    pnl_emoji = "\U0001F4B0" if pnl_pct >= 0 else "\U0001F4B8"
    text = (
        f"{emoji} *CIERRE {result}*\n"
        f"\n"
        f"\U0001F4B9 *{sym}* | {tf}\n"
        f"\u2022 Entrada: `{_fmt_price(entry)}`\n"
        f"\u2022 Salida: `{_fmt_price(exit_price)}`\n"
        f"{pnl_emoji} PnL: *{sign}{pnl_pct:.2f}%* ({sign}{pnl_usd:.2f}\u20ac)\n"
        f"\n\U0001F916 By ParraCorp-V2 | {sig_id}"
    )

    _send_async(text)
    mlog("WA", f"Cierre {sig_id} {status} {sym} enviado")


def send_daily_summary(stats):
    """Envia resumen diario."""
    if not is_configured():
        return

    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    wr = stats.get("win_rate", 0)
    pnl = stats.get("total_pnl_usd", 0)
    pf = stats.get("profit_factor", 0)
    sign = "+" if pnl >= 0 else ""

    pnl_emoji = "\U0001F4B0" if pnl >= 0 else "\U0001F4B8"
    text = (
        f"\U0001F4CA *RESUMEN DIARIO*\n"
        f"\n"
        f"\u2022 Operaciones: {wins + losses}\n"
        f"\u2022 Wins/Losses: {wins}W / {losses}L\n"
        f"\u2022 Win Rate: {wr:.0f}%\n"
        f"\u2022 Profit Factor: {pf:.2f}\n"
        f"\n"
        f"{pnl_emoji} PnL Total: *{sign}{pnl:.2f}\u20ac*\n"
        f"\n\U0001F916 By ParraCorp-V2 Motor"
    )

    _send_async(text)


def send_history_summary(trades, period_label=""):
    """Envia resumen de historial."""
    if not is_configured():
        return
    if not trades:
        _send_async(f"📊 *Historial {period_label}*\n\nSin operaciones.")
        return
    closed = [t for t in trades if t.get("status") in ("HIT_TP", "HIT_SL", "TRAILING_CLOSE", "CANCELLED", "SWAP_CLOSE", "TREND_PROTECT")]
    wins = [t for t in closed if t.get("pnl_usd", 0) > 0]
    losses = [t for t in closed if t.get("pnl_usd", 0) <= 0]
    total_pnl = sum(t.get("pnl_usd", 0) for t in closed)
    wr = len(wins) / len(closed) * 100 if closed else 0
    sign = "+" if total_pnl >= 0 else ""
    lines = [
        f"📊 *HISTORIAL {period_label.upper()}*",
        f"",
        f"• Operaciones: {len(closed)}",
        f"• W/L: {len(wins)}W / {len(losses)}L | WR: {wr:.0f}%",
        f"",
    ]
    trade_lines = []
    for t in closed:
        emoji = "✅" if t.get("pnl_usd", 0) > 0 else "❌"
        trade_lines.append(f"{emoji} {t.get('id','')} {t.get('action','')} {t.get('symbol','')} {t.get('pnl_usd',0):+.2f}\u20ac")

    footer = f"\n💰 PnL Total: *{sign}{total_pnl:.2f}\u20ac*\n\n🤖 By ParraCorp-V2 Motor"

    # Split into chunks to stay under message limits
    chunk_size = 40
    if len(trade_lines) <= chunk_size:
        lines.extend(trade_lines)
        lines.append(footer)
        _send_async("\n".join(lines))
    else:
        lines.extend(trade_lines[:chunk_size])
        _send_async("\n".join(lines))
        for i in range(chunk_size, len(trade_lines), chunk_size):
            chunk = trade_lines[i:i + chunk_size]
            part_num = i // chunk_size + 1
            total_parts = (len(trade_lines) + chunk_size - 1) // chunk_size
            msg_lines = [f"📊 *HISTORIAL {period_label.upper()} ({part_num+1}/{total_parts})*", ""]
            msg_lines.extend(chunk)
            if i + chunk_size >= len(trade_lines):
                msg_lines.append(footer)
            _send_async("\n".join(msg_lines))


def send_custom(text):
    """Envia mensaje personalizado."""
    if is_configured():
        _send_async(text)
