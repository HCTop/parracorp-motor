# -*- coding: utf-8 -*-
"""
signal_engines.py - Capa 2: 4 Motores de Senal + Trade Quality Score
ParraCorp v3.1

Cuatro motores independientes especializados:
  1. Momentum - Tendencia fuerte con slope EMA
  2. Mean Reversion - Z-Score + BB + RSI extremo
  3. Currency Strength - Fuerza relativa entre divisas
  4. Volatility Breakout - Squeeze + expansion

Trade Quality Score (TQS): suma ponderada segun regimen.
TQS < 0.65 = no consultar IA (ahorra coste).
"""
import numpy as np
from config import log as mlog

# ---------------------------------------------------------------------------
# 4.1  Motor Momentum
# ---------------------------------------------------------------------------

def motor_momentum(ema20_serie, closes, periodo_slope=5, p90_ref=None):
    """
    Detecta tendencia fuerte usando slope de EMA20 * momentum del precio.
    Returns: (score 0-1, direction BUY/SELL/NEUTRAL)
    """
    if len(ema20_serie) < periodo_slope + 1 or len(closes) < periodo_slope + 1:
        return 0.0, "NEUTRAL"

    slope = (ema20_serie[-1] - ema20_serie[-periodo_slope]) / periodo_slope
    momentum = closes[-1] - closes[-periodo_slope]

    # Normalizar por precio para hacerlo comparable entre pares
    price = closes[-1] if closes[-1] != 0 else 1.0
    slope_norm = slope / price
    mom_norm = momentum / price

    raw = abs(slope_norm * mom_norm) * 1e6  # escalar
    if p90_ref is None:
        p90_ref = 1.0
    score = min(raw / max(p90_ref, 1e-9), 1.0)

    if slope > 0 and momentum > 0:
        dir_ = "BUY"
    elif slope < 0 and momentum < 0:
        dir_ = "SELL"
    else:
        dir_ = "NEUTRAL"

    return round(score, 3), dir_


# ---------------------------------------------------------------------------
# 4.2  Motor Mean Reversion
# ---------------------------------------------------------------------------

def motor_mean_reversion(zscore, bb_distance, rsi):
    """
    Detecta condiciones de sobrecompra/sobreventa para mean reversion.
    zscore: desviaciones estandar del precio vs media
    bb_distance: (precio - BB_upper) / BB_ancho, rango [-1, 1]
    rsi: RSI 14 periodos
    Returns: (score 0-1, direction BUY/SELL/NEUTRAL)
    """
    # Extremo RSI
    if rsi > 70:
        rsi_ext = max(0, (rsi - 70) / 30)
    elif rsi < 30:
        rsi_ext = max(0, (30 - rsi) / 30)
    else:
        rsi_ext = 0.0

    # Se activa con zscore alto O RSI extremo O BB extremo
    if abs(zscore) < 1.0 and rsi_ext == 0.0 and abs(bb_distance) < 0.5:
        return 0.0, "NEUTRAL"

    z_n = min(abs(zscore) / 3.0, 1.0)
    bb_n = min(abs(bb_distance), 1.0)

    score = 0.4 * z_n + 0.35 * bb_n + 0.25 * rsi_ext

    # Direccion: zscore dominates as primary mean-reversion signal
    if abs(zscore) >= 1.0:
        # Strong zscore signal takes priority
        dir_ = "SELL" if zscore > 0 else "BUY"
    elif rsi > 70:
        dir_ = "SELL"
    elif rsi < 30:
        dir_ = "BUY"
    else:
        dir_ = "SELL" if zscore > 0 else "BUY"

    return round(score, 3), dir_


# ---------------------------------------------------------------------------
# 4.3  Motor Currency Strength
# ---------------------------------------------------------------------------

def motor_currency_strength(s_base, s_quote, tri_error=0.0):
    """
    Usa la fuerza relativa de las divisas del par.
    s_base: strength de la divisa base (tipicamente ±0.005)
    s_quote: strength de la divisa cotizada (tipicamente ±0.005)
    tri_error: error triangular del par (bonus)
    Returns: (score 0-1, direction BUY/SELL/NEUTRAL)
    """
    spread = s_base - s_quote

    # Umbral minimo: 0.05% de diferencia = suficiente para señal
    if abs(spread) < 0.0005:
        return 0.0, "NEUTRAL"

    # Normalizar: spread de 0.01 (1%) = score 1.0
    spread_n = min(abs(spread) / 0.01, 1.0)
    tri_bon = min(abs(tri_error) / 0.0005, 0.2) if tri_error else 0.0
    score = min(spread_n + tri_bon, 1.0)

    dir_ = "BUY" if spread > 0 else "SELL"
    return round(score, 3), dir_


# ---------------------------------------------------------------------------
# 4.4  Motor Volatility Breakout
# ---------------------------------------------------------------------------

def motor_breakout(vol_ratio, squeeze, adx):
    """
    Detecta ruptura de rango o expansion de volatilidad.
    vol_ratio: ATR_actual / ATR_media_20
    squeeze: bool, True si BB < KC
    adx: ADX actual
    Returns: (score 0-1, direction BREAKOUT/NEUTRAL)
    """
    expansion = min((vol_ratio - 1.0) / 0.5, 1.0) if vol_ratio > 1.0 else 0.0
    adx_n = min(adx / 50.0, 1.0) if adx else 0.0

    if squeeze:
        # Squeeze activo: bonus base
        score = 0.5 * expansion + 0.3 * adx_n + 0.2
    elif vol_ratio > 1.2 and adx > 25:
        # Expansion fuerte + ADX alto
        score = 0.5 * expansion + 0.5 * adx_n
    elif vol_ratio > 1.05 and adx > 18:
        # Expansion moderada (relajado para captar mas breakouts)
        score = 0.4 * expansion + 0.4 * adx_n
    elif adx > 25:
        # ADX alto sin expansion = tendencia fuerte, breakout parcial
        score = 0.3 * adx_n
    else:
        return 0.0, "NEUTRAL"

    return round(min(score, 1.0), 3), "BREAKOUT"


# ---------------------------------------------------------------------------
# 4.5  Divergencias Automaticas
# ---------------------------------------------------------------------------

def detectar_divergencias(closes, rsi_serie, lookback=5):
    """
    Detecta divergencias precio vs RSI.
    Returns: (signal BEARISH_DIV/BULLISH_DIV/NONE, confidence 0-1)
    """
    if len(closes) < lookback * 2 + 1 or len(rsi_serie) < lookback * 2 + 1:
        return "NONE", 0.0

    try:
        precio_max_rec = max(closes[-lookback:])
        precio_min_rec = min(closes[-lookback:])
        precio_max_ant = max(closes[-lookback * 2:-lookback])
        precio_min_ant = min(closes[-lookback * 2:-lookback])

        rsi_max_rec = max(rsi_serie[-lookback:])
        rsi_min_rec = min(rsi_serie[-lookback:])
        rsi_max_ant = max(rsi_serie[-lookback * 2:-lookback])
        rsi_min_ant = min(rsi_serie[-lookback * 2:-lookback])

        # Divergencia bajista: precio nuevo max pero RSI no
        if precio_max_rec > precio_max_ant and rsi_max_rec < rsi_max_ant:
            return "BEARISH_DIV", 0.80

        # Divergencia alcista: precio nuevo min pero RSI no
        if precio_min_rec < precio_min_ant and rsi_min_rec > rsi_min_ant:
            return "BULLISH_DIV", 0.80

    except (ValueError, IndexError):
        pass

    return "NONE", 0.0


# ---------------------------------------------------------------------------
# 4.5  Trade Quality Score (TQS)
# ---------------------------------------------------------------------------

# Pesos dinamicos por regimen — FOREX (tiene currency strength)
PESOS_REGIMEN = {
    "TRENDING_VOLATILE": {"momentum": 0.60, "reversion": 0.05, "strength": 0.30, "breakout": 0.05},
    "TRENDING_CALM":     {"momentum": 0.50, "reversion": 0.10, "strength": 0.30, "breakout": 0.10},
    "RANGING":           {"momentum": 0.10, "reversion": 0.50, "strength": 0.30, "breakout": 0.10},
    "CHOPPY":            {"bloquear": True},
    "NORMAL":            {"momentum": 0.40, "reversion": 0.20, "strength": 0.30, "breakout": 0.10},
}

# Pesos para activos SIN currency strength (crypto, indices, commodities, stocks)
PESOS_REGIMEN_NO_FX = {
    "TRENDING_VOLATILE": {"momentum": 0.65, "reversion": 0.10, "strength": 0.00, "breakout": 0.25},
    "TRENDING_CALM":     {"momentum": 0.55, "reversion": 0.20, "strength": 0.00, "breakout": 0.25},
    "RANGING":           {"momentum": 0.15, "reversion": 0.55, "strength": 0.00, "breakout": 0.30},
    "CHOPPY":            {"bloquear": True},
    "NORMAL":            {"momentum": 0.45, "reversion": 0.25, "strength": 0.00, "breakout": 0.30},
}

UMBRAL_TQS = 0.65
UMBRAL_TQS_NO_FX = 0.50  # Umbral mas bajo para activos sin currency strength (3 motores)


def trade_quality_score(m_score, r_score, s_score, b_score, regimen, pesos_override=None):
    """
    Calcula Trade Quality Score combinando los 4 motores con pesos por regimen.

    Args:
        m_score: score motor momentum (0-1)
        r_score: score motor mean reversion (0-1)
        s_score: score motor currency strength (0-1)
        b_score: score motor breakout (0-1)
        regimen: string del regimen actual
        pesos_override: dict opcional para override de pesos (learning loop)

    Returns: float TQS (0-1), 0.0 si regimen CHOPPY
    """
    if pesos_override:
        cfg = pesos_override
    else:
        cfg = PESOS_REGIMEN.get(regimen, PESOS_REGIMEN["NORMAL"])

    if cfg.get("bloquear"):
        return 0.0

    tqs = (
        cfg.get("momentum", 0.3) * m_score +
        cfg.get("reversion", 0.2) * r_score +
        cfg.get("strength", 0.3) * s_score +
        cfg.get("breakout", 0.2) * b_score
    )

    return round(tqs, 3)


def determinar_direccion_consensus(m_dir, r_dir, s_dir, m_score, r_score, s_score):
    """
    Determina la direccion final basada en los motores con mayor score.
    Ignora NEUTRAL y BREAKOUT.
    Returns: BUY / SELL / NEUTRAL
    """
    votos = []
    if m_dir in ("BUY", "SELL"):
        votos.append((m_dir, m_score))
    if r_dir in ("BUY", "SELL"):
        votos.append((r_dir, r_score))
    if s_dir in ("BUY", "SELL"):
        votos.append((s_dir, s_score))

    if not votos:
        return "NEUTRAL"

    # Sumar scores por direccion
    buy_score = sum(s for d, s in votos if d == "BUY")
    sell_score = sum(s for d, s in votos if d == "SELL")

    if buy_score > sell_score and buy_score > 0.3:
        return "BUY"
    elif sell_score > buy_score and sell_score > 0.3:
        return "SELL"
    return "NEUTRAL"


def _is_forex(symbol):
    """Detecta si un simbolo es forex (tiene currency strength util)."""
    sym = (symbol or "").upper().replace("/", "")
    fx_currencies = {"EUR","GBP","USD","JPY","CHF","AUD","CAD","NZD"}
    if len(sym) >= 6:
        base = sym[:3]
        quote = sym[3:6]
        return base in fx_currencies and quote in fx_currencies
    # Metals con USD
    if sym.startswith("XAU") or sym.startswith("XAG"):
        return True
    return False


def evaluar_senales(features, regimen, pesos_override=None):
    """
    Pipeline completo: ejecuta los 4 motores y calcula TQS.

    Args:
        features: dict con todas las features calculadas por data_feed
        regimen: regimen actual detectado
        pesos_override: pesos del learning loop (opcional)

    Returns: dict con scores, direccion, TQS, divergencia, pasa_umbral
    """
    # Extraer datos necesarios
    closes = features.get("closes", [])
    ema20_serie = features.get("ema20_serie", [])
    zscore = features.get("zscore_h1", 0.0)
    bb_distance = features.get("bb_distance", 0.0)
    rsi = features.get("rsi", 50.0)
    rsi_serie = features.get("rsi_serie", [])
    s_base = features.get("currency_strength_base", 0.0)
    s_quote = features.get("currency_strength_quote", 0.0)
    tri_error = features.get("triangular_error", 0.0)
    vol_ratio = features.get("vol_ratio", 1.0)
    squeeze = features.get("squeeze", False)
    adx = features.get("adx", 0.0)
    symbol = features.get("par", "")

    # Ejecutar motores
    m_score, m_dir = motor_momentum(ema20_serie, closes)
    r_score, r_dir = motor_mean_reversion(zscore, bb_distance, rsi)
    s_score, s_dir = motor_currency_strength(s_base, s_quote, tri_error)
    b_score, b_dir = motor_breakout(vol_ratio, squeeze, adx)

    # Divergencias
    div_signal, div_conf = detectar_divergencias(closes, rsi_serie)

    # Seleccionar pesos segun tipo de activo
    is_fx = _is_forex(symbol)
    if pesos_override:
        pesos_tabla = None  # se usa pesos_override directamente
    elif is_fx:
        pesos_tabla = PESOS_REGIMEN
    else:
        pesos_tabla = PESOS_REGIMEN_NO_FX

    # TQS
    if pesos_override:
        tqs = trade_quality_score(m_score, r_score, s_score, b_score, regimen, pesos_override)
    else:
        pesos_cfg = pesos_tabla.get(regimen, pesos_tabla.get("NORMAL", {}))
        tqs = trade_quality_score(m_score, r_score, s_score, b_score, regimen, pesos_cfg)

    # Direccion consensus de motores
    direccion = determinar_direccion_consensus(m_dir, r_dir, s_dir, m_score, r_score, s_score)

    # Ajustar por divergencia
    if div_signal == "BEARISH_DIV" and direccion == "BUY":
        tqs *= 0.7  # Penalizar si la divergencia contradice
    elif div_signal == "BULLISH_DIV" and direccion == "SELL":
        tqs *= 0.7

    umbral = UMBRAL_TQS if is_fx else UMBRAL_TQS_NO_FX
    pasa = tqs >= umbral and direccion != "NEUTRAL"

    result = {
        "momentum_score": m_score,
        "momentum_dir": m_dir,
        "reversion_score": r_score,
        "reversion_dir": r_dir,
        "strength_score": s_score,
        "strength_dir": s_dir,
        "breakout_score": b_score,
        "breakout_dir": b_dir,
        "trade_quality_score": round(tqs, 3),
        "direccion": direccion,
        "divergence_signal": div_signal,
        "divergence_confidence": div_conf,
        "pasa_umbral": pasa,
        "umbral_tqs": umbral,
        "is_forex": is_fx,
        "regimen": regimen,
    }

    if pasa:
        mlog("ENGINES", f"TQS={tqs:.3f}/{umbral} dir={direccion} [{regimen}] "
             f"mom={m_score:.2f} rev={r_score:.2f} str={s_score:.2f} brk={b_score:.2f}"
             f" {'FX' if is_fx else 'NO-FX'}")

    return result
