# -*- coding: utf-8 -*-
"""
confluence.py - Gold Confluence Engine (Python)
Replica exacta del Gold_Confluence_Bot.algo de cTrader.

4 confirmaciones: Structure + StochRSI/MACD + Supertrend Dual TF + Session
Parametros optimizados para XAUUSD (DD69).
"""
import math
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETROS OPTIMIZADOS (DD69 cbotset)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConfluenceParams:
    # Structure
    swing_lookback: int = 26
    min_structure_score: int = 1

    # StochRSI
    stoch_rsi_period: int = 9
    stoch_k_smooth: int = 2
    stoch_d_smooth: int = 4
    stoch_ob: int = 82
    stoch_os: int = 25

    # MACD
    macd_fast: int = 7
    macd_slow: int = 28
    macd_signal: int = 14

    # Supertrend H1
    h1_st_period: int = 8
    h1_st_mult: float = 2.7

    # Supertrend M15
    m15_st_period: int = 17
    m15_st_mult: float = 2.2

    # Session (UTC)
    sess_start: int = 4
    sess_end: int = 20

    # Confluence
    min_confirmations: int = 2

    # Risk
    risk_pct: float = 0.1
    sl_atr_mult: float = 2.0
    tp_rr: float = 1.5
    use_trailing: bool = True
    trail_atr: float = 1.0
    max_trades_day: int = 6
    min_bars_between: int = 2


DEFAULT_PARAMS = ConfluenceParams()


# ═══════════════════════════════════════════════════════════════════════════════
# SUPERTREND CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SupertrendState:
    st_up: float = 0.0
    st_dn: float = 0.0
    bull: bool = True
    prev_up: float = 0.0
    prev_dn: float = 0.0
    prev_bull: bool = True


def calc_supertrend(highs: List[float], lows: List[float], closes: List[float],
                    index: int, period: int, mult: float,
                    state: SupertrendState) -> SupertrendState:
    """Calcula Supertrend para una barra, actualizando el estado in-place."""
    if index < period + 1:
        return state

    # ATR manual (igual que cTrader bot)
    atr_sum = 0.0
    for j in range(period):
        k = index - j
        if k < 1:
            return state
        tr = max(
            highs[k] - lows[k],
            abs(highs[k] - closes[k - 1]),
            abs(lows[k] - closes[k - 1])
        )
        atr_sum += tr
    atr = atr_sum / period

    hl2 = (highs[index] + lows[index]) / 2.0
    upper_band = hl2 + mult * atr
    lower_band = hl2 - mult * atr

    state.prev_up = state.st_up
    state.prev_dn = state.st_dn
    state.prev_bull = state.bull

    # Lower band continuity
    if lower_band > state.prev_dn or closes[index - 1] < state.prev_dn:
        state.st_dn = lower_band
    else:
        state.st_dn = state.prev_dn

    # Upper band continuity
    if upper_band < state.prev_up or closes[index - 1] > state.prev_up:
        state.st_up = upper_band
    else:
        state.st_up = state.prev_up

    # Direction flip
    close = closes[index]
    if state.bull and close < state.st_dn:
        state.bull = False
    elif not state.bull and close > state.st_up:
        state.bull = True

    return state


# ═══════════════════════════════════════════════════════════════════════════════
# STOCHRSI CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def calc_rsi(closes: List[float], period: int, index: int) -> float:
    """RSI simple para el indice dado."""
    if index < period + 1:
        return 50.0

    gains = 0.0
    losses = 0.0
    for i in range(index - period, index):
        diff = closes[i + 1] - closes[i]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)

    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def calc_stoch_rsi(closes: List[float], index: int,
                   period: int = 9, k_smooth: int = 2, d_smooth: int = 4
                   ) -> Tuple[float, float, float]:
    """
    Calcula StochRSI K, D, y prevK (para detectar cruces).
    Replica exacta del bot cTrader.
    """
    if index < period * 2 + k_smooth:
        return 50.0, 50.0, 50.0

    def _stoch_rsi_raw(idx):
        rsi_now = calc_rsi(closes, period, idx)
        rsi_high = -999999.0
        rsi_low = 999999.0
        for i in range(period):
            r = calc_rsi(closes, period, idx - i)
            if r > rsi_high:
                rsi_high = r
            if r < rsi_low:
                rsi_low = r
        if rsi_high == rsi_low:
            return 50.0
        return (rsi_now - rsi_low) / (rsi_high - rsi_low) * 100.0

    # K = SMA of raw StochRSI over k_smooth bars
    sum_k = 0.0
    for i in range(k_smooth):
        sum_k += _stoch_rsi_raw(index - i)
    k = sum_k / k_smooth

    # Prev K
    sum_prev_k = 0.0
    for i in range(k_smooth):
        sum_prev_k += _stoch_rsi_raw(index - 1 - i)
    prev_k = sum_prev_k / k_smooth

    # D = simple average of K and prevK (simplified, matches bot)
    d = (k + prev_k) / 2.0

    return k, d, prev_k


# ═══════════════════════════════════════════════════════════════════════════════
# MACD CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════════

def _ema_series(values: List[float], period: int) -> List[float]:
    """Calcula serie EMA completa."""
    if not values or period <= 0:
        return []
    result = [0.0] * len(values)
    mult = 2.0 / (period + 1)
    result[0] = values[0]
    for i in range(1, len(values)):
        result[i] = (values[i] - result[i - 1]) * mult + result[i - 1]
    return result


def calc_macd(closes: List[float], fast: int = 7, slow: int = 28, signal_period: int = 14,
              index: int = -1) -> Tuple[float, float]:
    """Calcula MACD histogram y signal line en el indice dado."""
    if len(closes) < slow + signal_period:
        return 0.0, 0.0

    ema_fast = _ema_series(closes, fast)
    ema_slow = _ema_series(closes, slow)

    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
    signal_line = _ema_series(macd_line, signal_period)

    idx = index if index >= 0 else len(closes) - 1
    histogram = macd_line[idx] - signal_line[idx]
    return histogram, signal_line[idx]


# ═══════════════════════════════════════════════════════════════════════════════
# STRUCTURE ANALYZER
# ═══════════════════════════════════════════════════════════════════════════════

def analyze_structure(highs: List[float], lows: List[float],
                      index: int, lookback: int = 26) -> Tuple[int, int]:
    """
    Detecta estructura de mercado: HH/HL (alcista) o LH/LL (bajista).
    Retorna (bull_score, bear_score).
    Replica exacta del bot cTrader.
    """
    bull_score = 0
    bear_score = 0

    start = max(lookback, index - 200)

    swing_highs = []
    swing_lows = []

    for i in range(start, index - lookback + 1):
        # Check swing high
        is_high = True
        high = highs[i]
        for j in range(1, lookback + 1):
            if i - j < 0 or i + j >= len(highs):
                is_high = False
                break
            if highs[i - j] >= high or highs[i + j] >= high:
                is_high = False
                break
        if is_high:
            swing_highs.append(high)

        # Check swing low
        is_low = True
        low = lows[i]
        for j in range(1, lookback + 1):
            if i - j < 0 or i + j >= len(lows):
                is_low = False
                break
            if lows[i - j] <= low or lows[i + j] <= low:
                is_low = False
                break
        if is_low:
            swing_lows.append(low)

    # Score swing highs (HH vs LH)
    if len(swing_highs) >= 2:
        count = min(4, len(swing_highs))
        for i in range(len(swing_highs) - count + 1, len(swing_highs)):
            if swing_highs[i] > swing_highs[i - 1]:
                bull_score += 1  # HH
            else:
                bear_score += 1  # LH

    # Score swing lows (HL vs LL)
    if len(swing_lows) >= 2:
        count = min(4, len(swing_lows))
        for i in range(len(swing_lows) - count + 1, len(swing_lows)):
            if swing_lows[i] > swing_lows[i - 1]:
                bull_score += 1  # HL
            else:
                bear_score += 1  # LL

    return bull_score, bear_score


# ═══════════════════════════════════════════════════════════════════════════════
# CONFLUENCE ENGINE
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ConfluenceResult:
    action: str = "WAIT"
    confidence: int = 0
    bull_conf: int = 0
    bear_conf: int = 0
    entry: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    sl_dist: float = 0.0
    tp_dist: float = 0.0
    risk_pct: float = 0.1
    atr: float = 0.0
    details: dict = field(default_factory=dict)


class ConfluenceEngine:
    """
    Motor Gold Confluence — replica exacta del cTrader bot.
    Mantiene estado de Supertrend H1 y M15 entre barras.
    """

    def __init__(self, params: ConfluenceParams = None):
        self.p = params or DEFAULT_PARAMS
        self.m15_st = SupertrendState()
        self.h1_st = SupertrendState()
        self._last_trade_bar = -100
        self._trades_today = 0
        self._last_trade_day = -1
        self._warmed_up = False

    def warmup(self, m15_highs: List[float], m15_lows: List[float], m15_closes: List[float],
               h1_highs: List[float], h1_lows: List[float], h1_closes: List[float]):
        """Pre-calcula Supertrend en datos historicos para tener estado correcto."""
        # Warmup M15 Supertrend
        for i in range(self.p.m15_st_period + 2, len(m15_closes)):
            calc_supertrend(m15_highs, m15_lows, m15_closes, i,
                            self.p.m15_st_period, self.p.m15_st_mult, self.m15_st)

        # Warmup H1 Supertrend
        for i in range(self.p.h1_st_period + 2, len(h1_closes)):
            calc_supertrend(h1_highs, h1_lows, h1_closes, i,
                            self.p.h1_st_period, self.p.h1_st_mult, self.h1_st)

        self._warmed_up = True

    def evaluate(self,
                 m15_highs: List[float], m15_lows: List[float], m15_closes: List[float],
                 m15_index: int,
                 h1_highs: List[float], h1_lows: List[float], h1_closes: List[float],
                 h1_index: int,
                 hour_utc: int,
                 atr: float,
                 bar_index: int = 0,
                 day_key: int = 0,
                 direction_override: str = "Auto"
                 ) -> ConfluenceResult:
        """
        Evalua las 4 confirmaciones y retorna senal.

        Args:
            m15_highs/lows/closes: Series M15 completas
            m15_index: Indice actual en la serie M15
            h1_highs/lows/closes: Series H1 completas
            h1_index: Indice actual en la serie H1
            hour_utc: Hora UTC actual
            atr: ATR(14) del timeframe principal
            bar_index: Indice de barra (para control de frecuencia)
            day_key: Clave de dia (year*1000 + day_of_year) para max trades/dia
            direction_override: "Auto", "SoloBuy", "SoloSell", "Pausado"
        """
        result = ConfluenceResult()
        result.atr = atr

        if atr <= 0:
            return result

        # Daily trade counter
        if day_key != self._last_trade_day and day_key != 0:
            self._trades_today = 0
            self._last_trade_day = day_key

        close = m15_closes[m15_index]
        result.entry = close

        # ═══════════════════════════════════════════
        # 1. STRUCTURE
        # ═══════════════════════════════════════════
        struct_bull, struct_bear = analyze_structure(
            m15_highs, m15_lows, m15_index, self.p.swing_lookback
        )

        # ═══════════════════════════════════════════
        # 2. MOMENTUM: StochRSI + MACD
        # ═══════════════════════════════════════════
        stoch_k, stoch_d, prev_stoch_k = calc_stoch_rsi(
            m15_closes, m15_index,
            self.p.stoch_rsi_period, self.p.stoch_k_smooth, self.p.stoch_d_smooth
        )

        macd_hist, macd_sig = calc_macd(
            m15_closes, self.p.macd_fast, self.p.macd_slow, self.p.macd_signal,
            m15_index
        )

        # Bullish momentum (same logic as cTrader bot)
        mom_bull = ((stoch_k > stoch_d and prev_stoch_k <= stoch_d) or
                    (stoch_k < self.p.stoch_ob and stoch_k > self.p.stoch_os and macd_hist > 0))
        mom_strong = stoch_k < self.p.stoch_ob and macd_hist > 0

        # Bearish momentum
        mom_bear = ((stoch_k < stoch_d and prev_stoch_k >= stoch_d) or
                    (stoch_k > self.p.stoch_os and stoch_k < self.p.stoch_ob and macd_hist < 0))
        mom_strong_bear = stoch_k > self.p.stoch_os and macd_hist < 0

        # ═══════════════════════════════════════════
        # 3. SUPERTREND DUAL TF
        # ═══════════════════════════════════════════
        prev_m15_bull = self.m15_st.bull

        calc_supertrend(m15_highs, m15_lows, m15_closes, m15_index,
                        self.p.m15_st_period, self.p.m15_st_mult, self.m15_st)

        if h1_index >= self.p.h1_st_period + 1:
            calc_supertrend(h1_highs, h1_lows, h1_closes, h1_index,
                            self.p.h1_st_period, self.p.h1_st_mult, self.h1_st)

        st_bull = self.m15_st.bull and self.h1_st.bull
        st_bear = not self.m15_st.bull and not self.h1_st.bull

        # ═══════════════════════════════════════════
        # 4. SESSION
        # ═══════════════════════════════════════════
        in_session = self.p.sess_start <= hour_utc < self.p.sess_end

        # ═══════════════════════════════════════════
        # COUNT CONFIRMATIONS
        # ═══════════════════════════════════════════
        bull_conf = 0
        bear_conf = 0

        if struct_bull >= self.p.min_structure_score:
            bull_conf += 1
        if mom_bull or mom_strong:
            bull_conf += 1
        if st_bull:
            bull_conf += 1
        if in_session:
            bull_conf += 1

        if struct_bear >= self.p.min_structure_score:
            bear_conf += 1
        if mom_bear or mom_strong_bear:
            bear_conf += 1
        if st_bear:
            bear_conf += 1
        if in_session:
            bear_conf += 1

        result.bull_conf = bull_conf
        result.bear_conf = bear_conf

        # Build details
        result.details = {
            "structure_bull": struct_bull,
            "structure_bear": struct_bear,
            "stoch_k": round(stoch_k, 1),
            "stoch_d": round(stoch_d, 1),
            "macd_hist": round(macd_hist, 4),
            "m15_st_bull": self.m15_st.bull,
            "h1_st_bull": self.h1_st.bull,
            "st_aligned_bull": st_bull,
            "st_aligned_bear": st_bear,
            "in_session": in_session,
            "hour_utc": hour_utc,
            "mom_bull": mom_bull,
            "mom_bear": mom_bear,
        }

        # ═══════════════════════════════════════════
        # DIRECTION OVERRIDE
        # ═══════════════════════════════════════════
        if direction_override == "Pausado":
            result.action = "WAIT"
            result.details["blocked"] = "Pausado"
            return result

        if direction_override == "SoloSell":
            bull_conf = 0
        if direction_override == "SoloBuy":
            bear_conf = 0

        # ═══════════════════════════════════════════
        # TRADE CONTROLS
        # ═══════════════════════════════════════════
        can_trade = (self._trades_today < self.p.max_trades_day and
                     (bar_index - self._last_trade_bar) >= self.p.min_bars_between)

        if not can_trade:
            result.details["blocked"] = "max_trades" if self._trades_today >= self.p.max_trades_day else "min_bars"
            return result

        # ═══════════════════════════════════════════
        # ENTRY DECISION
        # ═══════════════════════════════════════════
        sl_dist = atr * self.p.sl_atr_mult
        if sl_dist < 0.3:
            sl_dist = 0.3
        tp_dist = sl_dist * self.p.tp_rr

        if bull_conf >= self.p.min_confirmations:
            result.action = "BUY"
            result.confidence = int(bull_conf / 4.0 * 100)
            result.sl = close - sl_dist
            result.tp = close + tp_dist
            result.sl_dist = sl_dist
            result.tp_dist = tp_dist
            result.risk_pct = self.p.risk_pct
            self._trades_today += 1
            self._last_trade_bar = bar_index

        elif bear_conf >= self.p.min_confirmations:
            result.action = "SELL"
            result.confidence = int(bear_conf / 4.0 * 100)
            result.sl = close + sl_dist
            result.tp = close - tp_dist
            result.sl_dist = sl_dist
            result.tp_dist = tp_dist
            result.risk_pct = self.p.risk_pct
            self._trades_today += 1
            self._last_trade_bar = bar_index

        return result

    def get_trailing_sl(self, trade_type: str, entry_price: float,
                        current_price: float, current_sl: float,
                        atr: float) -> Optional[float]:
        """Calcula nuevo SL para trailing stop. Retorna None si no mover."""
        if not self.p.use_trailing or atr <= 0:
            return None

        sl_dist = abs(entry_price - current_sl) if current_sl else atr * self.p.sl_atr_mult
        trail = atr * self.p.trail_atr

        if trade_type == "BUY":
            if current_price - entry_price < sl_dist:
                return None
            new_sl = current_price - trail
            if current_sl is None or new_sl > current_sl:
                return round(new_sl, 2)
        else:
            if entry_price - current_price < sl_dist:
                return None
            new_sl = current_price + trail
            if current_sl is None or new_sl < current_sl:
                return round(new_sl, 2)

        return None


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER: Download candles for dual timeframe
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_candles_yfinance(symbol: str = "XAUUSD", days: int = 60):
    """
    Descarga velas M15 y H1 via yfinance.
    Retorna (m15_df, h1_df) o (None, None) si falla.
    """
    try:
        import yfinance as yf
    except ImportError:
        import os, sys
        os.system(f"{sys.executable} -m pip install yfinance -q")
        import yfinance as yf

    yahoo_map = {
        "XAUUSD": "GC=F", "XAGUSD": "SI=F",
        "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X",
    }

    ticker = yahoo_map.get(symbol.upper(), f"{symbol}=X")

    try:
        m15_df = yf.download(ticker, period=f"{min(days, 60)}d", interval="15m", progress=False)
        h1_df = yf.download(ticker, period=f"{min(days, 730)}d", interval="1h", progress=False)

        if m15_df is None or len(m15_df) < 100:
            return None, None
        if h1_df is None or len(h1_df) < 100:
            return None, None

        return m15_df, h1_df
    except Exception as e:
        print(f"[CONFLUENCE] Error descargando datos: {e}")
        return None, None


def df_to_lists(df):
    """Convierte DataFrame a listas de highs, lows, closes."""
    highs = df["High"].values.flatten().tolist() if hasattr(df["High"].values, 'flatten') else df["High"].tolist()
    lows = df["Low"].values.flatten().tolist() if hasattr(df["Low"].values, 'flatten') else df["Low"].tolist()
    closes = df["Close"].values.flatten().tolist() if hasattr(df["Close"].values, 'flatten') else df["Close"].tolist()
    return highs, lows, closes


# ═══════════════════════════════════════════════════════════════════════════════
# STANDALONE SIGNAL CHECK (for production use)
# ═══════════════════════════════════════════════════════════════════════════════

_engine_instance: Optional[ConfluenceEngine] = None


def get_engine() -> ConfluenceEngine:
    """Singleton del motor Confluence."""
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = ConfluenceEngine(DEFAULT_PARAMS)
    return _engine_instance


def check_signal(m15_highs, m15_lows, m15_closes,
                 h1_highs, h1_lows, h1_closes,
                 hour_utc, atr, bar_index=0, day_key=0,
                 direction_override="Auto") -> dict:
    """
    API principal para el backend.
    Evalua confluencia y retorna dict compatible con signals.emit().
    """
    engine = get_engine()

    if not engine._warmed_up and len(m15_closes) > 50 and len(h1_closes) > 50:
        engine.warmup(m15_highs, m15_lows, m15_closes,
                      h1_highs, h1_lows, h1_closes)

    m15_idx = len(m15_closes) - 1
    h1_idx = len(h1_closes) - 1

    result = engine.evaluate(
        m15_highs, m15_lows, m15_closes, m15_idx,
        h1_highs, h1_lows, h1_closes, h1_idx,
        hour_utc, atr, bar_index, day_key,
        direction_override
    )

    return {
        "action": result.action,
        "confidence": result.confidence,
        "entry": result.entry,
        "sl": round(result.sl, 2) if result.sl else 0,
        "tp": round(result.tp, 2) if result.tp else 0,
        "sl_dist": round(result.sl_dist, 2),
        "tp_dist": round(result.tp_dist, 2),
        "risk_pct": result.risk_pct,
        "atr": round(result.atr, 2),
        "bull_conf": result.bull_conf,
        "bear_conf": result.bear_conf,
        "rr_ratio": round(result.tp_dist / result.sl_dist, 2) if result.sl_dist > 0 else 0,
        "trailing_stop": "atr" if DEFAULT_PARAMS.use_trailing else "none",
        "details": result.details,
        "reason": _build_reason(result),
    }


def _build_reason(r: ConfluenceResult) -> str:
    """Construye texto explicativo de la senal."""
    if r.action == "WAIT":
        blocked = r.details.get("blocked", "")
        if blocked:
            return f"Bloqueado: {blocked}"
        return f"Conf insuficiente: Bull={r.bull_conf}/4 Bear={r.bear_conf}/4"

    d = r.details
    parts = []
    if r.action == "BUY":
        parts.append(f"Struct={d.get('structure_bull', 0)}")
    else:
        parts.append(f"Struct={d.get('structure_bear', 0)}")
    parts.append(f"Mom={'OK' if d.get('mom_bull' if r.action == 'BUY' else 'mom_bear') else 'NO'}")
    parts.append(f"ST={'ALIGNED' if d.get('st_aligned_bull' if r.action == 'BUY' else 'st_aligned_bear') else 'NO'}")
    parts.append(f"Sess={'OK' if d.get('in_session') else 'NO'}")
    parts.append(f"StochK={d.get('stoch_k', 0):.0f}")
    parts.append(f"MACD={d.get('macd_hist', 0):.4f}")

    conf = r.bull_conf if r.action == "BUY" else r.bear_conf
    return f"{r.action} {conf}/4 | " + " | ".join(parts)
