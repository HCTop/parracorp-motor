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

from config import tipo_activo, log as mlog
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
        "BTCUSD": "BTC-USD", "ETHUSD": "ETH-USD",
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
        "par": symbol,
        "currency_strength_base": 0,
        "currency_strength_quote": 0,
        "triangular_error": 0,
    }

    return snapshot, features


# ══════════════════════════════════════════════════════════════════════════════
# REGIMEN DETECTOR (simplificado)
# ══════════════════════════════════════════════════════════════════════════════

def detect_regimen(adx, vol_ratio):
    if adx > 25 and vol_ratio > 1.3:
        return "TRENDING_VOLATILE"
    elif adx > 25:
        return "TRENDING_CALM"
    elif adx < 18 and vol_ratio < 0.8:
        return "RANGING"
    elif adx < 15 and vol_ratio < 0.7:
        return "CHOPPY"
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
        "session": {"name": "London_NY", "quality": 8, "minutes_to_close": 999},
        "session_quality": 8,
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
        # Forzar solo estadistico (sin gastar tokens)
        import config as cfg
        old_modo = cfg.state.get("ia_modo", "autonomo")
        cfg.state["ia_modo"] = "off"
        result = analyze(symbol, snapshot, engines_result, context, regimen_info, mtf_info, of_info, sr_info)
        cfg.state["ia_modo"] = old_modo
    else:
        result = analyze(symbol, snapshot, engines_result, context, regimen_info, mtf_info, of_info, sr_info)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# SIMULACION DE TRADES
# ══════════════════════════════════════════════════════════════════════════════

def simulate_trade(df, entry_idx, action, entry_price, sl, tp, trailing, atr):
    """Simula un trade barra a barra hasta SL, TP o fin de datos."""
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
                half_tp = entry_price + (tp - entry_price) * 0.5
                if close >= half_tp:
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
                half_tp = entry_price - (entry_price - tp) * 0.5
                if close <= half_tp:
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
    print(f"\n{'='*60}")
    print(f"  PARRACORP BACKTEST")
    print(f"  {symbol} | {tf}m | {days} dias | IA: {'SI' if use_ia else 'NO'}")
    print(f"  Capital: ${capital:,.0f} (compounding activo)")
    print(f"{'='*60}\n")

    # 1. Descargar datos
    df = download_data(symbol, tf, days)

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

        snapshot, features = build_snapshot(df, idx, symbol, tf)
        if snapshot is None:
            continue

        # Regimen
        regimen = detect_regimen(snapshot["adx"], snapshot["vol_ratio"])

        # Motores
        engines = evaluar_senales(features, regimen)

        tqs = engines.get("trade_quality_score", 0)
        if not engines.get("pasa_umbral", False):
            continue

        total_tqs_pass += 1

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
        print(f"  {color}#{trade['n']:3d} {action:4s} {trade['entry_time'][:16]} -> {trade['exit_time'][:16]} "
              f"| {status:14s} | {pnl_pips:+7.1f} pips | {pnl_usd:+8.2f} USD "
              f"| Capital: ${capital:,.2f} | Riesgo: ${risk_usd:.2f}{reset}")

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

    print(f"")
    print(f"  Velas analizadas:    {total_velas}")
    print(f"  Pasan TQS:           {total_tqs_pass} ({total_tqs_pass/total_velas*100:.1f}%)")
    print(f"  Llamadas IA:         {total_ia_calls}")
    print(f"  Total trades:        {len(trades)}")
    print(f"  Wins / Losses:       {len(wins)}W / {len(losses)}L")
    print(f"  Win Rate:            {wr:.1f}%")
    print(f"  Profit Factor:       {pf:.2f}")
    print(f"")
    print(f"  PnL Total:           {total_pnl:+.2f} USD ({total_pips:+.1f} pips)")
    print(f"  Avg Win:             {avg_win:+.2f} USD")
    print(f"  Avg Loss:            {avg_loss:+.2f} USD")
    print(f"  Max Drawdown:        {max_dd:.2f} USD")
    print(f"")
    print(f"  Por tipo de cierre:")
    print(f"    TP:                {tp_count}")
    print(f"    SL:                {sl_count}")
    print(f"    Trailing:          {trail_count}")
    print(f"")
    print(f"  Capital inicial:     ${capital_inicial:,.2f}")
    print(f"  Capital final:       ${capital:,.2f}")
    print(f"  Rentabilidad:        {((capital - capital_inicial) / capital_inicial) * 100:+.2f}%")
    print(f"")

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
