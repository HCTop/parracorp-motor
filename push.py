# -*- coding: utf-8 -*-
"""
push.py - Notificaciones FCM v1 API
"""
import os
import requests
from config import FIREBASE_PK_B64, FIREBASE_SA_JSON

_FCM_PROJECT_ID = "parracorptrading"
_credentials = None


def _get_access_token():
    global _credentials
    try:
        from google.oauth2 import service_account
        import google.auth.transport.requests as _gauth

        if _credentials is None:
            sa_file = os.path.join(os.path.dirname(__file__), "firebase-sa.json")

            if os.path.exists(sa_file):
                _credentials = service_account.Credentials.from_service_account_file(
                    sa_file, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
            elif FIREBASE_PK_B64:
                import re
                b64 = FIREBASE_PK_B64.strip().replace(" ", "").replace("\n", "").replace("\r", "")
                lines = [b64[i:i+64] for i in range(0, len(b64), 64)]
                pk = "-----BEGIN PRIVATE KEY-----\n" + "\n".join(lines) + "\n-----END PRIVATE KEY-----\n"
                info = {
                    "type": "service_account",
                    "project_id": _FCM_PROJECT_ID,
                    "private_key_id": "8c241fce416685e7804b653d54073f561f879ee7",
                    "private_key": pk,
                    "client_email": f"firebase-adminsdk-fbsvc@{_FCM_PROJECT_ID}.iam.gserviceaccount.com",
                    "client_id": "117277983952328323816",
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
                _credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=["https://www.googleapis.com/auth/firebase.messaging"])
            else:
                return None

        _credentials.refresh(_gauth.Request())
        return _credentials.token
    except Exception as e:
        print(f"[PUSH] Error token: {e}")
        _credentials = None
        return None


def send(token, title, body, signal_type="info"):
    """Envia push notification via FCM v1.
    signal_type: 'signal' (BUY/SELL), 'close' (TP/SL), 'alert' (price alert), 'info'
    """
    if not token:
        return

    try:
        access_token = _get_access_token()
        if not access_token:
            return

        # Canal diferente para señales vs info
        channel = "trading_signals" if signal_type == "signal" else "trading_general"
        sound = "signal_alert" if signal_type == "signal" else "default"

        resp = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{_FCM_PROJECT_ID}/messages:send",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            json={
                "message": {
                    "token": token,
                    "notification": {"title": title, "body": body},
                    "data": {"signal_type": signal_type},
                    "android": {
                        "priority": "high",
                        "notification": {"channel_id": channel, "sound": sound},
                    },
                }
            },
            timeout=5,
        )
        if resp.status_code == 200:
            print(f"[PUSH] OK: {title}")
        else:
            print(f"[PUSH] Error {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"[PUSH] Error: {e}")


def send_signal(token, signal):
    """Envia push de nueva senal."""
    if not signal:
        return
    action = signal.get("action", "?")
    symbol = signal.get("symbol", "?")
    conf = signal.get("confidence", 0)
    entry = signal.get("entry_price", 0)
    sl = signal.get("sl", 0)
    tp = signal.get("tp", 0)

    title = f"{'COMPRA' if action == 'BUY' else 'VENTA'} {symbol} ({conf}%)"
    body = f"Entrada: {entry}\nSL: {sl} | TP: {tp}\nR:R: {signal.get('risk_reward', 0)}"
    send(token, title, body, signal_type="signal")


def send_close(token, signal):
    """Envia push de senal cerrada."""
    if not signal:
        return
    status = signal.get("status", "?")
    pnl = signal.get("pnl_pct", 0) or 0
    # Tick verde si cerro en positivo (aunque status sea HIT_SL por SL movido a BE+)
    icon = "✅" if pnl >= 0 else "❌"
    title = f"{icon} {signal.get('symbol', '?')} {pnl:+.2f}%"
    body = f"Entrada: {signal.get('entry_price', 0)} > Salida: {signal.get('exit_price', 0)}"
    send(token, title, body, signal_type="close")


def send_alert(token, symbol, target_price, current_price, direction):
    """Envia push de alerta de precio."""
    arrow = "\u2B06" if direction == "above" else "\u2B07"
    title = f"{arrow} ALERTA {symbol} @ {current_price}"
    body = f"Precio alcanzó {target_price} ({direction})"
    send(token, title, body, signal_type="alert")
