# -*- coding: utf-8 -*-
"""
config.py - Configuracion centralizada ParraCorp v3.1

Variables de entorno Railway, estado global, persistencia, clasificacion activos.
Boton ON/OFF para el motor y la IA.
"""
import os
import json
import threading

# --- Cargar .env si existe (para backtest local) ---
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.isfile(_env_file):
    with open(_env_file) as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _v = _v.strip().strip('"').strip("'")
                if _k.strip() and _v:
                    os.environ.setdefault(_k.strip(), _v)

# --- Directorio persistente (Railway Volume o local) ---
_data_dir = "/data" if os.path.isdir("/data") and os.access("/data", os.W_OK) else None
_local_dir = os.path.dirname(os.path.abspath(__file__))

def data_path(filename):
    if _data_dir:
        return os.path.join(_data_dir, filename)
    return os.path.join(_local_dir, filename)

# --- Variables de entorno (Railway) ---
GROQ_KEYS = [k for k in [
    os.environ.get("GROQ_API_KEY", ""),
    os.environ.get("GROQ_KEY2", ""),
    os.environ.get("GROQ_KEY3", ""),
    os.environ.get("GROQ_KEY4", ""),
] if k]

GEMINI_KEYS = [k for k in [
    os.environ.get("GEMINI_API_KEY", ""),
    os.environ.get("GEMINI_KEY2", ""),
    os.environ.get("GEMINI_KEY3", ""),
    os.environ.get("GEMINI_KEY4", ""),
] if k]

NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")
FIREBASE_PK_B64 = os.environ.get("FIREBASE_PK_B64", "")
FIREBASE_SA_JSON = os.environ.get("FIREBASE_SA_JSON", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
WA_GROUP_NAME = os.environ.get("WA_GROUP_NAME", "")
PORT = int(os.environ.get("PORT", 5000))

# --- Log interno (circular buffer) ---
from collections import deque
from datetime import datetime as _dt

_MAX_LOGS = 2000
motor_logs = deque(maxlen=_MAX_LOGS)

_log_file = None
_log_file_date = None
_log_lock = threading.Lock()

def _get_log_file():
    """Retorna file handle para el log diario. Rota por dia."""
    global _log_file, _log_file_date
    today = _dt.utcnow().strftime("%Y-%m-%d")
    if _log_file_date != today:
        with _log_lock:
            if _log_file_date != today:
                if _log_file:
                    try:
                        _log_file.close()
                    except Exception:
                        pass
                log_dir = data_path("logs")
                os.makedirs(log_dir, exist_ok=True)
                path = os.path.join(log_dir, f"motor_{today}.log")
                _log_file = open(path, "a", encoding="utf-8", buffering=1)
                _log_file_date = today
    return _log_file

def get_log_file_path(date_str=None):
    """Retorna la ruta del fichero de log de un dia."""
    if not date_str:
        date_str = _dt.utcnow().strftime("%Y-%m-%d")
    return os.path.join(data_path("logs"), f"motor_{date_str}.log")

def log(tag, msg, data=None):
    ts = _dt.utcnow().strftime("%H:%M:%S")
    entry = {
        "ts": ts,
        "tag": tag,
        "msg": msg,
    }
    if data:
        entry["data"] = data
    motor_logs.append(entry)
    line = f"[{ts}] [{tag}] {msg}"
    print(line)
    # Persistir a fichero
    try:
        f = _get_log_file()
        if f:
            f.write(line + "\n")
    except Exception:
        pass

def get_logs(limit=500):
    return list(motor_logs)[-limit:]


# --- Watchlist por categorias (ICMarkets) ---
WL_CATALOGO = {
    "Forex Majors": [
        "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    ],
    "Forex Crosses": [
        "EURJPY", "GBPJPY", "EURGBP", "AUDJPY", "CADJPY", "NZDJPY", "CHFJPY",
        "EURAUD", "EURNZD", "EURCHF", "EURCAD",
        "GBPAUD", "GBPNZD", "GBPCAD", "GBPCHF",
        "AUDCAD", "AUDNZD", "AUDCHF",
        "CADCHF", "NZDCAD", "NZDCHF",
    ],
    "Forex Exoticos": [
        "USDSGD", "USDNOK", "USDSEK", "USDDKK", "USDPLN", "USDCZK",
        "USDHUF", "USDMXN", "USDZAR", "USDTRY", "USDCNH",
        "EURSGD", "EURNOK", "EURSEK", "EURDKK", "EURPLN", "EURCZK",
        "EURHUF", "EURMXN", "EURZAR", "EURTRY",
        "GBPSGD", "GBPNOK", "GBPSEK", "GBPDKK", "GBPPLN",
        "AUDSGD", "NZDSGD", "SGDJPY",
    ],
    "Metales": [
        "XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "XAUEUR", "XAUGBP", "XAUAUD",
    ],
    "Indices": [
        "US30", "NAS100", "SPX500",    # EEUU
        "DE40", "UK100", "FR40",       # Europa
        "ES35", "EU50", "IT40",        # Europa
        "JP225", "HK50", "AUS200",     # Asia-Pacifico
        "CHINA50", "INDIA50",          # Asia
        "STOXX50",                     # Euro Stoxx
    ],
    "Energia": [
        "USOIL", "UKOIL", "NATGAS",
    ],
    "Materias Primas": [
        "COCOA", "COFFEE", "COTTON", "SUGAR", "SOYBEAN", "WHEAT", "CORN",
        "COPPER",
    ],
    "Bonos": [
        "USTBOND",   # US Treasury Bond 30y
        "USTNOTE10", # US T-Note 10y
        "USTNOTE5",  # US T-Note 5y
        "USTNOTE2",  # US T-Note 2y
        "BUND",      # German Bund 10y
        "GILT",      # UK Gilt
        "JGB",       # Japan Government Bond
    ],
    "Crypto": [
        "BTCUSD", "ETHUSD", "SOLUSD", "XRPUSD", "BNBUSD",
        "DOGEUSD", "ADAUSD", "AVAXUSD", "LINKUSD", "DOTUSD",
        "MATICUSD", "LTCUSD", "UNIUSD", "XLMUSD", "ATOMUSD",
        "NEARUSD", "FILUSD", "APTUSD", "ARBUSD", "OPUSD",
    ],
    "Acciones EEUU": [
        "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA", "NVDA",
        "AMD", "NFLX", "CRM", "INTC", "PYPL", "DIS", "BA",
        "JPM", "GS", "V", "MA", "BAC", "WFC",
        "JNJ", "PFE", "UNH", "ABBV", "MRK",
        "XOM", "CVX", "COP",
        "KO", "PEP", "MCD", "WMT", "COST", "NKE",
        "COIN", "HOOD", "MSTR", "PLTR", "UBER", "SNAP",
    ],
    "Acciones Europa": [
        "ASML", "SAP", "LVMH", "NOVO", "SHELL", "AZN",
        "SIE", "ALV", "BMW", "VOW",
        "MC", "OR", "BNP", "SAN", "BARC",
    ],
    "Acciones Australia": [
        "BHP", "CBA", "CSL", "NAB", "WBC", "ANZ", "FMG", "RIO",
    ],
}

# Listas planas para compatibilidad
WL_RECOMENDADA = []  # Vacia — el usuario elige manualmente desde la app

# Todos los opcionales (flat)
WL_OPCIONAL = []
for _cat, _syms in WL_CATALOGO.items():
    for _s in _syms:
        if _s not in WL_RECOMENDADA and _s not in WL_OPCIONAL:
            WL_OPCIONAL.append(_s)

# --- Estado global ---
lock = threading.Lock()

state = {
    # Motor ON/OFF
    "motor_activo": True,   # True=motor analiza, False=motor parado (no gasta IA)
    "motor_ok": False,
    "ultimo_ciclo": "--",
    "ts_ciclo": 0,
    # Config trading
    "capital": 10000.0,
    "riesgo_pct": 1.0,
    "max_ops": 3,
    "rr_minimo": 1.5,
    # Watchlist
    "watchlist": list(WL_RECOMENDADA),
    "watchlist_opcional": [],  # Pares opcionales activados por el usuario
    # IA
    "ia_modo": "autonomo",  # "autonomo" = IA activa, "off" = solo modelo estadistico
    "ia_modelo": "gemini-2.5-flash",
    "ia_motores": "ambas",  # "ambas", "solo_groq", "solo_gemini"
    # Estado
    "daily_pnl": 0.0,
    "daily_reset_ts": 0,
    "push_token": "",
    "modo_conservador": False,
    "fallos_consecutivos": 0,
    "apalancamiento": 30,
    "avoid_swap": True,
    "divisa_base": "EUR",
}

# --- Persistencia ---
CONFIG_FILE = data_path("config_v3.json")

def cargar():
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            for k in data:
                if k in state:
                    state[k] = data[k]
            # Sanitizar: watchlist solo debe tener simbolos del catalogo
            _all_catalog = set()
            for _syms in WL_CATALOGO.values():
                _all_catalog.update(_syms)
            dirty = False
            wl = state["watchlist"]
            bad_wl = [s for s in wl if s not in _all_catalog]
            if bad_wl:
                state["watchlist"] = [s for s in wl if s in _all_catalog]
                print(f"[CONFIG] Eliminados {len(bad_wl)} invalidos de watchlist: {bad_wl}")
                dirty = True
            # Sanitizar opcional: solo simbolos del catalogo
            wl_op = state.get("watchlist_opcional", [])
            bad = [s for s in wl_op if s not in _all_catalog]
            if bad:
                state["watchlist_opcional"] = [s for s in wl_op if s in _all_catalog]
                print(f"[CONFIG] Eliminados {len(bad)} invalidos de opcional: {bad}")
                dirty = True
            if dirty:
                guardar()
            print(f"[CONFIG] OK: motor={'ON' if state['motor_activo'] else 'OFF'} "
                  f"ia={state['ia_modo']} wl={len(state['watchlist'])} capital={state['capital']}")
    except Exception as e:
        print(f"[CONFIG] Error: {e}")

def guardar():
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump({k: state[k] for k in [
                "motor_activo", "capital", "riesgo_pct", "max_ops", "rr_minimo",
                "watchlist", "watchlist_opcional",
                "ia_modo", "ia_motores",
                "push_token", "modo_conservador", "apalancamiento", "avoid_swap", "divisa_base",
            ]}, f, indent=2)
    except Exception as e:
        print(f"[CONFIG] Error guardando: {e}")

# --- Clasificacion de activos ---
FOREX = {"EURUSD","GBPUSD","USDJPY","USDCHF","AUDUSD","USDCAD","NZDUSD",
         "EURGBP","EURJPY","GBPJPY","AUDCAD","AUDNZD","EURAUD",
         "AUDJPY","CADJPY","NZDJPY","CHFJPY","EURNZD","EURCHF",
         "GBPAUD","GBPNZD","GBPCAD","GBPCHF","AUDCHF","CADCHF",
         "NZDCAD","NZDCHF","EURCAD"}
JPY = {"USDJPY","EURJPY","GBPJPY","AUDJPY","CADJPY","NZDJPY","CHFJPY"}
METAL = {"XAUUSD","XAGUSD","XPTUSD","XPDUSD"}
INDEX = {"US30","NAS100","SPX500","DE40","UK100","FR40","JP225","AU200","ES35","HK50"}
CRYPTO = {"BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","BNBUSDT",
          "DOGEUSDT","ADAUSDT","AVAXUSDT","LINKUSDT","DOTUSDT","MATICUSDT",
          "BTCUSD","ETHUSD","SOLUSD","XRPUSD","BNBUSD",
          "DOGEUSD","ADAUSD","AVAXUSD","LINKUSD","DOTUSD","MATICUSD",
          "LTCUSD","UNIUSD","XLMUSD","ATOMUSD","NEARUSD","FILUSD","APTUSD","ARBUSD","OPUSD"}
COMMODITY = {"USOIL","UKOIL","NATGAS","COPPER"}
STOCK = {"TSLA","NVDA","AAPL","AMZN","META","MSFT","GOOGL"}

def tipo_activo(s):
    sym = s.upper().replace("/", "")
    if sym in FOREX or (any(x in sym for x in ["EUR","GBP","CHF","AUD","CAD","NZD"]) and "USD" in sym):
        return "forex"
    if sym in METAL or "XAU" in sym or "XAG" in sym:
        return "metal"
    if sym in INDEX or any(x in sym for x in ["US30","NAS","SPX","DE40","UK100","FR40","JP225"]):
        return "indice"
    if sym in COMMODITY or any(x in sym for x in ["OIL","NATGAS","COPPER"]):
        return "commodity"
    if sym in STOCK:
        return "stock"
    return "crypto"

def detectar_exchange(simbolo):
    t = tipo_activo(simbolo)
    if t == "forex": return "OANDA", "forex"
    if t == "metal": return "OANDA", "cfd"
    if t in ("indice", "commodity"): return "SAXO", "cfd"
    if t == "stock": return "NASDAQ", "america"
    return "BINANCE", "crypto"

# Cargar al importar
cargar()
print(f"[CONFIG] Groq:{len(GROQ_KEYS)} Gemini:{len(GEMINI_KEYS)} "
      f"News:{'si' if NEWSAPI_KEY else 'no'} FCM:{'si' if FIREBASE_PK_B64 else 'no'} "
      f"TG:{'si' if TELEGRAM_BOT_TOKEN else 'no'} Motor:{'ON' if state['motor_activo'] else 'OFF'}")
