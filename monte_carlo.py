# -*- coding: utf-8 -*-
"""
monte_carlo.py - Mejora 17.11: Simulacion Monte Carlo
ParraCorp v3.1

Simula miles de secuencias aleatorias de trades para estimar:
- Distribucion de resultados futuros (P10, P50, P90)
- Drawdown maximo probable
- Probabilidad de ruina
"""
import numpy as np


def monte_carlo(pnl_trades, n_simulaciones=5000, n_futuros=100, capital_inicial=10000):
    """
    Simulacion Monte Carlo de resultados futuros.

    Args:
        pnl_trades: lista de PnL en USD de trades historicos
        n_simulaciones: numero de simulaciones (5000 por defecto)
        n_futuros: trades futuros a simular por run
        capital_inicial: capital para calcular % de ruina

    Returns: dict con percentiles, drawdown probable, prob ruina
    """
    if not pnl_trades or len(pnl_trades) < 5:
        return {
            "p10": 0, "p50": 0, "p90": 0,
            "dd_max_prob": 0,
            "prob_ruina_pct": 0,
            "n_simulaciones": 0,
            "n_trades_base": len(pnl_trades) if pnl_trades else 0,
            "media": 0,
            "error": f"Minimo 5 trades cerrados, hay {len(pnl_trades) if pnl_trades else 0}",
        }

    pnl_arr = np.array(pnl_trades, dtype=float)
    finales = []
    drawdowns = []
    ruinas = 0

    for _ in range(n_simulaciones):
        secuencia = np.random.choice(pnl_arr, size=n_futuros, replace=True)
        equity = np.cumsum(secuencia)

        # Drawdown maximo
        peak = np.maximum.accumulate(equity)
        dd = np.min(equity - peak)

        finales.append(equity[-1])
        drawdowns.append(dd)

        # Ruina = perder 50% del capital
        if np.min(equity) < -(capital_inicial * 0.5):
            ruinas += 1

    finales = np.array(finales)
    drawdowns = np.array(drawdowns)

    return {
        "p10": round(float(np.percentile(finales, 10)), 2),
        "p50": round(float(np.percentile(finales, 50)), 2),
        "p90": round(float(np.percentile(finales, 90)), 2),
        "dd_max_prob": round(float(np.mean(drawdowns)), 2),
        "dd_worst": round(float(np.min(drawdowns)), 2),
        "prob_ruina_pct": round(ruinas / n_simulaciones * 100, 1),
        "n_simulaciones": n_simulaciones,
        "n_trades_base": len(pnl_trades),
        "media": round(float(np.mean(finales)), 2),
        "std": round(float(np.std(finales)), 2),
    }
