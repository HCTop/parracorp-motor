# -*- coding: utf-8 -*-
"""
risk_engine.py - Capa 6: Gestion de Riesgo v3.1
ParraCorp v3.1

Position sizing, SL/TP por ATR+regimen, ajuste por regimen transition.
Sin broker - solo calcula tamanos de posicion para la senal.

Tamaños de contrato MT4/MT5:
- Forex: 1 lot = 100,000 unidades
- XAU (oro): 1 lot = 100 oz
- XAG (plata): 1 lot = 5,000 oz
- Indices: 1 lot = 1 contrato (pip_value varía)
- Crypto: 1 lot = 1 unidad
- Oil: 1 lot = 1,000 barriles
"""
from config import log as mlog, JPY, METAL, INDEX, CRYPTO, COMMODITY

MIN_PROFIT_USD = 1.0
_USD_BASE = {"USDJPY", "USDCHF", "USDCAD"}

# Contract sizes por tipo (MT4/MT5 standard)
_CONTRACT = {
    "XAU": 100,       # 1 lot = 100 oz
    "XAG": 5000,      # 1 lot = 5000 oz
    "XPT": 1,         # 1 lot = 1 oz (platino)
    "XPD": 1,         # 1 lot = 1 oz (paladio)
    "FOREX": 100000,  # 1 lot = 100,000 unidades
    "CRYPTO": 1,      # 1 lot = 1 unidad
    "OIL": 1000,      # 1 lot = 1000 barriles
}


def _quote_to_usd(sym):
    """
    Devuelve factor para convertir de divisa quote a USD.
    Para NZDJPY: quote=JPY, factor = 1/USDJPY ≈ 0.0067
    Para EURUSD: quote=USD, factor = 1.0
    """
    # Extraer quote currency (ultimos 3 chars)
    quote = sym[-3:]
    if quote == "USD":
        return 1.0
    try:
        from data_feed import get_price
        if quote == "JPY":
            r = get_price("USDJPY")
            return (1.0 / r) if r and r > 0 else (1.0 / 150.0)
        elif quote == "CHF":
            r = get_price("USDCHF")
            return (1.0 / r) if r and r > 0 else (1.0 / 0.90)
        elif quote == "CAD":
            r = get_price("USDCAD")
            return (1.0 / r) if r and r > 0 else (1.0 / 1.37)
        elif quote == "GBP":
            r = get_price("GBPUSD")
            return r if r and r > 0 else 1.26
        elif quote == "AUD":
            r = get_price("AUDUSD")
            return r if r and r > 0 else 0.65
        elif quote == "NZD":
            r = get_price("NZDUSD")
            return r if r and r > 0 else 0.60
    except Exception:
        pass
    return 1.0


def _get_contract_size(sym):
    """Devuelve contract size y tipo para un símbolo."""
    if sym.startswith("XAU"):
        return _CONTRACT["XAU"], "metal"
    if sym.startswith("XAG"):
        return _CONTRACT["XAG"], "metal"
    if sym.startswith("XPT"):
        return _CONTRACT["XPT"], "metal"
    if sym.startswith("XPD"):
        return _CONTRACT["XPD"], "metal"
    if sym in CRYPTO or sym.endswith("USDT") or sym.endswith("USD") and any(
        c in sym for c in ["BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE",
                           "AVAX", "DOT", "LINK", "MATIC", "LTC", "UNI",
                           "XLM", "ATOM", "NEAR", "FIL", "APT", "ARB", "OP"]):
        return _CONTRACT["CRYPTO"], "crypto"
    if any(x in sym for x in ["OIL", "BRENT", "WTI"]):
        return _CONTRACT["OIL"], "commodity"
    if sym in INDEX or any(x in sym for x in ["US30", "NAS", "SPX", "DE40", "UK100"]):
        return 1, "index"
    return _CONTRACT["FOREX"], "forex"


def calcular_lote(precio, sl, capital, riesgo_pct, simbolo, tp=None):
    """
    Calcula tamano de posicion basado en riesgo.
    Devuelve lote_std (lotes estándar MT4) como campo principal.
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
    contract_size, tipo = _get_contract_size(sym)

    sl_dist = abs(precio - sl)
    if sl_dist <= 0:
        result["rejected"] = True
        result["reject_reason"] = "SL = Precio"
        return result

    # Validar SL minimo en pips
    is_jpy = sym in JPY
    pip = 0.01 if is_jpy else 0.0001
    if tipo == "metal":
        pip = 0.01  # Metales usan 0.01 como pip
    elif tipo in ("crypto", "index", "commodity"):
        pip = 0.01

    sl_pips = sl_dist / pip
    if sl_pips < 3 and tipo == "forex":
        result["rejected"] = True
        result["reject_reason"] = f"SL muy ajustado ({sl_pips:.0f} pips)"
        return result

    riesgo_usd = capital * (riesgo_pct / 100)
    result["riesgo_usd"] = round(riesgo_usd, 2)

    if tipo == "metal":
        # Metales: PnL = diff * unidades_oz
        # unidades_oz = riesgo_usd / sl_dist
        unidades = riesgo_usd / sl_dist
        lote_std = unidades / contract_size
        result["unidades"] = round(unidades, 2)
        result["lote_std"] = round(lote_std, 4)  # XAG puede dar 0.0027, no truncar a 0.00
        result["lote"] = result["unidades"]  # unidades para calculo interno

    elif tipo == "crypto":
        # Crypto: PnL = diff * unidades
        unidades = riesgo_usd / sl_dist
        result["unidades"] = round(unidades, 4)
        result["lote_std"] = result["unidades"]  # 1 lot = 1 unidad
        result["lote"] = result["unidades"]

    elif sym in _USD_BASE:
        # USD como base: pip_value = pip / precio * contract_size
        pip_value_per_lot = (pip / precio) * contract_size if precio > 0 else 0
        if pip_value_per_lot > 0 and sl_pips > 0:
            lote_std = riesgo_usd / (sl_pips * pip_value_per_lot)
        else:
            lote_std = 0
        unidades = lote_std * contract_size
        result["unidades"] = max(1, round(unidades))
        result["lote_std"] = round(lote_std, 4)
        result["lote"] = result["unidades"]

    else:
        # Forex: pip_value en USD = pip * contract_size * quote_to_usd
        quote_factor = _quote_to_usd(sym) if tipo == "forex" else 1.0
        pip_value_per_lot = pip * contract_size * quote_factor
        if pip_value_per_lot > 0 and sl_pips > 0:
            lote_std = riesgo_usd / (sl_pips * pip_value_per_lot)
        else:
            lote_std = 0
        unidades = lote_std * contract_size
        result["unidades"] = max(1, round(unidades))
        result["lote_std"] = round(lote_std, 4)
        result["lote"] = result["unidades"]

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
    elif "XAU" in sym or "XAG" in sym:
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
    """
    Calcula P&L en USD.
    lote = unidades (no lotes std). Para forex lote=100000 = 1 lot std.
    Para pares cruzados (NZDJPY, GBPJPY, etc) convierte de quote currency a USD.
    """
    sym = simbolo.upper().replace("/", "")

    if action.upper() == "BUY":
        diff = salida - entrada
    else:
        diff = entrada - salida

    if sym in _USD_BASE:
        # USD como base: PnL = diff * unidades / precio_salida
        pnl = diff * lote / salida if salida else 0
    else:
        # PnL en quote currency = diff * lote
        pnl = diff * lote
        # Convertir a USD si quote != USD
        _, tipo = _get_contract_size(sym)
        if tipo == "forex" and not sym.endswith("USD"):
            pnl *= _quote_to_usd(sym)

    return round(pnl, 2)
