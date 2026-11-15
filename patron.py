"""Patron de teclas: una linea de texto que dice que tecla, cuanto tiempo y cuantas veces.

    A 3, D 5        mantiene A tres segundos y luego D cinco
    W 0.5-2         W entre medio segundo y dos, distinto cada vez
    Ctrl+C          un toque de la combinacion
    Espacio x3      tres toques seguidos
    espera 1.5      pausa sin tocar nada
"""
import re

import entrada

ORDENES = {"seguido": "En orden", "vaiven": "Ida y vuelta", "azar": "Barajado", "una": "Una al azar"}
ESPERAS = {"espera", "esperar", "pausa"}
MAX_SEGUNDOS, MAX_VECES = 86400.0, 1000

_NUM = r"\d*\.?\d+"
_TIEMPO = re.compile(rf"^({_NUM})(?:-({_NUM}))?s?$", re.I)
_VECES = re.compile(r"^x(\d+)$", re.I)
_MOUSE = {b.lower(): b for b in entrada.BOTONES_MOUSE}


def _tecla(nombre):
    """Nombre tal como lo conoce Relevo ('a' -> 'A', 'mouse izq' -> 'Mouse Izq'), o None."""
    n = nombre.strip()
    if n.lower() in _MOUSE:
        return _MOUSE[n.lower()]
    vk = entrada.vk_de_nombre(n)
    return entrada.nombre_de_vk(vk) if vk is not None else None


def _combo(nombre):
    teclas = [_tecla(t) for t in entrada.separar(nombre)]
    return teclas if teclas and all(teclas) else None


def _tiempo(texto):
    a, b = _TIEMPO.match(texto).groups()
    a, b = sorted((float(a), float(b if b is not None else a)))
    return min(a, MAX_SEGUNDOS), min(b, MAX_SEGUNDOS)


def leer(texto):
    """Devuelve (elementos, errores). Un elemento es dict(teclas, min, max, veces):
    `teclas` vacio es una espera, y `min` en None significa "la duracion normal del paso"."""
    elementos, errores = [], []
    for trozo in re.split(r"[,;\n]+", texto or ""):
        partes = trozo.split()
        if not partes:
            continue
        veces = 1
        if len(partes) > 1 and _VECES.match(partes[-1]):
            veces = max(1, min(int(partes.pop()[1:]), MAX_VECES))
        nombre = " ".join(partes)
        if nombre.lower() in ESPERAS:
            errores.append(f"\"{nombre}\" necesita un tiempo, por ejemplo: espera 1.5")
            continue
        es_tiempo = bool(_TIEMPO.match(partes[-1]))
        if es_tiempo and len(partes) == 1 and not nombre.isdigit():
            a, b = _tiempo(nombre)  # "0.5" suelto es una espera; "5" suelto es la tecla 5
            elementos.append(dict(teclas=[], min=a, max=b, veces=veces))
            continue
        duracion = (None, None)
        teclas = None
        if es_tiempo and len(partes) > 1:
            resto = " ".join(partes[:-1])
            if resto.lower() in ESPERAS:
                a, b = _tiempo(partes[-1])
                elementos.append(dict(teclas=[], min=a, max=b, veces=veces))
                continue
            teclas = _combo(resto)
            if teclas:
                duracion = _tiempo(partes[-1])
        teclas = teclas or _combo(nombre)  # "Mouse 4": el numero es parte del nombre
        if not teclas:
            errores.append(f"No conozco \"{nombre}\"")
            continue
        elementos.append(dict(teclas=teclas, min=duracion[0], max=duracion[1], veces=veces))
    return elementos, errores


def describir(texto):
    """'A 3 s → D 5 s' para mostrarlo en la lista de pasos."""
    trozos = []
    for el in leer(texto)[0]:
        t = "+".join(el["teclas"]) or "espera"
        if el["min"] is not None:
            t += f" {el['min']:g} s" if el["min"] == el["max"] else f" {el['min']:g}-{el['max']:g} s"
        if el["veces"] > 1:
            t += f" ×{el['veces']}"
        trozos.append(t)
    return " → ".join(trozos)
