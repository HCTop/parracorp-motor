# -*- coding: utf-8 -*-
"""
sr_engine.py - Capa 7: Soporte y Resistencia Dinamicos
ParraCorp v3.1

Detecta niveles clave usando fractales y pivot points.
Mejora colocacion SL/TP y filtra entradas cerca de S/R fuerte.
"""


def detectar_niveles_sr(highs, lows, closes, ventana=20):
    """
    Detecta niveles de soporte y resistencia usando fractales.
    Un fractal de maximo es cuando el high es el mayor de 5 velas.
    Un fractal de minimo es cuando el low es el menor de 5 velas.

    Args:
        highs: lista de maximos
        lows: lista de minimos
        closes: lista de cierres
        ventana: ventana de busqueda

    Returns: lista de niveles [{tipo, precio, fuerza}] ordenados por fuerza
    """
    if len(highs) < 5 or len(lows) < 5:
        return []

    niveles = []

    for i in range(2, len(highs) - 2):
        # Fractal de maximo (resistencia)
        if highs[i] == max(highs[i - 2:i + 3]):
            niveles.append({"tipo": "R", "precio": highs[i], "fuerza": 0})
        # Fractal de minimo (soporte)
        if lows[i] == min(lows[i - 2:i + 3]):
            niveles.append({"tipo": "S", "precio": lows[i], "fuerza": 0})

    # Fuerza = cuantas veces el precio ha respetado el nivel
    for niv in niveles:
        niv["fuerza"] = sum(
            1 for c in closes
            if abs(c - niv["precio"]) / max(niv["precio"], 0.0001) < 0.001
        )

    # Eliminar duplicados cercanos (merge niveles a menos de 0.1%)
    merged = []
    niveles_sorted = sorted(niveles, key=lambda x: x["precio"])
    for niv in niveles_sorted:
        if merged and abs(niv["precio"] - merged[-1]["precio"]) / max(merged[-1]["precio"], 0.0001) < 0.001:
            # Merge: quedarse con el de mayor fuerza
            if niv["fuerza"] > merged[-1]["fuerza"]:
                merged[-1] = niv
            else:
                merged[-1]["fuerza"] += niv["fuerza"]
        else:
            merged.append(niv)

    return sorted(merged, key=lambda x: x["fuerza"], reverse=True)[:10]


def distancia_sr_mas_cercano(precio_actual, niveles, pip_size=0.0001):
    """
    Calcula distancia en pips al nivel S/R mas cercano.

    Args:
        precio_actual: precio actual del par
        niveles: lista de niveles de detectar_niveles_sr()
        pip_size: tamaño de pip (0.0001 para forex, 0.01 para JPY)

    Returns: (distancia_pips, tipo S/R)
    """
    if not niveles:
        return 999.0, "NINGUNO"

    distancias = []
    for n in niveles:
        dist = abs(precio_actual - n["precio"]) / pip_size
        distancias.append((dist, n["tipo"], n["fuerza"]))

    # Ordenar por distancia
    distancias.sort(key=lambda x: x[0])
    dist, tipo, fuerza = distancias[0]

    return round(dist, 1), tipo


def get_sr_info(highs, lows, closes, precio_actual, simbolo=""):
    """
    Info completa de S/R para la app y la IA.

    Args:
        highs: lista de maximos
        lows: lista de minimos
        closes: lista de cierres
        precio_actual: precio actual
        simbolo: nombre del par (para calcular pip_size)

    Returns: dict con niveles, distancia, tipo zona
    """
    # Determinar pip_size
    sym = simbolo.upper()
    if "JPY" in sym:
        pip_size = 0.01
    elif "XAU" in sym:
        pip_size = 0.1
    elif "XAG" in sym:
        pip_size = 0.001
    elif any(x in sym for x in ["BTC", "ETH", "SOL", "BNB", "XRP", "DOGE"]):
        pip_size = 1.0
    elif any(x in sym for x in ["US30", "NAS", "SPX", "DE40", "UK100"]):
        pip_size = 1.0
    else:
        pip_size = 0.0001

    niveles = detectar_niveles_sr(highs, lows, closes)
    dist, tipo = distancia_sr_mas_cercano(precio_actual, niveles, pip_size)

    # Determinar zona
    if dist < 10:
        zone_type = tipo  # "S" o "R"
    else:
        zone_type = "NINGUNO"

    return {
        "sr_niveles": niveles[:5],  # Top 5 niveles
        "sr_distance_pips": dist,
        "sr_zone_type": zone_type,
        "sr_pip_size": pip_size,
        "sr_cerca": dist < 15,  # Alerta si cerca de S/R
    }
