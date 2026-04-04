# -*- coding: utf-8 -*-
"""
correlation.py - Selector de Activos Multianálisis (Correlation Tracker)

- Analisis en paralelo de multiples activos
- Correlacion con DXY (Indice del Dolar)
- Ranking de Oportunidad (Setup Score)
"""
import time
from data_feed import get_snapshot, describe_snapshot, get_price
from market_context import get_session, check_symbol_events
from config import log

# === CORRELATION ANTI-DUPLICATES =============================================

# (pair_a, pair_b, correlation_type)
# "positive" = move same direction, "negative" = move opposite direction
CORRELATIONS = [
    # Forex majors vs USD
    ("EURUSD", "GBPUSD", "positive"),    # ~0.85
    ("EURUSD", "USDCHF", "negative"),    # ~-0.90
    ("GBPUSD", "USDCHF", "negative"),    # ~-0.80
    ("AUDUSD", "NZDUSD", "positive"),    # ~0.90
    ("USDCAD", "USDCHF", "positive"),    # ~0.70
    # JPY crosses
    ("EURJPY", "GBPJPY", "positive"),    # ~0.80
    ("EURJPY", "AUDJPY", "positive"),    # ~0.75
    ("GBPJPY", "CADJPY", "positive"),    # ~0.70
    ("USDJPY", "CHFJPY", "positive"),    # ~0.70
    ("AUDJPY", "NZDJPY", "positive"),    # ~0.90
    # EUR/GBP crosses
    ("EURAUD", "GBPAUD", "positive"),    # ~0.80
    ("EURNZD", "GBPNZD", "positive"),    # ~0.80
    ("EURCAD", "GBPCAD", "positive"),    # ~0.75
    ("EURCHF", "GBPCHF", "positive"),    # ~0.70
    # Commodity currencies
    ("AUDCAD", "NZDCAD", "positive"),    # ~0.85
    ("AUDCHF", "NZDCHF", "positive"),    # ~0.85
    # Crypto
    ("BTCUSDT", "ETHUSDT", "positive"),  # ~0.85
    ("SOLUSDT", "ETHUSDT", "positive"),  # ~0.75
    ("DOTUSDT", "ETHUSDT", "positive"),  # ~0.75
    ("MATICUSDT", "ETHUSDT", "positive"),# ~0.75
    ("ADAUSDT", "DOTUSDT", "positive"),  # ~0.80
    ("LINKUSDT", "ETHUSDT", "positive"), # ~0.70
    # Metals
    ("XAUUSD", "XAGUSD", "positive"),    # ~0.80
    ("XAUUSD", "XPTUSD", "positive"),    # ~0.70
    ("XAGUSD", "XPTUSD", "positive"),    # ~0.75
    # Energy
    ("USOIL", "UKOIL", "positive"),      # ~0.95
    # Indices
    ("US30", "SPX500", "positive"),       # ~0.95
    ("NAS100", "SPX500", "positive"),     # ~0.90
    ("DE40", "FR40", "positive"),         # ~0.90
    ("DE40", "UK100", "positive"),        # ~0.80
]


def check_correlation(symbol, action, active_signals):
    """
    Check if a new signal would double exposure due to correlated pairs.

    Args:
        symbol: The new symbol to trade (e.g. "EURUSD")
        action: "BUY" or "SELL"
        active_signals: List of currently active signal dicts with "symbol", "action", "timeframe"

    Returns:
        (allowed: bool, reason: str)
    """
    if not active_signals:
        return True, "OK"

    sym = symbol.upper().replace("/", "")

    for sig in active_signals:
        sig_sym = sig.get("symbol", "").upper().replace("/", "")
        sig_action = sig.get("action", "").upper()

        # ALLOW same symbol on different timeframes (multi-TF confluence is good)
        if sig_sym == sym:
            continue

        # Check all correlation pairs
        for pair_a, pair_b, corr_type in CORRELATIONS:
            matched = False
            if (sym == pair_a and sig_sym == pair_b) or (sym == pair_b and sig_sym == pair_a):
                matched = True

            if not matched:
                continue

            if corr_type == "positive":
                # Same direction on positively correlated pair = BLOCKED (double exposure)
                if action == sig_action:
                    reason = (f"Correlacion positiva: {sym} {action} bloqueado porque "
                              f"{sig_sym} {sig_action} ya esta activo (misma direccion)")
                    log("CORR", reason)
                    return False, reason
            elif corr_type == "negative":
                # Opposite direction on negatively correlated pair = BLOCKED (same effect as double exposure)
                if action != sig_action:
                    reason = (f"Correlacion negativa: {sym} {action} bloqueado porque "
                              f"{sig_sym} {sig_action} ya esta activo (direccion opuesta = misma exposicion)")
                    log("CORR", reason)
                    return False, reason

    return True, "OK"


# Cache de rankings
_ranking_cache = {"data": [], "ts": 0}
_ranking_multi_cache = {"data": [], "ts": 0, "key": ""}
RANKING_TTL = 60  # 1 minuto


def _setup_score(snapshot):
    """
    Calcula un puntaje de configuracion (0-100) para un activo.
    Mide la confluencia tecnica para una posible entrada.
    """
    if not snapshot:
        return 0, "N/A", "Sin datos"

    score = 0
    reasons = []

    rsi = snapshot.get("rsi", 50)
    adx = snapshot.get("adx", 0)
    macd_h = snapshot.get("macd_hist", 0)
    st = snapshot.get("supertrend", "NEUTRO")
    squeeze = snapshot.get("squeeze", False)
    ema9 = snapshot.get("ema9", 0)
    ema20 = snapshot.get("ema20", 0)
    ema50 = snapshot.get("ema50", 0)
    bb_u = snapshot.get("bb_upper", 0)
    bb_l = snapshot.get("bb_lower", 0)
    precio = snapshot.get("precio", 0)
    tv_rec = snapshot.get("tv_recommend", 0)
    stoch_k = snapshot.get("stoch_k", 50)
    stoch_d = snapshot.get("stoch_d", 50)
    vol = snapshot.get("volume", 0)
    vol_sma = snapshot.get("volume_sma", 0)

    direction = "NEUTRAL"

    # 1. Tendencia EMA (20 pts max)
    if ema9 > ema20 > ema50:
        score += 20
        direction = "BUY"
        reasons.append("EMA alineadas alcista")
    elif ema9 < ema20 < ema50:
        score += 20
        direction = "SELL"
        reasons.append("EMA alineadas bajista")
    elif ema9 > ema20:
        score += 10
        direction = "BUY"
        reasons.append("EMA corto plazo alcista")
    elif ema9 < ema20:
        score += 10
        direction = "SELL"
        reasons.append("EMA corto plazo bajista")

    # 2. ADX fuerza (15 pts max)
    if adx > 30:
        score += 15
        reasons.append(f"ADX fuerte ({adx:.0f})")
    elif adx > 25:
        score += 10
        reasons.append(f"ADX moderado ({adx:.0f})")
    elif adx > 20:
        score += 5

    # 3. Supertrend (15 pts)
    if st == "UP" and direction in ("BUY", "NEUTRAL"):
        score += 15
        if direction == "NEUTRAL":
            direction = "BUY"
        reasons.append("Supertrend alcista")
    elif st == "DOWN" and direction in ("SELL", "NEUTRAL"):
        score += 15
        if direction == "NEUTRAL":
            direction = "SELL"
        reasons.append("Supertrend bajista")

    # 4. RSI (10 pts)
    if direction == "BUY" and rsi < 65 and rsi > 35:
        score += 10
        reasons.append(f"RSI favorable ({rsi:.0f})")
    elif direction == "SELL" and rsi > 35 and rsi < 65:
        score += 10
        reasons.append(f"RSI favorable ({rsi:.0f})")
    elif rsi > 70:
        score += 5
        reasons.append(f"RSI sobrecomprado ({rsi:.0f})")
    elif rsi < 30:
        score += 5
        reasons.append(f"RSI sobrevendido ({rsi:.0f})")

    # 5. MACD momentum (10 pts)
    if macd_h > 0 and direction in ("BUY", "NEUTRAL"):
        score += 10
        reasons.append("MACD momentum alcista")
    elif macd_h < 0 and direction in ("SELL", "NEUTRAL"):
        score += 10
        reasons.append("MACD momentum bajista")

    # 6. Stoch cruce (10 pts)
    if stoch_k > stoch_d and direction in ("BUY", "NEUTRAL"):
        score += 10
        reasons.append("Stoch cruce alcista")
    elif stoch_k < stoch_d and direction in ("SELL", "NEUTRAL"):
        score += 10
        reasons.append("Stoch cruce bajista")

    # 7. Volumen (10 pts)
    if vol and vol_sma and vol_sma > 0:
        vol_ratio = vol / vol_sma
        if vol_ratio > 1.3:
            score += 10
            reasons.append(f"Volumen alto ({vol_ratio:.1f}x)")
        elif vol_ratio > 1.0:
            score += 5

    # 8. Squeeze (10 pts bonus)
    if squeeze:
        score += 10
        reasons.append("SQUEEZE activo")

    # 9. TV Recommendation alignment
    if tv_rec > 0.3 and direction in ("BUY", "NEUTRAL"):
        score += 5
    elif tv_rec < -0.3 and direction in ("SELL", "NEUTRAL"):
        score += 5

    # BB position for entries
    if bb_u > bb_l and precio:
        bb_pos = (precio - bb_l) / (bb_u - bb_l)
        if direction == "BUY" and bb_pos < 0.3:
            score += 5
            reasons.append("Cerca de suelo BB")
        elif direction == "SELL" and bb_pos > 0.7:
            score += 5
            reasons.append("Cerca de techo BB")

    score = min(score, 100)
    summary = " | ".join(reasons[:4]) if reasons else "Sin confluencia clara"

    return score, direction, summary


def get_ranking_multi(pairs):
    """
    Analiza pares (symbol, tf) y los ordena por Setup Score.
    Cada combinacion symbol:tf aparece como entrada independiente.
    """
    global _ranking_multi_cache
    now = time.time()
    cache_key = str(sorted(pairs))
    if (_ranking_multi_cache["data"] and
        (now - _ranking_multi_cache["ts"]) < RANKING_TTL and
        _ranking_multi_cache["key"] == cache_key):
        return _ranking_multi_cache["data"]

    rankings = []
    session = get_session()
    _tf_labels = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
                  "60": "1h", "240": "4h", "1D": "1D", "D": "1D"}

    for symbol, tf in pairs:
        try:
            snapshot = get_snapshot(symbol, tf)
            if not snapshot:
                # Fallback: try price from any TF for this symbol
                price = get_price(symbol)
                if price and price > 0:
                    rankings.append({
                        "symbol": symbol,
                        "timeframe": _tf_labels.get(tf, tf),
                        "score": 0,
                        "direction": "NEUTRAL",
                        "summary": "Esperando datos...",
                        "price": price,
                        "rsi": 0, "adx": 0,
                        "supertrend": "?",
                        "atr_pct": 0,
                        "event_active": False,
                    })
                continue
            score, direction, summary = _setup_score(snapshot)
            event = check_symbol_events(symbol)
            if event.get("active"):
                score = max(0, score - 30)
                summary += f" | EVENTO: {event.get('event','')}"
            if session.get("quality", 0) <= 2:
                score = max(0, score - 20)
            rankings.append({
                "symbol": symbol,
                "timeframe": _tf_labels.get(tf, tf),
                "score": score,
                "direction": direction,
                "summary": summary,
                "price": snapshot.get("precio", 0),
                "rsi": snapshot.get("rsi", 50),
                "adx": snapshot.get("adx", 0),
                "supertrend": snapshot.get("supertrend", "?"),
                "atr_pct": snapshot.get("atr_pct", 0),
                "event_active": event.get("active", False),
            })
        except Exception as e:
            print(f"[RANKING] Error {symbol}:{tf}: {e}")

    rankings.sort(key=lambda x: x["score"], reverse=True)
    _ranking_multi_cache = {"data": rankings, "ts": now, "key": cache_key}
    return rankings


def get_ranking(watchlist, temporalidad="60"):
    """
    Analiza multiples activos y los ordena por Setup Score.

    Returns: lista de {
        "symbol": str,
        "score": int,
        "direction": "BUY"|"SELL"|"NEUTRAL",
        "summary": str,
        "price": float,
        "rsi": float,
        "adx": float,
        "supertrend": str,
        "event_active": bool,
    }
    """
    global _ranking_cache
    now = time.time()

    # Cache
    if _ranking_cache["data"] and (now - _ranking_cache["ts"]) < RANKING_TTL:
        return _ranking_cache["data"]

    rankings = []
    session = get_session()

    for symbol in watchlist:
        try:
            snapshot = get_snapshot(symbol, temporalidad)
            if not snapshot:
                continue

            score, direction, summary = _setup_score(snapshot)

            # Penalizar si hay evento
            event = check_symbol_events(symbol)
            if event.get("active"):
                score = max(0, score - 30)
                summary += f" | EVENTO: {event.get('event','')}"

            # Penalizar si sesion mala para este tipo
            if session.get("quality", 0) <= 2:
                score = max(0, score - 20)

            rankings.append({
                "symbol": symbol,
                "score": score,
                "direction": direction,
                "summary": summary,
                "price": snapshot.get("precio", 0),
                "rsi": snapshot.get("rsi", 50),
                "adx": snapshot.get("adx", 0),
                "supertrend": snapshot.get("supertrend", "?"),
                "atr_pct": snapshot.get("atr_pct", 0),
                "event_active": event.get("active", False),
            })

        except Exception as e:
            print(f"[RANKING] Error {symbol}: {e}")

    # Ordenar por score descendente
    rankings.sort(key=lambda x: x["score"], reverse=True)

    _ranking_cache = {"data": rankings, "ts": now}
    return rankings


def get_dxy_bias():
    """
    Obtiene bias del DXY (US Dollar Index) para filtrar pares USD.
    Returns: {"direction": "strong"|"weak"|"neutral", "price": float}
    """
    try:
        # DXY via streaming cache
        from data_feed import get_snapshot as _gs, _stream
        # Try to get DXY from stream bars
        if _stream:
            bars = _stream.get_bars("DXY", "60")
            if not bars or len(bars) < 21:
                return {"direction": "neutral", "price": 0}
            closes = [b[4] for b in bars]
            price = closes[-1]
            ema20 = sum(closes[-20:]) / min(20, len(closes[-20:]))
            # RSI simple
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            gains = [d for d in deltas[-14:] if d > 0]
            losses = [-d for d in deltas[-14:] if d < 0]
            avg_g = sum(gains) / 14 if gains else 0
            avg_l = sum(losses) / 14 if losses else 0.001
            rsi = 100 - (100 / (1 + avg_g / avg_l))
        else:
            return {"direction": "neutral", "price": 0}

        if price > ema20 * 1.002 and rsi > 55:
            return {"direction": "strong", "price": price}
        elif price < ema20 * 0.998 and rsi < 45:
            return {"direction": "weak", "price": price}
        return {"direction": "neutral", "price": price}

    except Exception:
        return {"direction": "neutral", "price": 0}
