# -*- coding: utf-8 -*-
"""
backtest.py - Backtest completo del sistema ParraCorp con IA

USO:
  python backtest.py --symbol EURUSD --tf 60 --days 30
  python backtest.py --symbol GBPJPY --tf 15 --days 7
  python backtest.py --symbol XAUUSD --tf 60 --days 90

Parametros:
  --symbol   Par a testear (default: EURUSD)
  --tf       Timeframe en minutos: 15, 30, 60, 240 (default: 60)
  --days     Dias de historia (default: 30)
  --no-ia    Solo modelo estadistico, sin Groq/Gemini
  --capital  Capital inicial (default: 10000)
"""
import argparse
import json
import time
import sys
import os
import pandas as pd
import numpy as np

# Agregar directorio actual al path para importar modulos del sistema
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import log as mlog
from signal_engines import evaluar_senales, _is_forex


# ══════════════════════════════════════════════════════════════════════════════
# DESCARGA DE DATOS HISTORICOS (TradingView via yfinance fallback)
# ══════════════════════════════════════════════════════════════════════════════

def download_data(symbol, tf_minutes, days):
    """Descarga datos OHLCV historicos."""
    try:
        import yfinance as yf
    except ImportError:
        print("Instalando yfinance...")
        os.system(f"{sys.executable} -m pip install yfinance -q")
        import yfinance as yf

    # Mapeo de simbolos a tickers de Yahoo Finance
    yahoo_map = {
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X",
        "USDCHF": "USDCHF=X", "AUDUSD": "AUDUSD=X", "USDCAD": "USDCAD=X",
        "NZDUSD": "NZDUSD=X", "EURJPY": "EURJPY=X", "GBPJPY": "GBPJPY=X",
        "EURGBP": "EURGBP=X", "AUDJPY": "AUDJPY=X", "CADJPY": "CADJPY=X",
        "GBPAUD": "GBPAUD=X", "GBPNZD": "GBPNZD=X", "GBPCAD": "GBPCAD=X",
        "EURNZD": "EURNZD=X", "EURAUD": "EURAUD=X", "EURCAD": "EURCAD=X",
        "XAUUSD": "GC=F", "XAGUSD": "SI=F",
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD", "SOLUSD": "SOL-USD",
        "AVAXUSD": "AVAX-USD", "LINKUSD": "LINK-USD", "DOTUSD": "DOT-USD",
        "XRPUSD": "XRP-USD", "BNBUSD": "BNB-USD", "DOGEUSD": "DOGE-USD",
        "ADAUSD": "ADA-USD", "MATICUSD": "MATIC-USD", "LTCUSD": "LTC-USD",
        "NVDA": "NVDA", "TSLA": "TSLA", "AAPL": "AAPL", "MSFT": "MSFT",
        "AMD": "AMD", "META": "META", "GOOGL": "GOOGL", "AMZN": "AMZN",
        "NAS100": "NQ=F", "US30": "YM=F", "SPX500": "ES=F",
        "USOIL": "CL=F",
    }

    ticker = yahoo_map.get(symbol.upper(), f"{symbol}=X")
    tf_map = {15: "15m", 30: "30m", 60: "1h", 240: "4h"}
    interval = tf_map.get(tf_minutes, "1h")

    # Yahoo limita: 15m/30m max 60 dias, 1h max 730 dias
    if tf_minutes <= 30 and days > 60:
        days = 60
        print(f"  Yahoo limita {interval} a 60 dias max")

    print(f"  Descargando {symbol} ({ticker}) {interval} ultimos {days} dias...")
    df = yf.download(ticker, period=f"{days}d", interval=interval, progress=False)

    if df.empty:
        print(f"  ERROR: No se encontraron datos para {symbol}")
        sys.exit(1)

    # Flatten MultiIndex columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.rename(columns={"Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
    df = df[["open", "high", "low", "close", "volume"]].dropna()
    print(f"  {len(df)} velas descargadas")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# CALCULO DE INDICADORES (replica de data_feed.py)
# ══════════════════════════════════════════════════════════════════════════════

def compute_indicators(df):
    """Calcula todos los indicadores tecnicos sobre el DataFrame (sin pandas-ta)."""
    c = df["close"]
    h = df["high"]
    l = df["low"]

    # RSI 14
    delta = c.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # Stochastic %K/%D
    low14 = l.rolling(14).min()
    high14 = h.rolling(14).max()
    raw_k = 100 * (c - low14) / (high14 - low14).replace(0, np.nan)
    df["STOCHk_14_3_3"] = raw_k.rolling(3).mean()
    df["STOCHd_14_3_3"] = df["STOCHk_14_3_3"].rolling(3).mean()

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df["MACD_12_26_9"] = ema12 - ema26
    df["MACDs_12_26_9"] = df["MACD_12_26_9"].ewm(span=9, adjust=False).mean()
    df["MACDh_12_26_9"] = df["MACD_12_26_9"] - df["MACDs_12_26_9"]

    # ADX
    plus_dm = h.diff()
    minus_dm = -l.diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0.0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0.0)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    plus_di = 100 * plus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    minus_di = 100 * minus_dm.rolling(14).mean() / atr14.replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    df["ADX_14"] = dx.rolling(14).mean()

    # Bollinger Bands
    sma20 = c.rolling(20).mean()
    std20 = c.rolling(20).std()
    df["BBU_20_2.0"] = sma20 + 2 * std20
    df["BBL_20_2.0"] = sma20 - 2 * std20

    # ATR
    df["ATRr_14"] = atr14

    # EMAs
    for span in [9, 20, 35, 50, 200]:
        df[f"EMA_{span}"] = c.ewm(span=span, adjust=False).mean()

    if "volume" in df.columns:
        df["volume_sma"] = df["volume"].rolling(20).mean()
    return df


def _safe(val, default=0):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return default
    return float(val)


def _col(df, prefix):
    for c in df.columns:
        if c.startswith(prefix):
            return c
    return None


# ══════════════════════════════════════════════════════════════════════════════
# CURRENCY STRENGTH PARA BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

# Pares de referencia para calcular fuerza de cada divisa
_CS_PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"]
_CS_DATA = {}  # {pair: DataFrame con close y EMA20}


def download_cs_data(tf_minutes, days):
    """Descarga datos de los 7 majors para calcular currency strength."""
    try:
        import yfinance as yf
    except ImportError:
        return

    tf_map = {15: "15m", 30: "30m", 60: "1h", 240: "4h"}
    interval = tf_map.get(tf_minutes, "1h")
    if tf_minutes <= 30 and days > 60:
        days = 60

    print("  Descargando datos de currency strength (7 majors)...")
    for pair in _CS_PAIRS:
        ticker = f"{pair}=X"
        try:
            df = yf.download(ticker, period=f"{days}d", interval=interval, progress=False)
            if df.empty:
                continue
            # Flatten MultiIndex if present
            if hasattr(df.columns, 'levels'):
                df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
            df.columns = [c.lower() for c in df.columns]
            df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()
            _CS_DATA[pair] = df
        except Exception:
            pass
    print(f"  Currency strength: {len(_CS_DATA)}/7 pares cargados")


def get_cs_at_index(symbol, idx):
    """
    Calcula currency strength para un simbolo en un indice temporal.
    Replica la logica de data_feed._calc_currency_strength().
    Returns: (s_base, s_quote)
    """
    if not _CS_DATA:
        return 0.0, 0.0

    sym = symbol.upper().replace("/", "")
    if len(sym) < 6:
        return 0.0, 0.0
    target_base = sym[:3]
    target_quote = sym[3:6]

    scores = {}
    counts = {}

    for pair, df in _CS_DATA.items():
        if idx >= len(df):
            continue
        row = df.iloc[idx]
        precio = row.get("close", 0)
        ema20 = row.get("ema20", 0)
        if not precio or not ema20 or pd.isna(precio) or pd.isna(ema20):
            continue

        diff = (precio - ema20) / ema20
        base = pair[:3]
        quote = pair[3:6]

        scores[base] = scores.get(base, 0.0) + diff
        counts[base] = counts.get(base, 0) + 1
        scores[quote] = scores.get(quote, 0.0) - diff  # Inverso
        counts[quote] = counts.get(quote, 0) + 1

    # Normalizar
    for c in scores:
        if counts.get(c, 0) > 0:
            scores[c] = scores[c] / counts[c]

    s_base = scores.get(target_base, 0.0)
    s_quote = scores.get(target_quote, 0.0)
    return round(s_base, 6), round(s_quote, 6)


def build_snapshot(df, idx, symbol, tf):
    """Construye el snapshot de indicadores para una vela."""
    if idx < 50:
        return None

    row = df.iloc[idx]
    precio = _safe(row.get("close"))
    if precio <= 0:
        return None

    atr_col = _col(df, "ATR")
    atr = _safe(row.get(atr_col) if atr_col else None, precio * 0.005)

    bb_upper = _safe(row.get(_col(df, "BBU_")), precio * 1.02)
    bb_lower = _safe(row.get(_col(df, "BBL_")), precio * 0.98)

    rsi = _safe(row.get(_col(df, "RSI_")), 50)
    stoch_k = _safe(row.get(_col(df, "STOCHk_")), 50)
    stoch_d = _safe(row.get(_col(df, "STOCHd_")), 50)
    macd_val = _safe(row.get(_col(df, "MACD_")))
    macd_sig = _safe(row.get(_col(df, "MACDs_")))
    macd_hist = _safe(row.get(_col(df, "MACDh_")))
    adx = _safe(row.get(_col(df, "ADX_")))
    ema9 = _safe(row.get("EMA_9"), precio)
    ema20 = _safe(row.get("EMA_20"), precio)
    ema35 = _safe(row.get("EMA_35"), precio)
    ema50 = _safe(row.get("EMA_50"), precio)
    ema200 = _safe(row.get("EMA_200"))

    bb_range = bb_upper - bb_lower
    bb_distance = (precio - (bb_lower + bb_range / 2)) / (bb_range / 2) if bb_range > 0 else 0

    squeeze = bb_range < (atr * 3.0)

    # Z-Score
    closes_arr = df["close"].values[max(0, idx-50):idx+1]
    mean50 = float(np.mean(closes_arr))
    std50 = float(np.std(closes_arr))
    zscore = (precio - mean50) / std50 if std50 > 0 else 0.0

    # Vol ratio
    if atr_col and atr_col in df.columns:
        atr_vals = df[atr_col].values[max(0, idx-20):idx+1]
        atr_vals = atr_vals[~np.isnan(atr_vals)]
        atr_media20 = float(np.mean(atr_vals)) if len(atr_vals) > 0 else atr
    else:
        atr_media20 = atr
    vol_ratio = atr / atr_media20 if atr_media20 > 0 else 1.0

    # EMA 35/50 cross
    ema35_50_cross = "NONE"
    if idx >= 1:
        prev = df.iloc[idx-1]
        prev_ema35 = _safe(prev.get("EMA_35"))
        prev_ema50 = _safe(prev.get("EMA_50"))
        if prev_ema35 and prev_ema50 and ema35 and ema50:
            if prev_ema35 <= prev_ema50 and ema35 > ema50:
                ema35_50_cross = "GOLDEN"
            elif prev_ema35 >= prev_ema50 and ema35 < ema50:
                ema35_50_cross = "DEATH"

    # Series para motores
    start = max(0, idx - 30)
    ema20_col = "EMA_20"
    ema20_serie = df[ema20_col].values[start:idx+1].tolist() if ema20_col in df.columns else []
    rsi_col = _col(df, "RSI_")
    rsi_serie = df[rsi_col].values[start:idx+1].tolist() if rsi_col and rsi_col in df.columns else []

    start60 = max(0, idx - 60)
    closes_list = df["close"].values[start60:idx+1].tolist()
    highs_list = df["high"].values[start60:idx+1].tolist()
    lows_list = df["low"].values[start60:idx+1].tolist()

    snapshot = {
        "precio": round(precio, 6),
        "open": _safe(row.get("open")),
        "high": _safe(row.get("high"), precio),
        "low": _safe(row.get("low"), precio),
        "close": round(precio, 6),
        "rsi": round(rsi, 2),
        "stoch_k": round(stoch_k, 2),
        "stoch_d": round(stoch_d, 2),
        "macd": round(macd_val, 6),
        "macd_signal": round(macd_sig, 6),
        "macd_hist": round(macd_hist, 6),
        "adx": round(adx, 2),
        "bb_upper": round(bb_upper, 6),
        "bb_lower": round(bb_lower, 6),
        "bb_width_pct": round(bb_range / precio * 100, 3) if precio > 0 else 0,
        "atr": round(atr, 6),
        "atr_pct": round(atr / precio * 100, 3) if precio > 0 else 0,
        "atr_media20": round(atr_media20, 6),
        "ema9": round(ema9, 6),
        "ema20": round(ema20, 6),
        "ema35": round(ema35, 6),
        "ema50": round(ema50, 6),
        "ema200": round(ema200, 6) if ema200 else 0,
        "ema35_50_cross": ema35_50_cross,
        "squeeze": squeeze,
        "volume": _safe(row.get("volume")),
        "volume_sma": _safe(row.get("volume_sma")),
        "supertrend": "UP" if precio > ema20 else "DOWN",
        "temporalidad": str(tf),
        "zscore_h1": round(zscore, 3),
        "bb_distance": round(bb_distance, 4),
        "vol_ratio": round(vol_ratio, 3),
        "par": symbol,
    }

    features = {
        "closes": closes_list,
        "highs": highs_list,
        "lows": lows_list,
        "ema20_serie": [x for x in ema20_serie if not np.isnan(x)],
        "rsi_serie": [x for x in rsi_serie if not np.isnan(x)],
        "rsi": rsi,
        "zscore_h1": zscore,
        "bb_distance": bb_distance,
        "vol_ratio": vol_ratio,
        "squeeze": squeeze,
        "adx": adx,
        "ema50": ema50,
        "par": symbol,
        "currency_strength_base": 0,
        "currency_strength_quote": 0,
        "triangular_error": 0,
    }

    # Currency strength (si hay datos descargados)
    if _CS_DATA:
        cs_base, cs_quote = get_cs_at_index(symbol, idx)
        features["currency_strength_base"] = cs_base
        features["currency_strength_quote"] = cs_quote
        snapshot["currency_spread"] = round(cs_base - cs_quote, 6)

    return snapshot, features


# ══════════════════════════════════════════════════════════════════════════════
# REGIMEN DETECTOR (simplificado)
# ══════════════════════════════════════════════════════════════════════════════

def detect_regimen(adx, vol_ratio, ema20=0, ema50=0):
    """Replica regime_detector.py detectar_regimen (produccion)."""
    t_fuerte = adx > 30
    t_debil = adx < 20
    alta_vol = vol_ratio > 1.5
    baja_vol = vol_ratio < 0.7
    sin_dir = abs(ema20 - ema50) / ema50 < 0.001 if ema50 else False

    if t_fuerte and alta_vol:
        return "TRENDING_VOLATILE"
    elif t_fuerte and not alta_vol:
        return "TRENDING_CALM"
    elif t_debil and baja_vol:
        return "RANGING"
    elif alta_vol and t_debil:
        return "CHOPPY"
    elif t_debil and sin_dir:
        return "RANGING"
    return "NORMAL"


# ══════════════════════════════════════════════════════════════════════════════
# BRAIN IA (importa del sistema real)
# ══════════════════════════════════════════════════════════════════════════════

def call_brain_ia(symbol, snapshot, engines_result, regimen, use_ia=True):
    """Llama al pipeline REAL de brain.py (mismo que produccion)."""
    from brain import analyze
    import brain

    direction = engines_result.get("direccion", "NEUTRAL")
    if direction == "NEUTRAL":
        return {"action": "WAIT", "confidence": 0}

    context = {
        "signals_active": [],
        "session": {"name": "Backtest", "quality": 5, "minutes_to_close": 999},
        "session_quality": 5,
        "session_fit": {"fit": "GOOD"},
        "bank_holiday": {},
        "high_impact_event": {},
    }
    regimen_info = {"regimen": regimen, "riesgo_pct": 1.0}
    mtf_info = {}
    of_info = {"delta": 0, "imbalance": 0}
    sr_info = {"sr_niveles": []}

    # Desactivar rate limit para backtest
    brain._last_call_ts = 0

    if not use_ia:
        # Modo estadistico puro: usar directamente la senal de los motores
        from brain import _sl_tp_por_activo
        tqs = engines_result.get("trade_quality_score", 0)
        if tqs < 0.65:
            return {"action": "WAIT", "confidence": int(tqs * 100)}
        precio = snapshot.get("precio", 0)
        atr = snapshot.get("atr", 0)
        if precio == 0 or atr == 0:
            return {"action": "WAIT", "confidence": 0}
        vol_ratio = snapshot.get("vol_ratio", 1.0)
        sl_atr, tp_atr = _sl_tp_por_activo(symbol, vol_ratio)
        if direction == "BUY":
            sl = precio - atr * sl_atr
            tp = precio + atr * tp_atr
        else:
            sl = precio + atr * sl_atr
            tp = precio - atr * tp_atr
        return {
            "action": direction,
            "confidence": int(tqs * 100),
            "sl": sl, "tp": tp,
            "risk_pct": 1.0,
            "trailing_stop": "atr" if tp_atr >= 2.0 else "none",
            "votos": {"stats": direction},
        }
    else:
        result = analyze(symbol, snapshot, engines_result, context, regimen_info, mtf_info, of_info, sr_info)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# SPREADS REALISTAS (ICMarkets / VTMarkets ECN, promedio en pip)
# ══════════════════════════════════════════════════════════════════════════════

# Spread en unidades de precio (no pips). Ajustado por tipo de par.
def get_spread(symbol):
    """Retorna spread medio en unidades de precio para el simbolo."""
    sym = symbol.upper().replace("/", "")

    # Forex majors (spread en pips -> convertir)
    spreads_pips = {
        # Majors: 0.1-0.3 pips ECN
        "EURUSD": 0.2, "GBPUSD": 0.3, "USDJPY": 0.2, "USDCHF": 0.3,
        "AUDUSD": 0.3, "USDCAD": 0.4, "NZDUSD": 0.4,
        # Crosses: 0.5-1.5 pips
        "EURJPY": 0.5, "GBPJPY": 0.8, "EURGBP": 0.3, "AUDJPY": 0.6,
        "CADJPY": 0.6, "GBPAUD": 1.2, "GBPNZD": 1.5, "GBPCAD": 1.2,
        "EURNZD": 1.2, "EURAUD": 1.0, "EURCAD": 0.8, "AUDNZD": 1.0,
        # Metales
        "XAUUSD": 1.5, "XAGUSD": 2.0,  # en centavos de USD
        # Indices
        "NAS100": 1.0, "US30": 1.5, "SPX500": 0.4, "US500": 0.4,
    }

    pip_spread = spreads_pips.get(sym, None)
    if pip_spread is not None:
        # Convertir pips a precio
        if "JPY" in sym:
            return pip_spread * 0.01  # 1 pip = 0.01
        elif "XAU" in sym:
            return pip_spread * 0.1   # spread de oro: 1.5 pips = $0.15
        elif "XAG" in sym:
            return pip_spread * 0.001
        elif any(x in sym for x in ["US30", "NAS", "SPX", "US500"]):
            return pip_spread * 1.0   # indices: ya en puntos
        else:
            return pip_spread * 0.0001  # forex standard

    # Crypto: spread como % del precio (ICMarkets crypto CFD)
    crypto_pct = {
        "BTCUSD": 0.04, "ETHUSD": 0.06, "SOLUSD": 0.10, "AVAXUSD": 0.12,
        "XRPUSD": 0.10, "BNBUSD": 0.10, "DOGEUSD": 0.15, "ADAUSD": 0.12,
        "LINKUSD": 0.10, "DOTUSD": 0.12, "MATICUSD": 0.15, "LTCUSD": 0.08,
    }
    pct = crypto_pct.get(sym, 0.10)  # default 0.10% para crypto desconocida
    return 0  # se calcula dinamicamente en simulate_trade

_CRYPTO_SPREAD_PCT = {
    "BTCUSD": 0.0004, "ETHUSD": 0.0006, "SOLUSD": 0.0010, "AVAXUSD": 0.0012,
    "XRPUSD": 0.0010, "BNBUSD": 0.0010, "DOGEUSD": 0.0015, "ADAUSD": 0.0012,
    "LINKUSD": 0.0010, "DOTUSD": 0.0012, "MATICUSD": 0.0015, "LTCUSD": 0.0008,
}


def get_spread_at_price(symbol, price):
    """Spread en unidades de precio. Para crypto usa % del precio actual."""
    sym = symbol.upper().replace("/", "")
    fixed = get_spread(sym)
    if fixed > 0:
        return fixed
    # Crypto: porcentaje del precio
    pct = _CRYPTO_SPREAD_PCT.get(sym, 0.0010)
    return price * pct


# ══════════════════════════════════════════════════════════════════════════════
# SIMULACION DE TRADES
# ══════════════════════════════════════════════════════════════════════════════

def simulate_trade(df, entry_idx, action, entry_price, sl, tp, trailing, atr, be_pct=0.5):
    """Simula un trade barra a barra hasta SL, TP o fin de datos.
    be_pct: porcentaje del TP para activar breakeven (0.5 = 50%, 0.4 = 40%)
    """
    for i in range(entry_idx + 1, len(df)):
        high = df.iloc[i]["high"]
        low = df.iloc[i]["low"]
        close = df.iloc[i]["close"]
        cur_atr = atr  # simplificado

        if action == "BUY":
            # Check SL
            if low <= sl:
                pnl = sl - entry_price
                status = "HIT_SL"
                if trailing != "none" and sl >= entry_price:
                    status = "TRAILING_CLOSE"
                return i, sl, pnl, status

            # Check TP
            if high >= tp:
                pnl = tp - entry_price
                return i, tp, pnl, "HIT_TP"

            # Trailing
            if trailing == "breakeven":
                trigger = entry_price + (tp - entry_price) * be_pct
                if close >= trigger:
                    sl = max(sl, entry_price)
            elif trailing == "atr1":
                new_sl = close - cur_atr
                sl = max(sl, new_sl)
            elif trailing == "atr2":
                new_sl = close - cur_atr * 0.5
                sl = max(sl, new_sl)

        else:  # SELL
            # Check SL
            if high >= sl:
                pnl = entry_price - sl
                status = "HIT_SL"
                if trailing != "none" and sl <= entry_price:
                    status = "TRAILING_CLOSE"
                return i, sl, pnl, status

            # Check TP
            if low <= tp:
                pnl = entry_price - tp
                return i, tp, pnl, "HIT_TP"

            # Trailing
            if trailing == "breakeven":
                trigger = entry_price - (entry_price - tp) * be_pct
                if close <= trigger:
                    sl = min(sl, entry_price)
            elif trailing == "atr1":
                new_sl = close + cur_atr
                sl = min(sl, new_sl)
            elif trailing == "atr2":
                new_sl = close + cur_atr * 0.5
                sl = min(sl, new_sl)

    # Si no se cerro, cerrar en la ultima barra
    last_close = df.iloc[-1]["close"]
    if action == "BUY":
        pnl = last_close - entry_price
    else:
        pnl = entry_price - last_close
    return len(df) - 1, last_close, pnl, "OPEN"


# ══════════════════════════════════════════════════════════════════════════════
# BACKTEST PRINCIPAL
# ══════════════════════════════════════════════════════════════════════════════

def run_backtest(symbol, tf, days, use_ia, capital):
    capital_inicial = capital
    spread_sample = get_spread_at_price(symbol, 1000)  # se recalcula por trade
    print(f"\n{'='*60}")
    print(f"  PARRACORP BACKTEST")
    print(f"  {symbol} | {tf}m | {days} dias | IA: {'SI' if use_ia else 'NO'}")
    print(f"  Capital: ${capital:,.0f} (compounding activo)")
    print(f"  Spread: ICMarkets/VTMarkets ECN (realista)")
    print(f"{'='*60}\n")

    # 1. Descargar datos
    df = download_data(symbol, tf, days)

    # 1b. Descargar datos de currency strength (para forex)
    from signal_engines import _is_forex
    if _is_forex(symbol):
        download_cs_data(tf, days)

    # 2. Calcular indicadores
    print("  Calculando indicadores...")
    df = compute_indicators(df)

    # 3. Iterar vela a vela
    trades = []
    active_trade = None
    total_ia_calls = 0
    total_tqs_pass = 0
    total_velas = 0

    print(f"  Analizando {len(df) - 50} velas...\n")

    for idx in range(50, len(df)):
        total_velas += 1

        # Skip si hay trade activo
        if active_trade is not None:
            if idx >= active_trade:
                active_trade = None
            else:
                continue

        # Filtro de sesion inteligente: cada par opera en sus sesiones optimas
        row_time = df.index[idx]
        hour_utc = row_time.hour if hasattr(row_time, 'hour') else 12
        sym_upper = symbol.upper().replace("/", "")

        # JPY pairs: Tokyo(00-09) + London(07-16) + NY(13-22) = 00-22
        if "JPY" in sym_upper:
            if hour_utc >= 22:  # Solo bloquear 22-00
                continue
        # AUD/NZD pairs: Sydney(22-07) + Tokyo(00-09) + London + NY = casi 24h, bloquear 17-22
        elif any(x in sym_upper for x in ("AUD", "NZD")) and "USD" in sym_upper:
            if 17 <= hour_utc < 22:  # Baja actividad tarde NY
                continue
        # Metales: London(07-16) + NY(13-22), bloquear 22-07
        elif any(x in sym_upper for x in ("XAU", "XAG", "XPT", "XPD")):
            if hour_utc >= 22 or hour_utc < 7:
                continue
        # Crypto: mejores horas 07-22 (Europa+US), bloquear madrugada
        elif sym_upper in ("BTCUSD","ETHUSD","SOLUSD","AVAXUSD","XRPUSD","BNBUSD",
                           "DOGEUSD","ADAUSD","LINKUSD","DOTUSD","MATICUSD","LTCUSD",
                           "BTCUSDT","ETHUSDT","SOLUSDT","AVAXUSDT","XRPUSDT","BNBUSDT",
                           "DOGEUSDT","ADAUSDT","LINKUSDT","DOTUSDT","MATICUSDT"):
            if hour_utc >= 22 or hour_utc < 7:
                continue
        # EUR/GBP/CHF/CAD: London(07-16) + NY(13-22), bloquear 22-07
        else:
            if hour_utc >= 22 or hour_utc < 7:
                continue

        snapshot, features = build_snapshot(df, idx, symbol, tf)
        if snapshot is None:
            continue

        # Regimen (con EMA20/50 para detectar sin_dir)
        regimen = detect_regimen(snapshot["adx"], snapshot["vol_ratio"], snapshot.get("ema20", 0), snapshot.get("ema50", 0))

        # Motores
        engines = evaluar_senales(features, regimen)

        tqs = engines.get("trade_quality_score", 0)
        if not engines.get("pasa_umbral", False):
            continue

        total_tqs_pass += 1

        # Inyectar hora de la vela para que brain.safety_filter use la hora correcta
        snapshot["_hour_utc"] = hour_utc

        # Brain (con o sin IA)
        try:
            result = call_brain_ia(symbol, snapshot, engines, regimen, use_ia)
            if use_ia:
                total_ia_calls += 1
                time.sleep(1.5)  # Rate limit APIs
        except Exception as e:
            print(f"  [!] Error brain en vela {idx}: {e}")
            continue

        action = result.get("action", "WAIT")
        if action not in ("BUY", "SELL"):
            continue

        # Ejecutar trade
        sl = result.get("sl", 0)
        tp = result.get("tp", 0)
        trailing = result.get("trailing_stop", "none")
        entry = snapshot["precio"]
        atr = snapshot["atr"]

        if sl == 0 or tp == 0:
            continue

        # Aplicar spread: BUY entra al ask (precio + spread/2), SELL al bid (precio - spread/2)
        spread = get_spread_at_price(symbol, entry)
        half_spread = spread / 2
        if action == "BUY":
            entry += half_spread   # peor entrada para BUY
            tp += half_spread      # TP tambien se desplaza
            sl += half_spread      # SL tambien
        else:
            entry -= half_spread   # peor entrada para SELL
            tp -= half_spread
            sl -= half_spread

        exit_idx, exit_price, pnl, status = simulate_trade(df, idx, action, entry, sl, tp, trailing, atr)

        # Calcular PnL en USD (simplificado)
        if "JPY" in symbol:
            pnl_pips = pnl * 100
        elif "XAU" in symbol:
            pnl_pips = pnl * 10
        else:
            pnl_pips = pnl * 10000

        risk_usd = capital * (result.get("risk_pct", 1.0) / 100)
        sl_dist = abs(entry - sl)
        pnl_usd = (pnl / sl_dist * risk_usd) if sl_dist > 0 else 0

        capital_before = capital
        capital += pnl_usd

        # Coste spread en USD para este trade
        spread_cost_usd = (spread / sl_dist * risk_usd) if sl_dist > 0 else 0

        trade = {
            "n": len(trades) + 1,
            "entry_time": str(df.index[idx]),
            "exit_time": str(df.index[exit_idx]),
            "action": action,
            "entry": round(entry, 5),
            "exit": round(exit_price, 5),
            "sl": round(sl, 5),
            "tp": round(tp, 5),
            "trailing": trailing,
            "pnl_pips": round(pnl_pips, 1),
            "pnl_usd": round(pnl_usd, 2),
            "spread_cost": round(spread_cost_usd, 2),
            "status": status,
            "tqs": round(tqs, 3),
            "regimen": regimen,
            "consensus": result.get("consensus", "?"),
            "confidence": result.get("confidence", 0),
            "bars": exit_idx - idx,
            "capital_before": round(capital_before, 2),
            "capital_after": round(capital, 2),
            "risk_usd": round(risk_usd, 2),
        }
        trades.append(trade)

        # Marcar barras ocupadas (no operar hasta que cierre este trade)
        active_trade = exit_idx

        # Print trade con capital
        color = "\033[92m" if pnl_usd > 0 else "\033[91m"
        reset = "\033[0m"
        trail_label = f" [{trailing}]" if trailing != "none" else ""
        print(f"  {color}#{trade['n']:3d} {action:4s} {trade['entry_time'][:16]} -> {trade['exit_time'][:16]} "
              f"| {status:14s} | {pnl_pips:+7.1f} pips | {pnl_usd:+8.2f} USD "
              f"| Capital: ${capital:,.2f} | Riesgo: ${risk_usd:.2f}{trail_label}{reset}")

    # Reset active_trade for proper counting
    # Recalculate skipped bars
    print(f"\n{'='*60}")
    print(f"  RESULTADOS")
    print(f"{'='*60}")

    if not trades:
        print("  No se generaron trades.")
        return

    wins = [t for t in trades if t["pnl_usd"] > 0]
    losses = [t for t in trades if t["pnl_usd"] <= 0]
    total_pnl = sum(t["pnl_usd"] for t in trades)
    total_pips = sum(t["pnl_pips"] for t in trades)
    wr = len(wins) / len(trades) * 100 if trades else 0
    avg_win = sum(t["pnl_usd"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_usd"] for t in losses) / len(losses) if losses else 0
    pf = abs(sum(t["pnl_usd"] for t in wins) / sum(t["pnl_usd"] for t in losses)) if losses and sum(t["pnl_usd"] for t in losses) != 0 else 999

    # Max drawdown
    equity = []
    eq = 0
    for t in trades:
        eq += t["pnl_usd"]
        equity.append(eq)
    peak = 0
    max_dd = 0
    for e in equity:
        peak = max(peak, e)
        dd = peak - e
        max_dd = max(max_dd, dd)

    # Trades por status
    tp_count = len([t for t in trades if t["status"] == "HIT_TP"])
    sl_count = len([t for t in trades if t["status"] == "HIT_SL"])
    trail_count = len([t for t in trades if t["status"] == "TRAILING_CLOSE"])
    be_count = len([t for t in trades if t["status"] == "TRAILING_CLOSE" and t.get("trailing") == "breakeven"])

    print(f"")
    print(f"  Velas analizadas:    {total_velas}")
    print(f"  Pasan TQS:           {total_tqs_pass} ({total_tqs_pass/total_velas*100:.1f}%)")
    print(f"  Llamadas IA:         {total_ia_calls}")
    print(f"  Total trades:        {len(trades)}")
    print(f"  Wins / Losses:       {len(wins)}W / {len(losses)}L")
    print(f"  Win Rate:            {wr:.1f}%")
    print(f"  Profit Factor:       {pf:.2f}")
    print(f"")
    total_spread = sum(t.get("spread_cost", 0) for t in trades)
    print(f"  PnL Total:           {total_pnl:+.2f} USD ({total_pips:+.1f} pips)")
    print(f"  Spread total:        -{total_spread:.2f} USD (incluido en PnL)")
    print(f"  Avg Win:             {avg_win:+.2f} USD")
    print(f"  Avg Loss:            {avg_loss:+.2f} USD")
    print(f"  Max Drawdown:        {max_dd:.2f} USD")
    print(f"")
    trailing_counts = {}
    for t in trades:
        tr = t.get("trailing", "none")
        trailing_counts[tr] = trailing_counts.get(tr, 0) + 1

    print(f"  Por tipo de cierre:")
    print(f"    TP:                {tp_count}")
    print(f"    SL:                {sl_count}")
    print(f"    Trailing:          {trail_count}")
    print(f"  Trailing usado:")
    for tr_type, tr_cnt in sorted(trailing_counts.items()):
        print(f"    {tr_type:18s} {tr_cnt} trades")
    print(f"")
    print(f"  Capital inicial:     ${capital_inicial:,.2f}")
    print(f"  Capital final:       ${capital:,.2f}")
    print(f"  Rentabilidad:        {((capital - capital_inicial) / capital_inicial) * 100:+.2f}%")
    print(f"")

    # ══════════════════════════════════════════════════════════════════
    # DESGLOSE POR DIA DE LA SEMANA
    # ══════════════════════════════════════════════════════════════════
    print(f"  {'='*60}")
    print(f"  RENDIMIENTO POR DIA DE LA SEMANA")
    print(f"  {'='*60}")
    day_names = ["Lun", "Mar", "Mie", "Jue", "Vie", "Sab", "Dom"]
    day_stats = {}
    for t in trades:
        try:
            dt = pd.Timestamp(t["entry_time"])
            day = dt.dayofweek  # 0=Lun, 6=Dom
        except Exception:
            continue
        if day not in day_stats:
            day_stats[day] = {"trades": 0, "wins": 0, "pnl": 0.0, "pips": 0.0}
        day_stats[day]["trades"] += 1
        if t["pnl_usd"] > 0:
            day_stats[day]["wins"] += 1
        day_stats[day]["pnl"] += t["pnl_usd"]
        day_stats[day]["pips"] += t["pnl_pips"]

    print(f"  {'Dia':5} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'PnL USD':>10} {'PnL Pips':>10} {'Avg USD':>9}")
    print(f"  {'-'*60}")
    for d in sorted(day_stats.keys()):
        s = day_stats[d]
        wr_d = s["wins"] / s["trades"] * 100 if s["trades"] > 0 else 0
        avg_d = s["pnl"] / s["trades"] if s["trades"] > 0 else 0
        color = "\033[92m" if s["pnl"] > 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  {color}{day_names[d]:5} {s['trades']:7d} {s['wins']:6d} {wr_d:6.1f}% {s['pnl']:+10.2f} {s['pips']:+10.1f} {avg_d:+9.2f}{reset}")

    # Mejor y peor dia
    if day_stats:
        best_day = max(day_stats.items(), key=lambda x: x[1]["pnl"])
        worst_day = min(day_stats.items(), key=lambda x: x[1]["pnl"])
        print(f"\n  \033[92m★ Mejor dia:  {day_names[best_day[0]]} ({best_day[1]['pnl']:+.2f} USD, WR {best_day[1]['wins']/best_day[1]['trades']*100:.0f}%)\033[0m")
        print(f"  \033[91m✗ Peor dia:   {day_names[worst_day[0]]} ({worst_day[1]['pnl']:+.2f} USD, WR {worst_day[1]['wins']/worst_day[1]['trades']*100:.0f}%)\033[0m")
    print()

    # ══════════════════════════════════════════════════════════════════
    # DESGLOSE POR HORA DE ENTRADA (UTC)
    # ══════════════════════════════════════════════════════════════════
    print(f"  {'='*60}")
    print(f"  RENDIMIENTO POR HORA (UTC)")
    print(f"  {'='*60}")
    hour_stats = {}
    for t in trades:
        try:
            dt = pd.Timestamp(t["entry_time"])
            h = dt.hour
        except Exception:
            continue
        if h not in hour_stats:
            hour_stats[h] = {"trades": 0, "wins": 0, "pnl": 0.0}
        hour_stats[h]["trades"] += 1
        if t["pnl_usd"] > 0:
            hour_stats[h]["wins"] += 1
        hour_stats[h]["pnl"] += t["pnl_usd"]

    print(f"  {'Hora':>6} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'PnL USD':>10} {'Avg USD':>9}  {'':1}")
    print(f"  {'-'*55}")
    for h in sorted(hour_stats.keys()):
        s = hour_stats[h]
        wr_h = s["wins"] / s["trades"] * 100 if s["trades"] > 0 else 0
        avg_h = s["pnl"] / s["trades"] if s["trades"] > 0 else 0
        bar_len = int(abs(s["pnl"]) / max(abs(s["pnl"]) for s in hour_stats.values()) * 15) if hour_stats else 0
        bar = ("█" * bar_len) if s["pnl"] > 0 else ("░" * bar_len)
        color = "\033[92m" if s["pnl"] > 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  {color}{h:02d}:00 {s['trades']:7d} {s['wins']:6d} {wr_h:6.1f}% {s['pnl']:+10.2f} {avg_h:+9.2f}  {bar}{reset}")

    # Mejor y peor hora
    if hour_stats:
        best_hour = max(hour_stats.items(), key=lambda x: x[1]["pnl"])
        worst_hour = min(hour_stats.items(), key=lambda x: x[1]["pnl"])
        print(f"\n  \033[92m★ Mejor hora: {best_hour[0]:02d}:00 UTC ({best_hour[1]['pnl']:+.2f} USD, {best_hour[1]['trades']} trades)\033[0m")
        print(f"  \033[91m✗ Peor hora:  {worst_hour[0]:02d}:00 UTC ({worst_hour[1]['pnl']:+.2f} USD, {worst_hour[1]['trades']} trades)\033[0m")
    print()

    # ══════════════════════════════════════════════════════════════════
    # DESGLOSE POR REGIMEN
    # ══════════════════════════════════════════════════════════════════
    print(f"  {'='*60}")
    print(f"  RENDIMIENTO POR REGIMEN")
    print(f"  {'='*60}")
    reg_stats = {}
    for t in trades:
        reg = t.get("regimen", "NORMAL")
        if reg not in reg_stats:
            reg_stats[reg] = {"trades": 0, "wins": 0, "pnl": 0.0}
        reg_stats[reg]["trades"] += 1
        if t["pnl_usd"] > 0:
            reg_stats[reg]["wins"] += 1
        reg_stats[reg]["pnl"] += t["pnl_usd"]

    print(f"  {'Regimen':20} {'Trades':>7} {'Wins':>6} {'WR%':>7} {'PnL USD':>10} {'Avg USD':>9}")
    print(f"  {'-'*60}")
    for reg in sorted(reg_stats.keys(), key=lambda x: reg_stats[x]["pnl"], reverse=True):
        s = reg_stats[reg]
        wr_r = s["wins"] / s["trades"] * 100 if s["trades"] > 0 else 0
        avg_r = s["pnl"] / s["trades"] if s["trades"] > 0 else 0
        color = "\033[92m" if s["pnl"] > 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  {color}{reg:20} {s['trades']:7d} {s['wins']:6d} {wr_r:6.1f}% {s['pnl']:+10.2f} {avg_r:+9.2f}{reset}")
    print()

    # Trades detallados
    print(f"  {'='*60}")
    print(f"  DETALLE DE TRADES")
    print(f"  {'='*60}")
    print(f"  {'#':>3} {'Dir':4} {'Entrada':>10} {'Salida':>10} {'Pips':>8} {'USD':>9} {'Status':14} {'Capital':>10} {'Riesgo':>8}")
    print(f"  {'-'*90}")
    for t in trades:
        color = "\033[92m" if t["pnl_usd"] > 0 else "\033[91m"
        reset = "\033[0m"
        print(f"  {color}{t['n']:3d} {t['action']:4s} {t['entry']:10.5f} {t['exit']:10.5f} "
              f"{t['pnl_pips']:+8.1f} {t['pnl_usd']:+9.2f} {t['status']:14s} "
              f"${t['capital_after']:>8,.2f} ${t['risk_usd']:>7.2f}{reset}")

    print(f"\n  Backtest completado.")


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ParraCorp Backtest")
    parser.add_argument("--symbol", default="EURUSD", help="Par/simbolo (default: EURUSD)")
    parser.add_argument("--tf", type=int, default=60, help="Timeframe en minutos: 15, 30, 60, 240 (default: 60)")
    parser.add_argument("--days", type=int, default=30, help="Dias de historia (default: 30)")
    parser.add_argument("--no-ia", action="store_true", help="Solo modelo estadistico, sin IA")
    parser.add_argument("--capital", type=float, default=10000, help="Capital inicial (default: 10000)")
    args = parser.parse_args()

    run_backtest(args.symbol, args.tf, args.days, not args.no_ia, args.capital)
