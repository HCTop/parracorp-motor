# -*- coding: utf-8 -*-
"""
alerts.py - Alertas de precio
"""
import json
import os
import time
import threading
import uuid

from config import data_path

_lock = threading.Lock()
ALERTS_FILE = data_path("alerts.json")
_alerts = []


def _load():
    global _alerts
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, "r", encoding="utf-8") as f:
                _alerts = json.load(f)
    except Exception as e:
        print(f"[ALERTS] Error cargando: {e}")


def _save():
    try:
        with open(ALERTS_FILE, "w", encoding="utf-8") as f:
            json.dump(_alerts, f, indent=2)
    except Exception as e:
        print(f"[ALERTS] Error guardando: {e}")


_load()


def create(symbol, target_price, direction, push_token):
    """
    Crea una alerta de precio.
    direction: "above" o "below"
    """
    with _lock:
        alert = {
            "id": f"ALR_{uuid.uuid4().hex[:8]}",
            "symbol": symbol.upper(),
            "target_price": float(target_price),
            "direction": direction,
            "push_token": push_token,
            "created_ts": int(time.time()),
            "triggered": False,
            "triggered_ts": None,
        }
        _alerts.append(alert)
        _save()
        return alert


def check(symbol, current_price):
    """
    Verifica alertas para un simbolo contra el precio actual.
    Returns: lista de alertas disparadas.
    """
    triggered = []
    price = float(current_price)
    with _lock:
        for alert in _alerts:
            if alert["triggered"] or alert["symbol"] != symbol.upper():
                continue
            target = alert["target_price"]
            if alert["direction"] == "above" and price >= target:
                alert["triggered"] = True
                alert["triggered_ts"] = int(time.time())
                triggered.append(dict(alert))
            elif alert["direction"] == "below" and price <= target:
                alert["triggered"] = True
                alert["triggered_ts"] = int(time.time())
                triggered.append(dict(alert))
        if triggered:
            _save()
    return triggered


def get_all(push_token=None):
    """Lista alertas, opcionalmente filtradas por token."""
    with _lock:
        if push_token:
            return [a for a in _alerts if a["push_token"] == push_token and not a["triggered"]]
        return [a for a in _alerts if not a["triggered"]]


def delete(alert_id):
    """Borra una alerta."""
    global _alerts
    with _lock:
        before = len(_alerts)
        _alerts = [a for a in _alerts if a["id"] != alert_id]
        if len(_alerts) < before:
            _save()
            return True
    return False
