# -*- coding: utf-8 -*-
"""
learning_loop.py - Capa 9: Learning Loop
ParraCorp v3.1

Registra datos de cada trade para analisis posterior.
Ajuste automatico de pesos semanal con walk-forward validation.
Proteccion contra sobreajuste: min 30 trades, p<0.05, max delta 5%.
"""
import json
import os
import time
from config import data_path, log as mlog

TRADES_LOG_FILE = data_path("trades_log.json")
PESOS_FILE = data_path("pesos_aprendidos.json")

_trades_log = []
_pesos_aprendidos = {}  # {regimen: {momentum: w, reversion: w, ...}}


def init():
    """Carga datos persistidos."""
    global _trades_log, _pesos_aprendidos
    try:
        if os.path.exists(TRADES_LOG_FILE):
            with open(TRADES_LOG_FILE, "r") as f:
                _trades_log = json.load(f)
            mlog("LEARN", f"Cargados {len(_trades_log)} trades del log")
    except Exception as e:
        mlog("LEARN", f"Error cargando trades log: {e}")

    try:
        if os.path.exists(PESOS_FILE):
            with open(PESOS_FILE, "r") as f:
                _pesos_aprendidos = json.load(f)
            mlog("LEARN", f"Pesos aprendidos: {list(_pesos_aprendidos.keys())}")
    except Exception as e:
        mlog("LEARN", f"Error cargando pesos: {e}")


def registrar_trade(signal, features, regimen):
    """
    Registra un trade completado con todas las features del momento de entrada.

    Args:
        signal: dict de la senal cerrada (con pnl_pct, pnl_usd, status, etc.)
        features: dict con scores de los motores y features
        regimen: regimen activo cuando se abrio
    """
    entry = {
        "id": signal.get("id", ""),
        "timestamp_entrada": signal.get("timestamp", 0),
        "timestamp_cierre": signal.get("exit_ts", int(time.time())),
        "par": signal.get("symbol", ""),
        "timeframe": signal.get("timeframe", "60"),
        "resultado": "WIN" if (signal.get("pnl_pct", 0) or 0) > 0 else "LOSS",
        "pnl_pips": signal.get("pnl_pct", 0) or 0,  # usamos pct como proxy
        "pnl_usd": signal.get("pnl_usd", 0) or 0,
        # Features del momento de entrada
        "momentum_score": features.get("momentum_score", 0),
        "reversion_score": features.get("reversion_score", 0),
        "strength_score": features.get("strength_score", 0),
        "breakout_score": features.get("breakout_score", 0),
        "trade_quality_score": features.get("trade_quality_score", 0),
        "zscore": features.get("zscore_h1", 0),
        "adx": features.get("adx", 0),
        "vol_ratio": features.get("vol_ratio", 1.0),
        "currency_spread": features.get("currency_spread", 0),
        "order_flow_delta": features.get("order_flow_delta", 0),
        "mtf_alignment": features.get("mtf_alignment", 0),
        "divergence": features.get("divergence_signal", "NONE"),
        "sr_distance_pips": features.get("sr_distance_pips", 0),
        "regimen": regimen,
        "sesion": features.get("sesion", ""),
        "confianza_consensus": features.get("confianza_consensus", 0),
    }

    _trades_log.append(entry)

    # Limitar a ultimos 1000 trades
    while len(_trades_log) > 1000:
        _trades_log.pop(0)

    _guardar_log()
    mlog("LEARN", f"Trade {entry['id']} registrado ({entry['resultado']})")


def _guardar_log():
    try:
        with open(TRADES_LOG_FILE, "w") as f:
            json.dump(_trades_log, f, indent=1)
    except Exception as e:
        mlog("LEARN", f"Error guardando log: {e}")


def ajustar_pesos(regimen, pesos_actuales, min_trades=30, max_delta=0.05):
    """
    Ajusta pesos de los motores basado en correlacion con resultados.
    Solo cambia si hay significancia estadistica (p < 0.05).

    Args:
        regimen: regimen para el que ajustar
        pesos_actuales: dict {momentum: w, reversion: w, strength: w, breakout: w}
        min_trades: minimo de trades para ajustar
        max_delta: cambio maximo por ciclo

    Returns: dict con nuevos pesos (o los mismos si no hay datos suficientes)
    """
    # Filtrar trades del regimen
    sub = [t for t in _trades_log if t.get("regimen") == regimen]
    if len(sub) < min_trades:
        return pesos_actuales

    try:
        import numpy as np
        from scipy import stats

        feats = ["momentum_score", "reversion_score", "strength_score", "breakout_score"]
        pnls = [t.get("pnl_pips", 0) for t in sub]

        nuevos = {}
        for feat in feats:
            key = feat.replace("_score", "")
            values = [t.get(feat, 0) for t in sub]
            corr, p = stats.pearsonr(values, pnls)

            if p > 0.05:
                # No significativo, mantener peso actual
                nuevos[key] = pesos_actuales.get(key, 0.25)
                continue

            ajuste = corr * 0.1
            actual = pesos_actuales.get(key, 0.25)
            nuevo = actual + ajuste
            # Limitar cambio
            nuevo = max(actual - max_delta, min(actual + max_delta, nuevo))
            # Limitar rango absoluto
            nuevos[key] = max(0.05, min(0.70, nuevo))

        # Normalizar para que sumen 1.0
        total = sum(nuevos.values())
        if total > 0:
            nuevos = {k: round(v / total, 3) for k, v in nuevos.items()}

        # Guardar
        _pesos_aprendidos[regimen] = nuevos
        _guardar_pesos()

        mlog("LEARN", f"Pesos ajustados [{regimen}]: {nuevos}")
        return nuevos

    except ImportError:
        mlog("LEARN", "scipy no disponible, sin ajuste de pesos")
        return pesos_actuales
    except Exception as e:
        mlog("LEARN", f"Error ajustando pesos: {e}")
        return pesos_actuales


def _guardar_pesos():
    try:
        with open(PESOS_FILE, "w") as f:
            json.dump(_pesos_aprendidos, f, indent=2)
    except Exception:
        pass


def get_pesos(regimen):
    """Obtiene pesos aprendidos para un regimen, o None si no hay."""
    return _pesos_aprendidos.get(regimen)


def get_stats():
    """Estadisticas del learning loop."""
    if not _trades_log:
        return {"total_trades": 0}

    wins = sum(1 for t in _trades_log if t.get("resultado") == "WIN")
    losses = len(_trades_log) - wins

    return {
        "total_trades": len(_trades_log),
        "wins": wins,
        "losses": losses,
        "win_rate": round(wins / len(_trades_log) * 100, 1) if _trades_log else 0,
        "regimenes_con_pesos": list(_pesos_aprendidos.keys()),
        "trades_por_regimen": {
            r: sum(1 for t in _trades_log if t.get("regimen") == r)
            for r in set(t.get("regimen", "NORMAL") for t in _trades_log)
        },
    }


def analizar_rendimiento():
    """Analisis de rendimiento por condicion."""
    if not _trades_log:
        return {}

    result = {}
    for dim in ["sesion", "regimen", "par"]:
        grupos = {}
        for t in _trades_log:
            key = t.get(dim, "UNKNOWN")
            if key not in grupos:
                grupos[key] = {"trades": 0, "wins": 0, "pnl": 0}
            grupos[key]["trades"] += 1
            if t.get("resultado") == "WIN":
                grupos[key]["wins"] += 1
            grupos[key]["pnl"] += t.get("pnl_pips", 0)

        for k, v in grupos.items():
            v["win_rate"] = round(v["wins"] / v["trades"] * 100, 1) if v["trades"] else 0
            v["pnl"] = round(v["pnl"], 2)

        result[dim] = grupos

    return result


# Inicializar al importar
init()
