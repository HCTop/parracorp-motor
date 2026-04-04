# -*- coding: utf-8 -*-
"""
order_flow.py - Capa 7: Order Flow Proxy (OFP)
ParraCorp v3.1

Simula flujo de ordenes institucional usando volumen de velas.
Detecta divergencias entre precio y presion real compradora/vendedora.
"""
import numpy as np


def calcular_order_flow(closes, highs, lows, volumes):
    """
    Calcula Order Flow Proxy usando datos OHLCV.

    Estima volumen alcista vs bajista por vela usando la posicion
    del cierre dentro del rango de la vela.

    Args:
        closes: lista de precios de cierre
        highs: lista de maximos
        lows: lista de minimos
        volumes: lista de volumenes

    Returns: dict con order_flow_delta, cvd_slope, of_divergencia
    """
    if not closes or len(closes) < 10:
        return {
            "order_flow_delta": 0.0,
            "cvd_slope": 0.0,
            "of_divergencia": False,
        }

    n = len(closes)
    deltas = []

    for i in range(n):
        rango = highs[i] - lows[i]
        if rango == 0:
            deltas.append(0.0)
            continue

        vol = volumes[i] if i < len(volumes) else 0
        # Estimacion: cierre arriba del rango = presion compradora
        vol_alcista = vol * (closes[i] - lows[i]) / rango
        vol_bajista = vol * (highs[i] - closes[i]) / rango
        deltas.append(vol_alcista - vol_bajista)

    # CVD - Cumulative Volume Delta
    cvd = list(np.cumsum(deltas))

    # Slope del CVD en las ultimas N velas
    slope_n = min(10, len(cvd))
    cvd_slope = (cvd[-1] - cvd[-slope_n]) / slope_n if slope_n > 1 else 0

    # Divergencia: precio sube pero CVD baja (trampa alcista) o viceversa
    lookback = min(5, len(closes) - 1)
    if lookback > 0:
        precio_cambio = (closes[-1] - closes[-lookback - 1]) / closes[-lookback - 1] if closes[-lookback - 1] else 0
        cvd_cambio = cvd[-1] - cvd[-lookback - 1]
        cvd_std = np.std(cvd[-lookback:]) if lookback > 1 else 1.0
        cvd_std = max(cvd_std, 1e-9)
        precio_sube = precio_cambio > 0.001  # meaningful up move (0.1%)
        precio_baja = precio_cambio < -0.001  # meaningful down move
        cvd_baja = cvd_cambio < -0.5 * cvd_std
        cvd_sube = cvd_cambio > 0.5 * cvd_std
        divergencia = (precio_sube and cvd_baja) or (precio_baja and cvd_sube)
    else:
        divergencia = False

    # Normalizar delta
    std_deltas = np.std(deltas) if len(deltas) > 1 else 1.0
    delta_norm = deltas[-1] / std_deltas if std_deltas else 0.0
    delta_norm = max(-1.0, min(1.0, delta_norm))

    return {
        "order_flow_delta": round(delta_norm, 4),
        "cvd_slope": round(cvd_slope, 6),
        "of_divergencia": divergencia,
    }
