# -*- coding: utf-8 -*-
"""
model_versioning.py - Mejora 17.12: Versionado de Modelos
ParraCorp v3.1

Registra cada version de pesos y parametros con sus metricas.
Permite revertir a versiones anteriores si el rendimiento empeora.
"""
import json
import hashlib
import os
import time
from config import data_path, log as mlog

VERSIONS_FILE = data_path("model_versions.json")

_versions = []


def init():
    """Carga versiones guardadas."""
    global _versions
    try:
        if os.path.exists(VERSIONS_FILE):
            with open(VERSIONS_FILE, "r") as f:
                _versions = json.load(f)
            mlog("VERSION", f"Cargadas {len(_versions)} versiones")
    except Exception as e:
        mlog("VERSION", f"Error cargando versiones: {e}")


def guardar_version(pesos, params, metricas):
    """
    Guarda una nueva version de configuracion con sus metricas.

    Args:
        pesos: dict de pesos por regimen
        params: dict de parametros generales (umbrales, etc.)
        metricas: dict con winrate, sharpe, n_trades, etc.

    Returns: hash de la version
    """
    config = {"pesos": pesos, "params": params}
    config_str = json.dumps(config, sort_keys=True)
    hash_ = hashlib.md5(config_str.encode()).hexdigest()[:8]

    version = {
        "hash": hash_,
        "config": config,
        "metricas": metricas,
        "created_at": int(time.time()),
        "activa": True,
    }

    # Desactivar version anterior
    for v in _versions:
        v["activa"] = False

    _versions.append(version)

    # Limitar a 50 versiones
    while len(_versions) > 50:
        _versions.pop(0)

    _guardar()
    mlog("VERSION", f"Version {hash_} guardada (WR={metricas.get('winrate', 0)}%)")
    return hash_


def revertir_a_version(hash_):
    """
    Revierte a una version anterior.

    Args:
        hash_: hash de la version a recuperar

    Returns: dict {pesos, params} o None
    """
    for v in _versions:
        if v["hash"] == hash_:
            # Desactivar todas
            for vv in _versions:
                vv["activa"] = False
            v["activa"] = True
            _guardar()
            mlog("VERSION", f"Revertido a version {hash_}")
            return v["config"]

    mlog("VERSION", f"Version {hash_} no encontrada")
    return None


def get_version_activa():
    """Obtiene la version activa actual."""
    for v in reversed(_versions):
        if v.get("activa"):
            return v
    return None


def get_historial():
    """Lista de versiones con metricas."""
    return [
        {
            "hash": v["hash"],
            "metricas": v["metricas"],
            "created_at": v["created_at"],
            "activa": v.get("activa", False),
        }
        for v in _versions[-20:]  # Ultimas 20
    ]


def comparar_versiones(hash_a, hash_b):
    """Compara metricas de dos versiones."""
    va = next((v for v in _versions if v["hash"] == hash_a), None)
    vb = next((v for v in _versions if v["hash"] == hash_b), None)

    if not va or not vb:
        return None

    return {
        "version_a": {"hash": hash_a, "metricas": va["metricas"]},
        "version_b": {"hash": hash_b, "metricas": vb["metricas"]},
    }


def _guardar():
    try:
        with open(VERSIONS_FILE, "w") as f:
            json.dump(_versions, f, indent=1)
    except Exception as e:
        mlog("VERSION", f"Error guardando: {e}")


def auto_check_rendimiento(metricas_actuales, umbral_degradacion=0.1):
    """
    Compara rendimiento actual con la version guardada.
    Si el rendimiento cae mas del umbral, alerta para revertir.

    Returns: (degradado: bool, version_mejor: hash o None, mensaje)
    """
    activa = get_version_activa()
    if not activa:
        return False, None, "Sin version de referencia"

    wr_actual = metricas_actuales.get("winrate", 0)
    wr_guardado = activa["metricas"].get("winrate", 0)

    if wr_guardado > 0 and wr_actual < wr_guardado * (1 - umbral_degradacion):
        # Buscar la mejor version historica
        mejor = max(_versions, key=lambda v: v["metricas"].get("winrate", 0))
        return True, mejor["hash"], \
            f"Degradacion: WR actual {wr_actual:.0f}% vs guardado {wr_guardado:.0f}%"

    return False, None, "Rendimiento estable"


# Inicializar
init()
