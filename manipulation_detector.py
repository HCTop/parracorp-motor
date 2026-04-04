# -*- coding: utf-8 -*-
"""
manipulation_detector.py - Mejora 17.7: Deteccion de Manipulacion
ParraCorp v3.1

Detecta patrones de stop hunting: spike rapido con cierre cerca de apertura,
movimientos en baja liquidez que no siguen la tendencia.
"""
import numpy as np


def detectar_stop_hunt(candles, umbral_spike=2.5):
    """
    Detecta spike sospechoso: vela con rango > umbral * ATR pero cierre cerca de apertura.

    Args:
        candles: lista de dicts con {open, high, low, close, rango}
                 o lista con [open, high, low, close]
        umbral_spike: multiplicador ATR para considerar spike

    Returns: (spike_detectado: bool, rango_relativo: float, tipo: str)
    """
    if not candles or len(candles) < 20:
        return False, 1.0, "NORMAL"

    # Calcular rangos
    rangos = []
    for c in candles:
        if isinstance(c, dict):
            r = c.get("high", 0) - c.get("low", 0)
        else:
            r = c[1] - c[2]  # high - low
        rangos.append(r)

    # ATR medio de las ultimas 20 velas
    atr_med = np.mean(rangos[-20:]) if rangos else 0

    if atr_med == 0:
        return False, 1.0, "NORMAL"

    # Ultima vela
    ultima = candles[-1]
    if isinstance(ultima, dict):
        rango = ultima.get("high", 0) - ultima.get("low", 0)
        body = abs(ultima.get("close", 0) - ultima.get("open", 0))
    else:
        rango = ultima[1] - ultima[2]
        body = abs(ultima[3] - ultima[0])

    if rango == 0:
        return False, 1.0, "NORMAL"

    rango_rel = rango / atr_med
    body_rel = body / rango

    # Spike: rango grande pero body pequeño (mecha larga, cierre en apertura)
    spike = rango_rel > umbral_spike and body_rel < 0.3

    if spike:
        # Determinar tipo de manipulacion
        if isinstance(ultima, dict):
            if ultima.get("close", 0) > ultima.get("open", 0):
                tipo = "BEAR_TRAP"  # Bajaron para cazar stops y subieron
            else:
                tipo = "BULL_TRAP"  # Subieron para cazar stops y bajaron
        else:
            if ultima[3] > ultima[0]:
                tipo = "BEAR_TRAP"
            else:
                tipo = "BULL_TRAP"
        return True, round(rango_rel, 2), tipo

    return False, round(rango_rel, 2), "NORMAL"


def detectar_liquidez_baja(hora_utc, adx, vol_ratio):
    """
    Detecta si estamos en periodo de baja liquidez donde
    los movimientos son menos fiables.

    Args:
        hora_utc: hora actual UTC (0-23)
        adx: ADX actual
        vol_ratio: ratio ATR actual / ATR media

    Returns: (baja_liquidez: bool, razon: str)
    """
    # Periodos de baja liquidez
    baja_liq = hora_utc >= 21 or hora_utc < 1  # Cierre NY - apertura Asia
    rollover = 21 <= hora_utc <= 23  # Rollover/swap time

    if rollover and adx < 15:
        return True, "Periodo de rollover con baja direccionalidad"

    if baja_liq and vol_ratio < 0.5:
        return True, "Baja liquidez con volatilidad muy reducida"

    return False, "OK"


def get_manipulation_info(candles, hora_utc=12, adx=25, vol_ratio=1.0):
    """
    Info completa de manipulacion para la app.

    Returns: dict con spike, liquidez, alerta
    """
    spike, rango_rel, tipo = detectar_stop_hunt(candles)
    baja_liq, liq_razon = detectar_liquidez_baja(hora_utc, adx, vol_ratio)

    alerta = spike or baja_liq

    return {
        "spike_detectado": spike,
        "spike_tipo": tipo,
        "spike_rango_rel": rango_rel,
        "baja_liquidez": baja_liq,
        "liquidez_razon": liq_razon,
        "alerta_manipulacion": alerta,
    }
