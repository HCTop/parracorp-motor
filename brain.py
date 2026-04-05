# -*- coding: utf-8 -*-
"""
brain.py - Capa 3+4: Consensus Engine v3.1
ParraCorp v3.1

Tres modelos votan en paralelo:
  1. Modelo Estadistico Local (sin IA, gratis)
  2. Groq (Llama 3.3 70B) - Rapido
  3. Gemini 2.5 Flash - Profundo (PAGADO, minimizar uso)

Consensus: 2/3 votos necesarios. Si TQS < 0.65, solo usa Stats (ahorra IA).
Boton ON/OFF: si ia_modo="off", solo modelo estadistico.
"""
import json
import os
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor

from config import GROQ_KEYS, GEMINI_KEYS, CRYPTO, state, lock, log, data_path
from portfolio_risk import check_correlacion

# --- Rotacion de keys ---
_groq_idx = 0
_gemini_idx = 0
_gemini_good_idx = None
_last_call_ts = 0
_MIN_INTERVAL = 1

# --- Contadores de tokens (persistente) ---
_TOKENS_FILE = data_path("ia_tokens.json")
ia_tokens = {"groq": 0, "gemini": 0}

def _load_tokens():
    global ia_tokens
    try:
        if os.path.exists(_TOKENS_FILE):
            with open(_TOKENS_FILE, "r") as f:
                ia_tokens.update(json.load(f))
    except Exception:
        pass

def _save_tokens():
    try:
        with open(_TOKENS_FILE, "w") as f:
            json.dump(ia_tokens, f)
    except Exception:
        pass

_load_tokens()
ia_modelo_actual = ""


def _next_groq_key():
    global _groq_idx
    if not GROQ_KEYS:
        return None
    key = GROQ_KEYS[_groq_idx % len(GROQ_KEYS)]
    _groq_idx += 1
    return key


def _next_gemini_key():
    global _gemini_idx, _gemini_good_idx
    if not GEMINI_KEYS:
        return None
    if _gemini_good_idx is not None:
        return GEMINI_KEYS[_gemini_good_idx % len(GEMINI_KEYS)]
    key = GEMINI_KEYS[_gemini_idx % len(GEMINI_KEYS)]
    _gemini_idx += 1
    return key


# === FILTRO DE SEGURIDAD (Hard Rules) ========================================

def safety_filter(snapshot, context, symbol):
    """Reglas que bloquean ANTES de cualquier analisis."""
    is_crypto = symbol.upper().replace("/", "") in CRYPTO

    # Festivo bancario
    holiday = context.get("bank_holiday", {})
    if holiday.get("is_holiday") and not is_crypto:
        if holiday.get("global_close"):
            return False, f"Festivo global: {holiday.get('name', '')} - mercados cerrados"
        if holiday.get("low_liquidity"):
            return False, f"Festivo bancario: {holiday.get('name', '')} - baja liquidez"

    # Evento de alto impacto
    event = context.get("high_impact_event", {})
    if event.get("active"):
        nivel = event.get("nivel", "precaucion")  # v3.1: 3 niveles
        mins = event.get("minutes_to", 0)
        if nivel == "bloquear" or mins < 15:
            return False, f"Evento {event.get('event', '')} en {mins}min - BLOQUEADO"
        elif nivel == "reducir":
            pass  # Se maneja en risk_engine reduciendo riesgo

    # Weekend
    session = context.get("session", {})
    if session.get("name", "").startswith("Weekend") and not is_crypto:
        return False, "Mercado cerrado (fin de semana)"

    # Volatilidad extrema
    atr_pct = snapshot.get("atr_pct", 0)
    if atr_pct > 5:
        return False, f"Volatilidad extrema (ATR={atr_pct:.1f}%)"

    # Evitar swap
    if not is_crypto and state.get("avoid_swap", True):
        mins_to_close = session.get("minutes_to_close", 999)
        tf = int(snapshot.get("temporalidad", "60"))
        min_required = max(90, tf * 2)
        if 0 < mins_to_close < min_required:
            return False, f"Cierre en {mins_to_close}min - evitar swap"

    # Sesion baja calidad
    quality = session.get("quality", 5)
    if quality <= 2 and not is_crypto:
        return False, f"Sesion {session.get('name', '?')} - calidad {quality}/5 (minimo 3)"

    return True, "OK"


# === MODELO 1: ESTADISTICO LOCAL (sin IA, siempre gratis) ===================

def modelo_estadistico(snapshot, engines_result, regimen_info, mtf_info, of_info, sr_info):
    """
    Modelo estadistico local segun PDF v3.1 Seccion 5.1.
    Sistema de votos por features cuantitativas. No usa IA.
    """
    direction = engines_result.get("direccion", "NEUTRAL")
    regimen = regimen_info.get("regimen", "NORMAL")

    if regimen_info.get("bloqueado"):
        return {"action": "WAIT", "confidence": 90, "reason": f"Regimen {regimen} bloqueado"}
    if direction == "NEUTRAL":
        return {"action": "WAIT", "confidence": 70, "reason": "Sin direccion clara"}
    if mtf_info.get("mtf_dir") == "BLOCK":
        return {"action": "WAIT", "confidence": 80, "reason": mtf_info.get("mtf_reason", "Conflicto MTF")}

    # Sistema de votos por features
    votes_buy = 0
    votes_sell = 0
    reasons = []

    # 1. TQS alto (los 4 motores ya evaluaron el mercado)
    tqs = engines_result.get("trade_quality_score", 0)
    if tqs >= 0.70:
        if direction == "BUY":
            votes_buy += 1
        elif direction == "SELL":
            votes_sell += 1
        reasons.append(f"TQS={tqs:.2f}")

    # 2. Momentum + ADX
    mom_score = engines_result.get("momentum_score", 0)
    adx = snapshot.get("adx", 0)
    if mom_score > 0.7 and adx > 25:
        mom_dir = engines_result.get("momentum_dir", "NEUTRAL")
        if mom_dir == "BUY":
            votes_buy += 1
        elif mom_dir == "SELL":
            votes_sell += 1
        reasons.append(f"MOM={mom_score:.2f}")

    # 3. EMA alignment (precio vs EMAs)
    precio = snapshot.get("precio", 0)
    ema9 = snapshot.get("ema9", 0)
    ema20 = snapshot.get("ema20", 0)
    ema50 = snapshot.get("ema50", 0)
    if precio > 0 and ema9 > 0 and ema20 > 0 and ema50 > 0:
        if precio > ema9 > ema20 > ema50:
            votes_buy += 1
            reasons.append("EMA_ALIGN_UP")
        elif precio < ema9 < ema20 < ema50:
            votes_sell += 1
            reasons.append("EMA_ALIGN_DN")

    # 4. RSI confirmacion (no en extremos contradictorios)
    rsi = snapshot.get("rsi", 50)
    if rsi > 55 and direction == "BUY":
        votes_buy += 1
        reasons.append(f"RSI={rsi:.0f}")
    elif rsi < 45 and direction == "SELL":
        votes_sell += 1
        reasons.append(f"RSI={rsi:.0f}")

    # 5. Z-score
    zscore = snapshot.get("zscore_h1", 0)
    if abs(zscore) > 2.0:
        if zscore < 0:
            votes_buy += 1
            reasons.append(f"Z={zscore:.1f}")
        else:
            votes_sell += 1
            reasons.append(f"Z={zscore:.1f}")

    # 6. Squeeze + vol_ratio
    if snapshot.get("squeeze", False) and snapshot.get("vol_ratio", 1.0) > 1.4:
        votes_buy += 1 if direction == "BUY" else 0
        votes_sell += 1 if direction == "SELL" else 0
        reasons.append("SQZ!")

    # 7. Breakout score alto
    brk_score = engines_result.get("breakout_score", 0)
    if brk_score > 0.7:
        if direction == "BUY":
            votes_buy += 1
        elif direction == "SELL":
            votes_sell += 1
        reasons.append(f"BRK={brk_score:.2f}")

    # 8. Currency spread (si disponible)
    cs_spread = snapshot.get("currency_spread", 0)
    if abs(cs_spread) > 0.0008:
        if cs_spread > 0:
            votes_buy += 1
            reasons.append("CS+")
        else:
            votes_sell += 1
            reasons.append("CS-")

    # 9. Divergencia
    div_sig = engines_result.get("divergence_signal", "NONE")
    if div_sig == "BULLISH_DIV":
        votes_buy += 1
        reasons.append("DIV_BULL")
    elif div_sig == "BEARISH_DIV":
        votes_sell += 1
        reasons.append("DIV_BEAR")

    # 10. MTF alignment (si disponible)
    mtf_align = mtf_info.get("mtf_alignment", 0.5)
    if mtf_align >= 1.0:
        if direction == "BUY":
            votes_buy += 1
        else:
            votes_sell += 1
        reasons.append("MTF=1.0")

    # 11. Order flow (si disponible)
    of_delta = of_info.get("order_flow_delta", 0)
    if abs(of_delta) > 0.3:
        if of_delta > 0:
            votes_buy += 1
        else:
            votes_sell += 1
        reasons.append(f"OF={of_delta:+.2f}")

    # Penalizaciones
    if of_info.get("of_divergencia", False):
        reasons.append("OF_DIV!")
    if sr_info.get("sr_cerca", False):
        reasons.append("SR!")

    # Decidir — necesita minimo 3 votos en la misma direccion
    total_votes = votes_buy + votes_sell
    if total_votes == 0:
        return {"action": "WAIT", "confidence": 40, "reason": "Sin votos features"}

    if votes_buy >= 3 and votes_buy > votes_sell:
        action = "BUY"
        conf = min(55 + votes_buy * 8, 95)
    elif votes_sell >= 3 and votes_sell > votes_buy:
        action = "SELL"
        conf = min(55 + votes_sell * 8, 95)
    elif votes_buy > votes_sell and votes_buy >= 2:
        action = "BUY"
        conf = min(45 + votes_buy * 8, 70)
        reasons.append("(pocos votos)")
    elif votes_sell > votes_buy and votes_sell >= 2:
        action = "SELL"
        conf = min(45 + votes_sell * 8, 70)
        reasons.append("(pocos votos)")
    else:
        action = "WAIT"
        conf = 45

    # Penalizar por OF divergencia y SR
    if of_info.get("of_divergencia", False):
        conf = max(conf - 10, 20)
    if sr_info.get("sr_cerca", False):
        conf = max(conf - 10, 20)

    return {
        "action": action,
        "confidence": conf,
        "reason": " | ".join(reasons),
    }


# === MODELO 2: GROQ (Rapido) ================================================

def _call_groq(prompt, max_tokens=400):
    global ia_modelo_actual
    key = _next_groq_key()
    if not key:
        return None
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "max_tokens": max_tokens,
                "response_format": {"type": "json_object"},
            },
            timeout=15,
        )
        if r.status_code == 429:
            log("GROQ", "Rate limited, rotando key")
            # Reintentar con siguiente key
            key2 = _next_groq_key()
            if key2:
                r = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key2}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.3,
                        "max_tokens": max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=15,
                )
                if r.status_code != 200:
                    return None
            else:
                return None
        if r.status_code != 200:
            log("GROQ", f"Error {r.status_code}: {r.text[:200]}")
            return None
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        ia_tokens["groq"] += data.get("usage", {}).get("total_tokens", 0)
        _save_tokens()
        ia_modelo_actual = "groq/llama-3.3-70b"
        return json.loads(content)
    except Exception as e:
        log("GROQ", f"Error: {e}")
        return None


def _interpret_context(symbol, snapshot, engines_result, context, htf_trend="N/A", sr_info=None):
    """Genera resumen interpretado del mercado para la IA."""
    precio = snapshot.get("precio", 0)
    rsi = snapshot.get("rsi", 50)
    adx = snapshot.get("adx", 0)
    macd = snapshot.get("macd_hist", 0)
    st = snapshot.get("supertrend", "?")
    squeeze = snapshot.get("squeeze", False)
    ema9 = snapshot.get("ema9", 0)
    ema20 = snapshot.get("ema20", 0)
    ema50 = snapshot.get("ema50", 0)
    ema200 = snapshot.get("ema200", 0)
    atr_pct = snapshot.get("atr_pct", 0)
    vol_ratio = snapshot.get("vol_ratio", 1.0)
    zscore = snapshot.get("zscore_h1", 0)
    stoch_k = snapshot.get("stoch_k", 50)
    direction = engines_result.get("direccion", "NEUTRAL")
    tqs = engines_result.get("trade_quality_score", 0)
    regimen = engines_result.get("regimen", "NORMAL")

    lines = []

    # Tendencia
    emas_list = [ema9, ema20, snapshot.get("ema35", 0), ema50, ema200]
    above_emas = sum(1 for e in emas_list if e > 0 and precio > e)
    total_emas = sum(1 for e in emas_list if e > 0)
    if total_emas > 0 and above_emas >= total_emas * 0.7:
        lines.append(f"TENDENCIA ALCISTA: precio sobre {above_emas}/{total_emas} EMAs")
    elif total_emas > 0 and above_emas <= total_emas * 0.3:
        lines.append(f"TENDENCIA BAJISTA: precio bajo {total_emas-above_emas}/{total_emas} EMAs")
    else:
        lines.append("TENDENCIA LATERAL: precio entre EMAs, sin direccion clara")

    if st == "up":
        lines.append("Supertrend ALCISTA (soporte activo)")
    elif st == "down":
        lines.append("Supertrend BAJISTA (resistencia activa)")

    # Cruce EMA 35/50
    ema35 = snapshot.get("ema35", 0)
    ema50 = snapshot.get("ema50", 0)
    cross = snapshot.get("ema35_50_cross", "NONE")
    if cross == "GOLDEN":
        lines.append("🔥 CRUCE ALCISTA EMA35/50: señal de compra fuerte")
    elif cross == "DEATH":
        lines.append("🔥 CRUCE BAJISTA EMA35/50: señal de venta fuerte")
    elif ema35 > 0 and ema50 > 0:
        if ema35 > ema50:
            lines.append(f"EMA35 sobre EMA50: tendencia alcista confirmada")
        else:
            lines.append(f"EMA35 bajo EMA50: tendencia bajista confirmada")

    # Momentum
    if adx > 30:
        di_plus = snapshot.get("di_plus", 0)
        di_minus = snapshot.get("di_minus", 0)
        dir_text = "compradores" if di_plus > di_minus else "vendedores"
        lines.append(f"MOMENTUM FUERTE: ADX={adx:.0f}, dominan {dir_text}")
    elif adx > 20:
        lines.append(f"Momentum moderado: ADX={adx:.0f}")
    else:
        lines.append(f"SIN MOMENTUM: ADX={adx:.0f} (mercado sin fuerza, evitar)")

    # RSI
    if rsi > 70:
        lines.append(f"⚠️ SOBRECOMPRA: RSI={rsi:.0f} - NO comprar, posible venta")
    elif rsi < 30:
        lines.append(f"⚠️ SOBREVENTA: RSI={rsi:.0f} - NO vender, posible compra")
    elif rsi > 60:
        lines.append(f"RSI={rsi:.0f} alcista")
    elif rsi < 40:
        lines.append(f"RSI={rsi:.0f} bajista")
    else:
        lines.append(f"RSI={rsi:.0f} neutral")

    # MACD
    if macd > 0:
        lines.append(f"MACD histograma positivo ({macd:.6f}) - presion compradora")
    elif macd < 0:
        lines.append(f"MACD histograma negativo ({macd:.6f}) - presion vendedora")

    # Volatilidad
    if squeeze:
        lines.append("🔥 SQUEEZE ACTIVO: compresion de volatilidad, posible explosion")
    if vol_ratio > 1.5:
        lines.append(f"Volumen {vol_ratio:.1f}x por encima de la media - movimiento significativo")
    elif vol_ratio < 0.7:
        lines.append(f"Volumen bajo ({vol_ratio:.1f}x) - señales menos fiables")

    # Z-Score (mean reversion)
    if abs(zscore) > 2.0:
        dir_z = "sobrevalorado (posible venta)" if zscore > 0 else "infravalorado (posible compra)"
        lines.append(f"Z-Score={zscore:.1f}: precio {dir_z}")

    # Stoch
    if stoch_k > 80:
        lines.append(f"Estocastico sobrecomprado ({stoch_k:.0f})")
    elif stoch_k < 20:
        lines.append(f"Estocastico sobrevendido ({stoch_k:.0f})")

    # Motores
    mom = engines_result.get("momentum_score", 0)
    rev = engines_result.get("reversion_score", 0)
    stren = engines_result.get("strength_score", 0)
    brk = engines_result.get("breakout_score", 0)
    motors = []
    if mom > 0.5: motors.append(f"Momentum({mom:.0%})")
    if rev > 0.5: motors.append(f"Reversion({rev:.0%})")
    if stren > 0.5: motors.append(f"Strength({stren:.0%})")
    if brk > 0.5: motors.append(f"Breakout({brk:.0%})")
    if motors:
        lines.append(f"Motores activos: {', '.join(motors)} -> {direction}")
    else:
        lines.append(f"Ningun motor con señal fuerte")

    # HTF
    if htf_trend and htf_trend != "N/A":
        lines.append(f"Timeframe superior: {htf_trend}")

    # Divergencias
    div = engines_result.get("divergence_signal", "NONE")
    if div != "NONE":
        lines.append(f"⚠️ DIVERGENCIA detectada: {div}")

    # Order flow
    of_delta = engines_result.get("order_flow_delta", 0)
    if abs(of_delta) > 0.3:
        of_dir = "compradores dominan" if of_delta > 0 else "vendedores dominan"
        lines.append(f"Order Flow: {of_dir} (delta={of_delta:+.2f})")

    # S/R levels
    if sr_info:
        sr_niveles = sr_info.get("sr_niveles", [])
        sr_dist = sr_info.get("sr_distance_pips", 999)
        sr_zone = sr_info.get("sr_zone_type", "NINGUNO")
        sr_cerca = sr_info.get("sr_cerca", False)

        if sr_niveles:
            soportes = [n for n in sr_niveles if n["tipo"] == "S"]
            resistencias = [n for n in sr_niveles if n["tipo"] == "R"]
            if soportes:
                top_s = soportes[0]
                lines.append(f"SOPORTE clave: {top_s['precio']:.5g} (fuerza {top_s['fuerza']})")
            if resistencias:
                top_r = resistencias[0]
                lines.append(f"RESISTENCIA clave: {top_r['precio']:.5g} (fuerza {top_r['fuerza']})")

            if sr_cerca:
                if sr_zone == "R":
                    lines.append(f"CERCA DE RESISTENCIA ({sr_dist:.0f} pips)")
                elif sr_zone == "S":
                    lines.append(f"CERCA DE SOPORTE ({sr_dist:.0f} pips)")
            elif sr_dist < 30:
                lines.append(f"S/R cercano a {sr_dist:.0f} pips ({sr_zone})")

            # Resumen de niveles para contexto
            all_levels = sorted(sr_niveles, key=lambda x: x["precio"])
            level_strs = [f"{'S' if n['tipo']=='S' else 'R'}:{n['precio']:.5g}" for n in all_levels[:5]]
            lines.append(f"Niveles S/R: {' | '.join(level_strs)}")

    # Racha
    fallos = state.get("fallos_consecutivos", 0)
    if fallos >= 3:
        lines.append(f"⚠️ RACHA NEGATIVA: {fallos} fallos consecutivos - ser MUY selectivo")
    elif fallos >= 2:
        lines.append(f"Precaucion: {fallos} fallos recientes")

    return "\n".join(lines)


def modelo_groq(symbol, snapshot, engines_result, context, htf_trend="N/A", sr_info=None):
    """
    Llamada a Groq con prompt interpretado v4.
    """
    precio = snapshot.get("precio", 0)
    atr = snapshot.get("atr", 0)
    tf = snapshot.get("temporalidad", "60")
    session = context.get("session", {})
    tqs = engines_result.get("trade_quality_score", 0)
    regimen = engines_result.get("regimen", "NORMAL")

    interpretation = _interpret_context(symbol, snapshot, engines_result, context, htf_trend, sr_info)

    prompt = f"""Eres un trader profesional. Los motores cuantitativos ya aprobaron esta señal (TQS={tqs:.0%}).
Tu rol es CONFIRMAR o RECHAZAR la operacion basandote en el contexto del mercado.
IMPORTANTE: Si la tendencia es clara y los motores la confirman, OPERA. No rechaces por RSI extremo en tendencia.

{symbol} | TF={tf}min | Precio={precio} | ATR={atr} ({snapshot.get('atr_pct',0):.2f}%)
Regimen: {regimen} | TQS: {tqs:.0%} | Sesion: {session.get('name','?')} (cal {session.get('quality',0)}/5)

=== ANALISIS DEL MERCADO ===
{interpretation}

=== HISTORIAL RECIENTE (ultimas 8 velas) ===
{snapshot.get('hist_chart', 'No disponible')}

=== REGLAS ===
- RSI extremo (>80 o <20) en RANGO: precaucion. En TENDENCIA: operar a favor
- ADX>25: tendencia fuerte, operar a favor. ADX<15: evitar
- Si los motores y el precio confirman la direccion: operar con confianza alta
- SL: 1.0-2.0 ATR | TP: 2.0-4.0 ATR (R:R minimo 2:1)
- Trailing: "none" normal, "breakeven" si momentum medio, "atr1" si ADX>30
- WAIT solo si hay contradiccion CLARA entre indicadores o riesgo evidente

JSON: {{"action":"BUY|SELL|WAIT","confidence":0-100,"sl_atr":1.5,"tp_atr":3.0,"risk_pct":1.0,"trailing_stop":"none","analysis":"1 frase con la razon"}}
"""
    log("GROQ", f"{symbol} Prompt enviado ({len(prompt)} chars)")
    result = _call_groq(prompt, max_tokens=300)
    if not result:
        return None

    action = result.get("action", "WAIT").upper()
    confidence = int(result.get("confidence", 0))
    analysis = result.get("analysis", "")
    log("GROQ", f"{symbol} -> {action} ({confidence}%) {analysis[:80]}")

    return {
        "action": action,
        "confidence": confidence,
        "reason": analysis,
        "sl_atr": float(result.get("sl_atr", 1.5)),
        "tp_atr": float(result.get("tp_atr", 3.0)),
        "risk_pct": float(result.get("risk_pct", 1.0)),
        "trailing_stop": result.get("trailing_stop", "none"),
    }


# === MODELO 3: GEMINI (Profundo - PAGADO, minimizar) ========================

_GEMINI_MODELS = ["gemini-2.5-flash"]


def _extract_gemini_text(data):
    candidates = data.get("candidates", [])
    if not candidates:
        return None
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    for part in reversed(parts):
        if part.get("thought"):
            continue
        if "text" in part:
            return part["text"].strip()
    for part in parts:
        if "text" in part:
            return part["text"].strip()
    return None


def _parse_json_response(text):
    if not text:
        return None
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find('{')
    end = cleaned.rfind('}')
    if start != -1 and end > start:
        try:
            return json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _call_gemini(prompt, max_tokens=400):
    global ia_modelo_actual, _gemini_good_idx, _gemini_idx
    if not GEMINI_KEYS:
        return None

    for model_name in _GEMINI_MODELS:
        for attempt in range(len(GEMINI_KEYS)):
            key = _next_gemini_key()
            if attempt > 0:
                _gemini_good_idx = None
                key = GEMINI_KEYS[(_gemini_idx) % len(GEMINI_KEYS)]
                _gemini_idx += 1
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.3,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            }
            if "2.5" in model_name:
                payload["generationConfig"]["thinkingConfig"] = {"thinkingBudget": 0}
            try:
                r = requests.post(url, json=payload, timeout=30)
                if r.status_code == 429:
                    log("GEMINI", f"Key {key[:8]}... quota 429")
                    time.sleep(1)
                    continue
                if r.status_code != 200:
                    log("GEMINI", f"Key {key[:8]}... HTTP {r.status_code}")
                    continue
                data = r.json()
                text = _extract_gemini_text(data)
                if not text:
                    continue
                parsed = _parse_json_response(text)
                if not parsed:
                    return None
                ia_modelo_actual = model_name
                ia_tokens["gemini"] += len(prompt.split()) + len(text.split())
                _save_tokens()
                _gemini_good_idx = GEMINI_KEYS.index(key) if key in GEMINI_KEYS else None
                log("GEMINI", f"OK ({key[:8]}...) {model_name}")
                return parsed
            except Exception as e:
                log("GEMINI", f"ERROR {key[:8]}...: {e}")
                continue
    return None


def modelo_gemini(symbol, snapshot, engines_result, context, groq_result=None, htf_trend="N/A", sr_info=None):
    """
    Analisis independiente con Gemini v4 (prompt interpretado).
    """
    precio = snapshot.get("precio", 0)
    atr = snapshot.get("atr", 0)
    tf = snapshot.get("temporalidad", "60")
    session = context.get("session", {})
    tqs = engines_result.get("trade_quality_score", 0)
    regimen = engines_result.get("regimen", "NORMAL")
    news = context.get("news", {})
    headlines = news.get("headlines", [])[:3]
    news_text = "\n".join(f"- {h}" for h in headlines) if headlines else "Sin noticias relevantes."

    interpretation = _interpret_context(symbol, snapshot, engines_result, context, htf_trend, sr_info)

    prompt = f"""RESPONDE UNICAMENTE CON JSON VALIDO.

Los motores cuantitativos ya aprobaron esta señal (TQS={tqs:.0%}). Tu rol es CONFIRMAR o RECHAZAR.
IMPORTANTE: Si la tendencia es clara y el momentum lo confirma, OPERA. RSI extremo en tendencia NO es razon para rechazar.

{symbol} | TF={tf}min | Precio={precio} | ATR={atr} ({snapshot.get('atr_pct',0):.2f}%)
Regimen: {regimen} | TQS: {tqs:.0%} | Sesion: {session.get('name','?')} (cal {session.get('quality',0)}/5)

=== ANALISIS DEL MERCADO ===
{interpretation}

=== HISTORIAL RECIENTE (ultimas 8 velas) ===
{snapshot.get('hist_chart', 'No disponible')}

=== NOTICIAS ===
{news_text}
Sentimiento: {news.get('sentiment','neutral')}

=== REGLAS ===
- RSI extremo en RANGO: precaucion. En TENDENCIA: operar a favor de la tendencia
- ADX>25: tendencia fuerte, confirma la operacion. ADX<15: evitar
- Noticias fuertes contra la direccion: WAIT
- SL: 1.0-2.0 ATR | TP: 2.0-4.0 ATR (R:R minimo 2:1)
- Trailing: "none" normal, "breakeven" si momentum medio, "atr1" si ADX>30
- WAIT solo si hay contradiccion CLARA o riesgo alto evidente

JSON: {{"action":"BUY|SELL|WAIT","confidence":0-100,"sl_atr":1.5,"tp_atr":3.0,"risk_pct":1.0,"trailing_stop":"none","reason":"1 frase"}}"""

    log("GEMINI", f"{symbol} Prompt enviado ({len(prompt)} chars)")
    result = _call_gemini(prompt, max_tokens=300)
    if not result:
        return None

    action = result.get("action", "WAIT").upper()
    confidence = int(result.get("confidence", 0))
    reason = result.get("reason", "")
    log("GEMINI", f"{symbol} -> {action} ({confidence}%) {reason[:80]}")

    return {
        "action": action,
        "confidence": confidence,
        "reason": reason,
        "sl_atr": float(result.get("sl_atr", 1.5)),
        "tp_atr": float(result.get("tp_atr", 3.0)),
        "risk_pct": float(result.get("risk_pct", 1.0)),
        "trailing_stop": result.get("trailing_stop", "none"),
    }


# === CONSENSUS ENGINE (2/3 votos) ============================================

def _consensus_vote(stats_result, groq_result, gemini_result):
    """
    Combina 3 votos. Necesita 2/3 de acuerdo.

    Returns: dict con action, confidence, sl_atr, tp_atr, risk_pct, trailing, reason, votos
    """
    votos = []

    # Voto Stats (siempre disponible)
    v_stats = stats_result.get("action", "WAIT")
    c_stats = stats_result.get("confidence", 0)
    votos.append(("STATS", v_stats, c_stats))

    # Voto Groq (puede ser None)
    if groq_result:
        v_groq = groq_result.get("action", "WAIT")
        c_groq = groq_result.get("confidence", 0)
        votos.append(("GROQ", v_groq, c_groq))
    else:
        votos.append(("GROQ", "WAIT", 0))

    # Voto Gemini (puede ser None)
    if gemini_result:
        v_gemini = gemini_result.get("action", "WAIT")
        c_gemini = gemini_result.get("confidence", 0)
        votos.append(("GEMINI", v_gemini, c_gemini))
    else:
        votos.append(("GEMINI", "WAIT", 0))

    # Contar votos por accion
    buy_count = sum(1 for _, a, _ in votos if a == "BUY")
    sell_count = sum(1 for _, a, _ in votos if a == "SELL")
    wait_count = sum(1 for _, a, _ in votos if a == "WAIT")

    # 2/3 necesarios
    if buy_count >= 2:
        final_action = "BUY"
    elif sell_count >= 2:
        final_action = "SELL"
    else:
        final_action = "WAIT"

    # Confidence = promedio de los votos concordantes
    concordantes = [(n, c) for n, a, c in votos if a == final_action]
    if concordantes:
        final_confidence = int(sum(c for _, c in concordantes) / len(concordantes))
    else:
        final_confidence = 0

    # Gate: confianza minima 65%
    if final_action in ("BUY", "SELL") and final_confidence < 65:
        mlog("BRAIN", f"Confianza {final_confidence}% < 65% minimo -> WAIT")
        final_action = "WAIT"

    # Parametros: prioridad Gemini > Groq > Stats
    params_source = gemini_result or groq_result or {}
    sl_atr = params_source.get("sl_atr", 1.5)
    tp_atr = params_source.get("tp_atr", 3.0)
    risk_pct = params_source.get("risk_pct", 1.0)
    trailing = params_source.get("trailing_stop", "none")

    # Reason combinada
    reason_parts = []
    for name, action, conf in votos:
        emoji = "\u2705" if action == final_action else "\u274C"
        reason_parts.append(f"{name}:{action}({conf}%){emoji}")

    reason_detail = stats_result.get("reason", "")
    if groq_result:
        reason_detail += " | " + groq_result.get("reason", "")
    if gemini_result:
        reason_detail += " | " + gemini_result.get("reason", "")

    votos_info = {
        "stats": {"action": v_stats, "confidence": c_stats},
        "groq": {"action": votos[1][1], "confidence": votos[1][2]},
        "gemini": {"action": votos[2][1], "confidence": votos[2][2]},
    }

    return {
        "action": final_action,
        "confidence": final_confidence,
        "sl_atr": sl_atr,
        "tp_atr": tp_atr,
        "risk_pct": min(max(risk_pct, 0.5), 2.0),
        "trailing_stop": trailing,
        "reason": " | ".join(reason_parts) + "\n" + reason_detail,
        "votos": votos_info,
        "consensus": f"{max(buy_count, sell_count, wait_count)}/3",
    }


# === PIPELINE PRINCIPAL ======================================================

def analyze(symbol, snapshot, engines_result, context, regimen_info, mtf_info, of_info, sr_info, htf_trend="N/A"):
    """
    Pipeline v3.1 completo.

    1. Safety filter
    2. Correlation check
    3. Modelo Estadistico (siempre)
    4. Si TQS >= umbral y ia_modo != "off":
       a. Groq + Gemini en PARALELO (spec PDF v3.1)
    5. Consensus vote (2/3)

    Returns: dict con action, confidence, sl, tp, risk_pct, votos, etc.
    """
    global _last_call_ts

    result = {
        "action": "WAIT", "confidence": 0,
        "entry": snapshot.get("precio", 0),
        "sl": 0, "tp": 0,
        "sl_atr_mult": 1.5, "tp_atr_mult": 3.0,
        "risk_pct": 1.0,
        "timeframe": snapshot.get("temporalidad", "60"),
        "reason": "",
        "groq_analysis": "",
        "blocked": False, "blocked_reason": "",
        "trailing_stop": "none",
        "votos": {},
        "consensus": "0/3",
        "tqs": engines_result.get("trade_quality_score", 0),
        "regimen": regimen_info.get("regimen", "NORMAL"),
    }

    # 1. Safety filter
    allowed, reason = safety_filter(snapshot, context, symbol)
    if not allowed:
        result["blocked"] = True
        result["blocked_reason"] = reason
        result["reason"] = reason
        log("FILTER", f"{symbol} BLOQUEADO: {reason}")
        return result

    # 2. Correlation check
    active_signals = context.get("signals_active", [])
    direction = engines_result.get("direccion", "NEUTRAL")
    if direction != "NEUTRAL" and active_signals:
        corr_ok, corr_reason = check_correlacion(symbol, direction, active_signals)
        if not corr_ok:
            result["blocked"] = True
            result["blocked_reason"] = corr_reason
            result["reason"] = corr_reason
            log("CORR", f"{symbol} BLOQUEADO: {corr_reason}")
            return result

    # 3. Modelo Estadistico (siempre se ejecuta, gratis)
    stats_result = modelo_estadistico(snapshot, engines_result, regimen_info, mtf_info, of_info, sr_info)
    log("STATS", f"{symbol} -> {stats_result['action']} ({stats_result['confidence']}%)")

    # 4. Decidir si consultar IA
    tqs = engines_result.get("trade_quality_score", 0)
    ia_modo = state.get("ia_modo", "off")

    groq_result = None
    gemini_result = None

    # Umbral TQS segun timeframe (15m mas exigente por ruido)
    tf_val = str(snapshot.get("temporalidad", "60"))
    tqs_umbral = engines_result.get("umbral_tqs", 0.65)
    if tf_val in ("1", "5", "15"):
        tqs_umbral = max(tqs_umbral, 0.75)
    if ia_modo == "off" or tqs < tqs_umbral:
        # Solo Stats, sin IA (ahorra dinero)
        if ia_modo == "off":
            log("BRAIN", f"{symbol} IA apagada, solo Stats")
        else:
            log("BRAIN", f"{symbol} TQS={tqs:.2f} < 0.65, skip IA")

        result.update({
            "action": stats_result["action"],
            "confidence": stats_result["confidence"],
            "reason": f"[Solo Stats] {stats_result['reason']}",
            "votos": {"stats": {"action": stats_result["action"], "confidence": stats_result["confidence"]}},
            "consensus": "1/1",
        })
    else:
        # Rate limit
        now = time.time()
        if now - _last_call_ts < _MIN_INTERVAL:
            result["reason"] = "Cooldown IA"
            return result
        _last_call_ts = now

        # 4a+4b. Groq + Gemini EN PARALELO (spec PDF v3.1)
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_groq = executor.submit(
                modelo_groq, symbol, snapshot, engines_result, context, htf_trend, sr_info
            )
            future_gemini = executor.submit(
                modelo_gemini, symbol, snapshot, engines_result, context, None, htf_trend, sr_info
            )
            groq_result = future_groq.result()
            gemini_result = future_gemini.result()

        log("BRAIN", f"{symbol} IA paralela: Groq={groq_result.get('action','?') if groq_result else 'FAIL'} "
            f"Gemini={gemini_result.get('action','?') if gemini_result else 'FAIL'}")

        # 5. Consensus
        consensus = _consensus_vote(stats_result, groq_result, gemini_result)

        result.update({
            "action": consensus["action"],
            "confidence": consensus["confidence"],
            "sl_atr_mult": consensus["sl_atr"],
            "tp_atr_mult": consensus["tp_atr"],
            "risk_pct": consensus["risk_pct"],
            "trailing_stop": consensus["trailing_stop"],
            "reason": consensus["reason"],
            "votos": consensus["votos"],
            "consensus": consensus["consensus"],
        })

        if groq_result:
            result["groq_analysis"] = groq_result.get("reason", "")

    # Calcular SL/TP final
    precio = snapshot.get("precio", 0)
    atr = snapshot.get("atr", 0)
    action = result["action"]
    sl_mult = result.get("sl_atr_mult", 1.5)
    tp_mult = result.get("tp_atr_mult", 3.0)

    # Validar R:R minimo
    rr = tp_mult / sl_mult if sl_mult > 0 else 0
    rr_min = state.get("rr_minimo", 1.5)
    if rr < rr_min and action in ("BUY", "SELL"):
        tp_mult = sl_mult * rr_min
        result["tp_atr_mult"] = tp_mult

    if action in ("BUY", "SELL"):
        if action == "BUY":
            sl_base = round(precio - atr * sl_mult, 6)
            tp_base = round(precio + atr * tp_mult, 6)
        else:
            sl_base = round(precio + atr * sl_mult, 6)
            tp_base = round(precio - atr * tp_mult, 6)

        # Ajustar SL/TP con S/R si hay niveles disponibles
        sl_final = sl_base
        tp_final = tp_base
        sr_niveles = sr_info.get("sr_niveles", []) if sr_info else []

        if sr_niveles and atr > 0:
            soportes = sorted([n["precio"] for n in sr_niveles if n["tipo"] == "S"], reverse=True)
            resistencias = sorted([n["precio"] for n in sr_niveles if n["tipo"] == "R"])

            if action == "BUY":
                # SL: buscar soporte justo debajo del SL base (refuerza el SL)
                for s in soportes:
                    if sl_base * 0.998 < s < precio:
                        # Colocar SL ligeramente debajo del soporte
                        candidate = round(s - atr * 0.2, 6)
                        # No alejarlo mas de 0.5 ATR del SL original
                        if abs(candidate - sl_base) < atr * 0.5:
                            sl_final = candidate
                            break
                # TP: buscar resistencia como objetivo
                for r in resistencias:
                    if r > precio and r > tp_base * 0.95:
                        # Usar resistencia como TP si esta cerca del TP base
                        if abs(r - tp_base) < atr * 1.0:
                            tp_final = round(r - atr * 0.1, 6)
                            break
            else:  # SELL
                # SL: buscar resistencia justo encima del SL base
                for r in resistencias:
                    if precio < r < sl_base * 1.002:
                        candidate = round(r + atr * 0.2, 6)
                        if abs(candidate - sl_base) < atr * 0.5:
                            sl_final = candidate
                            break
                # TP: buscar soporte como objetivo
                for s in soportes:
                    if s < precio and s < tp_base * 1.05:
                        if abs(s - tp_base) < atr * 1.0:
                            tp_final = round(s + atr * 0.1, 6)
                            break

            # Validar que R:R sigue siendo aceptable tras ajuste
            sl_dist = abs(precio - sl_final)
            tp_dist = abs(precio - tp_final)
            if sl_dist > 0 and tp_dist / sl_dist < rr_min:
                # Revertir al ATR base si S/R rompe el R:R
                sl_final = sl_base
                tp_final = tp_base

        result["sl"] = sl_final
        result["tp"] = tp_final
        result["entry"] = precio

    # Session fit info
    session_fit = context.get("session_fit", {})
    result["session_fit"] = session_fit.get("fit", "UNKNOWN")

    log("BRAIN", f"{symbol} FINAL -> {action} ({result['confidence']}%) "
        f"consensus={result['consensus']} TQS={tqs:.2f} [{regimen_info.get('regimen', '?')}]")

    return result
