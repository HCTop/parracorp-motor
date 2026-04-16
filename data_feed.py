# -*- coding: utf-8 -*-
"""
data_feed.py - Real-time TradingView WebSocket Streaming

Conexion WebSocket directa a TradingView (wss://data.tradingview.com).
Recibe barras OHLCV en tiempo real + quotes tick-by-tick.
Indicadores calculados localmente con pandas-ta.
Dispara callback en cada cierre de vela para analisis inmediato.
"""
import json
import re
import time
import random
import string
import threading
import pandas as pd
import numpy as np
from websocket import create_connection, WebSocketConnectionClosedException

from config import tipo_activo, detectar_exchange, log as mlog

# ── Constants ────────────────────────────────────────────────────────────────
_TV_WS_URL = "wss://data.tradingview.com/socket.io/websocket"
_TV_ORIGIN = "https://data.tradingview.com"
HIGHER_TF = {"1": "5", "5": "15", "15": "60", "30": "60", "60": "240", "240": "1D"}
TV_TF = {"1": "1", "5": "5", "15": "15", "30": "30", "60": "60", "240": "240", "1D": "1D", "D": "1D"}
COMPUTE_THROTTLE = 3  # seconds between full indicator recompute

# Supertrend direction state per (symbol, tf)
_st_prev_dir = {}  # {(symbol, tf): "UP" | "DOWN"}


# ── Protocol helpers ─────────────────────────────────────────────────────────
def _pack(msg):
    return f"~m~{len(msg)}~m~{msg}"

def _build(func, args):
    return json.dumps({"m": func, "p": args}, separators=(',', ':'))

def _parse_raw(raw):
    msgs, i = [], 0
    while i < len(raw):
        m = re.match(r'~m~(\d+)~m~', raw[i:])
        if not m:
            break
        ln = int(m.group(1))
        start = i + m.end()
        msgs.append(raw[start:start + ln])
        i = start + ln
    return msgs

def _gen_id(prefix):
    return prefix + ''.join(random.choices(string.ascii_lowercase, k=12))

def _safe(val, default=0):
    if val is None:
        return default
    try:
        v = float(val)
        return default if v != v else v  # NaN check
    except (TypeError, ValueError):
        return default

def _col(df, prefix):
    for c in df.columns:
        if c.startswith(prefix):
            return c
    return None

def _ema_simple(values, period):
    if len(values) < period:
        return values[-1] if values else 0
    mult = 2 / (period + 1)
    ema = sum(values[:period]) / period
    for v in values[period:]:
        ema = (v - ema) * mult + ema
    return ema


# ── Candle pattern detectors (simple, no TA-Lib needed) ──────────────────
def _detect_doji(df):
    """Doji: body < 10% of range."""
    body = abs(df["close"] - df["open"])
    rng = df["high"] - df["low"]
    return ((body < rng * 0.1) & (rng > 0)).astype(int)

def _detect_engulfing(df):
    """Bullish engulfing = +1, Bearish engulfing = -1."""
    result = pd.Series(0, index=df.index)
    if len(df) < 2:
        return result
    prev_o, prev_c = df["open"].shift(1), df["close"].shift(1)
    cur_o, cur_c = df["open"], df["close"]
    bullish = (prev_c < prev_o) & (cur_c > cur_o) & (cur_c > prev_o) & (cur_o < prev_c)
    bearish = (prev_c > prev_o) & (cur_c < cur_o) & (cur_c < prev_o) & (cur_o > prev_c)
    result[bullish] = 1
    result[bearish] = -1
    return result

def _detect_hammer(df):
    """Hammer: small body at top, long lower wick."""
    body = abs(df["close"] - df["open"])
    rng = df["high"] - df["low"]
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    return ((lower_wick > body * 2) & (upper_wick < body * 0.5) & (rng > 0)).astype(int)

def _detect_shooting_star(df):
    """Shooting star: small body at bottom, long upper wick."""
    body = abs(df["close"] - df["open"])
    rng = df["high"] - df["low"]
    upper_wick = df["high"] - df[["open", "close"]].max(axis=1)
    lower_wick = df[["open", "close"]].min(axis=1) - df["low"]
    return ((upper_wick > body * 2) & (lower_wick < body * 0.5) & (rng > 0)).astype(int)


# ── TVStream class ───────────────────────────────────────────────────────────
class TVStream:
    def __init__(self):
        self.ws = None
        self._running = False
        self._desired_pairs = []
        self._on_bar_close = None
        self._thread = None

        # Sessions
        self._chart_session = None
        self._quote_session = None

        # Series tracking
        self._counter = 0
        self._series_map = {}     # ser_id -> (symbol, tf)

        # Data stores (protected by _lock)
        self._lock = threading.Lock()
        self._bars = {}           # (symbol, tf) -> [[ts, o, h, l, c, v], ...]
        self._snapshots = {}      # (symbol, tf) -> snapshot dict
        self._prices = {}         # symbol -> float
        self._last_bar_ts = {}    # (symbol, tf) -> last bar timestamp
        self._last_compute = {}   # (symbol, tf) -> last indicator compute time

        # Callback dedup
        self._analyzing = set()
        self._analyzing_lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────────
    def start(self, pairs, on_bar_close=None):
        self._desired_pairs = list(pairs)
        self._on_bar_close = on_bar_close
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        mlog("WS", f"Streaming iniciado para {len(pairs)} pares")

    def update_pairs(self, new_pairs):
        self._desired_pairs = list(new_pairs)
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass

    def get_snapshot(self, symbol, tf):
        with self._lock:
            return self._snapshots.get((symbol, tf))

    def get_price(self, symbol):
        with self._lock:
            return self._prices.get(symbol, 0)

    def get_bars(self, symbol, tf):
        with self._lock:
            return list(self._bars.get((symbol, tf), []))

    # ── WebSocket lifecycle ──────────────────────────────────────────────
    def _run(self):
        backoff = 3
        while self._running:
            try:
                pairs = self._expand_pairs(self._desired_pairs)
                self._connect(pairs)
                backoff = 3
                self._recv_loop()
            except WebSocketConnectionClosedException as e:
                mlog("WS", f"Conexion cerrada: {e}")
            except Exception as e:
                import traceback
                mlog("WS", f"Error: {type(e).__name__}: {e}")
                traceback.print_exc()
            if self._running:
                time.sleep(backoff)
                backoff = min(backoff * 1.5, 30)

    def _expand_pairs(self, pairs):
        """Deduplicate pairs only (no auto-expansion, anon mode is limited)."""
        return list(set(tuple(p) for p in pairs))

    def _drain(self, timeout=0.5, max_reads=10):
        """Read and handle any pending server messages (heartbeats, etc)."""
        old = self.ws.gettimeout()
        self.ws.settimeout(timeout)
        count = 0
        try:
            while count < max_reads:
                try:
                    raw = self.ws.recv()
                    if raw:
                        for msg in _parse_raw(raw):
                            self._handle(msg)
                    count += 1
                except Exception:
                    break
        finally:
            self.ws.settimeout(old)

    def _connect(self, pairs):
        self.ws = create_connection(
            _TV_WS_URL,
            header={"Origin": _TV_ORIGIN},
            timeout=30,
        )
        self._quote_session = _gen_id("qs_")
        self._counter = 0
        self._series_map.clear()

        # 1. Read ALL initial server messages (greeting, config, heartbeats)
        self._drain(timeout=1.0, max_reads=5)

        # 2. Auth + locale
        self._send("set_auth_token", ["unauthorized_user_token"])
        self._send("set_locale", ["en", "US"])
        self._drain(timeout=0.5)

        # 3. Quote session
        self._send("quote_create_session", [self._quote_session])
        self._send("quote_set_fields", [
            self._quote_session, "lp", "ch", "chp", "volume", "bid", "ask"
        ])
        self._drain(timeout=0.5)

        # 4. Subscribe each pair in its OWN chart session (anon limit: 1 series/session)
        quote_syms = set()
        for sym, tf in pairs:
            self._subscribe_series(sym, tf)
            quote_syms.add(sym)
            self._drain(timeout=0.3)

        # 5. Quote subscriptions for live prices
        for sym in quote_syms:
            exc, _ = detectar_exchange(sym)
            self._send("quote_add_symbols", [self._quote_session, f"{exc}:{sym}"])

        self._drain(timeout=0.5)
        mlog("WS", f"Conectado - {len(pairs)} series ({len(pairs)} sessions), {len(quote_syms)} quotes")

    def _subscribe_series(self, symbol, tf):
        self._counter += 1
        n = self._counter

        # Each series gets its OWN chart session (anon limit = 1 series/session)
        cs = _gen_id("cs_")
        self._send("chart_create_session", [cs, ""])

        exc, _ = detectar_exchange(symbol)
        tv_sym = f"{exc}:{symbol}"
        tv_tf = TV_TF.get(tf, "60")

        resolve = json.dumps({"symbol": tv_sym, "adjustment": "splits"})
        self._send("resolve_symbol", [cs, f"sds_sym_{n}", f"={resolve}"])
        self._send("create_series", [
            cs, f"sds_{n}", f"s{n}", f"sds_sym_{n}", tv_tf, 200, ""
        ])

        self._series_map[f"sds_{n}"] = (symbol, tf)
        mlog("WS", f"Suscrito {tv_sym} tf={tv_tf} (session {cs[:8]}...)")

    def _send(self, func, args):
        if self.ws:
            self.ws.send(_pack(_build(func, args)))

    # ── Message handling ─────────────────────────────────────────────────
    def _recv_loop(self):
        while self._running:
            try:
                raw = self.ws.recv()
                if not raw:
                    continue
                for msg in _parse_raw(raw):
                    self._handle(msg)
            except WebSocketConnectionClosedException:
                raise
            except Exception as e:
                mlog("WS", f"Error en recv_loop: {type(e).__name__}: {e}")

    def _handle(self, msg):
        # Heartbeat echo
        if msg.startswith("~h~"):
            try:
                self.ws.send(_pack(msg))
            except Exception:
                pass
            return

        # Parse JSON
        try:
            data = json.loads(msg)
        except (json.JSONDecodeError, ValueError):
            return

        # Ignore non-dict messages (server greeting numbers, etc.)
        if not isinstance(data, dict):
            return

        m = data.get("m", "")
        p = data.get("p", [])

        if m in ("timescale_update", "du"):
            self._on_bars(p)
        elif m == "qsd":
            self._on_quote(p)
        elif m == "critical_error" or m == "protocol_error":
            mlog("WS", f"Server error: {m} - {p}")
        elif m and not hasattr(self, '_msg_types_logged'):
            self._msg_types_logged = set()
        if m and hasattr(self, '_msg_types_logged') and m not in self._msg_types_logged and m not in ("timescale_update", "du", "qsd"):
            self._msg_types_logged.add(m)
            mlog("WS-MSG", f"Tipo mensaje no procesado: {m}")

    _bar_call_count = 0  # diagnostic counter
    _bar_last_log_ts = 0

    def _on_bars(self, p):
        if len(p) < 2 or not isinstance(p[1], dict):
            return

        self._bar_call_count += 1
        # Log every 60 seconds how many _on_bars calls we got
        now = time.time()
        if now - self._bar_last_log_ts > 300:
            mlog("WS-PULSE", f"_on_bars {self._bar_call_count}x, series={len(self._series_map)}")
            self._bar_last_log_ts = now

        for ser_id, ser_data in p[1].items():
            if ser_id not in self._series_map:
                continue
            if not isinstance(ser_data, dict):
                continue

            symbol, tf = self._series_map[ser_id]
            bars_raw = ser_data.get("s", [])
            if not bars_raw:
                # DU updates may not have "s" key - check for other formats
                mlog("WS-DBG", f"{symbol}:{tf} ser_data keys={list(ser_data.keys())} (no 's' key)")
                continue

            new_bar_closed = False

            with self._lock:
                buf = self._bars.setdefault((symbol, tf), [])

                for bar in bars_raw:
                    v = bar.get("v", [])
                    if len(v) < 6:
                        continue
                    ts, o, h, l, c, vol = v[0], v[1], v[2], v[3], v[4], v[5]

                    # Update or append
                    found = False
                    for i in range(len(buf) - 1, max(len(buf) - 5, -1), -1):
                        if buf[i][0] == ts:
                            buf[i] = [ts, o, h, l, c, vol]
                            found = True
                            break
                    if not found:
                        buf.append([ts, o, h, l, c, vol])

                # Sort by timestamp
                buf.sort(key=lambda x: x[0])

                # Trim to 300 bars
                if len(buf) > 300:
                    self._bars[(symbol, tf)] = buf[-300:]
                    buf = self._bars[(symbol, tf)]

                # Detect new bar close
                if buf:
                    latest_ts = buf[-1][0]
                    prev_ts = self._last_bar_ts.get((symbol, tf))
                    # Log timestamp state periodically (first time + every new ts)
                    if prev_ts is None:
                        mlog("BAR-TS", f"{symbol}:{tf} INIT ts={latest_ts} bars={len(buf)}")
                    if prev_ts is not None and latest_ts > prev_ts:
                        new_bar_closed = True
                        mlog("BAR", f"{symbol}:{tf} NUEVA VELA ts={latest_ts} (prev={prev_ts}) bars={len(buf)}")
                    elif prev_ts is not None and latest_ts < prev_ts:
                        mlog("BAR-WARN", f"{symbol}:{tf} TS RETROCEDIO! ts={latest_ts} prev={prev_ts}")
                    self._last_bar_ts[(symbol, tf)] = latest_ts

                    # Update live price
                    self._prices[symbol] = buf[-1][4]

            # Compute snapshot
            now = time.time()
            if new_bar_closed:
                self._compute_snapshot(symbol, tf)
                self._last_compute[(symbol, tf)] = now
            else:
                # Quick price update + throttled full recompute
                self._update_price_only(symbol, tf)
                if now - self._last_compute.get((symbol, tf), 0) > COMPUTE_THROTTLE:
                    self._compute_snapshot(symbol, tf)
                    self._last_compute[(symbol, tf)] = now

            # Trigger callback on bar close
            if new_bar_closed and self._on_bar_close:
                self._dispatch_callback(symbol, tf)

    def _on_quote(self, p):
        if len(p) < 2 or not isinstance(p[1], dict):
            return
        name = p[1].get("n", "")
        v = p[1].get("v", {})
        lp = v.get("lp")
        if lp and name:
            symbol = name.split(":")[-1]
            with self._lock:
                self._prices[symbol] = float(lp)

    # ── Snapshot computation ─────────────────────────────────────────────
    def _update_price_only(self, symbol, tf):
        with self._lock:
            snap = self._snapshots.get((symbol, tf))
            buf = self._bars.get((symbol, tf))
            if snap and buf:
                last = buf[-1]
                snap["precio"] = round(last[4], 6)
                snap["close"] = round(last[4], 6)
                snap["high"] = round(last[2], 6)
                snap["low"] = round(last[3], 6)
                snap["ts"] = int(time.time())

    def _compute_snapshot(self, symbol, tf):
        with self._lock:
            buf = self._bars.get((symbol, tf))
            if not buf or len(buf) < 30:
                return

            df = pd.DataFrame(buf, columns=["time", "open", "high", "low", "close", "volume"])

        try:
            import pandas_ta as ta
            df.ta.rsi(length=14, append=True)
            df.ta.stoch(k=14, d=3, smooth_k=3, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.adx(length=14, append=True)
            df.ta.cci(length=20, append=True)
            df.ta.willr(length=14, append=True)
            df.ta.mom(length=10, append=True)
            df.ta.ao(append=True)
            df.ta.bbands(length=20, std=2, append=True)
            df.ta.atr(length=14, append=True)
            df.ta.ema(length=9, append=True)
            df.ta.ema(length=20, append=True)
            df.ta.ema(length=35, append=True)
            df.ta.ema(length=50, append=True)
            df.ta.ema(length=200, append=True)
            if "volume" in df.columns:
                df["volume_sma"] = df["volume"].rolling(20).mean()
                df.ta.obv(append=True)

            # +DI / -DI (from ADX calculation)
            df.ta.adx(length=14, append=True)  # re-appends DMP/DMN columns

            # Ichimoku Cloud
            df.ta.ichimoku(tenkan=9, kijun=26, senkou=52, append=True)

            # Candle patterns
            df["cdl_doji"] = _detect_doji(df)
            df["cdl_engulfing"] = _detect_engulfing(df)
            df["cdl_hammer"] = _detect_hammer(df)
            df["cdl_shooting_star"] = _detect_shooting_star(df)

        except Exception as e:
            mlog("DATA", f"Error indicadores {symbol}:{tf}: {e}")
            return

        last = df.iloc[-1]
        precio = _safe(last.get("close"))
        if precio <= 0:
            return

        high = _safe(last.get("high"), precio)
        low = _safe(last.get("low"), precio)
        atr = _safe(last.get(_col(df, "ATR")), precio * 0.005)
        bb_upper = _safe(last.get(_col(df, "BBU_")), precio * 1.02)
        bb_lower = _safe(last.get(_col(df, "BBL_")), precio * 0.98)

        # Supertrend with state tracking
        hl2 = (high + low) / 2
        st_up = hl2 + 3.0 * atr
        st_lo = hl2 - 3.0 * atr
        st_key = (symbol, tf)
        prev_st_dir = _st_prev_dir.get(st_key, "UP")
        if prev_st_dir == "UP":
            # Was UP: stay UP unless price closes below lower band
            if precio < st_lo:
                st_dir, st_line = "DOWN", round(st_up, 5)
            else:
                st_dir, st_line = "UP", round(st_lo, 5)
        else:
            # Was DOWN: stay DOWN unless price closes above upper band
            if precio > st_up:
                st_dir, st_line = "UP", round(st_lo, 5)
            else:
                st_dir, st_line = "DOWN", round(st_up, 5)
        _st_prev_dir[st_key] = st_dir

        squeeze = (bb_upper - bb_lower) < (atr * 3.0)
        vwap = round((high + low + precio) / 3, 5)

        rsi = _safe(last.get(_col(df, "RSI_")), 50)
        stoch_k = _safe(last.get(_col(df, "STOCHk_")), 50)
        stoch_d = _safe(last.get(_col(df, "STOCHd_")), 50)
        macd_val = _safe(last.get(_col(df, "MACD_")))
        macd_sig = _safe(last.get(_col(df, "MACDs_")))
        macd_hist = _safe(last.get(_col(df, "MACDh_")))
        adx = _safe(last.get(_col(df, "ADX_")))
        cci = max(-500, min(500, _safe(last.get(_col(df, "CCI_")))))
        willr = _safe(last.get(_col(df, "WILLR_")), -50)
        mom = _safe(last.get(_col(df, "MOM_")))
        ao = _safe(last.get(_col(df, "AO_")))
        ema9 = _safe(last.get("EMA_9"), precio)
        ema20 = _safe(last.get("EMA_20"), precio)
        ema35 = _safe(last.get("EMA_35"), precio)
        ema50 = _safe(last.get("EMA_50"), precio)
        ema200 = _safe(last.get("EMA_200"))
        vol = _safe(last.get("volume"))
        vol_sma = _safe(last.get("volume_sma"))

        # +DI / -DI
        di_plus = _safe(last.get(_col(df, "DMP_")))
        di_minus = _safe(last.get(_col(df, "DMN_")))

        # OBV
        obv = _safe(last.get(_col(df, "OBV")))

        # Ichimoku
        ichi_tenkan = _safe(last.get(_col(df, "ITS_")))
        ichi_kijun = _safe(last.get(_col(df, "IKS_")))
        ichi_span_a = _safe(last.get(_col(df, "ISA_")))
        ichi_span_b = _safe(last.get(_col(df, "ISB_")))

        # Candle patterns
        cdl_doji = int(_safe(last.get("cdl_doji")))
        cdl_engulfing = int(_safe(last.get("cdl_engulfing")))
        cdl_hammer = int(_safe(last.get("cdl_hammer")))
        cdl_shooting_star = int(_safe(last.get("cdl_shooting_star")))

        # Fibonacci levels (from recent swing high/low in last 50 bars)
        fib_levels = self._calc_fib(df)

        # TV recommend proxy
        bulls = sum([
            1 if 40 < rsi < 70 else 0,
            1 if macd_hist > 0 else 0,
            1 if precio > ema20 else 0,
            1 if st_dir == "UP" else 0,
        ])
        tv_rec = (bulls / 4.0) - 0.5

        # Pivots from daily bars
        pivots = self._calc_pivots(symbol)

        # ── v3.1 Feature Engine additions ──────────────────────────────
        # Z-Score H1 (desviacion vs media 50 periodos)
        closes_arr = df["close"].values
        mean50 = float(np.mean(closes_arr[-50:])) if len(closes_arr) >= 50 else float(np.mean(closes_arr))
        std50 = float(np.std(closes_arr[-50:])) if len(closes_arr) >= 50 else float(np.std(closes_arr))
        zscore_h1 = round((precio - mean50) / std50, 3) if std50 > 0 else 0.0

        # BB distance: posicion relativa dentro de las bandas [-1, 1]
        bb_range = bb_upper - bb_lower
        bb_distance = round((precio - (bb_lower + bb_range / 2)) / (bb_range / 2), 4) if bb_range > 0 else 0.0

        # Vol Ratio (ATR actual / ATR media 20 velas)
        atr_col = _col(df, "ATR")
        if atr_col and atr_col in df.columns:
            atr_vals = df[atr_col].dropna().values
            atr_media20 = float(np.mean(atr_vals[-20:])) if len(atr_vals) >= 20 else float(np.mean(atr_vals)) if len(atr_vals) > 0 else atr
        else:
            atr_media20 = atr
        vol_ratio = round(atr / atr_media20, 3) if atr_media20 > 0 else 1.0

        # Cruce EMA 35/50
        ema35_50_cross = "NONE"
        if "EMA_35" in df.columns and "EMA_50" in df.columns and len(df) >= 2:
            prev = df.iloc[-2]
            prev_ema35 = _safe(prev.get("EMA_35"))
            prev_ema50 = _safe(prev.get("EMA_50"))
            if prev_ema35 and prev_ema50 and ema35 and ema50:
                if prev_ema35 <= prev_ema50 and ema35 > ema50:
                    ema35_50_cross = "GOLDEN"  # cruce alcista
                elif prev_ema35 >= prev_ema50 and ema35 < ema50:
                    ema35_50_cross = "DEATH"   # cruce bajista

        # Series historicas para motores (listas)
        ema20_serie = df["EMA_20"].dropna().tolist()[-30:] if "EMA_20" in df.columns else []
        rsi_col_name = _col(df, "RSI_")
        rsi_serie = df[rsi_col_name].dropna().tolist()[-30:] if rsi_col_name and rsi_col_name in df.columns else []
        closes_list = closes_arr.tolist()[-60:]
        highs_list = df["high"].values.tolist()[-60:]
        lows_list = df["low"].values.tolist()[-60:]
        volumes_list = df["volume"].values.tolist()[-60:] if "volume" in df.columns else []

        snapshot = {
            "precio": round(precio, 6), "open": _safe(last.get("open")),
            "high": round(high, 6), "low": round(low, 6), "close": round(precio, 6),
            "rsi": round(rsi, 2), "stoch_k": round(stoch_k, 2), "stoch_d": round(stoch_d, 2),
            "macd": round(macd_val, 6), "macd_signal": round(macd_sig, 6),
            "macd_hist": round(macd_hist, 6), "adx": round(adx, 2),
            "di_plus": round(di_plus, 2), "di_minus": round(di_minus, 2),
            "cci": round(cci, 2), "williams_r": round(willr, 2),
            "momentum": round(mom, 4), "ao": round(ao, 4),
            "bb_upper": round(bb_upper, 6), "bb_lower": round(bb_lower, 6),
            "bb_width_pct": round((bb_upper - bb_lower) / precio * 100, 3) if precio > 0 else 0,
            "atr": round(atr, 6),
            "atr_pct": round(atr / precio * 100, 3) if precio > 0 else 0,
            "atr_media20": round(atr_media20, 6),
            "ema9": round(ema9, 6), "ema20": round(ema20, 6),
            "ema35": round(ema35, 6), "ema50": round(ema50, 6),
            "ema200": round(ema200, 6) if ema200 else 0,
            "ema35_50_cross": ema35_50_cross,
            "volume": vol, "volume_sma": vol_sma,
            "obv": round(obv, 2),
            "supertrend": st_dir, "st_line": st_line,
            "squeeze": squeeze, "vwap_proxy": vwap,
            # Ichimoku
            "ichi_tenkan": round(ichi_tenkan, 6), "ichi_kijun": round(ichi_kijun, 6),
            "ichi_span_a": round(ichi_span_a, 6), "ichi_span_b": round(ichi_span_b, 6),
            # Candle patterns
            "cdl_doji": cdl_doji, "cdl_engulfing": cdl_engulfing,
            "cdl_hammer": cdl_hammer, "cdl_shooting_star": cdl_shooting_star,
            # Fibonacci
            **fib_levels,
            **pivots,
            "tv_recommend": round(tv_rec, 3), "tv_recommend_ma": round(tv_rec, 3),
            "tipo": tipo_activo(symbol), "temporalidad": tf,
            "ts": int(time.time()),
            # Historical chart summary
            "hist_chart": self._build_hist_chart(df),
            # ── v3.1 Feature Engine ──
            "zscore_h1": zscore_h1,
            "bb_distance": bb_distance,
            "vol_ratio": vol_ratio,
            # Series para motores de señal
            "closes": closes_list,
            "highs": highs_list,
            "lows": lows_list,
            "volumes": volumes_list,
            "ema20_serie": ema20_serie,
            "rsi_serie": rsi_serie,
        }

        with self._lock:
            self._snapshots[(symbol, tf)] = snapshot

    def _calc_pivots(self, symbol):
        """Compute classic pivots from bar buffer (uses daily if available, else intraday)."""
        result = {"pivot_s3": 0, "pivot_s2": 0, "pivot_s1": 0,
                  "pivot_mid": 0, "pivot_r1": 0, "pivot_r2": 0, "pivot_r3": 0}
        # Try daily bars first, then any available TF
        with self._lock:
            daily = self._bars.get((symbol, "1D"))
            if not daily or len(daily) < 2:
                # Use intraday bars to estimate pivots from previous session
                for (s, t), bars in self._bars.items():
                    if s == symbol and len(bars) >= 10:
                        daily = bars
                        break
        if not daily or len(daily) < 2:
            return result
        prev = daily[-2]
        h, l, c = prev[2], prev[3], prev[4]
        if h <= 0 or l <= 0 or c <= 0:
            return result
        pp = (h + l + c) / 3
        result["pivot_mid"] = round(pp, 6)
        result["pivot_s1"] = round(2 * pp - h, 6)
        result["pivot_r1"] = round(2 * pp - l, 6)
        result["pivot_s2"] = round(pp - (h - l), 6)
        result["pivot_r2"] = round(pp + (h - l), 6)
        result["pivot_s3"] = round(l - 2 * (h - pp), 6)
        result["pivot_r3"] = round(h + 2 * (pp - l), 6)
        return result

    def _calc_fib(self, df):
        """Fibonacci retracement from recent 50-bar swing high/low."""
        result = {"fib_0": 0, "fib_236": 0, "fib_382": 0, "fib_500": 0, "fib_618": 0, "fib_1": 0}
        try:
            window = df.tail(50)
            swing_high = window["high"].max()
            swing_low = window["low"].min()
            if swing_high <= swing_low:
                return result
            diff = swing_high - swing_low
            result["fib_0"] = round(swing_high, 6)
            result["fib_236"] = round(swing_high - diff * 0.236, 6)
            result["fib_382"] = round(swing_high - diff * 0.382, 6)
            result["fib_500"] = round(swing_high - diff * 0.5, 6)
            result["fib_618"] = round(swing_high - diff * 0.618, 6)
            result["fib_1"] = round(swing_low, 6)
        except Exception:
            pass
        return result

    def _build_hist_chart(self, df):
        """Build compact historical summary from last 8 candles for IA context.

        Returns a string like:
        Velas:▲▲▼▲▼▲▲▲ RSI:45>48>52>55>58>62>65>67 ADX:18>20>22>24>25>26>27>28
        Vol:0.8x,1.2x,0.9x,1.5x,1.1x,0.7x,1.3x,1.0x SRng:2.1%
        """
        try:
            n = 8
            tail = df.tail(n)
            if len(tail) < 4:
                return ""

            parts = []

            # 1. Candle direction sequence (▲ green, ▼ red)
            dirs = []
            for _, row in tail.iterrows():
                o, c = row.get("open", 0), row.get("close", 0)
                dirs.append("▲" if c >= o else "▼")
            parts.append(f"Velas:{''.join(dirs)}")

            # 2. RSI evolution
            rsi_col = _col(df, "RSI_")
            if rsi_col and rsi_col in tail.columns:
                rsi_vals = [f"{_safe(v):.0f}" for v in tail[rsi_col].values]
                parts.append(f"RSI:{'>'.join(rsi_vals)}")

            # 3. ADX evolution
            adx_col = _col(df, "ADX_")
            if adx_col and adx_col in tail.columns:
                adx_vals = [f"{_safe(v):.0f}" for v in tail[adx_col].values]
                parts.append(f"ADX:{'>'.join(adx_vals)}")

            # 4. MACD histogram evolution (direction trend)
            macd_col = _col(df, "MACDh_")
            if macd_col and macd_col in tail.columns:
                mh_vals = tail[macd_col].values
                mh_dirs = []
                for i in range(1, len(mh_vals)):
                    v = _safe(mh_vals[i])
                    prev = _safe(mh_vals[i-1])
                    if v > 0:
                        mh_dirs.append("+" if v > prev else "~")
                    else:
                        mh_dirs.append("-" if v < prev else "~")
                parts.append(f"MACD_h:{''.join(mh_dirs)}")

            # 5. Volume relative to SMA (multiples)
            if "volume_sma" in tail.columns and "volume" in tail.columns:
                vol_ratios = []
                for _, row in tail.iterrows():
                    vs = _safe(row.get("volume_sma"), 1)
                    v = _safe(row.get("volume"), 0)
                    ratio = v / vs if vs > 0 else 0
                    vol_ratios.append(f"{ratio:.1f}x")
                parts.append(f"Vol:{','.join(vol_ratios)}")

            # 6. Price range (swing high-low as % of current price)
            highs = tail["high"].values
            lows = tail["low"].values
            swing_h = max(highs)
            swing_l = min(lows)
            last_price = _safe(tail.iloc[-1].get("close"), 1)
            if last_price > 0:
                swing_range_pct = (swing_h - swing_l) / last_price * 100
                parts.append(f"Rng:{swing_range_pct:.2f}%")

            # 7. Higher highs / lower lows pattern
            closes = [_safe(tail.iloc[i].get("close")) for i in range(len(tail))]
            hh_count = sum(1 for i in range(1, len(closes)) if closes[i] > closes[i-1])
            ll_count = len(closes) - 1 - hh_count
            if hh_count >= len(closes) - 2:
                parts.append("Patron:HH")  # higher highs
            elif ll_count >= len(closes) - 2:
                parts.append("Patron:LL")  # lower lows
            elif hh_count == ll_count:
                parts.append("Patron:RANGO")

            return " ".join(parts)

        except Exception:
            return ""

    def _dispatch_callback(self, symbol, tf):
        with self._analyzing_lock:
            if (symbol, tf) in self._analyzing:
                return
            self._analyzing.add((symbol, tf))

        def _run():
            try:
                if self._on_bar_close:
                    self._on_bar_close(symbol, tf)
            except Exception as e:
                mlog("CB", f"Callback error {symbol}:{tf}: {e}")
            finally:
                with self._analyzing_lock:
                    self._analyzing.discard((symbol, tf))

        threading.Thread(target=_run, daemon=True).start()


# ── v3.1 Currency Strength Matrix ────────────────────────────────────────────
_CURRENCIES = ["EUR", "USD", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD"]
_PAIRS_FOR_STRENGTH = [
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD",
    "EURJPY", "GBPJPY", "EURGBP", "NZDUSD",
]

_currency_strength = {}  # {currency: strength_value}
_currency_strength_ts = 0


def _calc_currency_strength():
    """
    Calcula la fuerza relativa de cada divisa basada en los cambios %
    de los pares activos en la watchlist + pares de referencia vs sus EMAs.
    """
    global _currency_strength, _currency_strength_ts
    if not _stream:
        return

    import config as _cfg

    # Recopilar todos los pares: fijos + watchlist activa
    wl = _cfg.state.get("watchlist", [])
    wl_extra = _cfg.state.get("watchlist_opcional", [])
    all_pairs_raw = set(_PAIRS_FOR_STRENGTH)
    for item in wl + wl_extra:
        # Formato puede ser "EURUSD:60" o "EURUSD"
        sym = item.split(":")[0].upper().replace("/", "")
        if len(sym) >= 6:
            all_pairs_raw.add(sym[:6])

    # Extraer todas las divisas presentes
    all_currencies = set(_CURRENCIES)
    for pair in all_pairs_raw:
        if len(pair) >= 6:
            all_currencies.add(pair[:3])
            all_currencies.add(pair[3:6])

    scores = {c: 0.0 for c in all_currencies}
    counts = {c: 0 for c in all_currencies}

    for pair in all_pairs_raw:
        snap = _stream.get_snapshot(pair, "60")
        if not snap:
            continue
        precio = snap.get("precio", 0)
        ema20 = snap.get("ema20", 0)
        if not precio or not ema20:
            continue

        # Fuerza = distancia relativa al EMA20
        diff = (precio - ema20) / ema20

        sym = pair.upper()
        base = sym[:3]
        quote = sym[3:6]

        if base in scores:
            scores[base] += diff
            counts[base] += 1
        if quote in scores:
            scores[quote] -= diff  # Inverso para la cotizada
            counts[quote] += 1

    # Normalizar
    for c in all_currencies:
        if counts[c] > 0:
            scores[c] = round(scores[c] / counts[c], 6)

    _currency_strength = scores
    _currency_strength_ts = time.time()


def get_currency_strength(symbol=""):
    """
    Obtiene la fuerza de las divisas del par.

    Returns: dict con strength_base, strength_quote, spread, matrix completa
    """
    now = time.time()
    if now - _currency_strength_ts > 60:
        _calc_currency_strength()

    sym = symbol.upper().replace("/", "")
    base = sym[:3] if len(sym) >= 6 else sym
    quote = sym[3:6] if len(sym) >= 6 else "USD"

    s_base = _currency_strength.get(base, 0.0)
    s_quote = _currency_strength.get(quote, 0.0)

    return {
        "currency_strength_base": s_base,
        "currency_strength_quote": s_quote,
        "currency_spread": round(s_base - s_quote, 6),
        "currency_matrix": dict(_currency_strength),
    }


def _calc_triangular_error(symbol):
    """
    Calcula el error de arbitraje triangular como medida
    de desalineacion temporal del precio.

    Para EURUSD: compara EURUSD vs EURGBP * GBPUSD.
    """
    if not _stream:
        return 0.0

    sym = symbol.upper()
    if sym == "EURUSD":
        # EURUSD vs EURGBP * GBPUSD
        eurgbp = get_price("EURGBP")
        gbpusd = get_price("GBPUSD")
        eurusd = get_price("EURUSD")
        if eurgbp > 0 and gbpusd > 0 and eurusd > 0:
            synth = eurgbp * gbpusd
            return abs(eurusd - synth) / eurusd
    elif sym == "GBPUSD":
        eurgbp = get_price("EURGBP")
        eurusd = get_price("EURUSD")
        gbpusd = get_price("GBPUSD")
        if eurgbp > 0 and eurusd > 0 and gbpusd > 0:
            synth = eurusd / eurgbp
            return abs(gbpusd - synth) / gbpusd

    return 0.0


def get_extended_features(symbol, tf="60"):
    """
    Retorna features extendidas v3.1 para un par (Currency Strength + Triangular).
    Se llama desde bot.py para enriquecer el snapshot antes de los motores.
    """
    cs = get_currency_strength(symbol)
    tri_error = _calc_triangular_error(symbol)

    return {
        **cs,
        "triangular_error": round(tri_error, 8),
    }


# ── Module singleton ─────────────────────────────────────────────────────────
_stream: TVStream | None = None


def start_streaming(pairs, on_bar_close=None):
    global _stream
    if _stream:
        _stream._running = False
    _stream = TVStream()
    _stream.start(pairs, on_bar_close)


def update_subscriptions(pairs):
    if _stream:
        _stream.update_pairs(pairs)


def get_snapshot(simbolo, temporalidad="60"):
    if _stream:
        return _stream.get_snapshot(simbolo, temporalidad)
    return None


def get_price(simbolo):
    if _stream:
        p = _stream.get_price(simbolo)
        if p > 0:
            return p
    return 0


def get_htf_trend(simbolo, temporalidad="60"):
    htf = HIGHER_TF.get(temporalidad)
    if not htf or not _stream:
        return "N/A"
    bars = _stream.get_bars(simbolo, htf)
    if not bars or len(bars) < 21:
        return "N/A"
    closes = [b[4] for b in bars]
    ema21 = _ema_simple(closes, 21)
    price = closes[-1]
    if price > ema21 * 1.001:
        return "ALCISTA"
    elif price < ema21 * 0.999:
        return "BAJISTA"
    return "LATERAL"


def get_ohlcv(simbolo, intervalo="1h"):
    tf_map = {"1m": "1", "5m": "5", "15m": "15", "30m": "30",
              "1h": "60", "4h": "240", "1d": "1D"}
    tf = tf_map.get(intervalo, "60")
    if not _stream:
        return []
    bars = _stream.get_bars(simbolo, tf)
    return [{"time": int(b[0]), "open": round(b[1], 5), "high": round(b[2], 5),
             "low": round(b[3], 5), "close": round(b[4], 5)} for b in bars
            if b[2] >= b[3] and b[1] > 0]


def describe_snapshot(snapshot):
    if not snapshot:
        return "Sin datos disponibles."

    p = snapshot["precio"]
    rsi = snapshot["rsi"]
    adx = snapshot["adx"]
    macd_h = snapshot["macd_hist"]
    st = snapshot["supertrend"]
    sq = snapshot["squeeze"]
    ema9 = snapshot["ema9"]
    ema20 = snapshot["ema20"]
    ema50 = snapshot["ema50"]
    bb_u = snapshot["bb_upper"]
    bb_l = snapshot["bb_lower"]
    atr_pct = snapshot["atr_pct"]

    parts = []
    if ema9 > ema20 > ema50:
        parts.append("Tend:ALCISTA(EMA9>20>50)")
    elif ema9 < ema20 < ema50:
        parts.append("Tend:BAJISTA(EMA9<20<50)")
    elif ema9 > ema20:
        parts.append("Tend:Alcista(EMA9>20)")
    elif ema9 < ema20:
        parts.append("Tend:Bajista(EMA9<20)")
    else:
        parts.append("Tend:Lateral")

    ema200 = snapshot.get("ema200", 0)
    if ema200 > 0:
        if p > ema200:
            parts.append(f"EMA200:precio ENCIMA")
        else:
            parts.append(f"EMA200:precio DEBAJO")

    parts.append(f"ST:{st}")

    if rsi > 70:
        parts.append(f"RSI:{rsi} SOBRECOMPRADO")
    elif rsi < 30:
        parts.append(f"RSI:{rsi} SOBREVENDIDO")
    else:
        parts.append(f"RSI:{rsi}")

    parts.append(f"ADX:{adx}")
    di_p = snapshot.get("di_plus", 0)
    di_m = snapshot.get("di_minus", 0)
    if di_p > 0 or di_m > 0:
        parts.append(f"+DI:{di_p:.0f} -DI:{di_m:.0f}")

    parts.append(f"MACD:{'alcista' if macd_h > 0 else 'bajista'}")

    stk = snapshot.get("stoch_k", 50)
    std = snapshot.get("stoch_d", 50)
    if stk > 80:
        parts.append(f"Stoch:{stk:.0f} SOBRECOMPRADO")
    elif stk < 20:
        parts.append(f"Stoch:{stk:.0f} SOBREVENDIDO")

    cci = snapshot.get("cci", 0)
    if abs(cci) > 100:
        parts.append(f"CCI:{cci:.0f}")

    willr = snapshot.get("williams_r", -50)
    if willr > -20:
        parts.append(f"WillR:{willr:.0f} SOBRECOMPRADO")
    elif willr < -80:
        parts.append(f"WillR:{willr:.0f} SOBREVENDIDO")

    mom = snapshot.get("momentum", 0)
    if mom != 0:
        parts.append(f"MOM:{'+'if mom>0 else ''}{mom:.2f}")

    ao_val = snapshot.get("ao", 0)
    if ao_val != 0:
        parts.append(f"AO:{'+'if ao_val>0 else ''}{ao_val:.2f}")

    bb_range = bb_u - bb_l
    if bb_range > 0:
        bb_pos = (p - bb_l) / bb_range
        if bb_pos > 0.9:
            parts.append("BB:TECHO")
        elif bb_pos < 0.1:
            parts.append("BB:SUELO")
        else:
            parts.append(f"BB:{bb_pos:.0%}")

    bb_w = snapshot.get("bb_width_pct", 0)
    if bb_w > 0:
        parts.append(f"BBW:{bb_w:.1f}%")

    if sq:
        parts.append("SQUEEZE!")

    parts.append(f"ATR:{atr_pct:.2f}%")
    parts.append(f"VWAP:{snapshot.get('vwap_proxy',0)}")

    # Ichimoku
    tenkan = snapshot.get("ichi_tenkan", 0)
    kijun = snapshot.get("ichi_kijun", 0)
    span_a = snapshot.get("ichi_span_a", 0)
    span_b = snapshot.get("ichi_span_b", 0)
    if tenkan > 0 and kijun > 0:
        if p > max(span_a, span_b):
            parts.append("Ichi:ENCIMA nube")
        elif p < min(span_a, span_b):
            parts.append("Ichi:DEBAJO nube")
        else:
            parts.append("Ichi:DENTRO nube")
        if tenkan > kijun:
            parts.append("TK>KJ(alcista)")
        else:
            parts.append("TK<KJ(bajista)")

    # OBV
    obv = snapshot.get("obv", 0)
    if obv != 0:
        parts.append(f"OBV:{obv:.0f}")

    # Volume
    vol = snapshot.get("volume", 0)
    vol_sma = snapshot.get("volume_sma", 0)
    if vol and vol_sma and vol_sma > 0:
        r = vol / vol_sma
        if r > 1.5:
            parts.append(f"Vol:{r:.1f}x(ALTO)")
        elif r < 0.5:
            parts.append(f"Vol:{r:.1f}x(BAJO)")

    # Candle patterns
    patterns = []
    if snapshot.get("cdl_doji"):
        patterns.append("DOJI")
    eng = snapshot.get("cdl_engulfing", 0)
    if eng == 1:
        patterns.append("ENGULFING_ALCISTA")
    elif eng == -1:
        patterns.append("ENGULFING_BAJISTA")
    if snapshot.get("cdl_hammer"):
        patterns.append("HAMMER")
    if snapshot.get("cdl_shooting_star"):
        patterns.append("SHOOTING_STAR")
    if patterns:
        parts.append(f"Velas:{','.join(patterns)}")

    # Fibonacci
    fib_500 = snapshot.get("fib_500", 0)
    if fib_500 > 0:
        fib_dist = abs(p - fib_500) / p * 100
        if fib_dist < 0.5:
            parts.append(f"Fib:CERCA 50%({fib_500})")

    return " | ".join(parts)
