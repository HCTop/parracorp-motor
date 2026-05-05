# -*- coding: utf-8 -*-
"""
telegram_bot.py - Envio de senales a Telegram

Usa la Bot API de Telegram (solo requests, sin dependencias extra).
Envia senales de apertura, cierre y resumen diario a un grupo/canal.
"""
import os
import requests
import threading
from config import log as mlog

_TOKEN = ""
_CHAT_ID = ""


def configure(token, chat_id):
    """Configura el bot con token y chat_id."""
    global _TOKEN, _CHAT_ID
    _TOKEN = token
    _CHAT_ID = str(chat_id)
    if _TOKEN and _CHAT_ID:
        mlog("TG", f"Bot configurado (chat_id={_CHAT_ID})")


def is_configured():
    return bool(_TOKEN and _CHAT_ID)


def _send_message(text, parse_mode="HTML"):
    """Envia mensaje al grupo/canal configurado."""
    if not _TOKEN or not _CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{_TOKEN}/sendMessage"
        r = requests.post(url, json={
            "chat_id": _CHAT_ID,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }, timeout=10)
        if r.status_code == 200:
            return True
        else:
            mlog("TG", f"Error {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        mlog("TG", f"Error enviando: {e}")
        return False


def _send_async(text, parse_mode="HTML"):
    """Envia mensaje en hilo separado para no bloquear."""
    threading.Thread(
        target=_send_message,
        args=(text, parse_mode),
        daemon=True,
    ).start()


def _send_photo(image_path, caption=""):
    """Envia foto al grupo/canal configurado."""
    if not _TOKEN or not _CHAT_ID:
        return False
    try:
        url = f"https://api.telegram.org/bot{_TOKEN}/sendPhoto"
        with open(image_path, "rb") as f:
            r = requests.post(url, data={
                "chat_id": _CHAT_ID,
                "caption": caption,
                "parse_mode": "HTML",
            }, files={"photo": f}, timeout=30)
        if r.status_code == 200:
            return True
        else:
            mlog("TG", f"Error foto {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        mlog("TG", f"Error enviando foto: {e}")
        return False


def _send_photo_async(image_path, caption=""):
    """Envia foto en hilo separado."""
    threading.Thread(
        target=_send_photo,
        args=(image_path, caption),
        daemon=True,
    ).start()


# === Formateo de senales =====================================================

def _fmt_price(price, symbol=""):
    """Formatea precio con decimales apropiados."""
    try:
        price = float(price or 0)
    except (ValueError, TypeError):
        return "0"
    if price >= 1000:
        return f"{price:,.2f}"
    elif price >= 1:
        return f"{price:.4f}"
    else:
        return f"{price:.6f}"


def _tf_label(tf):
    _map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "240": "4h", "1D": "1D"}
    return _map.get(str(tf), str(tf))




def _pip_size(symbol):
    """Pip size por instrumento (estandar MT4/MT5)."""
    s = (symbol or "").upper()
    if "JPY" in s: return 0.01
    if "XAU" in s: return 0.10
    if "XAG" in s: return 0.01
    if "BTC" in s or "ETH" in s: return 1.0
    if any(x in s for x in ("US30","NAS","SPX","US500","US100","GER","UK100","JP225")):
        return 1.0
    return 0.0001


def _pips_for(symbol, entry_price, pnl_pct):
    """Pips con signo (positivo = profit)."""
    if entry_price <= 0: return 0
    ps = _pip_size(symbol)
    if ps <= 0: return 0
    return int(entry_price * pnl_pct / 100.0 / ps)


def _extract_source(signal):
    """Devuelve el nombre de la fuente (signal_name o el primer [X] del reason).
    Para senales internas devuelve 'ParraCorp Motor'."""
    src = signal.get("signal_name") or signal.get("source")
    if src and src not in ("external", "internal"):
        return src
    reason = signal.get("reason", "") or ""
    if reason.startswith("[") and "]" in reason:
        end = reason.index("]")
        candidate = reason[1:end].strip()
        if candidate:
            return candidate
    return "ParraCorp Motor"


def send_signal_open(signal, chart_path=None):
    """Envia senal de apertura al grupo, con grafico si disponible."""
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
        f"{emoji} <b>SENAL {dir_text}</b> {arrow}\n"
        f"\n"
        f"\U0001F4B9 <b>{sym}</b> | {tf}\n"
        f"\n"
        f"\u2022 Entrada: <code>{_fmt_price(entry, sym)}</code>\n"
        f"\u2022 Stop Loss: <code>{_fmt_price(sl, sym)}</code>\n"
        f"\u2022 Take Profit: <code>{_fmt_price(tp, sym)}</code>\n"
        f"\u2022 R:R: <b>{rr:.1f}:1</b> | Conf: {conf}%\n"
    )
    lote_txt = f"{lote_std:.2f}" if lote_std >= 0.01 else "0.01"
    min_lot = signal.get("min_lot_applied", False)
    text += f"\u2022 Lote: <b>{lote_txt}</b>"
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
        text += f"\u2022 Trailing: <b>{ts_label}</b>\n"
    text += f"\n\U0001F916 By {_extract_source(signal)} | {sig_id}"

    # Enviar con grafico si disponible
    if chart_path and os.path.exists(chart_path):
        _send_photo_async(chart_path, caption=text)
    else:
        _send_async(text)
    mlog("TG", f"Senal {sig_id} {action} {sym} enviada")


def send_signal_close(signal):
    """Envia cierre de senal al grupo."""
    if not is_configured():
        return

    sym = signal.get("symbol", "")
    action = signal.get("action", "")
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
    # Emoji segun PnL real (parcial con breakeven+ = win visual).
    if status == "CANCELLED":
        emoji = "\u26D4"
    elif status == "TRAILING_CLOSE":
        emoji = "\U0001F3AF"
    elif status in ("SWAP_CLOSE", "TREND_PROTECT"):
        emoji = "\U0001F6E1" if pnl_usd >= 0 else "\u26A0"
    else:
        emoji = "\u2705" if pnl_usd > 0 else "\u274C"

    pnl_emoji = "\U0001F4B0" if pnl_usd >= 0 else "\U0001F4B8"
    sign = "+" if pnl_pct >= 0 else ""
    pips = _pips_for(sym, entry, pnl_pct)
    pips_str = f"{'+' if pips >= 0 else ''}{pips}pip"

    text = (
        f"{emoji} <b>CIERRE {result}</b>\n"
        f"\n"
        f"\U0001F4B9 <b>{sym}</b> | {tf}\n"
        f"\u2022 Entrada: <code>{_fmt_price(entry, sym)}</code>\n"
        f"\u2022 Salida: <code>{_fmt_price(exit_price, sym)}</code>\n"
        f"{pnl_emoji} PnL: <b>{sign}{pnl_pct:.2f}%</b> ({pips_str} | {sign}{pnl_usd:.2f}\u20ac)\n"
        f"\n"
        f"\U0001F916 By {_extract_source(signal)} | {sig_id}"
    )

    _send_async(text)
    mlog("TG", f"Cierre {sig_id} {status} {sym} enviado")


def send_daily_summary(stats):
    """Envia resumen diario al grupo."""
    if not is_configured():
        return

    wr = stats.get("win_rate", 0)
    wins = stats.get("wins", 0)
    losses = stats.get("losses", 0)
    pnl = stats.get("total_pnl_usd", 0)
    pf = stats.get("profit_factor", 0)
    best = stats.get("best_trade", 0)
    worst = stats.get("worst_trade", 0)

    pnl_emoji = "\U0001F4B0" if pnl >= 0 else "\U0001F4B8"

    text = (
        f"\U0001F4CA <b>RESUMEN DIARIO</b>\n"
        f"\n"
        f"\u2022 Operaciones: {wins + losses}\n"
        f"\u2022 Wins/Losses: {wins}W / {losses}L\n"
        f"\u2022 Win Rate: {wr:.0f}%\n"
        f"\u2022 Profit Factor: {pf:.2f}\n"
        f"\u2022 Mejor: {best:+.2f}%\n"
        f"\u2022 Peor: {worst:+.2f}%\n"
        f"\n"
        f"{pnl_emoji} PnL Total: <b>{'+' if pnl >= 0 else ''}{pnl:.2f}\u20ac</b>\n"
        f"\n"
        f"\U0001F916 By ParraCorp-V2 Motor"
    )

    _send_async(text)
    mlog("TG", "Resumen diario enviado")


def send_history_summary(trades, period_label=""):
    """Envia resumen de historial al grupo."""
    if not is_configured():
        return
    if not trades:
        _send_async(f"\U0001F4CA <b>Historial {period_label}</b>\n\nSin operaciones.")
        return

    closed = [t for t in trades if t.get("status") in ("HIT_TP", "HIT_SL", "TRAILING_CLOSE", "CANCELLED", "SWAP_CLOSE", "TREND_PROTECT")]
    wins = [t for t in closed if t.get("pnl_usd", 0) > 0]
    losses = [t for t in closed if t.get("pnl_usd", 0) <= 0]
    total_pnl = sum(t.get("pnl_usd", 0) for t in closed)
    wr = len(wins) / len(closed) * 100 if closed else 0

    pnl_emoji = "\U0001F4B0" if total_pnl >= 0 else "\U0001F4B8"
    sign = "+" if total_pnl >= 0 else ""

    lines = [
        f"\U0001F4CA <b>HISTORIAL {period_label.upper()}</b>",
        f"",
        f"\u2022 Operaciones: {len(closed)}",
        f"\u2022 Wins/Losses: {len(wins)}W / {len(losses)}L",
        f"\u2022 Win Rate: {wr:.0f}%",
        f"",
    ]

    # List ALL trades, splitting into multiple messages if needed
    trade_lines = []
    for t in closed:
        sym = t.get("symbol", "?")
        action = t.get("action", "?")
        pnl = t.get("pnl_usd", 0)
        sid = t.get("id", "")
        emoji = "\u2705" if pnl > 0 else "\u274C"
        trade_lines.append(f"{emoji} {sid} {action} {sym} {pnl:+.2f}\u20ac")

    footer = [
        f"",
        f"{pnl_emoji} PnL Total: <b>{sign}{total_pnl:.2f}\u20ac</b>",
        f"",
        f"\U0001F916 By ParraCorp-V2 Motor",
    ]

    # Split into chunks to stay under Telegram 4096 char limit
    chunk_size = 40  # trades per message
    if len(trade_lines) <= chunk_size:
        lines.extend(trade_lines)
        lines.extend(footer)
        _send_async("\n".join(lines))
    else:
        # First message: header + first chunk
        lines.extend(trade_lines[:chunk_size])
        _send_async("\n".join(lines))
        # Middle messages: remaining chunks
        for i in range(chunk_size, len(trade_lines), chunk_size):
            chunk = trade_lines[i:i + chunk_size]
            part_num = i // chunk_size + 1
            total_parts = (len(trade_lines) + chunk_size - 1) // chunk_size
            msg_lines = [f"\U0001F4CA <b>HISTORIAL {period_label.upper()} ({part_num+1}/{total_parts})</b>", ""]
            msg_lines.extend(chunk)
            if i + chunk_size >= len(trade_lines):
                msg_lines.extend(footer)
            _send_async("\n".join(msg_lines))
    mlog("TG", f"Historial {period_label} enviado ({len(closed)} trades)")


def send_custom(text):
    """Envia mensaje personalizado."""
    if not is_configured():
        return
    _send_async(text)
