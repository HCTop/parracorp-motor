# -*- coding: utf-8 -*-
"""
risk_engine.py - Capa 6: Gestion de Riesgo v3.1
ParraCorp v3.1

Position sizing, SL/TP por ATR+regimen, ajuste por regimen transition.
Sin broker - solo calcula tamanos de posicion para la senal.
"""
from config import log as mlog, JPY, METAL, INDEX, CRYPTO, COMMODITY

MIN_PROFIT_USD = 1.0
_USD_BASE = {"USDJPY", "USDCHF", "USDCAD"}


def calcular_lote(precio, sl, capital, riesgo_pct, simbolo, tp=None):
    """
    Calcula tamano de posicion basado en riesgo.
    """
    result = {
        "lote": 0, "unidades": 0, "lote_std": 0.0,
        "riesgo_usd": 0, "rr_ratio": 0,
        "rejected": False, "reject_reason": "",
    }

    if not precio or not sl or precio <= 0 or sl <= 0:
        result["rejected"] = True
        result["reject_reason"] = "Precio o SL invalido"
        return result

    sym = simbolo.upper().replace("/", "")
    is_jpy = sym in JPY
    pip = 0.01 if is_jpy else 0.0001

    sl_dist = abs(precio - sl)
    sl_pips = sl_dist / pip

    if sl_pips < 3:
        result["rejected"] = True
        result["reject_reason"] = f"SL muy ajustado ({sl_pips:.0f} pips)"
        return result

    riesgo_usd = capital * (riesgo_pct / 100)
    result["riesgo_usd"] = round(riesgo_usd, 2)

    if sym.startswith("XAU"):
        # XAU: 1 lote std = 100 oz, pip = $0.01, pip_value = $0.01/oz
        # P&L = diff_precio * unidades_oz
        # unidades_oz = riesgo_usd / sl_dist (porque $1 movimiento = $1/oz)
        unidades = riesgo_usd / sl_dist if sl_dist > 0 else 0
        result["unidades"] = round(max(unidades, 0.01), 2)
        result["lote"] = result["unidades"]
        result["lote_std"] = round(result["unidades"] / 100, 2)
    elif sym in CRYPTO or sym.endswith("USDT"):
        unidades = riesgo_usd / sl_dist if sl_dist > 0 else 0
        result["unidades"] = round(unidades, 4)
        result["lote"] = result["unidades"]
        result["lote_std"] = result["unidades"]
    elif sym in _USD_BASE:
        unidades = riesgo_usd / (sl_pips * pip * precio) if (sl_pips * pip * precio) > 0 else 0
        result["unidades"] = max(1, round(unidades))
        result["lote"] = result["unidades"]
        result["lote_std"] = round(result["unidades"] / 100000, 4)
    else:
        unidades = riesgo_usd / (sl_pips * pip) if (sl_pips * pip) > 0 else 0
        result["unidades"] = max(1, round(unidades))
        result["lote"] = result["unidades"]
        result["lote_std"] = round(result["unidades"] / 100000, 4)

    if tp and sl_dist > 0:
        tp_dist = abs(precio - tp)
        result["rr_ratio"] = round(tp_dist / sl_dist, 2)

    return result


def validar_senal(action, precio, sl, tp, simbolo):
    """Valida que la senal tenga sentido basico."""
    if not precio or not sl or not tp:
        return False, "Precio/SL/TP no definidos"
    if precio <= 0 or sl <= 0 or tp <= 0:
        return False, "Valores negativos o cero"

    sym = simbolo.upper()

    if action == "BUY":
        if sl >= precio:
            return False, f"BUY: SL ({sl}) debe ser < precio ({precio})"
        if tp <= precio:
            return False, f"BUY: TP ({tp}) debe ser > precio ({precio})"
    elif action == "SELL":
        if sl <= precio:
            return False, f"SELL: SL ({sl}) debe ser > precio ({precio})"
        if tp >= precio:
            return False, f"SELL: TP ({tp}) debe ser < precio ({precio})"

    sl_pct = abs(precio - sl) / precio * 100
    if sym in CRYPTO or sym.endswith("USDT"):
        min_sl = 0.15
    elif "XAU" in sym:
        min_sl = 0.10
    else:
        min_sl = 0.05
    if sl_pct < min_sl:
        return False, f"SL demasiado ajustado ({sl_pct:.2f}% < {min_sl}%)"

    max_sl = 15 if (sym in CRYPTO or sym.endswith("USDT")) else 5
    if sl_pct > max_sl:
        return False, f"SL demasiado lejos ({sl_pct:.2f}% > {max_sl}%)"

    return True, "OK"


def ajustar_riesgo_por_regimen(riesgo_base, regimen_info):
    """Ajusta riesgo segun regimen y transicion."""
    riesgo = riesgo_base
    riesgo_regimen = regimen_info.get("riesgo_pct", 1.0)
    riesgo = min(riesgo, riesgo_regimen)

    if regimen_info.get("transicion", False):
        riesgo *= 0.5

    if regimen_info.get("bloqueado", False):
        return 0.0

    return round(max(riesgo, 0.3), 2)


def pnl_usd(entrada, salida, lote, simbolo, action):
    """Calcula P&L en USD."""
    sym = simbolo.upper().replace("/", "")

    if action.upper() == "BUY":
        diff = salida - entrada
    else:
        diff = entrada - salida

    if sym in _USD_BASE:
        pnl = diff * lote / salida if salida else 0
    else:
        pnl = diff * lote

    return round(pnl, 2)
