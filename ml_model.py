# -*- coding: utf-8 -*-
"""
ml_model.py - Mejora 17.6: Machine Learning Ligero (LightGBM)
ParraCorp v3.1

Modelo LightGBM entrenado con historial de trades.
Captura patrones no lineales. Complementa la IA, no la reemplaza.
Walk-forward con TimeSeriesSplit para evitar sobreajuste.
"""
import os
import json
import pickle
from config import data_path, log as mlog

MODEL_FILE = data_path("ml_model.pkl")
FEATURES = [
    "momentum_score", "strength_score", "zscore", "adx",
    "vol_ratio", "currency_spread", "order_flow_delta", "mtf_alignment",
]

_modelo = None
_modelo_info = None


def entrenar_modelo(trades_log):
    """
    Entrena modelo LightGBM con historial de trades.
    Usa TimeSeriesSplit para evitar sobreajuste.

    Args:
        trades_log: lista de dicts con features y resultado

    Returns: dict con metricas o None si no hay datos suficientes
    """
    global _modelo, _modelo_info

    if len(trades_log) < 50:
        mlog("ML", f"Insuficientes trades ({len(trades_log)}/50)")
        return None

    try:
        from lightgbm import LGBMClassifier
        from sklearn.model_selection import TimeSeriesSplit
        import numpy as np

        # Preparar datos
        X = []
        y = []
        for t in trades_log:
            row = [t.get(f, 0) for f in FEATURES]
            if any(v is None for v in row):
                continue
            X.append(row)
            y.append(1 if (t.get("pnl_pips", 0) or 0) > 0 else 0)

        if len(X) < 50:
            return None

        X = np.array(X, dtype=float)
        y = np.array(y, dtype=int)

        # Walk-forward validation
        tscv = TimeSeriesSplit(n_splits=min(5, len(X) // 20))
        scores = []

        modelo = LGBMClassifier(
            n_estimators=100,
            max_depth=4,
            learning_rate=0.05,
            verbose=-1,
        )

        for train_idx, val_idx in tscv.split(X):
            modelo.fit(X[train_idx], y[train_idx])
            score = modelo.score(X[val_idx], y[val_idx])
            scores.append(score)

        # Entrenar modelo final con todos los datos
        modelo.fit(X, y)
        _modelo = modelo

        # Feature importance
        importances = dict(zip(FEATURES, modelo.feature_importances_.tolist()))

        info = {
            "accuracy_cv": round(float(np.mean(scores)), 3),
            "n_trades": len(X),
            "n_splits": len(scores),
            "scores_por_split": [round(s, 3) for s in scores],
            "feature_importance": {k: round(v, 3) for k, v in
                                   sorted(importances.items(), key=lambda x: x[1], reverse=True)},
        }
        _modelo_info = info

        # Guardar modelo
        with open(MODEL_FILE, "wb") as f:
            pickle.dump(modelo, f)

        mlog("ML", f"Modelo entrenado: accuracy={info['accuracy_cv']:.3f} n={len(X)}")
        return info

    except ImportError:
        mlog("ML", "lightgbm/sklearn no disponible")
        return None
    except Exception as e:
        mlog("ML", f"Error entrenando: {e}")
        return None


def predecir(features_actuales):
    """
    Predice probabilidad de win con el modelo entrenado.

    Args:
        features_actuales: dict con las features actuales

    Returns: float probabilidad de win (0-1), o None si no hay modelo
    """
    global _modelo

    if _modelo is None:
        # Intentar cargar modelo guardado
        try:
            if os.path.exists(MODEL_FILE):
                with open(MODEL_FILE, "rb") as f:
                    _modelo = pickle.load(f)
            else:
                return None
        except Exception:
            return None

    try:
        row = [features_actuales.get(f, 0) for f in FEATURES]
        prob_win = _modelo.predict_proba([row])[0][1]
        return round(float(prob_win), 3)
    except Exception:
        return None


def get_info():
    """Info del modelo para la app."""
    return _modelo_info or {"status": "sin_entrenar"}
