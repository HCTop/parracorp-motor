# -*- coding: utf-8 -*-
"""
regime_detector.py - Capa 5: Deteccion de Regimen Dinamico
ParraCorp v3.1

5 regimenes de mercado con parametros dinamicos:
  TRENDING_VOLATILE, TRENDING_CALM, RANGING, CHOPPY, NORMAL

Adapta TP, SL, ADX minimo, trailing y riesgo automaticamente.
Detecta transiciones y reduce riesgo durante cambios de regimen.
"""
from collections import deque
from config import log as mlog

# ---------------------------------------------------------------------------
# 7.2  Parametros por regimen
# ---------------------------------------------------------------------------

REGIMEN_CONFIG = {
    "TRENDING_VOLATILE": {
        "tp_atr_mult": 3.0,
        "sl_atr_mult": 2.0,
        "adx_min": 28,
        "trailing": "atr1",
        "riesgo_pct": 1.0,
        "motor_priority": "Momentum 60%",
    },
    "TRENDING_CALM": {
        "tp_atr_mult": 2.5,
        "sl_atr_mult": 1.5,
        "adx_min": 25,
        "trailing": "breakeven",
        "riesgo_pct": 1.0,
        "motor_priority": "Momentum 50%",
    },
    "RANGING": {
        "tp_atr_mult": 1.2,
        "sl_atr_mult": 1.0,
        "adx_min": 15,
        "trailing": "none",
        "riesgo_pct": 0.7,
        "motor_priority": "Reversion 50%",
    },
    "NORMAL": {
        "tp_atr_mult": 2.0,
        "sl_atr_mult": 1.5,
        "adx_min": 20,
        "trailing": "breakeven",
        "riesgo_pct": 1.0,
        "motor_priority": "Momentum 40%",
    },
    "CHOPPY": {
        "tp_atr_mult": 0,
        "sl_atr_mult": 0,
        "adx_min": 999,
        "trailing": "BLOQUEADO",
        "riesgo_pct": 0.0,
        "motor_priority": "No operar",
    },
}

# Historial de regimenes para detectar transiciones (per-symbol)
_historial_regimen = {}  # {symbol: deque(maxlen=20)}


# ---------------------------------------------------------------------------
# 7.1  Clasificacion de regimenes
# ---------------------------------------------------------------------------

def detectar_regimen(adx, atr, atr_media20, ema20, ema50, symbol="__default__"):
    """
    Clasifica el mercado en uno de 5 regimenes.

    Args:
        adx: ADX actual
        atr: ATR actual
        atr_media20: media ATR ultimas 20 velas
        ema20: EMA 20 actual
        ema50: EMA 50 actual
        symbol: simbolo del activo (para historial per-symbol)

    Returns: string del regimen
    """
    if not all([adx, atr, atr_media20, ema50]):
        return "NORMAL"

    t_fuerte = adx > 30
    t_debil = adx < 20
    alta_vol = atr > atr_media20 * 1.5
    baja_vol = atr < atr_media20 * 0.7
    sin_dir = abs(ema20 - ema50) / ema50 < 0.001 if ema50 else False

    if t_fuerte and alta_vol:
        regimen = "TRENDING_VOLATILE"
    elif t_fuerte and not alta_vol:
        regimen = "TRENDING_CALM"
    elif t_debil and baja_vol:
        regimen = "RANGING"
    elif alta_vol and t_debil:
        regimen = "CHOPPY"
    elif t_debil and sin_dir:
        regimen = "RANGING"
    else:
        regimen = "NORMAL"

    if symbol not in _historial_regimen:
        _historial_regimen[symbol] = deque(maxlen=20)
    _historial_regimen[symbol].append(regimen)
    return regimen


# ---------------------------------------------------------------------------
# 7.3  Deteccion de transicion
# ---------------------------------------------------------------------------

def regimen_estable(ventana=5, symbol="__default__"):
    """
    Comprueba si el regimen ha sido estable en las ultimas N lecturas.
    Returns: True si todos los ultimos N regimenes son iguales
    """
    hist = list(_historial_regimen.get(symbol, deque()))
    if len(hist) < ventana:
        return False
    return len(set(hist[-ventana:])) == 1


def riesgo_con_transicion(regimen_actual, riesgo_base, symbol="__default__"):
    """
    Reduce el riesgo al 50% durante transiciones de regimen.

    Args:
        regimen_actual: regimen detectado
        riesgo_base: riesgo % configurado
        symbol: simbolo del activo

    Returns: riesgo ajustado
    """
    if not regimen_estable(symbol=symbol):
        return round(riesgo_base * 0.5, 2)
    return riesgo_base


def get_config(regimen):
    """Obtiene la configuracion para un regimen dado."""
    return REGIMEN_CONFIG.get(regimen, REGIMEN_CONFIG["NORMAL"])


def get_historial(symbol="__default__"):
    """Retorna el historial de regimenes recientes."""
    return list(_historial_regimen.get(symbol, deque()))


def esta_bloqueado(regimen):
    """True si el regimen actual bloquea operaciones."""
    return regimen == "CHOPPY"


def get_info(regimen, symbol="__default__"):
    """Informacion completa del regimen para la app."""
    cfg = get_config(regimen)
    estable = regimen_estable(symbol=symbol)
    hist = list(_historial_regimen.get(symbol, deque()))
    prev = hist[-2] if len(hist) >= 2 else regimen

    return {
        "regimen": regimen,
        "estable": estable,
        "transicion": not estable,
        "regimen_anterior": prev,
        "tp_atr_mult": cfg["tp_atr_mult"],
        "sl_atr_mult": cfg["sl_atr_mult"],
        "adx_min": cfg["adx_min"],
        "trailing": cfg["trailing"],
        "riesgo_pct": cfg["riesgo_pct"],
        "bloqueado": esta_bloqueado(regimen),
        "motor_priority": cfg["motor_priority"],
    }
