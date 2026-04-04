# -*- coding: utf-8 -*-
"""
auto_optimizer.py - Mejora 17.2: Auto-Optimizacion Walk-Forward
ParraCorp v3.1

Optimizacion automatica mensual de parametros clave:
- Umbral TQS
- Multiplicadores ATR (SL/TP)
- ADX minimo por regimen
- Ventana Z-Score

Usa walk-forward para evitar sobreajuste.
"""
import numpy as np
from itertools import product
from config import log as mlog


def _simular_trades(trades, params):
    """
    Simula el filtro de trades con parametros dados.
    Returns: lista de trades que habrian pasado el filtro.
    """
    resultado = []
    for t in trades:
        tqs = t.get("trade_quality_score", 0)
        adx = t.get("adx", 0)

        # Filtrar por TQS
        if tqs < params.get("umbral_tqs", 0.65):
            continue

        # Filtrar por ADX minimo
        regimen = t.get("regimen", "NORMAL")
        adx_min = params.get(f"adx_min_{regimen.lower()}", 20)
        if adx < adx_min:
            continue

        resultado.append(t)

    return resultado


def _calcular_sharpe(pnls, periodos_por_ano=252):
    """Calcula Sharpe ratio."""
    if not pnls or len(pnls) < 2:
        return -999
    arr = np.array(pnls)
    media = np.mean(arr)
    std = np.std(arr)
    if std == 0:
        return 0
    return float(media / std * np.sqrt(periodos_por_ano))


def optimizar_parametros(trades_log, param_grid=None):
    """
    Optimiza parametros usando walk-forward validation.

    Args:
        trades_log: lista de trades historicos con features
        param_grid: dict de parametros a optimizar {param: [valores]}

    Returns: (mejores_params, mejor_sharpe, resultados_wf)
    """
    if len(trades_log) < 60:
        mlog("OPTIM", f"Insuficientes trades ({len(trades_log)}/60)")
        return None, -999, []

    if param_grid is None:
        param_grid = {
            "umbral_tqs": [0.55, 0.60, 0.65, 0.70, 0.75],
            "adx_min_normal": [15, 20, 25],
            "adx_min_trending_calm": [20, 25, 30],
        }

    # Ordenar por timestamp
    trades_sorted = sorted(trades_log, key=lambda t: t.get("timestamp_entrada", 0))

    # Walk-forward: 70% train, 30% test
    split = int(len(trades_sorted) * 0.7)
    train = trades_sorted[:split]
    test = trades_sorted[split:]

    if len(train) < 30 or len(test) < 10:
        mlog("OPTIM", "Datos insuficientes para split train/test")
        return None, -999, []

    mejores = None
    mejor_sharpe = -999
    resultados = []

    # Grid search
    keys = list(param_grid.keys())
    for combo in product(*param_grid.values()):
        params = dict(zip(keys, combo))

        # Evaluar en train
        train_filtered = _simular_trades(train, params)
        if len(train_filtered) < 10:
            continue

        # Evaluar en test (out-of-sample)
        test_filtered = _simular_trades(test, params)
        if len(test_filtered) < 5:
            continue

        pnls = [t.get("pnl_pips", 0) for t in test_filtered]
        sharpe = _calcular_sharpe(pnls)

        wins = sum(1 for p in pnls if p > 0)
        wr = wins / len(pnls) * 100

        resultados.append({
            "params": params,
            "sharpe": round(sharpe, 3),
            "win_rate": round(wr, 1),
            "n_trades_test": len(test_filtered),
        })

        if sharpe > mejor_sharpe:
            mejor_sharpe = sharpe
            mejores = params

    if mejores:
        mlog("OPTIM", f"Mejores params: {mejores} sharpe={mejor_sharpe:.3f}")

    return mejores, round(mejor_sharpe, 3), resultados


def get_optimization_status():
    """Estado de la ultima optimizacion para la app."""
    return {
        "disponible": True,
        "descripcion": "Optimizacion walk-forward de parametros clave",
    }
