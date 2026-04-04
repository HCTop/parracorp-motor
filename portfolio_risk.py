# -*- coding: utf-8 -*-
"""
portfolio_risk.py - Mejora 17.5: Portfolio-Level Risk Management
ParraCorp v3.1

Gestiona riesgo a nivel de portfolio completo:
- Exposicion por divisa
- Correlacion entre posiciones abiertas
- Value at Risk simplificado
"""
import numpy as np
from config import log as mlog

# Limite maximo de exposicion por divisa (en % del capital)
LIMITE_EXPOSICION_DIVISA = 3.0  # max % del capital por divisa

# Correlaciones hardcodeadas entre pares principales
CORRELACIONES = {
    ("EURUSD", "GBPUSD"): 0.85,
    ("EURUSD", "USDCHF"): -0.90,
    ("EURUSD", "USDJPY"): -0.30,
    ("GBPUSD", "GBPJPY"): 0.75,
    ("AUDUSD", "NZDUSD"): 0.90,
    ("USDJPY", "EURJPY"): 0.70,
    ("EURUSD", "EURGBP"): 0.50,
    ("XAUUSD", "EURUSD"): 0.40,
    ("XAUUSD", "USDJPY"): -0.45,
}


def _divisas_en_par(symbol):
    """Extrae las 2 divisas de un par forex."""
    sym = symbol.upper().replace("/", "")
    # Metales y crypto
    if sym.startswith("XAU"):
        return ["XAU", "USD"]
    if sym.startswith("XAG"):
        return ["XAG", "USD"]
    if any(sym.endswith(x) for x in ["USDT", "USD"]):
        base = sym.replace("USDT", "").replace("USD", "")
        return [base, "USD"]
    # Forex standard
    if len(sym) == 6:
        return [sym[:3], sym[3:]]
    return [sym, "USD"]


def exposicion_por_divisa(ops_abiertas, capital):
    """
    Calcula la exposicion total por divisa como % del capital.

    Args:
        ops_abiertas: lista de signals activos con {symbol, lote, entry_price, action}
        capital: capital total

    Returns: dict {divisa: {lotes, pct_capital, operaciones}}
    """
    if not capital or capital == 0:
        return {}

    expo = {}
    for op in ops_abiertas:
        sym = op.get("symbol", "")
        divisas = _divisas_en_par(sym)
        riesgo = op.get("riesgo_usd", 0) or (capital * op.get("risk_pct", 1) / 100)

        for div in divisas:
            if div not in expo:
                expo[div] = {"riesgo_usd": 0, "operaciones": 0, "pares": []}
            expo[div]["riesgo_usd"] += riesgo
            expo[div]["operaciones"] += 1
            expo[div]["pares"].append(sym)

    # Calcular porcentajes
    for div, data in expo.items():
        data["pct_capital"] = round(data["riesgo_usd"] / capital * 100, 1)

    return expo


def puede_abrir(ops_abiertas, nuevo_par, riesgo_nuevo_usd, capital):
    """
    Verifica si se puede abrir una nueva posicion sin sobreexponer una divisa.

    Returns: (allowed: bool, reason: str)
    """
    if not capital:
        return True, "OK"

    divisas = _divisas_en_par(nuevo_par)
    expo = exposicion_por_divisa(ops_abiertas, capital)

    for div in divisas:
        expo_actual = expo.get(div, {}).get("riesgo_usd", 0)
        expo_nueva = expo_actual + riesgo_nuevo_usd
        pct = expo_nueva / capital * 100

        if pct > LIMITE_EXPOSICION_DIVISA:
            return False, f"Limite exposicion {div}: {pct:.1f}% > {LIMITE_EXPOSICION_DIVISA}%"

    return True, "OK"


def check_correlacion(nuevo_par, nueva_dir, ops_abiertas):
    """
    Verifica que la nueva posicion no este altamente correlacionada
    con posiciones existentes en la misma direccion.

    Returns: (allowed: bool, reason: str)
    """
    for op in ops_abiertas:
        par_existente = op.get("symbol", "")
        dir_existente = op.get("action", "")

        # Buscar correlacion
        key1 = (nuevo_par, par_existente)
        key2 = (par_existente, nuevo_par)
        corr = CORRELACIONES.get(key1) or CORRELACIONES.get(key2)

        if corr is None:
            continue

        # Correlacion positiva alta + misma direccion = duplicado
        if corr > 0.75 and nueva_dir == dir_existente:
            return False, f"Alta correlacion ({corr:.2f}) con {par_existente} en misma direccion"

        # Correlacion negativa alta + direccion opuesta = duplicado
        if corr < -0.75 and nueva_dir != dir_existente:
            return False, f"Correlacion inversa ({corr:.2f}) con {par_existente} opuesto"

    return True, "OK"


def var_portfolio_simple(ops_abiertas):
    """
    Value at Risk simplificado del portfolio.
    Suma de riesgos individuales con factor de diversificacion.

    Returns: dict con var_total, factor_diversificacion
    """
    if not ops_abiertas:
        return {"var_total": 0, "factor_div": 1.0, "n_ops": 0}

    riesgos = [op.get("riesgo_usd", 0) for op in ops_abiertas if op.get("riesgo_usd")]
    if not riesgos:
        return {"var_total": 0, "factor_div": 1.0, "n_ops": len(ops_abiertas)}

    # VaR no diversificado (peor caso)
    var_nodiv = sum(riesgos)

    # Factor de diversificacion simple basado en numero de pares distintos
    pares_unicos = len(set(op.get("symbol", "") for op in ops_abiertas))
    factor = min(1.0, 0.7 + 0.1 * pares_unicos)  # 0.8 para 1 par, ~1.0 para 3+

    var_total = var_nodiv * factor

    return {
        "var_total": round(var_total, 2),
        "var_no_diversificado": round(var_nodiv, 2),
        "factor_div": round(factor, 2),
        "n_ops": len(ops_abiertas),
        "riesgos_individuales": riesgos,
    }


def get_portfolio_info(ops_abiertas, capital):
    """Info completa del portfolio para la app."""
    expo = exposicion_por_divisa(ops_abiertas, capital)
    var = var_portfolio_simple(ops_abiertas)

    return {
        "exposicion_divisa": expo,
        "var": var,
        "n_operaciones": len(ops_abiertas),
        "capital": capital,
    }
