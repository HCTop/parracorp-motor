# -*- coding: utf-8 -*-
"""
bot.py - ParraCorp v3.1 - Orquestador Principal
Pipeline 9 capas. Solo senales (sin broker). Telegram + WhatsApp.
Boton ON/OFF para motor e IA.
"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import os
_env_file = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(_env_file):
    with open(_env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from flask import Flask, request, jsonify
import threading
import time
import json
from datetime import datetime

import config as cfg
from config import log as mlog
from data_feed import (get_snapshot, get_price, get_ohlcv, get_htf_trend,
                       describe_snapshot, get_extended_features, get_currency_strength)
from market_context import (get_full_context, get_session, get_calendar,
                            get_session_countdown, get_news_data, get_upcoming_events,
                            check_bank_holiday)
from brain import analyze as brain_analyze, ia_tokens, ia_modelo_actual
from risk_engine import calcular_lote, validar_senal, ajustar_riesgo_por_regimen
from signals import (emit as emit_signal, check_prices, get_active, get_history,
                     get_stats, cancel as cancel_signal, close_signal, vote as vote_signal,
                     delete_from_history)
from push import send as push_send, send_signal as push_signal, send_close as push_close

# v3.1 modules
from signal_engines import evaluar_senales
from regime_detector import detectar_regimen, get_info as regimen_info, get_config as regimen_config
from order_flow import calcular_order_flow
from mtf import get_mtf_info
from sr_engine import get_sr_info
from portfolio_risk import puede_abrir, get_portfolio_info, exposicion_por_divisa
from manipulation_detector import get_manipulation_info
from alert_engine import generar_alertas_condicion
from learning_loop import registrar_trade, get_pesos, get_stats as learn_stats
from monte_carlo import monte_carlo
from model_versioning import get_historial as version_historial

import telegram_bot as tg
import whatsapp_bot as wa
import alerts as price_alerts
from push import send_alert as push_alert
from chart_gen import generate_signal_chart, cleanup_old_charts

app = Flask(__name__)

# Custom JSON encoder para numpy types
import numpy as np
from flask.json.provider import DefaultJSONProvider

class NumpyJSONProvider(DefaultJSONProvider):
    def default(self, o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (np.bool_,)):
            return bool(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        return super().default(o)

app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)

# Cooldown per-symbol: evita re-entrada inmediata tras cierre
_symbol_cooldown = {}  # {symbol: timestamp_until}
_COOLDOWN_SECONDS = 3600  # 1 hora de cooldown tras cierre (alineado con TF 1H)

# Cache
_snapshot_cache = {}
_htf_cache = {}
_context_cache = {}
_engines_cache = {}
_regime_cache = {}
_brain_cache = {}   # {(symbol, tf): {"votos": {...}, "consensus": str, "ts": int}}
_cache_lock = threading.Lock()
_features_history = {}  # {symbol: [last N features]}

@app.after_request
def _cors(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


# === MOTOR PRINCIPAL v3.1 =====================================================

def _tf_label(tf):
    _map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "240": "4h", "1D": "1D", "D": "1D"}
    return _map.get(str(tf), f"{tf}m" if tf else "")


def _parse_watchlist_pairs(watchlist):
    pairs = []
    for entry in watchlist:
        parts = entry.split(":")
        symbol = parts[0]
        tf = parts[1] if len(parts) >= 2 else "60"
        pairs.append((symbol, tf))
    return pairs if pairs else [("EURUSD", "60")]


_motor_off_log_ts = 0
_no_snapshot_log_ts = {}

def _on_new_bar(symbol, tf):
    """Callback v3.1: pipeline de 9 capas en cada cierre de vela."""
    global _motor_off_log_ts
    try:
        # Check motor ON/OFF
        if not cfg.state.get("motor_activo", True):
            now = time.time()
            if now - _motor_off_log_ts > 300:
                mlog("MOTOR", "Motor APAGADO - no se procesan barras")
                _motor_off_log_ts = now
            return

        snapshot = get_snapshot(symbol, tf)
        if not snapshot:
            now = time.time()
            last = _no_snapshot_log_ts.get((symbol, tf), 0)
            if now - last > 300:
                mlog("DATA", f"{symbol}:{tf} sin snapshot disponible (esperando datos WS)")
                _no_snapshot_log_ts[(symbol, tf)] = now
            return

        cfg.state["motor_ok"] = True
        cfg.state["ultimo_ciclo"] = datetime.now().strftime("%H:%M:%S")
        cfg.state["ts_ciclo"] = int(time.time())

        with _cache_lock:
            _snapshot_cache[(symbol, tf)] = snapshot

        # === CAPA 0+1: Market Data + Features ===
        ext_features = get_extended_features(symbol, tf)
        features = {**snapshot, **ext_features, "par": symbol}

        context = get_full_context(symbol, tf)
        with _cache_lock:
            _context_cache[symbol] = context

        htf = get_htf_trend(symbol, tf)
        with _cache_lock:
            _htf_cache[(symbol, tf)] = htf

        context["signals_active"] = get_active()

        # === CAPA 5: Regimen ===
        # Save previous regimen BEFORE updating the cache
        with _cache_lock:
            reg_prev = _regime_cache.get((symbol, tf), {}).get("regimen", None)

        regimen = detectar_regimen(
            snapshot.get("adx", 0),
            snapshot.get("atr", 0),
            snapshot.get("atr_media20", snapshot.get("atr", 0)),
            snapshot.get("ema20", 0),
            snapshot.get("ema50", 0),
            symbol=symbol,
        )
        if reg_prev is None:
            reg_prev = regimen
        reg_info = regimen_info(regimen, symbol=symbol)

        with _cache_lock:
            _regime_cache[(symbol, tf)] = reg_info

        # === CAPA 2: Motores de Senal ===
        pesos_aprendidos = get_pesos(regimen)
        engines_result = evaluar_senales(features, regimen, pesos_aprendidos)

        # === CAPA 7: Order Flow ===
        of_info = calcular_order_flow(
            features.get("closes", []),
            features.get("highs", []),
            features.get("lows", []),
            features.get("volumes", []),
        )
        engines_result.update(of_info)

        # === CAPA 7: MTF ===
        # Obtener datos del timeframe superior
        htf_snap = get_snapshot(symbol, "240") if tf == "60" else None
        htf_data = {
            "ema20": htf_snap.get("ema20", 0) if htf_snap else 0,
            "ema50": htf_snap.get("ema50", 0) if htf_snap else 0,
            "adx": htf_snap.get("adx", 0) if htf_snap else 0,
        }
        mtf_info = get_mtf_info(htf_data, engines_result.get("direccion", "NEUTRAL"))
        engines_result.update(mtf_info)

        # === CAPA 7: S/R ===
        sr_info = get_sr_info(
            features.get("highs", []),
            features.get("lows", []),
            features.get("closes", []),
            snapshot.get("precio", 0),
            symbol,
        )

        # === CAPA 7: Manipulacion ===
        hora_utc = datetime.utcnow().hour
        manip_info = get_manipulation_info(
            [{"open": snapshot.get("open", 0), "high": snapshot.get("high", 0),
              "low": snapshot.get("low", 0), "close": snapshot.get("close", 0)}],
            hora_utc, snapshot.get("adx", 0), features.get("vol_ratio", 1.0),
        )
        if manip_info.get("alerta_manipulacion"):
            mlog("MANIP", f"{symbol} Alerta: {manip_info}")

        # Cache engines
        with _cache_lock:
            _engines_cache[(symbol, tf)] = engines_result

        # Guardar features historicas para alertas inteligentes
        if symbol not in _features_history:
            _features_history[symbol] = []
        _features_history[symbol].append(features)
        if len(_features_history[symbol]) > 30:
            _features_history[symbol] = _features_history[symbol][-30:]

        # === ALERTAS INTELIGENTES (17.8) ===
        alertas = generar_alertas_condicion(
            {**features, **engines_result},
            _features_history.get(symbol, []),
            regimen, reg_prev,
        )
        for alerta in alertas:
            mlog("ALERTA", f"{alerta['emoji']} {alerta['mensaje']}")

        # === CAPA 3+4: Brain v4 (IA como cerebro principal) ===
        tqs = engines_result.get("trade_quality_score", 0)
        direccion = engines_result.get("direccion", "NEUTRAL")

        # Stats se ejecuta siempre (gratis) - se pasa como CONTEXTO a la IA
        from brain import modelo_estadistico
        stats_result = modelo_estadistico(snapshot, engines_result, reg_info, mtf_info, of_info, sr_info)

        # Inyectar stats como contexto en engines_result para que la IA lo reciba
        engines_result["_stats_context"] = stats_result

        # Guardar cache pre-IA (Groq/Gemini pendientes, Stats como referencia)
        with _cache_lock:
            _brain_cache[(symbol, tf)] = {
                "votos": {
                    "groq": _brain_cache.get((symbol, tf), {}).get("votos", {}).get("groq", {"action": "PENDING", "confidence": 0}),
                    "gemini": _brain_cache.get((symbol, tf), {}).get("votos", {}).get("gemini", {"action": "PENDING", "confidence": 0}),
                    "stats": {"action": stats_result["action"], "confidence": stats_result["confidence"]},
                },
                "consensus": "pendiente",
                "action": "WAIT",
                "confidence": 0,
                "reason": f"[Stats ref: {stats_result['action']} {stats_result['confidence']}%] Esperando IA...",
                "ts": int(time.time()),
            }

        # === Bloqueos DUROS (solo lo objetivo e indiscutible) ===
        skip_reason = None

        # Cooldown per-symbol (FIX4: no re-entrar inmediatamente tras cierre)
        cooldown_until = _symbol_cooldown.get(symbol, 0)
        if time.time() < cooldown_until:
            remaining = int(cooldown_until - time.time())
            skip_reason = f"Cooldown {symbol}: {remaining}s restantes"

        # Spike de manipulacion detectado (dato objetivo, no opinion)
        elif manip_info.get("spike_detectado"):
            skip_reason = "Spike detectado"
            mlog("MANIP", f"{symbol} Spike detectado - skip senal")

        # Drawdown diario extremo (proteccion de capital)
        elif cfg.state.get("daily_pnl", 0) < 0:
            capital = cfg.state.get("capital", 10000)
            dd_pct = abs(cfg.state["daily_pnl"]) / capital * 100 if capital > 0 else 0
            if dd_pct >= 5.0:
                skip_reason = f"Drawdown diario {dd_pct:.1f}% >= 5%"
                mlog("RISK", f"MOTOR BLOQUEADO: drawdown diario {dd_pct:.1f}%")

        # NOTA: Regimen CHOPPY, TQS bajo, ADX bajo, MTF conflicto YA NO bloquean.
        # Esos datos se pasan a la IA via _interpret_context() y ella decide.
        # La IA los ve como: "SIN MOMENTUM: ADX=12", "Regimen: CHOPPY", "MTF BLOCK", etc.

        if skip_reason:
            with _cache_lock:
                existing = _brain_cache.get((symbol, tf), {})
                existing["reason"] = f"[Stats: {stats_result['action']} {stats_result['confidence']}%] {skip_reason}"
            _log_cycle(symbol, tf, snapshot, htf, tqs, regimen, engines_result, skip_reason)
            return

        # Brain v4: IA decide (Modelo B en TF 1H, Stats fallback en otros TFs)
        result = brain_analyze(
            symbol, snapshot, engines_result, context,
            reg_info, mtf_info, of_info, sr_info,
            htf_trend=htf,
        )

        # Cache brain result (votos)
        with _cache_lock:
            _brain_cache[(symbol, tf)] = {
                "votos": result.get("votos", {}),
                "consensus": result.get("consensus", ""),
                "action": result.get("action", "WAIT"),
                "confidence": result.get("confidence", 0),
                "reason": result.get("reason", ""),
                "ts": int(time.time()),
            }

        # === CAPA 8: Emision de senal ===
        if result["action"] in ("BUY", "SELL") and not result.get("blocked"):
            valid, reason = validar_senal(
                result["action"], result["entry"],
                result["sl"], result["tp"], symbol,
            )
            if not valid:
                mlog("RISK", f"{symbol} Senal rechazada: {reason}")
            else:
                # Portfolio risk check
                active = get_active()
                riesgo_base = result.get("risk_pct", 1.0)
                riesgo_ajustado = ajustar_riesgo_por_regimen(riesgo_base, reg_info)

                lot_result = calcular_lote(
                    result["entry"], result["sl"],
                    cfg.state["capital"], riesgo_ajustado, symbol,
                    tp=result["tp"],
                )

                if lot_result["rejected"]:
                    mlog("RISK", f"{symbol} Lote rechazado: {lot_result['reject_reason']}")
                else:
                    # Portfolio exposure check
                    can_open, expo_reason = puede_abrir(
                        active, symbol, lot_result["riesgo_usd"], cfg.state["capital"]
                    )
                    if not can_open:
                        mlog("PORTF", f"{symbol} Exposicion: {expo_reason}")
                    else:
                        sig = emit_signal(
                            symbol=symbol,
                            action=result["action"],
                            entry_price=result["entry"],
                            sl=result["sl"],
                            tp=result["tp"],
                            timeframe=tf,
                            risk_pct=riesgo_ajustado,
                            confidence=result["confidence"],
                            reason=result["reason"],
                            lote=lot_result["lote"],
                            unidades=lot_result["unidades"],
                            lote_std=lot_result["lote_std"],
                            groq_analysis=result.get("groq_analysis", ""),
                            rr_ratio=lot_result["rr_ratio"],
                            tqs=tqs,
                            regimen=regimen,
                            votos=result.get("votos", {}),
                            consensus=result.get("consensus", ""),
                            trailing_stop=result.get("trailing_stop", "none"),
                            mtf_alignment=mtf_info.get("mtf_alignment", 0),
                            of_delta=of_info.get("order_flow_delta", 0),
                            sr_distance=sr_info.get("sr_distance_pips", 0),
                            divergence=engines_result.get("divergence_signal", "NONE"),
                            riesgo_usd=lot_result["riesgo_usd"],
                            atr=snapshot.get("atr", 0),
                        )
                        if sig:
                            # Notificaciones
                            chart_path = generate_signal_chart(sig, get_ohlcv)
                            tg.send_signal_open(sig, chart_path=chart_path)
                            wa.send_signal_open(sig, chart_path=chart_path)

                            token = cfg.state.get("push_token", "")
                            if token:
                                threading.Thread(
                                    target=push_signal, args=(token, sig)
                                ).start()

        _log_cycle(symbol, tf, snapshot, htf, tqs, regimen, engines_result)

    except Exception as e:
        import traceback
        mlog("ERROR", f"Pipeline {symbol}:{tf}: {e}")
        traceback.print_exc()


_hourly_log_ts = {}  # {(symbol, tf): last_hourly_log_timestamp}

def _log_cycle(symbol, tf, snapshot, htf, tqs, regimen, engines_result=None, skip_reason=None):
    precio = snapshot.get("precio", 0)
    eng = engines_result or {}
    direccion = eng.get("direccion", "?")
    pasa = eng.get("pasa_umbral", False)
    umbral = eng.get("umbral_tqs", 0.65)

    # Scores individuales de cada motor
    mom = eng.get("momentum_score", 0)
    rev = eng.get("reversion_score", 0)
    stg = eng.get("strength_score", 0)
    brk = eng.get("breakout_score", 0)

    # Divergencia y squeeze
    div_sig = eng.get("divergence_signal", "NONE")
    div_conf = eng.get("divergence_confidence", 0)
    squeeze = snapshot.get("squeeze", False)

    # Order flow
    of_delta = eng.get("order_flow_delta", 0)
    of_cvd = eng.get("cvd_slope", 0)
    of_div = eng.get("of_divergencia", False)

    # MTF
    mtf_align = eng.get("mtf_alignment", 0)
    mtf_dir = eng.get("mtf_dir", "?")

    # Brain / skip reason
    brain_str = ""
    if skip_reason:
        brain_str = f"SKIP:{skip_reason}"
    else:
        with _cache_lock:
            bc = _brain_cache.get((symbol, tf))
        if bc:
            brain_str = f"BRAIN:{bc.get('action','?')}({bc.get('confidence',0)}%) {bc.get('consensus','')}"

    # === Log corto siempre (cada ciclo) ===
    mlog("CICLO", f"{symbol}:{tf} P={precio:.5f} DIR:{direccion} "
         f"TQS:{tqs:.2f}/{umbral} {'PASS' if pasa else 'FAIL'} [{regimen}] "
         f"mom:{mom:.2f} rev:{rev:.2f} str:{stg:.2f} brk:{brk:.2f} "
         f"SQZ:{'Y' if squeeze else 'N'} DIV:{div_sig} | {brain_str}")

    # === Log detallado cada hora (o primera vez) ===
    now = time.time()
    key = (symbol, tf)
    last_hourly = _hourly_log_ts.get(key, 0)
    if now - last_hourly >= 3600:
        _hourly_log_ts[key] = now
        _log_hourly_detail(symbol, tf, snapshot, htf, tqs, regimen, eng, skip_reason)


def _log_hourly_detail(symbol, tf, snapshot, htf, tqs, regimen, eng, skip_reason):
    """Log detallado cada hora: pipeline completo para diagnostico."""
    precio = snapshot.get("precio", 0)
    rsi = snapshot.get("rsi", 0)
    adx = snapshot.get("adx", 0)
    di_plus = snapshot.get("di_plus", 0)
    di_minus = snapshot.get("di_minus", 0)
    macd_hist = snapshot.get("macd_hist", 0)
    st = snapshot.get("supertrend", "?")
    atr = snapshot.get("atr", 0)
    squeeze = snapshot.get("squeeze", False)
    ema9 = snapshot.get("ema9", 0)
    ema20 = snapshot.get("ema20", 0)
    ema50 = snapshot.get("ema50", 0)
    ema200 = snapshot.get("ema200", 0)

    session = get_session()
    ia_modo = cfg.state.get("ia_modo", "off")
    motor_on = cfg.state.get("motor_activo", True)

    mlog("REPORT", f"===== REPORTE HORARIO {symbol}:{tf} =====")
    mlog("REPORT", f"  Estado: Motor={'ON' if motor_on else 'OFF'} IA={ia_modo} Session={session}")
    mlog("REPORT", f"  Precio: {precio:.5f} | EMA9:{ema9:.5f} EMA20:{ema20:.5f} EMA50:{ema50:.5f} EMA200:{ema200:.5f}")
    mlog("REPORT", f"  Indicadores: RSI:{rsi:.1f} ADX:{adx:.1f} DI+:{di_plus:.1f} DI-:{di_minus:.1f} "
         f"MACD_H:{macd_hist:.5f} ST:{st} ATR:{atr:.5f} Squeeze:{'SI' if squeeze else 'NO'}")
    mlog("REPORT", f"  HTF Trend: {htf} | Regimen: {regimen}")

    # Inputs de motores (diagnostico)
    zscore = snapshot.get("zscore_h1", 0)
    bb_dist = snapshot.get("bb_distance", 0)
    vol_ratio = snapshot.get("vol_ratio", 1.0)
    cs_base = eng.get("currency_strength_base", snapshot.get("currency_strength_base", 0))
    cs_quote = eng.get("currency_strength_quote", snapshot.get("currency_strength_quote", 0))
    cs_spread = eng.get("currency_spread", snapshot.get("currency_spread", 0))
    n_closes = len(snapshot.get("closes", []))
    n_ema20s = len(snapshot.get("ema20_serie", []))
    n_volumes = len(snapshot.get("volumes", []))

    mlog("REPORT", f"  Inputs motores: zscore={zscore:.3f} bb_dist={bb_dist:.4f} vol_ratio={vol_ratio:.3f} "
         f"cs_spread={cs_spread:.6f} (base={cs_base:.4f} quote={cs_quote:.4f})")
    mlog("REPORT", f"  Series: closes={n_closes} ema20s={n_ema20s} volumes={n_volumes}")

    # Motores individuales
    mom = eng.get("momentum_score", 0)
    mom_dir = eng.get("momentum_dir", "?")
    rev = eng.get("reversion_score", 0)
    rev_dir = eng.get("reversion_dir", "?")
    stg = eng.get("strength_score", 0)
    stg_dir = eng.get("strength_dir", "?")
    brk = eng.get("breakout_score", 0)
    brk_dir = eng.get("breakout_dir", "?")
    direccion = eng.get("direccion", "NEUTRAL")
    pasa = eng.get("pasa_umbral", False)

    mlog("REPORT", f"  Motor Momentum:  score={mom:.3f} dir={mom_dir}")
    mlog("REPORT", f"  Motor Reversion: score={rev:.3f} dir={rev_dir} (zscore={zscore:.2f} bb={bb_dist:.3f} rsi={rsi:.1f})")
    mlog("REPORT", f"  Motor Strength:  score={stg:.3f} dir={stg_dir} (spread={cs_spread:.6f})")
    mlog("REPORT", f"  Motor Breakout:  score={brk:.3f} dir={brk_dir} (vol_ratio={vol_ratio:.2f} sqz={'Y' if squeeze else 'N'} adx={adx:.1f})")
    umbral_r = eng.get("umbral_tqs", 0.65)
    mlog("REPORT", f"  TQS Final: {tqs:.3f} / umbral {umbral_r} -> {'PASA' if pasa else 'NO PASA'}")
    mlog("REPORT", f"  Direccion consensus motores: {direccion}")

    # Divergencia
    div_sig = eng.get("divergence_signal", "NONE")
    div_conf = eng.get("divergence_confidence", 0)
    mlog("REPORT", f"  Divergencia: {div_sig} (conf:{div_conf:.0f}%)")

    # Order Flow
    of_delta = eng.get("order_flow_delta", 0)
    of_cvd = eng.get("cvd_slope", 0)
    of_div = eng.get("of_divergencia", False)
    mlog("REPORT", f"  Order Flow: delta={of_delta:.2f} cvd_slope={of_cvd:.4f} divergencia={'SI' if of_div else 'NO'} "
         f"(volumes_disponibles={n_volumes})")

    # MTF
    mtf_dir = eng.get("mtf_dir", "?")
    mtf_align = eng.get("mtf_alignment", 0)
    mlog("REPORT", f"  MTF: dir={mtf_dir} alignment={mtf_align:.0f}%")

    # Brain / IA decision
    with _cache_lock:
        bc = _brain_cache.get((symbol, tf), {})
    if bc:
        votos = bc.get("votos", {})
        mlog("REPORT", f"  Brain: action={bc.get('action','?')} confidence={bc.get('confidence',0)}% "
             f"consensus={bc.get('consensus','?')}")
        for ia_name, voto in votos.items():
            mlog("REPORT", f"    {ia_name}: {voto.get('action','?')} ({voto.get('confidence',0)}%)")
        if bc.get("reason"):
            mlog("REPORT", f"  Razon: {bc.get('reason','')}")

    # Bloqueo
    if skip_reason:
        mlog("REPORT", f"  >>> BLOQUEADO: {skip_reason}")
        # Explicar por que
        if "TQS" in (skip_reason or ""):
            deficit = 0.65 - tqs
            mlog("REPORT", f"  >>> TQS necesita +{deficit:.3f} para pasar. "
                 f"Motores mas bajos: "
                 f"{'momentum' if mom < 0.3 else ''} "
                 f"{'reversion' if rev < 0.3 else ''} "
                 f"{'strength' if stg < 0.3 else ''} "
                 f"{'breakout' if brk < 0.3 else ''}")
        elif "Regimen" in (skip_reason or ""):
            mlog("REPORT", f"  >>> ADX={adx:.1f} indica mercado choppy/sin tendencia")
        elif "NEUTRAL" in (skip_reason or "") or "direccion" in (skip_reason or "").lower():
            mlog("REPORT", f"  >>> Motores no coinciden en direccion. "
                 f"mom={mom_dir} rev={rev_dir} str={stg_dir} brk={brk_dir}")
    else:
        mlog("REPORT", f"  >>> Pipeline completo ejecutado, IA consultada")

    # Senales activas
    active = get_active()
    if active:
        mlog("REPORT", f"  Senales activas: {len(active)} -> "
             f"{', '.join(s.get('symbol','?')+' '+s.get('action','?') for s in active)}")
    else:
        mlog("REPORT", f"  Senales activas: 0")

    mlog("REPORT", f"===== FIN REPORTE {symbol}:{tf} =====")


def _price_checker():
    """Hilo que verifica SL/TP contra precios actuales."""
    while True:
        try:
            active = get_active()
            for sig in active:
                sym = sig["symbol"]
                price = get_price(sym)
                if price > 0:
                    triggered = check_prices(sym, price)
                    for ts in triggered:
                        # Notificar cierre
                        tg.send_signal_close(ts)
                        wa.send_signal_close(ts)
                        token = cfg.state.get("push_token", "")
                        if token:
                            threading.Thread(
                                target=push_close, args=(token, ts)
                            ).start()
                        # Learning loop
                        try:
                            eng = _engines_cache.get((sym, sig.get("timeframe", "60")), {})
                            registrar_trade(ts, eng, ts.get("regimen", "NORMAL"))
                        except Exception:
                            pass
            time.sleep(5)
        except Exception as e:
            mlog("PRICE", f"Error checker: {e}")
            time.sleep(10)


def _alert_checker():
    """Hilo que verifica price alerts."""
    while True:
        try:
            all_alerts = price_alerts.get_all()
            for alert in all_alerts:
                sym = alert["symbol"]
                price = get_price(sym)
                if price > 0:
                    triggered = price_alerts.check(sym, price)
                    for t in triggered:
                        msg = f"Alerta: {sym} {'por encima' if t['direction']=='above' else 'por debajo'} de {t['target_price']}"
                        tg.send_custom(msg)
                        token = t.get("push_token") or cfg.state.get("push_token", "")
                        if token:
                            push_alert(token, msg)
            time.sleep(10)
        except Exception:
            time.sleep(30)


_SCAN_INTERVAL = 300  # Escaneo completo cada 5 minutos
_SCAN_TIMEFRAMES = ["15", "60", "240"]  # Multi-timeframe: 15m, 1H, 4H
_last_full_scan = 0
_last_daily_reset_date = None


def _full_scan_loop():
    """Hilo que analiza TODOS los pares en multiples timeframes periodicamente.
    Complementa el callback de cierre de vela para no esperar 1h entre analisis."""
    global _last_full_scan, _last_daily_reset_date
    time.sleep(30)  # Esperar a que el motor arranque y tenga datos
    while True:
        try:
            # Reset diario de daily_pnl y cooldowns
            today = datetime.now().strftime("%Y-%m-%d")
            if _last_daily_reset_date != today:
                _last_daily_reset_date = today
                cfg.state["daily_pnl"] = 0.0
                _symbol_cooldown.clear()
                mlog("MOTOR", f"Reset diario: daily_pnl=0, cooldowns limpiados ({today})")

            if not cfg.state.get("motor_activo", True):
                time.sleep(10)
                continue

            watchlist = cfg.state.get("watchlist", [])
            wl_extra = cfg.state.get("watchlist_opcional", [])
            full_wl = list(set(watchlist + wl_extra))
            symbols = list(set(entry.split(":")[0] for entry in full_wl))

            if not symbols:
                time.sleep(10)
                continue

            total = len(symbols) * len(_SCAN_TIMEFRAMES)
            mlog("SCAN", f"Escaneo completo: {len(symbols)} pares x {len(_SCAN_TIMEFRAMES)} TFs = {total}")
            _last_full_scan = time.time()

            for symbol in symbols:
                if not cfg.state.get("motor_activo", True):
                    break
                for tf in _SCAN_TIMEFRAMES:
                    try:
                        _on_new_bar(symbol, tf)
                    except Exception as e:
                        mlog("SCAN", f"Error {symbol}:{tf}: {e}")
                    time.sleep(0.5)  # Pausa entre analisis

            elapsed = time.time() - _last_full_scan
            mlog("SCAN", f"Escaneo completado en {elapsed:.0f}s ({total} analisis)")

            # Esperar hasta el proximo escaneo
            wait = max(0, _SCAN_INTERVAL - elapsed)
            time.sleep(wait)

        except Exception as e:
            mlog("ERROR", f"Scan loop error: {e}")
            time.sleep(30)


def motor_principal():
    """Motor v3.1 event-driven + escaneo periodico."""
    from data_feed import start_streaming, update_subscriptions

    mlog("MOTOR", "Iniciando motor v3.1 (pipeline 9 capas)")
    cleanup_old_charts()

    # Iniciar hilos auxiliares
    threading.Thread(target=_price_checker, daemon=True).start()
    threading.Thread(target=_alert_checker, daemon=True).start()
    threading.Thread(target=_full_scan_loop, daemon=True).start()

    current_pairs = set()

    while True:
        try:
            if not cfg.state.get("motor_activo", True):
                cfg.state["motor_ok"] = False
                time.sleep(5)
                continue

            watchlist = cfg.state.get("watchlist", [])
            wl_extra = cfg.state.get("watchlist_opcional", [])
            full_wl = list(set(watchlist + wl_extra))

            if not full_wl:
                mlog("MOTOR", "Watchlist vacia - esperando")
                time.sleep(5)
                continue

            pairs = set(tuple(p) for p in _parse_watchlist_pairs(full_wl))

            # Suscribir pares de senales activas
            try:
                for s in get_active():
                    sym = s.get("symbol", "")
                    if sym and not any(p[0] == sym for p in pairs):
                        pairs.add((sym, "60"))
            except Exception:
                pass

            if pairs != current_pairs:
                mlog("MOTOR", f"Suscribiendo {len(pairs)} pares")
                if not current_pairs:
                    start_streaming(list(pairs), _on_new_bar)
                else:
                    update_subscriptions(list(pairs))
                current_pairs = pairs
                cfg.state["motor_ok"] = True

            # Sync cache
            for sym, tf in pairs:
                snap = get_snapshot(sym, tf)
                if snap:
                    with _cache_lock:
                        _snapshot_cache[(sym, tf)] = snap

            time.sleep(5)

        except Exception as e:
            cfg.state["motor_ok"] = False
            mlog("ERROR", f"Motor error: {e}")
            time.sleep(10)


# === API REST ENDPOINTS ======================================================

@app.route("/estado")
def estado():
    """Estado completo del sistema para la app."""
    sym = request.args.get("s", "EURUSD")
    tf = request.args.get("tf", "60")
    try:
        return _build_estado(sym, tf)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        mlog("ERROR", f"/estado crash sym={sym}: {e}\n{tb}")
        return jsonify({"error": str(e), "traceback": tb}), 500


def _tech_summary(snapshot):
    """Calcula resumen tecnico estilo Investing.com: buy/sell/neutral por MAs e indicadores."""
    precio = snapshot.get("precio", 0)
    if not precio:
        return {"ma": {"buy": 0, "sell": 0, "neutral": 0, "label": "Neutral"},
                "indicators": {"buy": 0, "sell": 0, "neutral": 0, "label": "Neutral"},
                "summary": {"buy": 0, "sell": 0, "neutral": 0, "label": "Neutral", "score": 0}}

    # --- Moving Averages ---
    ma_buy, ma_sell, ma_neutral = 0, 0, 0
    for ema_key in ("ema9", "ema20", "ema35", "ema50", "ema200"):
        val = snapshot.get(ema_key, 0)
        if val > 0:
            if precio > val:
                ma_buy += 1
            elif precio < val:
                ma_sell += 1
            else:
                ma_neutral += 1
    # SMA20 (bb_mid ~ sma20)
    sma20 = snapshot.get("sma20", 0) or snapshot.get("bb_mid", 0)
    if sma20 > 0:
        if precio > sma20:
            ma_buy += 1
        elif precio < sma20:
            ma_sell += 1
        else:
            ma_neutral += 1
    # Supertrend como MA
    st = snapshot.get("supertrend", "")
    if st == "up":
        ma_buy += 1
    elif st == "down":
        ma_sell += 1
    # VWAP
    vwap = snapshot.get("vwap_proxy", 0)
    if vwap > 0:
        if precio > vwap:
            ma_buy += 1
        elif precio < vwap:
            ma_sell += 1
        else:
            ma_neutral += 1

    # --- Technical Indicators ---
    ind_buy, ind_sell, ind_neutral = 0, 0, 0
    # RSI
    rsi = snapshot.get("rsi", 50)
    if rsi > 60:
        ind_buy += 1
    elif rsi < 40:
        ind_sell += 1
    else:
        ind_neutral += 1
    # Stochastic
    stoch_k = snapshot.get("stoch_k", 50)
    stoch_d = snapshot.get("stoch_d", 50)
    if stoch_k > 80:
        ind_sell += 1
    elif stoch_k < 20:
        ind_buy += 1  # oversold bounce
    elif stoch_k > stoch_d:
        ind_buy += 1
    elif stoch_k < stoch_d:
        ind_sell += 1
    else:
        ind_neutral += 1
    # MACD
    macd = snapshot.get("macd_hist", 0)
    if macd > 0:
        ind_buy += 1
    elif macd < 0:
        ind_sell += 1
    else:
        ind_neutral += 1
    # ADX + DI
    adx = snapshot.get("adx", 0)
    di_plus = snapshot.get("di_plus", 0)
    di_minus = snapshot.get("di_minus", 0)
    if adx > 20:
        if di_plus > di_minus:
            ind_buy += 1
        else:
            ind_sell += 1
    else:
        ind_neutral += 1
    # CCI
    cci = snapshot.get("cci", 0)
    if cci > 100:
        ind_buy += 1
    elif cci < -100:
        ind_sell += 1
    else:
        ind_neutral += 1
    # Williams %R
    wr = snapshot.get("williams_r", -50)
    if wr > -20:
        ind_sell += 1
    elif wr < -80:
        ind_buy += 1
    else:
        ind_neutral += 1
    # Bollinger position
    bb_upper = snapshot.get("bb_upper", 0)
    bb_lower = snapshot.get("bb_lower", 0)
    if bb_upper > 0 and bb_lower > 0:
        bb_mid = (bb_upper + bb_lower) / 2
        if precio > bb_mid:
            ind_buy += 1
        elif precio < bb_mid:
            ind_sell += 1
        else:
            ind_neutral += 1

    def _label(b, s, n):
        total = b + s + n
        if total == 0:
            return "Neutral"
        ratio_buy = b / total
        ratio_sell = s / total
        if ratio_buy >= 0.65:
            return "Strong Buy"
        elif ratio_buy >= 0.45:
            return "Buy"
        elif ratio_sell >= 0.65:
            return "Strong Sell"
        elif ratio_sell >= 0.45:
            return "Sell"
        return "Neutral"

    def _score(b, s, n):
        total = b + s + n
        if total == 0:
            return 0.0
        return round((b - s) / total, 2)  # -1.0 (strong sell) to +1.0 (strong buy)

    tb = ma_buy + ind_buy
    ts = ma_sell + ind_sell
    tn = ma_neutral + ind_neutral

    return {
        "ma": {"buy": ma_buy, "sell": ma_sell, "neutral": ma_neutral,
               "label": _label(ma_buy, ma_sell, ma_neutral), "score": _score(ma_buy, ma_sell, ma_neutral)},
        "indicators": {"buy": ind_buy, "sell": ind_sell, "neutral": ind_neutral,
                       "label": _label(ind_buy, ind_sell, ind_neutral), "score": _score(ind_buy, ind_sell, ind_neutral)},
        "summary": {"buy": tb, "sell": ts, "neutral": tn,
                    "label": _label(tb, ts, tn), "score": _score(tb, ts, tn)},
    }


def _build_estado(sym, tf):
    with _cache_lock:
        snapshot = _snapshot_cache.get((sym, tf)) or {}
        htf = _htf_cache.get((sym, tf), "N/A")
        ctx = _context_cache.get(sym, {})
        engines = _engines_cache.get((sym, tf), {})
        regime = _regime_cache.get((sym, tf), {})
        brain = _brain_cache.get((sym, tf), {})

    # === Calcular en vivo si el cache esta vacio ===
    # Skip heavy computation if fast=1 (used by app on startup)
    fast = request.args.get("fast", "0") == "1"

    if not fast:
        if not snapshot:
            try:
                snapshot = get_snapshot(sym, tf) or {}
                if snapshot:
                    with _cache_lock:
                        _snapshot_cache[(sym, tf)] = snapshot
            except Exception:
                pass

        if not engines and snapshot:
            try:
                ext_features = get_extended_features(sym, tf)
                features = {**snapshot, **ext_features, "par": sym}

                # Regimen
                regimen_str = detectar_regimen(
                    snapshot.get("adx", 0),
                    snapshot.get("atr", 0),
                    snapshot.get("atr_media20", snapshot.get("atr", 0)),
                    snapshot.get("ema20", 0),
                    snapshot.get("ema50", 0),
                    symbol=sym,
                )
                regime = regimen_info(regimen_str, symbol=sym)
                with _cache_lock:
                    _regime_cache[(sym, tf)] = regime

                # Engines
                pesos = get_pesos(regimen_str)
                engines = evaluar_senales(features, regimen_str, pesos)

                # Order Flow
                of_info = calcular_order_flow(
                    features.get("closes", []),
                    features.get("highs", []),
                    features.get("lows", []),
                    features.get("volumes", []),
                )
                engines.update(of_info)

                # MTF
                htf_snap = get_snapshot(sym, "240") if tf == "60" else None
                htf_data = {
                    "ema20": htf_snap.get("ema20", 0) if htf_snap else 0,
                    "ema50": htf_snap.get("ema50", 0) if htf_snap else 0,
                    "adx": htf_snap.get("adx", 0) if htf_snap else 0,
                }
                mtf_data = get_mtf_info(htf_data, engines.get("direccion", "NEUTRAL"))
                engines.update(mtf_data)

                if htf_snap:
                    htf = get_htf_trend(sym, tf)
                    with _cache_lock:
                        _htf_cache[(sym, tf)] = htf

                with _cache_lock:
                    _engines_cache[(sym, tf)] = engines

                # Brain on-the-fly si no hay cache
                if not brain and snapshot and engines:
                    try:
                        from brain import modelo_estadistico
                        sr_info = get_sr_info(
                            features.get("highs", []), features.get("lows", []),
                            features.get("closes", []), snapshot.get("precio", 0), sym,
                        )
                        stats_r = modelo_estadistico(snapshot, engines, regime, mtf_data, of_info, sr_info)
                        brain = {
                            "votos": {
                                "stats": {"action": stats_r["action"], "confidence": stats_r["confidence"]},
                                "groq": {"action": "WAIT", "confidence": 0},
                                "gemini": {"action": "WAIT", "confidence": 0},
                            },
                            "consensus": f"1/1 [Stats]",
                            "action": stats_r["action"],
                            "confidence": stats_r["confidence"],
                            "reason": stats_r.get("reason", ""),
                            "ts": int(time.time()),
                        }
                        with _cache_lock:
                            _brain_cache[(sym, tf)] = brain
                    except Exception:
                        pass
            except Exception as e:
                mlog("ESTADO", f"Error calculando live para {sym}: {e}")

    try:
        active = get_active()
        _enrich_pnl_live(active)
    except Exception:
        active = []
    try:
        stats = get_stats()
    except Exception:
        stats = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "pnl_total": 0}
    try:
        session = get_session()
    except Exception:
        session = "Unknown"
    try:
        countdown = get_session_countdown()
    except Exception:
        countdown = ""
    if not fast:
        try:
            events = get_upcoming_events()
        except Exception:
            events = []
    else:
        events = []
    news = ctx.get("news") or {}
    if not news and not fast:
        try:
            news = get_news_data()
        except Exception:
            news = {"headlines": [], "sentiment": "neutral"}
    if not news:
        news = {"headlines": [], "sentiment": "neutral"}
    try:
        bank = check_bank_holiday()
    except Exception:
        bank = {"is_holiday": False, "name": "", "markets": [], "low_liquidity": False}
    if not fast:
        try:
            cs = get_currency_strength(sym)
        except Exception:
            cs = {"currency_strength_base": 0, "currency_strength_quote": 0, "currency_spread": 0, "currency_matrix": {}}
    else:
        cs = {"currency_strength_base": 0, "currency_strength_quote": 0, "currency_spread": 0, "currency_matrix": {}}
    try:
        portfolio = get_portfolio_info(active, cfg.state["capital"])
    except Exception:
        portfolio = {"exposicion_divisa": {}, "n_operaciones": 0, "capital": cfg.state["capital"], "var": {"var_total": 0, "factor_div": 1, "n_ops": 0}}

    return jsonify({
        # Motor
        "motor_ok": cfg.state.get("motor_ok", False),
        "motor_activo": cfg.state.get("motor_activo", True),
        "ultimo_ciclo": cfg.state.get("ultimo_ciclo", "--"),
        "ts_ciclo": cfg.state.get("ts_ciclo", 0),
        # Config
        "capital": cfg.state["capital"],
        "riesgo_pct": cfg.state["riesgo_pct"],
        "ia_modo": cfg.state.get("ia_modo", "off"),
        "ia_modelo": ia_modelo_actual or cfg.state.get("ia_modelo", ""),
        "ia_tokens": ia_tokens,
        "modo_conservador": cfg.state.get("modo_conservador", False),
        "fallos_consecutivos": cfg.state.get("fallos_consecutivos", 0),
        # Datos mercado
        "precio": snapshot.get("precio", 0),
        "indicadores": {
            "rsi": snapshot.get("rsi", 0),
            "adx": snapshot.get("adx", 0),
            "di_plus": snapshot.get("di_plus", 0),
            "di_minus": snapshot.get("di_minus", 0),
            "macd_hist": snapshot.get("macd_hist", 0),
            "supertrend": snapshot.get("supertrend", ""),
            "squeeze": snapshot.get("squeeze", False),
            "ema9": snapshot.get("ema9", 0),
            "ema20": snapshot.get("ema20", 0),
            "ema50": snapshot.get("ema50", 0),
            "ema200": snapshot.get("ema200", 0),
            "bb_upper": snapshot.get("bb_upper", 0),
            "bb_lower": snapshot.get("bb_lower", 0),
            "atr": snapshot.get("atr", 0),
            "atr_pct": snapshot.get("atr_pct", 0),
            "vwap_proxy": snapshot.get("vwap_proxy", 0),
            "stoch_k": snapshot.get("stoch_k", 0),
            "stoch_d": snapshot.get("stoch_d", 0),
            "cci": snapshot.get("cci", 0),
            "williams_r": snapshot.get("williams_r", 0),
            "volume": snapshot.get("volume", 0),
            "volume_sma": snapshot.get("volume_sma", 0),
            "zscore_h1": snapshot.get("zscore_h1", 0),
            "vol_ratio": snapshot.get("vol_ratio", 1.0),
        },
        # v3.1 Engines
        "engines": {
            "momentum_score": engines.get("momentum_score", 0),
            "momentum_dir": engines.get("momentum_dir", "NEUTRAL"),
            "reversion_score": engines.get("reversion_score", 0),
            "reversion_dir": engines.get("reversion_dir", "NEUTRAL"),
            "strength_score": engines.get("strength_score", 0),
            "strength_dir": engines.get("strength_dir", "NEUTRAL"),
            "breakout_score": engines.get("breakout_score", 0),
            "breakout_dir": engines.get("breakout_dir", "NEUTRAL"),
            "trade_quality_score": engines.get("trade_quality_score", 0),
            "direccion": engines.get("direccion", "NEUTRAL"),
            "divergence_signal": engines.get("divergence_signal", "NONE"),
        },
        # v3.1 Regimen
        "regimen": regime,
        # v3.1 Order Flow
        "order_flow": {
            "delta": engines.get("order_flow_delta", 0),
            "cvd_slope": engines.get("cvd_slope", 0),
            "divergencia": engines.get("of_divergencia", False),
        },
        # v3.1 MTF
        "mtf": {
            "alignment": engines.get("mtf_alignment", 0),
            "direction": engines.get("mtf_dir", "NEUTRAL"),
            "reason": engines.get("mtf_reason", ""),
            "htf_trend": htf,
        },
        # v3.1 Currency Strength
        "currency_strength": cs,
        # v3.1 Portfolio
        "portfolio": portfolio,
        # Sesion
        "session": session,
        "countdown": countdown,
        "events": events,
        "news": news,
        "bank_holiday": bank,
        # Resumen tecnico (gauges)
        "tech_summary": _tech_summary(snapshot),
        # Senal activa
        "senal": active[0] if active else None,
        "senales_activas": len(active),
        # Stats
        "stats": stats,
        # Brain (ultimo analisis de IAs)
        "brain": {
            "votos": brain.get("votos", {}),
            "consensus": brain.get("consensus", ""),
            "action": brain.get("action", "WAIT"),
            "confidence": brain.get("confidence", 0),
            "reason": brain.get("reason", ""),
            "ts": brain.get("ts", 0),
        },
        # Watchlist
        "watchlist": cfg.state.get("watchlist", []),
        "watchlist_opcional": cfg.state.get("watchlist_opcional", []),
        "wl_recomendada": cfg.WL_RECOMENDADA,
        "wl_disponible": cfg.WL_OPCIONAL,
        "wl_catalogo": cfg.WL_CATALOGO,
    })


def _enrich_pnl_live(signals_list):
    """Enriquece señales activas con pnl_usd y pnl_eur en tiempo real."""
    from risk_engine import pnl_usd
    eurusd = get_price("EURUSD") or 1.08
    for sig in signals_list:
        if sig.get("status") != "ACTIVE":
            continue
        try:
            p = get_price(sig["symbol"])
            if not p or p <= 0:
                continue
            sig["current_price"] = p
            entry = sig["entry_price"]
            action = sig["action"]
            lote = sig.get("lote", 0)
            sig["pnl_usd"] = pnl_usd(entry, p, lote, sig["symbol"], action)
            sig["pnl_eur"] = round(sig["pnl_usd"] / eurusd, 2) if eurusd > 0 else sig["pnl_usd"]
        except Exception:
            pass
    return signals_list


@app.route("/signals/active")
def signals_active():
    active = get_active()
    _enrich_pnl_live(active)
    return jsonify(active)


@app.route("/signals/history")
def signals_history():
    limit = request.args.get("limit", 50, type=int)
    include_active = request.args.get("active", "0") == "1"
    history = get_history(limit)
    if include_active:
        active = get_active()
        _enrich_pnl_live(active)
        # Prepend active signals (most recent first, before closed history)
        return jsonify(active + history)
    return jsonify(history)


@app.route("/signals/stats")
def signals_stats():
    return jsonify(get_stats())


@app.route("/signals/cancel/<sig_id>", methods=["POST"])
def signal_cancel(sig_id):
    sym = request.json.get("symbol", "") if request.json else ""
    price = get_price(sym) if sym else None
    result = cancel_signal(sig_id, price)
    if result:
        tg.send_signal_close(result)
        wa.send_signal_close(result)
    return jsonify({"ok": result is not None})


@app.route("/signals/vote/<sig_id>", methods=["POST"])
def signal_vote(sig_id):
    vote = request.json.get("vote", "") if request.json else ""
    ok = vote_signal(sig_id, vote)
    return jsonify({"ok": ok})


@app.route("/signals/delete/<sig_id>", methods=["DELETE"])
def signal_delete(sig_id):
    ok = delete_from_history(sig_id)
    return jsonify({"ok": ok})


@app.route("/signals/share/<sig_id>", methods=["POST"])
def signal_share(sig_id):
    """Reenvía una señal activa a Telegram."""
    active = get_active()
    sig = next((s for s in active if s.get("id") == sig_id), None)
    if not sig:
        # Buscar en historial también
        history = get_history(200)
        sig = next((s for s in history if s.get("id") == sig_id), None)
    if not sig:
        return jsonify({"ok": False, "error": "Signal not found"})
    chart_path = None
    try:
        chart_path = generate_signal_chart(sig, get_ohlcv)
    except Exception as e:
        mlog("SHARE", f"Error grafico: {e}")
        import traceback
        traceback.print_exc()
    # Usar formato correcto segun estado del trade
    status = sig.get("status", "ACTIVE")
    try:
        if status in ("HIT_TP", "HIT_SL", "TRAILING_CLOSE", "CANCELLED", "SWAP_CLOSE", "TREND_PROTECT"):
            tg.send_signal_close(sig)
            wa.send_signal_close(sig)
        else:
            tg.send_signal_open(sig, chart_path=chart_path)
            wa.send_signal_open(sig, chart_path=chart_path)
    except Exception as e:
        mlog("SHARE", f"Error enviando: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})
    return jsonify({"ok": True})


@app.route("/signals/share-history", methods=["POST"])
def signal_share_history():
    """Comparte resumen del historial por periodo (day/week/month/all)."""
    import time as _time
    period = request.args.get("period", "all")
    history = get_history(500)

    now = _time.time()
    if period == "day":
        cutoff = now - 86400
        label = "Hoy"
    elif period == "week":
        cutoff = now - 7 * 86400
        label = "Semana"
    elif period == "month":
        cutoff = now - 30 * 86400
        label = "Mes"
    else:
        cutoff = 0
        label = "Completo"

    filtered = [t for t in history if t.get("timestamp", 0) >= cutoff]
    tg.send_history_summary(filtered, label)
    wa.send_history_summary(filtered, label)
    return jsonify({"ok": True, "trades": len(filtered), "period": period})


# === Motor ON/OFF ===

@app.route("/motor/toggle", methods=["POST"])
def motor_toggle():
    """Enciende/apaga el motor completo."""
    cfg.state["motor_activo"] = not cfg.state.get("motor_activo", True)
    cfg.guardar()
    status = "ON" if cfg.state["motor_activo"] else "OFF"
    mlog("MOTOR", f"Motor {'encendido' if cfg.state['motor_activo'] else 'APAGADO'}")
    return jsonify({"motor_activo": cfg.state["motor_activo"], "status": status})


@app.route("/ia/toggle", methods=["POST"])
def ia_toggle():
    """Alterna IA entre autonomo y off."""
    current = cfg.state.get("ia_modo", "off")
    cfg.state["ia_modo"] = "off" if current == "autonomo" else "autonomo"
    cfg.guardar()
    mlog("IA", f"IA modo: {cfg.state['ia_modo']}")
    return jsonify({"ia_modo": cfg.state["ia_modo"]})


@app.route("/ia/log", methods=["GET"])
def ia_decisions_log():
    """Descarga el log de decisiones IA (ia_decisions.jsonl).
    Params: ?last=N (ultimas N decisiones, default 100)
    """
    from brain import IA_DECISIONS_LOG
    import os
    if not os.path.exists(IA_DECISIONS_LOG):
        return jsonify({"decisions": [], "total": 0})

    last_n = request.args.get("last", 100, type=int)
    try:
        with open(IA_DECISIONS_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # Ultimas N lineas
        recent = lines[-last_n:] if len(lines) > last_n else lines
        decisions = []
        for line in recent:
            line = line.strip()
            if line:
                try:
                    decisions.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return jsonify({"decisions": list(reversed(decisions)), "total": len(lines)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/ia/log/download", methods=["GET"])
def ia_log_download():
    """Descarga el archivo completo ia_decisions.jsonl."""
    from brain import IA_DECISIONS_LOG
    from flask import send_file
    import os
    if not os.path.exists(IA_DECISIONS_LOG):
        return jsonify({"error": "No hay log de decisiones aun"}), 404
    return send_file(IA_DECISIONS_LOG, as_attachment=True, download_name="ia_decisions.jsonl")


# === Config ===

@app.route("/config", methods=["POST"])
def update_config():
    data = request.json or {}
    for key in ["capital", "riesgo_pct", "rr_minimo", "apalancamiento", "avoid_swap"]:
        if key in data:
            cfg.state[key] = data[key]
    if "watchlist" in data:
        cfg.state["watchlist"] = data["watchlist"]
    if "watchlist_opcional" in data:
        cfg.state["watchlist_opcional"] = data["watchlist_opcional"]
    if "push_token" in data:
        cfg.state["push_token"] = data["push_token"]
    cfg.guardar()
    return jsonify({"ok": True})


# === Ranking ===

@app.route("/ranking")
def ranking():
    from correlation import get_ranking, get_dxy_bias
    tf = request.args.get("tf", "60")
    wl = cfg.state.get("watchlist", []) + cfg.state.get("watchlist_opcional", [])
    symbols = list(set(w.split(":")[0] for w in wl))
    r = get_ranking(symbols, tf)
    dxy = get_dxy_bias()
    return jsonify({"ranking": r, "dxy": dxy})


# === Analizar ===

@app.route("/analizar")
def analizar():
    sym = request.args.get("s", "EURUSD")
    tf = request.args.get("tf", "60")
    with _cache_lock:
        snap = _snapshot_cache.get((sym, tf), {})
        engines = _engines_cache.get((sym, tf), {})
        regime = _regime_cache.get((sym, tf), {})
    return jsonify({
        "symbol": sym, "tf": tf,
        "snapshot": snap,
        "engines": engines,
        "regimen": regime,
        "htf": _htf_cache.get((sym, tf), "N/A"),
        "description": describe_snapshot(snap) if snap else "",
    })


# === Price Alerts ===

@app.route("/alerts", methods=["GET"])
def alerts_list():
    token = request.args.get("token", cfg.state.get("push_token", ""))
    return jsonify(price_alerts.get_all(token))


@app.route("/alerts/create", methods=["POST"])
def alerts_create():
    d = request.json or {}
    a = price_alerts.create(d.get("symbol", ""), d.get("target_price", 0),
                            d.get("direction", "above"), d.get("push_token", ""))
    return jsonify(a or {"error": "invalid"})


@app.route("/alerts/delete/<alert_id>", methods=["DELETE"])
def alerts_delete(alert_id):
    return jsonify({"ok": price_alerts.delete(alert_id)})


# === Logs ===

@app.route("/logs")
def logs():
    limit = request.args.get("limit", 500, type=int)
    return jsonify(cfg.get_logs(limit))


@app.route("/logs/download")
def logs_download():
    """Descarga el fichero de log del dia (o de una fecha especifica)."""
    from flask import Response
    date_str = request.args.get("date", datetime.utcnow().strftime("%Y-%m-%d"))
    path = cfg.get_log_file_path(date_str)

    # Intentar leer fichero de disco
    content = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            pass

    # Fallback: logs en memoria
    if not content:
        content = "\n".join(f"[{e['ts']}] [{e['tag']}] {e['msg']}" for e in cfg.get_logs(2000))

    if not content:
        content = "No hay logs disponibles para " + date_str

    return Response(
        content,
        mimetype="text/plain",
        headers={
            "Content-Disposition": f"attachment; filename=motor_{date_str}.log",
            "Content-Type": "text/plain; charset=utf-8",
        }
    )


@app.route("/trades/download")
def trades_download():
    """Descarga el fichero trades.jsonl con TRADE_OPEN/TRADE_CLOSE estructurados."""
    from flask import Response
    path = cfg.data_path("trades.jsonl")
    content = ""
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            content = f"Error leyendo trades.jsonl: {e}"
    if not content:
        content = "trades.jsonl vacio o no existe todavia"
    return Response(
        content,
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": "attachment; filename=trades.jsonl",
            "Content-Type": "application/x-ndjson; charset=utf-8",
        }
    )


@app.route("/logs/dates")
def logs_dates():
    """Lista fechas disponibles de logs."""
    log_dir = cfg.data_path("logs")
    dates = []
    try:
        if os.path.isdir(log_dir):
            for f in sorted(os.listdir(log_dir), reverse=True):
                if f.startswith("motor_") and f.endswith(".log"):
                    dates.append(f.replace("motor_", "").replace(".log", ""))
    except Exception:
        pass
    return jsonify(dates)


# === Monte Carlo ===

@app.route("/montecarlo")
def montecarlo():
    history = get_history(200)
    pnls = [s.get("pnl_usd", 0) for s in history if s.get("status") in ("HIT_TP", "HIT_SL", "TRAILING_CLOSE")]
    result = monte_carlo(pnls, capital_inicial=cfg.state["capital"])
    return jsonify(result)


# === Learning Loop / ML ===

@app.route("/learning/stats")
def learning_stats():
    return jsonify(learn_stats())


@app.route("/learning/train", methods=["POST"])
def learning_train():
    try:
        from ml_model import entrenar_modelo
        from learning_loop import _trades_log
        result = entrenar_modelo(_trades_log)
        return jsonify(result or {"error": "insuficientes datos"})
    except Exception as e:
        return jsonify({"error": str(e)})


# === Model Versioning ===

@app.route("/versions")
def versions():
    return jsonify(version_historial())


# === Calendar ===

@app.route("/calendar")
def calendar():
    return jsonify(get_calendar())


# === Currency Strength ===

@app.route("/strength")
def strength():
    sym = request.args.get("s", "EURUSD")
    return jsonify(get_currency_strength(sym))


# === Telegram ===

@app.route("/telegram/status")
def tg_status():
    return jsonify({
        "configured": bool(cfg.TELEGRAM_BOT_TOKEN),
        "chat_id": cfg.TELEGRAM_CHAT_ID or "no configurado",
    })


# === WhatsApp ===

@app.route("/wa/status")
def wa_status():
    try:
        return jsonify(wa.is_ready())
    except Exception:
        return jsonify({"connected": False})


# === Test Brain (force IA pipeline) ===

@app.route("/test/brain", methods=["POST"])
def test_brain():
    """Fuerza el pipeline de IAs para un par. Salta safety filters y TQS threshold."""
    try:
        sym = request.json.get("symbol", "EURUSD") if request.json else "EURUSD"
        tf = request.json.get("tf", "60") if request.json else "60"

        snapshot = get_snapshot(sym, tf)
        if not snapshot:
            return jsonify({"ok": False, "error": f"No hay datos para {sym}"})

        ext_features = get_extended_features(sym, tf)
        features = {**snapshot, **ext_features, "par": sym}

        # Regimen
        regimen_str = detectar_regimen(
            snapshot.get("adx", 0), snapshot.get("atr", 0),
            snapshot.get("atr_media20", snapshot.get("atr", 0)),
            snapshot.get("ema20", 0), snapshot.get("ema50", 0),
            symbol=sym,
        )
        reg_info = regimen_info(regimen_str, symbol=sym)

        # Engines
        pesos = get_pesos(regimen_str)
        engines_result = evaluar_senales(features, regimen_str, pesos)

        # Order Flow
        of_info = calcular_order_flow(
            features.get("closes", []), features.get("highs", []),
            features.get("lows", []), features.get("volumes", []),
        )
        engines_result.update(of_info)

        # MTF
        htf_snap = get_snapshot(sym, "240") if tf == "60" else None
        htf_data = {
            "ema20": htf_snap.get("ema20", 0) if htf_snap else 0,
            "ema50": htf_snap.get("ema50", 0) if htf_snap else 0,
            "adx": htf_snap.get("adx", 0) if htf_snap else 0,
        }
        mtf_data = get_mtf_info(htf_data, engines_result.get("direccion", "NEUTRAL"))
        engines_result.update(mtf_data)

        htf = get_htf_trend(sym, tf)

        # S/R
        sr_info = get_sr_info(
            features.get("highs", []), features.get("lows", []),
            features.get("closes", []), snapshot.get("precio", 0), sym,
        )

        context = get_full_context(sym, tf)
        context["signals_active"] = get_active()

        # --- 1. Modelo Estadistico ---
        from brain import modelo_estadistico, modelo_groq, modelo_gemini, _consensus_vote
        stats_result = modelo_estadistico(snapshot, engines_result, reg_info, mtf_data, of_info, sr_info)
        mlog("TEST_BRAIN", f"Stats: {stats_result['action']} ({stats_result['confidence']}%)")

        # --- 2. Groq ---
        groq_result = modelo_groq(sym, snapshot, engines_result, context, htf)
        if groq_result:
            mlog("TEST_BRAIN", f"Groq: {groq_result['action']} ({groq_result['confidence']}%)")
        else:
            mlog("TEST_BRAIN", "Groq: sin respuesta")

        # --- 3. Gemini (siempre en test) ---
        gemini_result = modelo_gemini(sym, snapshot, engines_result, context, groq_result, htf)
        if gemini_result:
            mlog("TEST_BRAIN", f"Gemini: {gemini_result['action']} ({gemini_result['confidence']}%)")
        else:
            mlog("TEST_BRAIN", "Gemini: sin respuesta")

        # --- 4. Consensus ---
        consensus = _consensus_vote(stats_result, groq_result, gemini_result)
        mlog("TEST_BRAIN", f"Consensus: {consensus['action']} ({consensus['confidence']}%) {consensus['consensus']}")

        return jsonify({
            "ok": True,
            "symbol": sym,
            "precio": snapshot.get("precio", 0),
            "tqs": engines_result.get("trade_quality_score", 0),
            "regimen": regimen_str,
            "engines": {
                "momentum": engines_result.get("momentum_score", 0),
                "reversion": engines_result.get("reversion_score", 0),
                "strength": engines_result.get("strength_score", 0),
                "breakout": engines_result.get("breakout_score", 0),
                "direccion": engines_result.get("direccion", "NEUTRAL"),
            },
            "votos": {
                "stats": stats_result,
                "groq": groq_result,
                "gemini": gemini_result,
            },
            "consensus": consensus,
        })
    except Exception as e:
        mlog("TEST_BRAIN", f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


# === Test Signal ===

@app.route("/test/signal", methods=["POST"])
def test_signal():
    """Emite una senal de prueba para verificar todo el pipeline."""
    try:
        symbol = "EURUSD"
        price = get_price(symbol) or 1.08500
        action = "BUY"
        sl = round(price - 0.00150, 5)
        tp = round(price + 0.00300, 5)
        rr = 2.0
        votos = {
            "stats": {"action": "BUY", "confidence": 78},
            "groq": {"action": "BUY", "confidence": 82},
            "gemini": {"action": "WAIT", "confidence": 0},
        }
        signal = emit_signal(
            symbol=symbol, action=action, entry_price=price,
            sl=sl, tp=tp, timeframe="60",
            risk_pct=1.0, confidence=80, reason="TEST SIGNAL - Verificacion del sistema",
            lote=0.10, unidades=10000, lote_std=0.10,
            groq_analysis="Test signal to verify pipeline",
            rr_ratio=rr, tqs=0.75, regimen="NORMAL",
            votos=votos, consensus="BUY",
            trailing_stop="none", mtf_alignment=0.6,
            of_delta=15.0, sr_distance=25.0, divergence="NONE",
            riesgo_usd=100,
        )
        if signal:
            mlog("TEST", f"Senal de prueba emitida: {signal['id']}")
            # Enviar a Telegram y WhatsApp
            try:
                tg.send_signal_open(signal)
            except Exception as e:
                mlog("TEST", f"Error enviando a Telegram: {e}")
            try:
                wa.send_signal_open(signal)
            except Exception as e:
                mlog("TEST", f"Error enviando a WhatsApp: {e}")
            return jsonify({"ok": True, "signal": signal})
        else:
            return jsonify({"ok": False, "error": "Ya existe senal activa en EURUSD o error emitiendo"})
    except Exception as e:
        mlog("TEST", f"Error en test signal: {e}")
        return jsonify({"ok": False, "error": str(e)})


# === Manual Signal ===

@app.route("/signals/manual", methods=["POST"])
def signal_manual():
    """Crea una posicion manual con parametros del usuario."""
    try:
        data = request.json or {}
        symbol = data.get("symbol", "").upper()
        action = data.get("action", "").upper()
        entry = float(data.get("entry_price", 0))
        sl = float(data.get("sl", 0))
        tp = float(data.get("tp", 0))
        trailing = data.get("trailing_stop", "none")
        tf = data.get("timeframe", "60")

        if not symbol or action not in ("BUY", "SELL"):
            return jsonify({"ok": False, "error": "symbol y action (BUY/SELL) requeridos"})

        # Obtener precio actual si no se especifica entry
        if entry <= 0:
            entry = get_price(symbol) or 0
        if entry <= 0:
            return jsonify({"ok": False, "error": f"No se pudo obtener precio de {symbol}"})

        # Validar SL/TP basico
        if sl <= 0 or tp <= 0:
            return jsonify({"ok": False, "error": "SL y TP requeridos"})

        from risk_engine import calcular_lote, validar_senal
        ok, msg = validar_senal(action, entry, sl, tp, symbol)
        if not ok:
            return jsonify({"ok": False, "error": msg})

        # Calcular lote
        riesgo_pct = float(data.get("risk_pct", cfg.state.get("riesgo_pct", 1.0)))
        lot_result = calcular_lote(entry, sl, cfg.state["capital"], riesgo_pct, symbol, tp=tp)
        if lot_result["rejected"]:
            return jsonify({"ok": False, "error": lot_result["reject_reason"]})

        sig = emit_signal(
            symbol=symbol, action=action, entry_price=entry,
            sl=sl, tp=tp, timeframe=tf,
            risk_pct=riesgo_pct, confidence=100,
            reason="MANUAL - Posicion abierta manualmente",
            lote=lot_result["lote"], unidades=lot_result["unidades"],
            lote_std=lot_result["lote_std"],
            rr_ratio=lot_result["rr_ratio"],
            tqs=1.0, regimen="MANUAL",
            votos={"manual": {"action": action, "confidence": 100}},
            consensus="MANUAL",
            trailing_stop=trailing,
            riesgo_usd=lot_result["riesgo_usd"],
        )

        if sig:
            mlog("MANUAL", f"Posicion manual: {sig['id']} {action} {symbol} @{entry} SL={sl} TP={tp}")
            try:
                chart_path = generate_signal_chart(sig, get_ohlcv)
                tg.send_signal_open(sig, chart_path=chart_path)
                wa.send_signal_open(sig, chart_path=chart_path)
            except Exception as e:
                mlog("MANUAL", f"Error notificaciones: {e}")
            return jsonify({"ok": True, "signal": sig})
        else:
            return jsonify({"ok": False, "error": f"Ya existe senal activa en {symbol}"})

    except Exception as e:
        mlog("MANUAL", f"Error: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)})


# === Documentacion PDF ===

@app.route("/doc/pdf")
def doc_pdf():
    """Genera y devuelve la documentacion tecnica completa en PDF."""
    from flask import send_file
    try:
        from pdf_report import generate_pdf
        buf = generate_pdf()
        return send_file(buf, mimetype="application/pdf",
                         download_name="ParraCorp_Documentacion.pdf",
                         as_attachment=True)
    except Exception as e:
        mlog("PDF", f"Error generando PDF: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# === Health ===

@app.route("/")
@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "version": "3.2",
        "motor_activo": cfg.state.get("motor_activo", True),
        "ia_modo": cfg.state.get("ia_modo", "off"),
        "motor_ok": cfg.state.get("motor_ok", False),
    })


# === Startup ===

# Configurar Telegram y WhatsApp al arrancar
if cfg.TELEGRAM_BOT_TOKEN and cfg.TELEGRAM_CHAT_ID:
    tg.configure(cfg.TELEGRAM_BOT_TOKEN, cfg.TELEGRAM_CHAT_ID)
if cfg.WA_GROUP_NAME:
    wa.configure(cfg.WA_GROUP_NAME)

if __name__ != "__main__":
    # Gunicorn: iniciar motor en hilo
    motor_thread = threading.Thread(target=motor_principal, daemon=True)
    motor_thread.start()
    mlog("STARTUP", "Motor v3.1 arrancado en hilo de gunicorn")

if __name__ == "__main__":
    motor_thread = threading.Thread(target=motor_principal, daemon=True)
    motor_thread.start()
    app.run(host="0.0.0.0", port=cfg.PORT, debug=False)
