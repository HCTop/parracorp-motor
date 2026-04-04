# -*- coding: utf-8 -*-
"""
market_context.py - Contexto externo del mercado.

- Calendario economico (Forex Factory - high impact events)
- Reloj de sesiones (Sydney, Tokyo, London, New York)
- Sentiment de noticias (NewsAPI)
"""
import time
import datetime
import requests

from config import NEWSAPI_KEY

# --- Cache ---
_calendar_cache = {"events": [], "ts": 0}
_news_cache = {}  # {query: {"headlines": [], "sentiment": str, "ts": int}}
CACHE_TTL_CALENDAR = 600  # 10 min
CACHE_TTL_NEWS = 300      # 5 min


# --- Compute movable holidays dynamically ---

def _easter(year):
    """Compute Easter Sunday date using the Anonymous Gregorian algorithm."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """Return the nth occurrence of weekday (0=Mon) in the given month."""
    first = datetime.date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + datetime.timedelta(days=offset + 7 * (n - 1))


def _last_weekday(year, month, weekday):
    """Return the last occurrence of weekday (0=Mon) in the given month."""
    if month == 12:
        last_day = datetime.date(year + 1, 1, 1) - datetime.timedelta(days=1)
    else:
        last_day = datetime.date(year, month + 1, 1) - datetime.timedelta(days=1)
    offset = (last_day.weekday() - weekday) % 7
    return last_day - datetime.timedelta(days=offset)


def _build_holidays(year):
    """Build bank holidays list for a given year, including movable holidays."""
    easter = _easter(year)
    good_friday = easter - datetime.timedelta(days=2)
    easter_monday = easter + datetime.timedelta(days=1)

    holidays = [
        # Fixed - Globales
        (1, 1, "Año Nuevo", ["US", "UK", "EU", "JP", "ALL"]),
        (12, 25, "Navidad", ["US", "UK", "EU", "ALL"]),
        (12, 26, "Boxing Day / San Esteban", ["UK", "EU"]),
        (12, 31, "Nochevieja (liquidez minima)", ["US", "UK", "EU"]),
        # Fixed - US
        (6, 19, "Juneteenth (US)", ["US"]),
        (7, 4, "Independence Day (US)", ["US"]),
        # Fixed - EU
        (5, 1, "Dia del Trabajo (EU)", ["EU"]),
        # Fixed - JP
        (1, 2, "Año Nuevo JP", ["JP"]),
        (1, 3, "Año Nuevo JP", ["JP"]),
        (2, 11, "Dia de la Fundacion (JP)", ["JP"]),
        (4, 29, "Showa Day (JP)", ["JP"]),
        (5, 3, "Dia de la Constitucion (JP)", ["JP"]),
        (5, 5, "Dia del Niño (JP)", ["JP"]),
    ]

    # Movable US holidays
    mlk = _nth_weekday(year, 1, 0, 3)  # 3rd Monday Jan
    pres = _nth_weekday(year, 2, 0, 3)  # 3rd Monday Feb
    memorial = _last_weekday(year, 5, 0)  # Last Monday May
    labor = _nth_weekday(year, 9, 0, 1)  # 1st Monday Sep
    thanksgiving = _nth_weekday(year, 11, 3, 4)  # 4th Thursday Nov

    holidays.append((mlk.month, mlk.day, "Martin Luther King Day (US)", ["US"]))
    holidays.append((pres.month, pres.day, "Presidents Day (US)", ["US"]))
    holidays.append((memorial.month, memorial.day, "Memorial Day (US)", ["US"]))
    holidays.append((labor.month, labor.day, "Labor Day (US)", ["US"]))
    holidays.append((thanksgiving.month, thanksgiving.day, "Thanksgiving (US)", ["US"]))

    # Movable UK holidays
    early_may = _nth_weekday(year, 5, 0, 1)  # 1st Monday May
    spring_bh = _last_weekday(year, 5, 0)  # Last Monday May
    summer_bh = _last_weekday(year, 8, 0)  # Last Monday Aug

    holidays.append((early_may.month, early_may.day, "Early May Bank Holiday (UK)", ["UK"]))
    holidays.append((spring_bh.month, spring_bh.day, "Spring Bank Holiday (UK)", ["UK"]))
    holidays.append((summer_bh.month, summer_bh.day, "Summer Bank Holiday (UK)", ["UK"]))

    # Easter-based
    holidays.append((good_friday.month, good_friday.day, "Viernes Santo (EU)", ["EU", "UK", "US"]))
    holidays.append((easter_monday.month, easter_monday.day, "Lunes de Pascua (EU)", ["EU", "UK"]))

    return holidays


# Cache holidays per year
_holidays_cache = {}


def _get_holidays(year):
    if year not in _holidays_cache:
        _holidays_cache[year] = _build_holidays(year)
    return _holidays_cache[year]


def check_bank_holiday():
    """
    Verifica si hoy es festivo bancario.
    Returns: {"is_holiday": bool, "name": str, "markets": [str], "low_liquidity": bool}
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    month, day = now.month, now.day

    for h_month, h_day, h_name, h_markets in _get_holidays(now.year):
        if month == h_month and day == h_day:
            is_global = "ALL" in h_markets
            return {
                "is_holiday": True,
                "name": h_name,
                "markets": h_markets,
                "low_liquidity": True,
                "global_close": is_global,
            }

    return {"is_holiday": False, "name": "", "markets": [], "low_liquidity": False, "global_close": False}


# === VOLATILIDAD POR PAR / SESION ============================================
# Mapa de que activos mueven mas en que sesiones.
# "best" = sesion principal donde mas volumen y volatilidad tiene el par
# "good" = sesion secundaria aceptable
# "low"  = sesion donde el par apenas mueve (riesgo de SL por ruido)

# Categorias de activos y sus sesiones optimas
_SESSION_VOLATILITY = {
    # Forex Majors EUR
    "EURUSD":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "EURGBP":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "EURJPY":  {"best": ["London", "London-NY Overlap", "Tokyo"], "good": ["New York", "Tokyo-Sydney"], "low": ["Sydney"]},
    "EURCHF":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "EURAUD":  {"best": ["London", "London-NY Overlap"], "good": ["Sydney", "Tokyo-Sydney"], "low": ["New York"]},
    "EURCAD":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "EURNZD":  {"best": ["London", "London-NY Overlap"], "good": ["Sydney", "Tokyo-Sydney"], "low": ["New York"]},

    # Forex Majors GBP
    "GBPUSD":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "GBPJPY":  {"best": ["London", "London-NY Overlap", "Tokyo"], "good": ["New York", "Tokyo-Sydney"], "low": ["Sydney"]},
    "GBPCHF":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "GBPAUD":  {"best": ["London", "London-NY Overlap"], "good": ["Sydney", "Tokyo-Sydney"], "low": ["New York"]},
    "GBPCAD":  {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "GBPNZD":  {"best": ["London", "London-NY Overlap"], "good": ["Sydney", "Tokyo-Sydney"], "low": ["New York"]},

    # Forex Majors USD
    "USDJPY":  {"best": ["Tokyo", "London-NY Overlap", "New York"], "good": ["London", "Tokyo-Sydney"], "low": ["Sydney"]},
    "USDCHF":  {"best": ["London", "London-NY Overlap", "New York"], "good": [], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "USDCAD":  {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},

    # AUD / NZD - Oceania
    "AUDUSD":  {"best": ["Sydney", "Tokyo-Sydney", "London-NY Overlap"], "good": ["Tokyo", "London"], "low": ["New York"]},
    "AUDNZD":  {"best": ["Sydney", "Tokyo-Sydney"], "good": ["Tokyo"], "low": ["London", "New York"]},
    "AUDJPY":  {"best": ["Sydney", "Tokyo-Sydney", "Tokyo"], "good": ["London"], "low": ["New York"]},
    "AUDCAD":  {"best": ["Sydney", "Tokyo-Sydney"], "good": ["London", "New York"], "low": []},
    "NZDUSD":  {"best": ["Sydney", "Tokyo-Sydney"], "good": ["Tokyo", "London"], "low": ["New York"]},
    "NZDJPY":  {"best": ["Sydney", "Tokyo-Sydney", "Tokyo"], "good": ["London"], "low": ["New York"]},
    "NZDCAD":  {"best": ["Sydney", "Tokyo-Sydney"], "good": ["London", "New York"], "low": []},

    # CAD
    "CADJPY":  {"best": ["New York", "London-NY Overlap"], "good": ["Tokyo", "London"], "low": ["Sydney"]},
    "CADCHF":  {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},

    # CHF
    "CHFJPY":  {"best": ["London", "London-NY Overlap"], "good": ["Tokyo"], "low": ["Sydney", "New York"]},

    # Metales
    "XAUUSD":  {"best": ["London", "London-NY Overlap", "New York"], "good": ["Tokyo"], "low": ["Sydney", "Tokyo-Sydney"]},
    "XAGUSD":  {"best": ["London", "London-NY Overlap", "New York"], "good": ["Tokyo"], "low": ["Sydney", "Tokyo-Sydney"]},

    # Indices
    "US30":    {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "US500":   {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "NAS100":  {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "GER40":   {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "UK100":   {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "JPN225":  {"best": ["Tokyo", "Tokyo-Sydney"], "good": ["London"], "low": ["New York", "Sydney"]},

    # Petroleo
    "USOIL":   {"best": ["New York", "London-NY Overlap"], "good": ["London"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
    "UKOIL":   {"best": ["London", "London-NY Overlap"], "good": ["New York"], "low": ["Tokyo", "Sydney", "Tokyo-Sydney"]},
}

# Pares con alias comunes
_ALIASES = {
    "XBRUSD": "UKOIL", "XTIUSD": "USOIL",
    "SPX500": "US500", "SP500": "US500",
    "DJ30": "US30", "USTEC": "NAS100",
    "DAX": "GER40", "FTSE": "UK100", "NIKKEI": "JPN225",
}


def get_session_fit(symbol, session_name):
    """
    Evalua que tan bien encaja un activo en la sesion actual.
    Returns: {
        "fit": "BEST" | "GOOD" | "LOW" | "UNKNOWN",
        "best_sessions": [str],
        "warning": str or "",
        "wait_for": str or "",  # sesion recomendada para esperar
    }
    """
    sym = symbol.upper().replace("/", "")
    # Intentar alias
    sym = _ALIASES.get(sym, sym)

    vol_map = _SESSION_VOLATILITY.get(sym)
    if not vol_map:
        # Crypto no tiene sesion preferida (24/7)
        if "USDT" in sym or "BTC" in sym or "ETH" in sym:
            return {"fit": "GOOD", "best_sessions": ["24/7"], "warning": "", "wait_for": ""}
        return {"fit": "UNKNOWN", "best_sessions": [], "warning": "", "wait_for": ""}

    best = vol_map.get("best", [])
    good = vol_map.get("good", [])
    low = vol_map.get("low", [])

    if session_name in best:
        return {"fit": "BEST", "best_sessions": best, "warning": "", "wait_for": ""}
    elif session_name in good:
        return {"fit": "GOOD", "best_sessions": best, "warning": "", "wait_for": ""}
    elif session_name in low:
        wait = best[0] if best else ""
        return {
            "fit": "LOW",
            "best_sessions": best,
            "warning": f"{sym} tiene baja volatilidad en {session_name}. Riesgo de SL por ruido.",
            "wait_for": wait,
        }
    else:
        # Sesion no mapeada (Off-hours, etc) - tratar como GOOD por defecto
        # para no bloquear señales en sesiones intermedias
        return {
            "fit": "GOOD",
            "best_sessions": best,
            "warning": "",
            "wait_for": "",
        }


# === SESIONES DE TRADING =====================================================

def get_session():
    """
    Identifica la sesion de trading actual basada en hora UTC.
    Returns: {"name": str, "quality": int 0-10, "overlap": bool, "active_markets": [str],
              "minutes_to_close": int, "market_closing_soon": bool}
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    h = now.hour
    m = now.minute

    # Sesiones (UTC):
    # Sydney:  22:00 - 07:00
    # Tokyo:   00:00 - 09:00
    # London:  07:00 - 16:00
    # New York: 13:00 - 22:00
    sessions = []
    if h >= 22 or h < 7:
        sessions.append("Sydney")
    if 0 <= h < 9:
        sessions.append("Tokyo")
    if 7 <= h < 16:
        sessions.append("London")
    if 13 <= h < 22:
        sessions.append("New York")

    overlap = len(sessions) >= 2

    # Calidad de la sesion para trading
    if "London" in sessions and "New York" in sessions:
        name, quality = "London-NY Overlap", 10
    elif "London" in sessions:
        name, quality = "London", 8
    elif "New York" in sessions:
        name, quality = "New York", 8
    elif "Tokyo" in sessions and "Sydney" in sessions:
        name, quality = "Tokyo-Sydney", 5
    elif "Tokyo" in sessions:
        name, quality = "Tokyo", 6
    elif "Sydney" in sessions:
        name, quality = "Sydney", 3
    else:
        name, quality = "Off-hours", 1

    # Fin de semana: Saturday, Sunday, o Friday despues de 22:00 UTC (NY close)
    wd = now.weekday()
    is_weekend = wd >= 5 or (wd == 4 and h >= 22)
    if is_weekend:
        name, quality = "Weekend (Cerrado)", 0
        sessions = []  # No hay mercados activos en fin de semana
        overlap = False

    # Minutos hasta cierre de mercado forex (viernes 22:00 UTC = cierre semanal)
    # Para intradía: cierre de la última sesión principal = NY close 22:00 UTC
    # Swap se cobra ~21:00-22:00 UTC (varía por broker, usamos 21:00 como límite)
    SWAP_HOUR = 21  # UTC - hora a la que se cobra swap
    minutes_now = h * 60 + m
    swap_minutes = SWAP_HOUR * 60

    if now.weekday() < 5:  # Lun-Vie
        if minutes_now < swap_minutes:
            minutes_to_close = swap_minutes - minutes_now
        else:
            # Ya pasó la hora de swap, siguiente día
            minutes_to_close = (24 * 60 - minutes_now) + swap_minutes
    else:
        # Weekend - mercado cerrado
        minutes_to_close = 0

    # "Cerrando pronto" si faltan menos de 90 min para swap
    market_closing_soon = 0 < minutes_to_close <= 90

    return {
        "name": name,
        "quality": quality,
        "overlap": overlap,
        "active_markets": sessions,
        "hour_utc": h,
        "weekday": now.strftime("%A"),
        "minutes_to_close": minutes_to_close,
        "market_closing_soon": market_closing_soon,
    }


# === CALENDARIO ECONOMICO ====================================================

def get_calendar():
    """
    Eventos economicos de alto impacto de esta semana (Forex Factory).
    Returns: lista de eventos.
    """
    global _calendar_cache
    if _calendar_cache["events"] and (time.time() - _calendar_cache["ts"]) < CACHE_TTL_CALENDAR:
        return _calendar_cache["events"]

    try:
        url = "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json"
        r = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (compatible; ParraCorp/2.0)"
        })
        if r.status_code != 200:
            return _calendar_cache.get("events", [])

        all_events = r.json()
        high_impact = []
        for ev in all_events:
            impact = ev.get("impact", "").lower()
            if impact in ("high", "holiday"):
                high_impact.append({
                    "title": ev.get("title", ""),
                    "country": ev.get("country", ""),
                    "date": ev.get("date", ""),
                    "impact": impact,
                    "forecast": ev.get("forecast", ""),
                    "previous": ev.get("previous", ""),
                })

        _calendar_cache = {"events": high_impact, "ts": time.time()}
        return high_impact

    except Exception as e:
        print(f"[CONTEXT] Error calendario: {e}")
    return _calendar_cache.get("events", [])


def check_high_impact(currency, minutes=30):
    """
    Verifica si hay evento de alto impacto proximo para una moneda.
    Returns: {"active": bool, "event": str, "minutes_to": int}
    """
    events = get_calendar()
    if not events:
        return {"active": False}

    now = datetime.datetime.now(datetime.timezone.utc)

    for ev in events:
        if ev.get("country", "").upper() != currency.upper():
            continue
        ev_date = ev.get("date", "")
        if not ev_date:
            continue

        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%m-%d-%Y %H:%M:%S"]:
            try:
                ev_time = datetime.datetime.strptime(ev_date, fmt)
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=datetime.timezone.utc)
                break
            except ValueError:
                continue
        else:
            continue

        diff = (ev_time - now).total_seconds() / 60
        if -15 <= diff <= minutes:
            return {
                "active": True,
                "event": ev.get("title", "Unknown"),
                "country": currency,
                "minutes_to": round(diff),
            }

    return {"active": False}


def currencies_in_symbol(symbol):
    """Extrae monedas de un simbolo. EURUSD -> [EUR, USD]"""
    sym = symbol.upper().replace("/", "")
    known = ["EUR","USD","GBP","JPY","CHF","AUD","NZD","CAD","XAU","XAG","BTC","ETH","SOL"]
    found = []
    remaining = sym
    for c in known:
        if remaining.startswith(c):
            found.append(c)
            remaining = remaining[len(c):]
        elif remaining.endswith(c):
            found.append(c)
            remaining = remaining[:-len(c)]
    if not found:
        mid = len(sym) // 2
        found = [sym[:mid], sym[mid:]]
    return found


def check_symbol_events(symbol, minutes=30):
    """Verifica eventos de alto impacto para todas las monedas del simbolo."""
    currencies = currencies_in_symbol(symbol)
    for ccy in currencies:
        result = check_high_impact(ccy, minutes)
        if result.get("active"):
            return result
    return {"active": False}


# === SENTIMENT DE NOTICIAS ====================================================

def get_news_sentiment(query="forex market"):
    """
    Obtiene titulares recientes y analiza sentiment basico.
    Usa NewsAPI si hay key, si no retorna neutral.
    Returns: {"headlines": [str], "sentiment": "bullish"|"bearish"|"neutral", "count": int}
    """
    if not NEWSAPI_KEY:
        return {"headlines": [], "sentiment": "neutral", "count": 0}

    cached = _news_cache.get(query)
    if cached and (time.time() - cached["ts"]) < CACHE_TTL_NEWS:
        return cached

    try:
        url = "https://newsapi.org/v2/everything"
        params = {
            "q": query,
            "language": "es",
            "sortBy": "publishedAt",
            "pageSize": 10,
            "apiKey": NEWSAPI_KEY,
        }
        r = requests.get(url, params=params, timeout=10)
        if r.status_code != 200:
            return {"headlines": [], "sentiment": "neutral", "count": 0}

        articles = r.json().get("articles", [])
        headlines = [a.get("title", "") for a in articles if a.get("title")]

        # Sentiment basico por keywords
        bullish_words = ["surge", "rally", "gain", "rise", "bull", "high", "record",
                         "growth", "up", "boost", "recover", "positive"]
        bearish_words = ["crash", "fall", "drop", "bear", "low", "loss", "decline",
                         "fear", "risk", "down", "sell", "negative", "crisis"]

        text = " ".join(headlines).lower()
        bull_count = sum(1 for w in bullish_words if w in text)
        bear_count = sum(1 for w in bearish_words if w in text)

        if bull_count > bear_count + 2:
            sentiment = "bullish"
        elif bear_count > bull_count + 2:
            sentiment = "bearish"
        else:
            sentiment = "neutral"

        result = {"headlines": headlines[:5], "sentiment": sentiment,
                  "count": len(headlines), "ts": time.time()}
        _news_cache[query] = result
        return result

    except Exception as e:
        print(f"[CONTEXT] Error noticias: {e}")
        return {"headlines": [], "sentiment": "neutral", "count": 0}


def get_session_countdown():
    """
    Calcula datos de countdown de la sesion actual.
    Horarios UTC:
      Asia:      0:00 - 8:00
      London:    8:00 - 16:30
      NY:       13:30 - 21:00
      Off-hours: 21:00 - 0:00
    Returns: dict con session_name, session_quality, session_minutes_left,
             session_next, session_pct
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    h = now.hour
    m = now.minute
    minutes_now = h * 60 + m

    # Define sessions as (name, start_minutes, end_minutes, quality, next_session)
    sessions_def = [
        ("Asia",      0,    480,  6, "London"),      # 0:00 - 8:00
        ("London",    480,  990,  8, "NY"),           # 8:00 - 16:30
        ("NY",        810,  1260, 8, "Off-hours"),    # 13:30 - 21:00
        ("Off-hours", 1260, 1440, 1, "Asia"),         # 21:00 - 0:00
    ]

    # Determine current session (priority: overlap > London > NY > Asia > Off-hours)
    active = []
    for name, start, end, quality, nxt in sessions_def:
        if start <= minutes_now < end:
            active.append((name, start, end, quality, nxt))

    if not active:
        # Should not happen, but fallback
        return {
            "session_name": "Off-hours",
            "session_quality": 1,
            "session_minutes_left": 0,
            "session_next": "Asia",
            "session_pct": 100.0,
        }

    # Check for London-NY overlap (13:30 - 16:30 UTC)
    london_active = any(s[0] == "London" for s in active)
    ny_active = any(s[0] == "NY" for s in active)

    if london_active and ny_active:
        # Overlap zone: 13:30 - 16:30
        overlap_start = 810   # 13:30
        overlap_end = 990     # 16:30
        session_name = "London-NY Overlap"
        quality = 10
        total = overlap_end - overlap_start
        elapsed = minutes_now - overlap_start
        minutes_left = overlap_end - minutes_now
        next_session = "NY"
    else:
        # Pick highest quality session
        best = max(active, key=lambda s: s[3])
        session_name, start, end, quality, next_session = best
        total = end - start
        elapsed = minutes_now - start
        minutes_left = end - minutes_now

    pct = round(elapsed / total * 100, 1) if total > 0 else 0
    pct = max(0, min(100, pct))
    minutes_left = max(0, minutes_left)

    # Weekend override (includes Friday after 22:00 UTC)
    wd = now.weekday()
    if wd >= 5 or (wd == 4 and h >= 22):
        session_name = "Weekend (Cerrado)"
        quality = 0
        minutes_left = 0
        next_session = "Asia (Domingo 22:00 UTC)"
        pct = 100.0

    return {
        "session_name": session_name,
        "session_quality": quality,
        "session_minutes_left": minutes_left,
        "session_next": next_session,
        "session_pct": pct,
    }


def get_news_data():
    """
    Returns cached news data for the /news endpoint.
    Aggregates all cached news queries to avoid extra API calls.
    """
    if not _news_cache:
        # Try fetching default query if no cache exists
        result = get_news_sentiment("forex market")
        if result and result.get("headlines"):
            return result
        return {"headlines": [], "sentiment": "neutral", "ts": 0}

    # Return the most recently cached entry
    latest = None
    latest_ts = 0
    for query, data in _news_cache.items():
        ts = data.get("ts", 0)
        if ts > latest_ts:
            latest_ts = ts
            latest = data

    return latest if latest else {"headlines": [], "sentiment": "neutral", "ts": 0}


def get_upcoming_events(hours=48):
    """
    Devuelve los proximos eventos de alto impacto en las proximas N horas.
    Returns: lista de eventos con tiempo restante.
    """
    events = get_calendar()
    if not events:
        return []

    now = datetime.datetime.now(datetime.timezone.utc)
    upcoming = []

    for ev in events:
        ev_date = ev.get("date", "")
        if not ev_date:
            continue
        for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%m-%d-%Y %H:%M:%S"]:
            try:
                ev_time = datetime.datetime.strptime(ev_date, fmt)
                if ev_time.tzinfo is None:
                    ev_time = ev_time.replace(tzinfo=datetime.timezone.utc)
                break
            except ValueError:
                continue
        else:
            continue

        diff_min = (ev_time - now).total_seconds() / 60
        if -30 <= diff_min <= hours * 60:
            upcoming.append({
                "title": ev.get("title", ""),
                "country": ev.get("country", ""),
                "impact": ev.get("impact", ""),
                "forecast": ev.get("forecast", ""),
                "previous": ev.get("previous", ""),
                "minutes_to": round(diff_min),
                "date": ev_date,
            })

    upcoming.sort(key=lambda x: x["minutes_to"])
    return upcoming


def get_full_context(symbol, temporalidad="60"):
    """
    Contexto completo del mercado para un simbolo.
    Combina: sesion + calendario + noticias + festivos + volatilidad.
    """
    session = get_session()
    events = check_symbol_events(symbol, minutes=30)
    holiday = check_bank_holiday()

    # Noticias relevantes
    tipo = symbol.upper().replace("USDT", "").replace("USD", "")
    news = get_news_sentiment(f"{tipo} market")

    # Volatilidad del par en esta sesion
    session_fit = get_session_fit(symbol, session.get("name", ""))

    return {
        "session": session,
        "high_impact_event": events,
        "news": news,
        "bank_holiday": holiday,
        "session_fit": session_fit,
    }
