"""Perfiles, macros, pasos y plantillas. Todo se guarda como JSON."""
import copy
import json
import os
import random
import string

APP = "Relevo"
RUTA = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP, "config.json")

MODOS = {"alternar": "Encender / apagar", "mantener": "Mientras la mantengo", "una_vez": "Una sola vez"}

# tipo -> (nombre visible, icono MDL2, descripcion, valores por defecto)
PASOS = {
    "click": ("Click", "", "Clicks de mouse a la velocidad que elijas",
              {"boton": "Mouse Izq", "veces": 1, "cps": 4.5}),
    "tecla": ("Tecla", "", "Pulsa una tecla o combinación, y cuánto dura",
              {"teclas": "Espacio", "min": 0.0, "max": 0.0}),
    "aleatoria": ("Tecla al azar", "", "Elige una tecla de tu lista cada vez",
                  {"lista": "W A S D", "min": 0.5, "max": 5.0}),
    "espera": ("Espera", "", "Pausa fija o entre dos tiempos",
               {"min": 1.0, "max": 1.0}),
    "estado": ("Mantener / soltar", "", "Deja algo presionado hasta que lo sueltes",
               {"accion": "presionar", "objetivo": "Mouse Izq"}),
    "mouse": ("Mover mouse", "", "A un punto de la pantalla o relativo",
              {"x": 0, "y": 0, "relativo": False}),
    "rueda": ("Rueda", "", "Gira la rueda arriba o abajo",
              {"muescas": 1}),
    "texto": ("Escribir", "", "Escribe un texto letra por letra",
              {"texto": "Hola", "cps": 20.0}),
    "repetir": ("Repetir", "", "Vuelve atrás y repite los ultimos pasos",
                {"atras": 1, "veces": 1}),
}


def nuevo_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def nuevo_paso(tipo, **valores):
    paso = {"tipo": tipo, "activo": True, "prob": 100}
    paso.update(copy.deepcopy(PASOS[tipo][3]))
    paso.update(valores)
    return paso


def nueva_macro(nombre="Nueva macro", tecla="", pasos=None, **extra):
    macro = {"id": nuevo_id(), "nombre": nombre, "tecla": tecla, "modo": "alternar", "repeticiones": 0,
             "variacion": 10, "velocidad": 1.0, "ventana": "", "cuenta": 3, "pasos": pasos or []}
    macro.update(extra)
    return macro


def _plantilla_autoclick():
    return nueva_macro("Autoclick", "F1", [nuevo_paso("click", cps=4.5)])


def _plantilla_movimiento():
    return nueva_macro("Movimiento aleatorio", "F8", [
        nuevo_paso("aleatoria", lista="W A S D", min=0.5, max=5.0),
        nuevo_paso("espera", min=0.2, max=0.2)], variacion=0)


PLANTILLAS = [
    ("En blanco", "Empieza de cero y arma los pasos tú mismo", lambda: nueva_macro()),
    ("Autoclick", "Clicks continuos a 4.5 por segundo, con variación natural", _plantilla_autoclick),
    ("Movimiento aleatorio", "WASD al azar, de 0.5 a 5 s por paso", _plantilla_movimiento),
    ("Mantener click", "El botón queda presionado mientras la macro corre", lambda: nueva_macro(
        "Mantener click", "", [nuevo_paso("estado", accion="presionar", objetivo="Mouse Izq"),
                               nuevo_paso("espera", min=3600.0, max=3600.0)], variacion=0)),
    ("Repetir tecla", "Pulsa una tecla una y otra vez sin gastar la tuya", lambda: nueva_macro(
        "Repetir tecla", "", [nuevo_paso("tecla", teclas="E"), nuevo_paso("espera", min=0.5, max=0.5)])),
    ("Anti-AFK", "Un salto y un paso cada cierto tiempo para no quedar inactivo", lambda: nueva_macro(
        "Anti-AFK", "", [nuevo_paso("tecla", teclas="Espacio"), nuevo_paso("aleatoria", lista="W A S D", min=0.2, max=0.6),
                         nuevo_paso("espera", min=60.0, max=120.0)])),
    ("Combo de teclas", "Secuencia 1-2-3 repetida tres veces y descanso", lambda: nueva_macro(
        "Combo de teclas", "", [nuevo_paso("tecla", teclas="1"), nuevo_paso("espera", min=0.2, max=0.2),
                                nuevo_paso("tecla", teclas="2"), nuevo_paso("espera", min=0.2, max=0.2),
                                nuevo_paso("tecla", teclas="3"), nuevo_paso("espera", min=0.2, max=0.2),
                                nuevo_paso("repetir", atras=6, veces=2), nuevo_paso("espera", min=2.0, max=2.0)])),
    ("Scroll continuo", "Baja una página sin desgastar la rueda ni el dedo", lambda: nueva_macro(
        "Scroll continuo", "", [nuevo_paso("rueda", muescas=-3), nuevo_paso("espera", min=1.5, max=1.5)])),
]

AJUSTES_BASE = {
    "tema": "Noche", "acento": "#C8F04B", "encima": False, "opacidad": 100, "sonido": False,
    "tecla_detener": "F10", "tecla_cerrar": "F9", "compacto": False, "perfil": "",
    "registro": True, "registro_dias": 7, "ancho": 1000, "alto": 680, "admin": False,
}


def _perfil_inicial():
    return {"id": nuevo_id(), "nombre": "Mi perfil", "macros": [_plantilla_autoclick()]}


# ------------------------------------------------------------ normalizacion

def _num(valor, base, minimo, maximo, tipo=float):
    try:
        v = tipo(valor)
    except (TypeError, ValueError):
        v = base
    return max(minimo, min(maximo, v))


def normalizar_paso(p):
    """Completa y acota un paso: los JSON importados pueden traer cualquier cosa."""
    if not isinstance(p, dict) or p.get("tipo") not in PASOS:
        return None
    n = nuevo_paso(p["tipo"])
    for clave, base in n.items():
        if clave in p and clave != "tipo":
            if isinstance(base, bool):
                n[clave] = bool(p[clave])
            elif isinstance(base, int):
                n[clave] = _num(p[clave], base, -100000, 100000, int)
            elif isinstance(base, float):
                n[clave] = _num(p[clave], base, 0.0, 86400.0)
            elif isinstance(base, str):
                n[clave] = str(p[clave])
    n["prob"] = _num(n["prob"], 100, 0, 100, int)
    if n["tipo"] in ("click", "repetir"):
        n["veces"] = _num(n["veces"], 1, 1, 10000, int)
    if n["tipo"] == "repetir":
        n["atras"] = _num(n["atras"], 1, 1, 1000, int)
    if "cps" in n:
        n["cps"] = _num(n["cps"], 4.5, 0.0, 100.0)
    return n


def normalizar_macro(m):
    if not isinstance(m, dict):
        return None
    n = nueva_macro()
    n["id"] = str(m.get("id") or nuevo_id())
    n["nombre"] = str(m.get("nombre") or "Macro")[:60]
    n["tecla"] = str(m.get("tecla") or "")
    n["modo"] = m.get("modo") if m.get("modo") in MODOS else "alternar"
    n["repeticiones"] = _num(m.get("repeticiones"), 0, 0, 1000000, int)
    n["variacion"] = _num(m.get("variacion"), 10, 0, 50, int)
    n["velocidad"] = _num(m.get("velocidad"), 1.0, 0.1, 10.0)
    n["ventana"] = str(m.get("ventana") or "")
    n["cuenta"] = _num(m.get("cuenta"), 3, 0, 3600, int)
    pasos = m.get("pasos") if isinstance(m.get("pasos"), list) else []
    n["pasos"] = [x for x in map(normalizar_paso, pasos) if x]
    return n


def normalizar_perfil(p):
    if not isinstance(p, dict):
        return None
    macros = p.get("macros") if isinstance(p.get("macros"), list) else []
    return {"id": str(p.get("id") or nuevo_id()), "nombre": str(p.get("nombre") or "Perfil")[:40],
            "macros": [x for x in map(normalizar_macro, macros) if x]}


# ---------------------------------------------------------------- almacen

class Almacen:
    def __init__(self, ruta=RUTA):
        self.ruta = ruta
        self.ajustes = dict(AJUSTES_BASE)
        self.perfiles = []
        self.stats = {"clicks": 0, "teclas": 0, "segundos": 0.0}
        self.cargar()

    def cargar(self):
        datos = {}
        try:
            with open(self.ruta, encoding="utf-8") as f:
                datos = json.load(f)
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            # Archivo danado: se conserva una copia en vez de pisarlo.
            try:
                os.replace(self.ruta, self.ruta + ".danado")
            except OSError:
                pass
        if isinstance(datos, dict):
            if isinstance(datos.get("ajustes"), dict):
                self.ajustes.update({k: v for k, v in datos["ajustes"].items() if k in AJUSTES_BASE})
            if isinstance(datos.get("stats"), dict):
                for k in self.stats:
                    self.stats[k] = _num(datos["stats"].get(k), 0, 0, 1e15)
            perfiles = datos.get("perfiles") if isinstance(datos.get("perfiles"), list) else []
            self.perfiles = [x for x in map(normalizar_perfil, perfiles) if x]
        if not self.perfiles:
            self.perfiles = [_perfil_inicial()]
        if not self.perfil_por_id(self.ajustes["perfil"]):
            self.ajustes["perfil"] = self.perfiles[0]["id"]

    def guardar(self):
        os.makedirs(os.path.dirname(self.ruta), exist_ok=True)
        temporal = self.ruta + ".tmp"
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump({"version": 1, "ajustes": self.ajustes, "stats": self.stats, "perfiles": self.perfiles},
                      f, ensure_ascii=False, indent=1)
        os.replace(temporal, self.ruta)

    def perfil_por_id(self, pid):
        return next((p for p in self.perfiles if p["id"] == pid), None)

    @property
    def perfil(self):
        return self.perfil_por_id(self.ajustes["perfil"])


def exportar(perfil, ruta):
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump({"relevo": 1, "perfil": perfil}, f, ensure_ascii=False, indent=1)


def importar(ruta):
    """Lee un perfil exportado. Devuelve un perfil con ids nuevos o lanza ValueError."""
    with open(ruta, encoding="utf-8") as f:
        datos = json.load(f)
    perfil = normalizar_perfil(datos.get("perfil") if isinstance(datos, dict) else None)
    if not perfil:
        raise ValueError("No es un perfil de Relevo")
    perfil["id"] = nuevo_id()
    for m in perfil["macros"]:
        m["id"] = nuevo_id()
    return perfil
