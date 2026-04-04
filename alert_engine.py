# -*- coding: utf-8 -*-
"""
alert_engine.py - Mejora 17.8: Alertas Inteligentes (no-trade)
ParraCorp v3.1

Genera alertas de condicion de mercado (no de trading):
- Squeeze detectado
- Cambio brusco de currency strength
- Divergencia fuerte
- Cambio de regimen
"""
from config import log as mlog


def generar_alertas_condicion(features_act, features_hist=None, regimen_actual="", regimen_anterior=""):
    """
    Genera alertas basadas en condiciones de mercado.

    Args:
        features_act: dict con features actuales
        features_hist: lista de dicts con features historicas (ultimas N lecturas)
        regimen_actual: regimen actual
        regimen_anterior: regimen de la lectura anterior

    Returns: lista de alertas [{tipo, mensaje, prioridad}]
    """
    alertas = []

    par = features_act.get("par", "")

    # 1. Squeeze detectado
    squeeze = features_act.get("squeeze", False)
    squeeze_prev = False
    if features_hist and len(features_hist) > 5:
        squeeze_prev = features_hist[-5].get("squeeze", False) if isinstance(features_hist[-5], dict) else False

    if squeeze and not squeeze_prev:
        alertas.append({
            "tipo": "SQUEEZE",
            "mensaje": f"Squeeze detectado en {par} - posible explosion de rango inminente",
            "prioridad": "alta",
            "emoji": "\u26A1",
        })

    # 2. Cambio brusco de currency strength
    cs_actual = features_act.get("currency_spread", 0)
    if features_hist and len(features_hist) > 12:
        cs_prev = features_hist[-12].get("currency_spread", 0) if isinstance(features_hist[-12], dict) else 0
        delta_strength = abs(cs_actual - cs_prev)
        if delta_strength > 0.4:
            alertas.append({
                "tipo": "STRENGTH_SHIFT",
                "mensaje": f"Cambio brusco de fuerza de divisa en {par} (delta={delta_strength:.2f})",
                "prioridad": "media",
                "emoji": "\U0001F4CA",
            })

    # 3. Divergencia fuerte
    div = features_act.get("divergence_signal", "NONE")
    if div in ("BEARISH_DIV", "BULLISH_DIV"):
        div_text = "bajista" if "BEARISH" in div else "alcista"
        alertas.append({
            "tipo": "DIVERGENCE",
            "mensaje": f"Divergencia {div_text} detectada en {par}",
            "prioridad": "alta",
            "emoji": "\u26A0",
        })

    # 4. Cambio de regimen
    if regimen_actual and regimen_anterior and regimen_actual != regimen_anterior:
        alertas.append({
            "tipo": "REGIME_CHANGE",
            "mensaje": f"Cambio de regimen: {regimen_anterior} -> {regimen_actual}",
            "prioridad": "media",
            "emoji": "\U0001F504",
        })

    # 5. Volatilidad extrema
    vol_ratio = features_act.get("vol_ratio", 1.0)
    if vol_ratio > 2.0:
        alertas.append({
            "tipo": "HIGH_VOL",
            "mensaje": f"Volatilidad extrema en {par} (ratio={vol_ratio:.1f}x)",
            "prioridad": "alta",
            "emoji": "\U0001F525",
        })

    # 6. Order flow divergencia
    of_div = features_act.get("of_divergencia", False)
    if of_div:
        alertas.append({
            "tipo": "OF_DIVERGENCE",
            "mensaje": f"Divergencia de order flow en {par} - precio y volumen no coinciden",
            "prioridad": "media",
            "emoji": "\U0001F50D",
        })

    return alertas
