# -*- coding: utf-8 -*-
"""
mtf.py - Capa 7: Confirmacion Multi-Timeframe (MTF)
ParraCorp v3.1

Verifica que el timeframe mayor (H4) y el menor (H1) esten alineados.
Si hay conflicto, la senal se bloquea o penaliza.
"""


def tendencia_timeframe(ema20, ema50, adx):
    """
    Determina la tendencia de un timeframe usando EMA20 vs EMA50 y ADX.

    Args:
        ema20: EMA 20 periodos
        ema50: EMA 50 periodos
        adx: ADX del timeframe

    Returns: BULLISH / BEARISH / NEUTRAL
    """
    if not ema20 or not ema50 or not adx:
        return "NEUTRAL"

    if ema20 > ema50 and adx > 20:
        return "BULLISH"
    elif ema20 < ema50 and adx > 20:
        return "BEARISH"
    return "NEUTRAL"


def mtf_alignment(tendencia_h4, tendencia_h1, senal_h1):
    """
    Evalua la alineacion entre H4 y H1.

    Args:
        tendencia_h4: BULLISH/BEARISH/NEUTRAL del timeframe mayor
        tendencia_h1: BULLISH/BEARISH/NEUTRAL del timeframe operativo
        senal_h1: BUY/SELL/NEUTRAL de los motores de senal

    Returns: (alignment 0-1, direction BUY/SELL/BLOCK, reason)
    """
    if not tendencia_h4 or tendencia_h4 == "NEUTRAL":
        # H4 neutral: permitir senal H1 con descuento
        return 0.6, senal_h1 if senal_h1 != "NEUTRAL" else "NEUTRAL", \
            "H4 neutral - senal H1 con descuento"

    if tendencia_h4 == "BULLISH" and senal_h1 == "BUY":
        return 1.0, "BUY", "H4+H1 alineados alcistas"

    if tendencia_h4 == "BEARISH" and senal_h1 == "SELL":
        return 1.0, "SELL", "H4+H1 alineados bajistas"

    if tendencia_h4 == "BULLISH" and senal_h1 == "SELL":
        return 0.0, "BLOCK", "Conflicto: H4 alcista vs senal SELL H1"

    if tendencia_h4 == "BEARISH" and senal_h1 == "BUY":
        return 0.0, "BLOCK", "Conflicto: H4 bajista vs senal BUY H1"

    # Default: H4 tiene tendencia pero senal H1 es NEUTRAL
    return 0.3, "NEUTRAL", "H4 con tendencia pero H1 sin senal clara"


def get_mtf_info(htf_data, signal_dir):
    """
    Calcula info MTF completa a partir de datos del timeframe superior.

    Args:
        htf_data: dict con ema20, ema50, adx del timeframe superior
        signal_dir: direccion de la senal actual (BUY/SELL/NEUTRAL)

    Returns: dict con alignment, direction, reason, htf_trend
    """
    if not htf_data:
        return {
            "mtf_alignment": 0.5,
            "mtf_dir": signal_dir,
            "mtf_reason": "Sin datos HTF",
            "htf_trend": "NEUTRAL",
        }

    ema20 = htf_data.get("ema20", 0)
    ema50 = htf_data.get("ema50", 0)
    adx = htf_data.get("adx", 0)

    htf_trend = tendencia_timeframe(ema20, ema50, adx)
    h1_trend = signal_dir  # Ya tenemos la senal del TF operativo

    alignment, direction, reason = mtf_alignment(htf_trend, h1_trend, signal_dir)

    return {
        "mtf_alignment": alignment,
        "mtf_dir": direction,
        "mtf_reason": reason,
        "htf_trend": htf_trend,
    }
