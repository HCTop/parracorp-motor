# -*- coding: utf-8 -*-
"""
signals.py - Capa 8: Motor de Senales v3.1
ParraCorp v3.1

Estructura de senal enriquecida con TQS, regimen, consensus, MTF, OFP.
Paper trading contra precios reales. Sin broker.
"""
import json
import os
import time
import threading
from config import data_path, log as mlog, state

def _send_alert(sig, symbol, title, msg):
    """Envia alerta a push + telegram + whatsapp."""
    try:
        from bot import _push_send
        _push_send(title, msg)
    except Exception as e:
        mlog("ALERT", f"Push error {symbol}: {e}")
    try:
        import telegram_bot
        telegram_bot.send_custom(msg)
    except Exception as e:
        mlog("ALERT", f"Telegram error {symbol}: {e}")
    try:
        import whatsapp_bot
        whatsapp_bot.send_custom(msg)
    except Exception as e:
        mlog("ALERT", f"WhatsApp error {symbol}: {e}")

SIGNALS_FILE = data_path("signals_v3.json")
HISTORY_FILE = data_path("history_v3.json")
TRADES_JSONL = data_path("trades.jsonl")


def _append_trade_event(event_type, payload):
    """Persiste un evento de trade (TRADE_OPEN/TRADE_CLOSE) en trades.jsonl."""
    try:
        record = {"event": event_type, "ts": int(time.time()), **payload}
        with open(TRADES_JSONL, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        mlog("TRADES", f"Error escribiendo {event_type}: {e}")

_signals = []
_history = []
_signal_counter = 0
_lock = threading.Lock()


def _load():
    global _signals, _history, _signal_counter
    try:
        if os.path.exists(SIGNALS_FILE):
            with open(SIGNALS_FILE, "r") as f:
                _signals = json.load(f)
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                _history = json.load(f)
        ids = [int(s["id"].split("_")[1]) for s in _signals + _history if "id" in s and "_" in s["id"]]
        _signal_counter = max(ids) if ids else 0
        mlog("SIG", f"Cargadas {len(_signals)} activas, {len(_history)} historial")
    except Exception as e:
        mlog("SIG", f"Error carga: {e}")


def _save():
    try:
        with open(SIGNALS_FILE, "w") as f:
            json.dump(_signals, f, indent=1)
        with open(HISTORY_FILE, "w") as f:
            json.dump(_history, f, indent=1)
    except Exception as e:
        mlog("SIG", f"Error guardando: {e}")


def emit(symbol, action, entry_price, sl, tp, timeframe="60",
         risk_pct=1.0, confidence=0, reason="", lote=0, unidades=0,
         lote_std=0.0, groq_analysis="", rr_ratio=0,
         tqs=0.0, regimen="", votos=None, consensus="",
         trailing_stop="none", mtf_alignment=0.0, of_delta=0.0,
         sr_distance=0.0, divergence="NONE", riesgo_usd=0, atr=0.0):
    """
    Emite una nueva senal v3.1 enriquecida.
    """
    global _signal_counter

    with _lock:
        # No duplicar mismo par activo
        for s in _signals:
            if s["symbol"] == symbol and s["status"] == "ACTIVE":
                mlog("SIG", f"{symbol} ya tiene senal activa")
                return None

        _signal_counter += 1
        sig_id = f"SIG_{_signal_counter:04d}"

        signal = {
            "id": sig_id,
            "symbol": symbol,
            "action": action,
            "entry_price": round(entry_price, 6),
            "sl": round(sl, 6),
            "tp": round(tp, 6),
            "timeframe": str(timeframe),
            "risk_pct": risk_pct,
            "risk_reward": rr_ratio,
            "confidence": confidence,
            "reason": reason,
            "groq_analysis": groq_analysis,
            "status": "ACTIVE",
            "timestamp": int(time.time()),
            "exit_price": 0,
            "exit_ts": 0,
            "pnl_pct": 0,
            "pnl_usd": 0,
            "lote": lote,
            "unidades": unidades,
            "lote_std": lote_std,
            "riesgo_usd": riesgo_usd,
            "user_vote": "",
            # v3.1 enrichment
            "trade_quality_score": tqs,
            "regimen": regimen,
            "votos": votos or {},
            "consensus": consensus,
            "trailing_stop": trailing_stop,
            "atr": atr,
            "mtf_alignment": mtf_alignment,
            "order_flow_delta": of_delta,
            "sr_distance_pips": sr_distance,
            "divergence": divergence,
        }

        _signals.append(signal)
        _save()

        mlog("SIGNAL", f"EMITIDA {sig_id} {action} {symbol} @{entry_price} "
             f"SL={sl} TP={tp} TQS={tqs:.2f} [{regimen}] {consensus}")

        # Log estructurado del trade abierto
        sl_dist = abs(entry_price - sl)
        tp_dist = abs(entry_price - tp)
        _append_trade_event("TRADE_OPEN", {
            "id": sig_id,
            "symbol": symbol,
            "action": action,
            "timeframe": str(timeframe),
            "entry": round(entry_price, 6),
            "sl": round(sl, 6),
            "tp": round(tp, 6),
            "sl_dist": round(sl_dist, 6),
            "tp_dist": round(tp_dist, 6),
            "rr_ratio": rr_ratio,
            "atr": atr,
            "tqs": tqs,
            "regimen": regimen,
            "confidence": confidence,
            "consensus": consensus,
            "votos": votos or {},
            "trailing_stop": trailing_stop,
            "risk_pct": risk_pct,
            "riesgo_usd": riesgo_usd,
            "lote": lote,
            "lote_std": lote_std,
            "unidades": unidades,
            "mtf_alignment": mtf_alignment,
            "of_delta": of_delta,
            "sr_distance_pips": sr_distance,
            "divergence": divergence,
            "reason": reason[:300] if reason else "",
            "groq_analysis": groq_analysis[:300] if groq_analysis else "",
            "capital": state.get("capital", 0),
            "max_ops": state.get("max_ops", 0),
        })
        return signal


def check_prices(symbol, current_price, candle_low=None, candle_high=None):
    """Verifica SL/TP contra precio actual y mechas de vela (paper trading)."""
    triggered = []
    # Usar mechas para detectar toques que el precio actual ya no muestra
    c_low = candle_low if candle_low and candle_low > 0 else current_price
    c_high = candle_high if candle_high and candle_high > 0 else current_price

    with _lock:
        for sig in _signals:
            if sig["symbol"] != symbol or sig["status"] != "ACTIVE":
                continue

            entry = sig["entry_price"]
            sl = sig["sl"]
            tp = sig["tp"]
            action = sig["action"]
            # === Alertas TP: 50% y 70% (solo si TP > 2 ATR = operacion larga) ===
            tp_dist = abs(tp - entry)
            atr = sig.get("atr", 0)
            tp_in_atr = (tp_dist / atr) if atr > 0 else 0
            if tp_dist > 0 and tp_in_atr >= 2.0:
                if action == "BUY":
                    progress = (current_price - entry) / tp_dist
                else:
                    progress = (entry - current_price) / tp_dist

                # Si salta directo al 70%+, solo mandar la del 70% (no ambas)
                if progress >= 0.7 and not sig.get("_notified_70pct", False):
                    sig["_notified_70pct"] = True
                    sig["_notified_50pct"] = True
                    if action == "BUY":
                        new_sl = entry + tp_dist * 0.50
                    else:
                        new_sl = entry - tp_dist * 0.50
                    old_sl = sig["sl"]
                    sig["sl"] = round(new_sl, 6)
                    sl = sig["sl"]  # actualizar variable local para check SL/TP
                    _save()
                    mlog("PARTIAL", f"{sig['id']} {symbol} {progress*100:.0f}% TP - SL movido: {old_sl:.5f} → {new_sl:.5f}")
                    _msg = (f"🔥 {progress*100:.0f}% TP alcanzado {symbol} {action} [{sig['id']}]\n"
                            f"Precio: {current_price:.5f} ({progress*100:.0f}%)\n"
                            f"Entry: {entry:.5f} | TP: {tp:.5f}\n"
                            f"✅ SL movido a {new_sl:.5f} (protege +50%)")
                    _send_alert(sig, symbol, f"70% TP {symbol} {action}", _msg)

                elif progress >= 0.5 and not sig.get("_notified_50pct", False):
                    sig["_notified_50pct"] = True
                    if action == "BUY":
                        new_sl = entry + tp_dist * 0.25
                    else:
                        new_sl = entry - tp_dist * 0.25
                    old_sl = sig["sl"]
                    sig["sl"] = round(new_sl, 6)
                    sl = sig["sl"]  # actualizar variable local para check SL/TP
                    _save()
                    mlog("PARTIAL", f"{sig['id']} {symbol} {progress*100:.0f}% TP - SL movido: {old_sl:.5f} → {new_sl:.5f}")
                    _msg = (f"⚠️ {progress*100:.0f}% TP alcanzado {symbol} {action} [{sig['id']}]\n"
                            f"Precio: {current_price:.5f} ({progress*100:.0f}%)\n"
                            f"Entry: {entry:.5f} | TP: {tp:.5f}\n"
                            f"✅ SL movido a {new_sl:.5f} (protege +25%)")
                    _send_alert(sig, symbol, f"50% TP {symbol} {action}", _msg)

            hit = None
            if action == "BUY":
                # BUY: SL se toca con la mecha baja, TP con la mecha alta
                if c_low <= sl:
                    hit = "HIT_SL"
                elif c_high >= tp:
                    hit = "HIT_TP"
            elif action == "SELL":
                # SELL: SL se toca con la mecha alta, TP con la mecha baja
                if c_high >= sl:
                    hit = "HIT_SL"
                elif c_low <= tp:
                    hit = "HIT_TP"

            # Trailing eliminado - ya no se usa

            if hit:
                sig["status"] = hit
                # Exit price = SL o TP exacto (no el precio actual, que puede haber rebotado)
                if hit == "HIT_SL":
                    exit_p = sl
                elif hit == "HIT_TP":
                    exit_p = tp
                else:
                    exit_p = current_price
                sig["exit_price"] = round(exit_p, 6)
                sig["exit_ts"] = int(time.time())

                # PnL calculo con el precio de salida real (SL o TP)
                if action == "BUY":
                    pnl_pct = (exit_p - entry) / entry * 100
                else:
                    pnl_pct = (entry - exit_p) / entry * 100

                sig["pnl_pct"] = round(pnl_pct, 4)

                # PnL USD
                from risk_engine import pnl_usd
                sig["pnl_usd"] = pnl_usd(entry, exit_p, sig["lote"], symbol, action)

                # Actualizar estado global
                if hit == "HIT_SL":
                    state["fallos_consecutivos"] = state.get("fallos_consecutivos", 0) + 1
                    if state["fallos_consecutivos"] >= 3:
                        state["modo_conservador"] = True
                elif hit in ("HIT_TP", "TRAILING_CLOSE"):
                    state["fallos_consecutivos"] = 0
                    state["modo_conservador"] = False

                state["daily_pnl"] = round(state.get("daily_pnl", 0) + sig["pnl_usd"], 2)

                _history.append(dict(sig))
                triggered.append(sig)

                mlog("SIGNAL", f"{sig['id']} {hit} {symbol} PnL={pnl_pct:+.2f}% ${sig['pnl_usd']:+.2f}")

                # Set cooldown per-symbol para evitar re-entrada inmediata
                try:
                    import bot as _bot_module
                    _bot_module._symbol_cooldown[symbol] = time.time() + _bot_module._COOLDOWN_SECONDS
                except Exception:
                    pass

                # Log estructurado del trade cerrado
                duration_s = sig["exit_ts"] - sig.get("timestamp", sig["exit_ts"])
                _append_trade_event("TRADE_CLOSE", {
                    "id": sig["id"],
                    "symbol": symbol,
                    "action": action,
                    "status": hit,
                    "entry": entry,
                    "exit": round(exit_p, 6),
                    "sl_final": sig["sl"],   # SL al cierre (puede haberse movido por trailing)
                    "tp": sig["tp"],
                    "trailing_stop": "none",
                    "pnl_pct": sig["pnl_pct"],
                    "pnl_usd": sig["pnl_usd"],
                    "duration_s": duration_s,
                    "duration_min": round(duration_s / 60, 1),
                    "lote": sig.get("lote", 0),
                    "tqs": sig.get("trade_quality_score", 0),
                    "regimen": sig.get("regimen", ""),
                    "confidence": sig.get("confidence", 0),
                    "consensus": sig.get("consensus", ""),
                    "fallos_consecutivos": state.get("fallos_consecutivos", 0),
                    "daily_pnl_after": state.get("daily_pnl", 0),
                })

        # Limpiar cerradas de activas
        _signals[:] = [s for s in _signals if s["status"] == "ACTIVE"]

        # Limitar historial
        while len(_history) > 500:
            _history.pop(0)

        if triggered:
            _save()

    return triggered


def close_signal(signal_id, current_price=None, status="CANCELLED"):
    """Cierra manualmente una senal."""
    with _lock:
        for sig in _signals:
            if sig["id"] == signal_id:
                sig["status"] = status
                if current_price:
                    sig["exit_price"] = round(current_price, 6)
                    entry = sig["entry_price"]
                    action = sig["action"]
                    if action == "BUY":
                        sig["pnl_pct"] = round((current_price - entry) / entry * 100, 4)
                    else:
                        sig["pnl_pct"] = round((entry - current_price) / entry * 100, 4)
                    from risk_engine import pnl_usd
                    sig["pnl_usd"] = pnl_usd(entry, current_price, sig["lote"], sig["symbol"], action)
                sig["exit_ts"] = int(time.time())
                _history.append(dict(sig))
                _signals.remove(sig)
                _save()

                # Log estructurado del cierre manual
                duration_s = sig["exit_ts"] - sig.get("timestamp", sig["exit_ts"])
                _append_trade_event("TRADE_CLOSE", {
                    "id": sig["id"],
                    "symbol": sig["symbol"],
                    "action": sig["action"],
                    "status": status,
                    "entry": sig["entry_price"],
                    "exit": sig.get("exit_price", 0),
                    "sl_final": sig.get("sl", 0),
                    "tp": sig.get("tp", 0),
                    "trailing_stop": sig.get("trailing_stop", "none"),
                    "pnl_pct": sig.get("pnl_pct", 0),
                    "pnl_usd": sig.get("pnl_usd", 0),
                    "duration_s": duration_s,
                    "duration_min": round(duration_s / 60, 1),
                    "lote": sig.get("lote", 0),
                    "tqs": sig.get("trade_quality_score", 0),
                    "regimen": sig.get("regimen", ""),
                    "confidence": sig.get("confidence", 0),
                    "manual": True,
                })
                return sig
    return None


def cancel(signal_id, current_price=None):
    return close_signal(signal_id, current_price, "CANCELLED")


def vote(signal_id, user_vote):
    """Voto del usuario (win/loss)."""
    with _lock:
        for sig in _history:
            if sig["id"] == signal_id:
                sig["user_vote"] = user_vote
                if user_vote == "loss":
                    state["fallos_consecutivos"] = state.get("fallos_consecutivos", 0) + 1
                    if state["fallos_consecutivos"] >= 3:
                        state["modo_conservador"] = True
                elif user_vote == "win":
                    state["fallos_consecutivos"] = 0
                    state["modo_conservador"] = False
                _save()
                return True
    return False


def get_active(symbol=None):
    with _lock:
        if symbol:
            return [s for s in _signals if s["symbol"] == symbol and s["status"] == "ACTIVE"]
        return [s for s in _signals if s["status"] == "ACTIVE"]


def get_history(limit=50):
    with _lock:
        return list(reversed(_history[-limit:]))


def get_stats():
    """Estadisticas de rendimiento."""
    with _lock:
        closed = [s for s in _history if s["status"] in ("HIT_TP", "HIT_SL", "TRAILING_CLOSE")]
        if not closed:
            return {
                "total": 0, "wins": 0, "losses": 0,
                "win_rate": 0, "profit_factor": 0,
                "avg_win": 0, "avg_loss": 0, "total_pnl": 0,
                "best_trade": 0, "worst_trade": 0,
                "modo_conservador": state.get("modo_conservador", False),
                "fallos_consecutivos": state.get("fallos_consecutivos", 0),
            }

        wins = [s for s in closed if s["status"] in ("HIT_TP", "TRAILING_CLOSE")]
        losses = [s for s in closed if s["status"] == "HIT_SL"]

        total_win_usd = sum(s.get("pnl_usd", 0) for s in wins) if wins else 0
        total_loss_usd = abs(sum(s.get("pnl_usd", 0) for s in losses)) if losses else 0

        pnl_list = [s.get("pnl_usd", 0) for s in closed]

        return {
            "total": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(closed) * 100, 1) if closed else 0,
            "profit_factor": round(total_win_usd / total_loss_usd, 2) if total_loss_usd > 0 else 999,
            "avg_win": round(total_win_usd / len(wins), 2) if wins else 0,
            "avg_loss": round(total_loss_usd / len(losses), 2) if losses else 0,
            "total_pnl": round(sum(pnl_list), 2),
            "best_trade": round(max(pnl_list), 2) if pnl_list else 0,
            "worst_trade": round(min(pnl_list), 2) if pnl_list else 0,
            "modo_conservador": state.get("modo_conservador", False),
            "fallos_consecutivos": state.get("fallos_consecutivos", 0),
            "daily_pnl": state.get("daily_pnl", 0),
        }


def delete_from_history(sig_id):
    """Elimina un trade del historial por ID."""
    with _lock:
        before_history = len(_history)
        _history[:] = [s for s in _history if s.get("id") != sig_id]
        if len(_history) < before_history:
            _save()
            mlog("SIG", f"Eliminado del historial: {sig_id}")
            return True
        # Also check active signals
        before_signals = len(_signals)
        _signals[:] = [s for s in _signals if s.get("id") != sig_id]
        _save()
        return len(_signals) < before_signals


# Cargar al importar
_load()
