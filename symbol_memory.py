# -*- coding: utf-8 -*-
"""
symbol_memory.py - Memoria de rendimiento por simbolo y del dia.

Lee el historial real (signals.get_history) y devuelve texto compacto e
informativo para inyectar en el prompt de las IAs. No bloquea ninguna
decision: es solo contexto para que el modelo sea consciente de como le
ha ido en cada simbolo recientemente.
"""
import time
import datetime

_CLOSED_STATES = ("HIT_TP", "HIT_SL", "TRAILING_CLOSE")


def _load_closed():
    try:
        from signals import get_history
        all_sigs = get_history(limit=500)  # mas reciente primero
    except Exception:
        return []
    return [s for s in all_sigs if s.get("status", "") in _CLOSED_STATES]


def get_symbol_memory(symbol, days=30, min_trades=5):
    """
    Devuelve dict con estadisticas del simbolo en la ventana dada.
    Si hay menos de min_trades operaciones cerradas, devuelve None
    (la IA usara su criterio normal).
    """
    closed = _load_closed()
    if not closed:
        return None

    cutoff = time.time() - days * 86400
    rows = [s for s in closed
            if s.get("symbol", "") == symbol
            and s.get("timestamp", 0) >= cutoff]

    if len(rows) < min_trades:
        return None

    wins = [r for r in rows if r.get("pnl_pct", 0) > 0]
    losses = [r for r in rows if r.get("pnl_pct", 0) <= 0]
    pnl_usd = sum(r.get("pnl_usd", 0) for r in rows)
    wr = len(wins) / len(rows) * 100
    avg_loss = (sum(r.get("pnl_usd", 0) for r in losses) / len(losses)) if losses else 0
    avg_win = (sum(r.get("pnl_usd", 0) for r in wins) / len(wins)) if wins else 0

    # Racha actual de perdidas (contando desde la mas reciente)
    consec = 0
    for r in rows:  # mas reciente primero
        if r.get("pnl_pct", 0) <= 0:
            consec += 1
        else:
            break

    # Ultimas 5 en orden cronologico
    rows_chrono = list(reversed(rows))
    last5 = ["W" if r.get("pnl_pct", 0) > 0 else "L" for r in rows_chrono[-5:]]

    return {
        "symbol": symbol,
        "n": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(wr, 1),
        "pnl_usd": round(pnl_usd, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "avg_win_usd": round(avg_win, 2),
        "consecutive_losses": consec,
        "last5": " ".join(last5),
        "days": days,
    }


def format_symbol_memory(mem):
    if not mem:
        return ""
    return (
        f"\n=== TU HISTORIAL CON {mem['symbol']} (ultimos {mem['days']} dias) ===\n"
        f"Operaciones cerradas: {mem['n']}  "
        f"({mem['wins']} ganadas / {mem['losses']} perdidas, WR {mem['win_rate']}%)\n"
        f"PnL acumulado: {mem['pnl_usd']:+.2f} USD  "
        f"| Ganancia media: {mem['avg_win_usd']:+.2f}  "
        f"| Perdida media: {mem['avg_loss_usd']:+.2f}\n"
        f"Racha actual de perdidas: {mem['consecutive_losses']}  "
        f"| Ultimas 5: {mem['last5']}\n"
        f"(Datos informativos del fichero historico. Tu decides libremente.)"
    )


def get_day_memory():
    """Estado de operaciones cerradas HOY."""
    closed = _load_closed()
    if not closed:
        return None

    today = datetime.date.today()
    rows = []
    for s in closed:
        ts = s.get("exit_ts", 0) or s.get("timestamp", 0)
        if ts <= 0:
            continue
        try:
            d = datetime.datetime.fromtimestamp(ts).date()
        except Exception:
            continue
        if d == today:
            rows.append(s)

    if not rows:
        return None

    wins = [r for r in rows if r.get("pnl_pct", 0) > 0]
    pnl_usd = sum(r.get("pnl_usd", 0) for r in rows)
    return {
        "n": len(rows),
        "wins": len(wins),
        "losses": len(rows) - len(wins),
        "pnl_usd": round(pnl_usd, 2),
    }


def format_day_memory(day, capital):
    if not day:
        return ""
    dd_pct = (day["pnl_usd"] / capital * 100) if capital and capital > 0 else 0
    return (
        f"\n=== ESTADO DEL DIA ===\n"
        f"Operaciones cerradas hoy: {day['n']}  "
        f"({day['wins']} ganadas / {day['losses']} perdidas)\n"
        f"PnL del dia: {day['pnl_usd']:+.2f} USD ({dd_pct:+.1f}% del capital)"
    )
