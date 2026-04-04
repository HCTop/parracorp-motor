# -*- coding: utf-8 -*-
"""
chart_gen.py - Generador de graficos de senales con TP/SL

Genera imagen PNG con velas reales + zonas TP/SL para enviar
por Telegram, WhatsApp y push notifications.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import os
import time
from config import log as mlog, data_path

# Directorio para imagenes temporales
_CHART_DIR = data_path("charts")
if not os.path.isdir(_CHART_DIR):
    try:
        os.makedirs(_CHART_DIR, exist_ok=True)
    except Exception:
        _CHART_DIR = "/tmp"


def _tf_label(tf):
    _map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1H", "240": "4H", "1D": "1D"}
    return _map.get(str(tf), str(tf))


def _tf_to_intervalo(tf):
    _map = {"1": "1m", "5": "5m", "15": "15m", "30": "30m",
            "60": "1h", "240": "4h", "1D": "1d"}
    return _map.get(str(tf), "1h")


def generate_signal_chart(signal, get_ohlcv_fn):
    """
    Genera imagen PNG del grafico con zonas TP/SL.

    Args:
        signal: dict con symbol, action, entry_price, sl, tp, timeframe, risk_reward, id
        get_ohlcv_fn: funcion(symbol, intervalo) que devuelve lista de barras OHLCV

    Returns: path al archivo PNG, o None si falla
    """
    try:
        sym = signal.get("symbol", "")
        action = signal.get("action", "BUY")
        entry = signal.get("entry_price", 0)
        sl = signal.get("sl", 0)
        tp = signal.get("tp", 0)
        rr = signal.get("risk_reward", 0)
        tf = signal.get("timeframe", "60")
        sig_id = signal.get("id", "")
        conf = signal.get("confidence", 0)

        if not entry or not sl or not tp:
            return None

        # Obtener velas reales
        intervalo = _tf_to_intervalo(tf)
        bars = get_ohlcv_fn(sym, intervalo)
        if not bars or len(bars) < 15:
            mlog("CHART", f"{sym} pocas velas ({len(bars) if bars else 0})")
            return None

        # Construir DataFrame - forzar todo a float
        from datetime import datetime
        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        skipped = 0
        for b in bars:
            try:
                t = int(b["time"])
                o = float(b["open"])
                h_ = float(b["high"])
                l_ = float(b["low"])
                c = float(b["close"])
                v = float(b.get("volume", 100))
                if o <= 0 or h_ <= 0 or l_ <= 0 or c <= 0:
                    skipped += 1
                    continue
                dates.append(datetime.utcfromtimestamp(t))
                opens.append(o)
                highs.append(h_)
                lows.append(l_)
                closes.append(c)
                volumes.append(v)
            except (ValueError, TypeError, KeyError) as exc:
                skipped += 1
                mlog("CHART", f"  Barra ignorada: {exc} -> {b}")
                continue

        if len(dates) < 15:
            mlog("CHART", f"{sym} pocas velas validas ({len(dates)}, {skipped} ignoradas)")
            return None

        # Construir con Series tipadas — evita dtype object
        idx = pd.DatetimeIndex(dates)
        df = pd.DataFrame({
            "Open": pd.array(opens, dtype="float64"),
            "High": pd.array(highs, dtype="float64"),
            "Low": pd.array(lows, dtype="float64"),
            "Close": pd.array(closes, dtype="float64"),
            "Volume": pd.array(volumes, dtype="float64"),
        }, index=idx)
        df = df.tail(50)

        mlog("CHART", f"{sym} DataFrame: shape={df.shape} dtypes={dict(df.dtypes)}")

        n_candles = len(df)

        # Estilo oscuro tipo TradingView
        mc = mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge={"up": "#26a69a", "down": "#ef5350"},
            wick={"up": "#26a69a", "down": "#ef5350"},
        )
        style = mpf.make_mpf_style(
            marketcolors=mc,
            base_mpf_style="nightclouds",
            facecolor="#131722",
            edgecolor="#131722",
            figcolor="#131722",
            gridcolor="#1e2030",
            gridstyle="--",
            gridaxis="horizontal",
            y_on_right=True,
            rc={
                "font.size": 9,
                "axes.labelcolor": "#9598a1",
                "xtick.color": "#9598a1",
                "ytick.color": "#9598a1",
            },
        )

        # Crear grafico con espacio de proyeccion a la derecha
        # Reservar ~20% extra a la derecha para las zonas TP/SL
        projection = max(int(n_candles * 0.25), 8)
        tight_layout = {"left": 0.06, "right": 0.88, "top": 0.85, "bottom": 0.10}

        fig, axes = mpf.plot(
            df, type="candle", style=style,
            volume=False,
            figsize=(10, 6),
            returnfig=True,
            datetime_format="%d/%m %H:%M",
            xrotation=0,
            tight_layout=tight_layout,
        )
        ax = axes[0]

        # Extender eje X para proyeccion (velas terminan a la izquierda)
        x_candle_end = n_candles - 1
        x_proj_end = n_candles - 1 + projection
        ax.set_xlim(-1, x_proj_end)

        # Header
        tf_text = _tf_label(tf)
        fig.text(0.06, 0.94, f"{sym}  {tf_text}",
                 color="#e0e0e0", fontsize=14, fontweight="bold",
                 transform=fig.transFigure)

        dir_text = "COMPRA" if action == "BUY" else "VENTA"
        fig.text(0.06, 0.90,
                 f"{dir_text}  |  R:R {int(rr)}:1  |  Entry {entry:.1f}  |  TP {tp:.1f}  |  SL {sl:.1f}",
                 color="#9598a1", fontsize=10, transform=fig.transFigure)

        fig.text(0.95, 0.94, "ParraCorp",
                 color="#4fc3f7", fontsize=12, fontweight="bold",
                 ha="right", transform=fig.transFigure)

        # Zonas TP/SL solo desde el punto de entrada hacia la derecha
        x_entry = x_candle_end
        x_end = x_proj_end

        if action == "BUY":
            ax.fill_between([x_entry, x_end], tp, entry,
                            alpha=0.12, color="#26a69a", zorder=0)
            ax.fill_between([x_entry, x_end], sl, entry,
                            alpha=0.12, color="#ef5350", zorder=0)
        else:  # SELL - TP abajo, SL arriba
            ax.fill_between([x_entry, x_end], entry, tp,
                            alpha=0.12, color="#26a69a", zorder=0)
            ax.fill_between([x_entry, x_end], entry, sl,
                            alpha=0.12, color="#ef5350", zorder=0)

        # Lineas horizontales desde entry hasta el final
        ax.hlines(tp, x_entry, x_end, colors="#26a69a", linewidth=1.2, linestyle="--", alpha=0.8)
        ax.hlines(sl, x_entry, x_end, colors="#ef5350", linewidth=1.2, linestyle="--", alpha=0.8)
        ax.hlines(entry, x_entry, x_end, colors="#ffffff", linewidth=1, linestyle="-", alpha=0.6)

        # Punto de entrada
        ax.plot(x_entry, entry, "o", color="#2962ff", markersize=8, zorder=5)

        # Labels en la zona de proyeccion
        label_x = x_entry + projection * 0.5
        dir_label = "COMPRA" if action == "BUY" else "VENTA"

        ax.text(label_x, tp, f" TP {tp:.1f} ", fontsize=9, fontweight="bold",
                color="#131722", va="center", ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#26a69a", alpha=0.9, edgecolor="none"),
                zorder=6)

        ax.text(label_x, entry, f" {dir_label} {entry:.1f} ", fontsize=9, fontweight="bold",
                color="#ffffff", va="center", ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#2962ff", alpha=0.7, edgecolor="none"),
                zorder=6)

        ax.text(label_x, sl, f" SL {sl:.1f} ", fontsize=9, fontweight="bold",
                color="#131722", va="center", ha="center",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#ef5350", alpha=0.9, edgecolor="none"),
                zorder=6)

        # Guardar
        filename = f"signal_{sig_id}_{int(time.time())}.png"
        filepath = os.path.join(_CHART_DIR, filename)
        fig.savefig(filepath, dpi=150, bbox_inches="tight", facecolor="#131722")
        plt.close(fig)

        mlog("CHART", f"Grafico generado: {filename}")
        return filepath

    except Exception as e:
        mlog("CHART", f"Error generando grafico: {e}")
        import traceback
        traceback.print_exc()
        return None


def cleanup_old_charts(max_age_hours=24):
    """Elimina graficos antiguos."""
    try:
        now = time.time()
        for f in os.listdir(_CHART_DIR):
            if f.endswith(".png"):
                fp = os.path.join(_CHART_DIR, f)
                if now - os.path.getmtime(fp) > max_age_hours * 3600:
                    os.remove(fp)
    except Exception:
        pass
