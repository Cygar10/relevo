"""Corre las macros en hilos, atiende los atajos globales y graba acciones."""
import ctypes
import queue
import random
import threading
import time

import entrada
from datos import nuevo_paso

_winmm = ctypes.WinDLL("winmm")
ESPERA_MIN_CICLO = 0.001  # una macro sin esperas no debe saturar la CPU ni el programa
TOQUE = 0.03              # duracion minima de una pulsacion: muchos programas leen por fotograma
TOQUE_CLICK = 0.015


class Ejecutor(threading.Thread):
    """Una macro corriendo. Lee la macro en vivo: mover un slider aplica al instante."""

    def __init__(self, macro, stats, al_terminar=None, salida=entrada, registro=None, origen="atajo"):
        super().__init__(daemon=True)
        self.macro, self.stats, self.al_terminar, self.salida = macro, stats, al_terminar, salida
        self.registro, self.origen = registro, origen
        self.parar = threading.Event()
        self.motivo = ""
        self.conteo = {"clicks": 0, "teclas": 0}
        self.sostenidas = []
        self.pausada = False

    def detener(self, motivo):
        if not self.parar.is_set():
            self.motivo = motivo
            self.parar.set()

    def _anotar(self, tipo, texto=""):
        if self.registro:
            self.registro(self.macro, tipo, texto)

    def _contar(self, clave, n=1):
        self.stats[clave] += n
        self.conteo[clave] += n

    # ------------------------------------------------------------ tiempos
    def _ajustar(self, seg):
        v = self.macro["variacion"] / 100
        return seg * random.uniform(1 - v, 1 + v) / max(self.macro["velocidad"], 0.1)

    def _ventana_ok(self):
        filtro = self.macro["ventana"].strip().lower()
        return not filtro or filtro in entrada.titulo_ventana_activa().lower()

    def _revisar_ventana(self):
        """Si cambiaste de ventana, suelta todo y espera a que vuelvas."""
        if self._ventana_ok():
            return
        self.pausada = True
        self._anotar("PAUSA", "cambiaste de ventana")
        retenidas = list(self.sostenidas)
        self._soltar_todo()
        while not self.parar.is_set() and not self._ventana_ok():
            self.parar.wait(0.1)
        self.pausada = False
        if not self.parar.is_set():
            self._anotar("SIGUE", "volviste a la ventana")
            for t in retenidas:
                self._bajar(t)

    def _dormir(self, seg):
        fin = time.perf_counter() + seg
        while not self.parar.is_set():
            self._revisar_ventana()
            resta = fin - time.perf_counter()
            if resta <= 0:
                return
            self.parar.wait(min(resta, 0.05))

    # ------------------------------------------------------------- salida
    def _bajar(self, t):
        self.salida.presionar(t)
        if t not in self.sostenidas:
            self.sostenidas.append(t)

    def _subir(self, t):
        self.salida.soltar(t)
        if t in self.sostenidas:
            self.sostenidas.remove(t)

    def _soltar_todo(self):
        for t in reversed(list(self.sostenidas)):
            self._subir(t)

    def _pulsar(self, teclas, seg):
        for t in teclas:
            self._bajar(t)
        self._dormir(max(seg, TOQUE))
        for t in reversed(teclas):
            self._subir(t)
        self._contar("teclas", len(teclas))

    # -------------------------------------------------------------- pasos
    def _click(self, p):
        for _ in range(p["veces"]):
            if self.parar.is_set():
                return
            self._revisar_ventana()
            self._bajar(p["boton"])
            self._dormir(TOQUE_CLICK)
            self._subir(p["boton"])
            self._contar("clicks")
            if p["cps"] > 0:
                self._dormir(max(self._ajustar(1 / p["cps"]) - TOQUE_CLICK, 0))

    def _tecla(self, p):
        teclas = [t for t in entrada.separar(p["teclas"]) if entrada.es_valida(t)]
        if teclas:
            self._pulsar(teclas, self._ajustar(self._rango(p)))

    def _aleatoria(self, p):
        teclas = [t for t in p["lista"].replace(",", " ").split() if entrada.es_valida(t)]
        if teclas:
            self._pulsar([random.choice(teclas)], self._ajustar(self._rango(p)))

    @staticmethod
    def _rango(p):
        a, b = sorted((p["min"], p["max"]))
        return random.uniform(a, b)

    def _espera(self, p):
        self._dormir(self._ajustar(self._rango(p)))

    def _estado(self, p):
        if entrada.es_valida(p["objetivo"]):
            (self._bajar if p["accion"] == "presionar" else self._subir)(p["objetivo"])

    def _mouse(self, p):
        self.salida.mover(p["x"], p["y"], p["relativo"])

    def _rueda(self, p):
        self.salida.rueda(p["muescas"])

    def _texto(self, p):
        for c in p["texto"]:
            if self.parar.is_set():
                return
            self.salida.escribir_caracter(c)
            self._contar("teclas")
            if p["cps"] > 0:
                self._dormir(self._ajustar(1 / p["cps"]))

    def _ciclo(self, pasos):
        faltan = {}  # repeticiones pendientes de cada paso "repetir"
        i = 0
        while i < len(pasos) and not self.parar.is_set():
            p = pasos[i]
            if p["tipo"] == "repetir":
                faltan.setdefault(i, p["veces"])
                if faltan[i] > 0:
                    faltan[i] -= 1
                    i = max(i - p["atras"], 0)
                    continue
                del faltan[i]
            elif p["prob"] >= 100 or random.random() * 100 < p["prob"]:
                self._revisar_ventana()
                getattr(self, "_" + p["tipo"])(p)
            i += 1

    def run(self):
        _winmm.timeBeginPeriod(1)
        inicio = time.perf_counter()
        hechas = 0
        final = ""
        self._anotar("INICIO", f"con {self.origen}")
        try:
            while not self.parar.is_set():
                pasos = [p for p in self.macro["pasos"] if p.get("activo", True)]
                if not pasos:
                    final = "sin pasos activos"
                    break
                self._ciclo(pasos)
                if self.parar.is_set():
                    break
                hechas += 1
                reps = self.macro["repeticiones"]
                if self.macro["modo"] == "una_vez":
                    reps = reps or 1
                if reps and hechas >= reps:
                    final = "completó las repeticiones"
                    break
                self._dormir(ESPERA_MIN_CICLO)
        except Exception as e:
            final = "se detuvo por un error"
            self._anotar("ERROR", f"{type(e).__name__}: {e}")
        finally:
            self._soltar_todo()
            duracion = time.perf_counter() - inicio
            self.stats["segundos"] += duracion
            _winmm.timeEndPeriod(1)
            self._anotar("FIN", f"{final or self.motivo or 'detenida'}  |  {duracion:.1f} s  |  {hechas} ciclos  |  "
                                f"{self.conteo['clicks']} clicks  |  {self.conteo['teclas']} teclas")
            if self.al_terminar:
                self.al_terminar(self)


class Motor:
    def __init__(self, stats, salida=entrada):
        self.stats, self.salida = stats, salida
        self.macros = []
        self.tecla_detener, self.tecla_cerrar = "", ""
        self.al_cerrar = None
        self.al_cambiar = None
        self.registro = None           # registro(macro, tipo, texto): lo conecta la UI
        self.escribiendo = False      # la UI lo activa si tienes el foco en un campo de texto
        self.rect_propio = None        # ventana propia: los clicks ahi no se graban
        self._corriendo = {}
        self._lock = threading.RLock()
        self._cola = queue.SimpleQueue()
        self._sostenidas = []
        self._captura = None
        self._grabacion = None
        self._teclado = entrada.gancho_teclado(lambda n, a: self._cola.put((n, a, None, None)))
        self._mouse = entrada.gancho_mouse(lambda n, a, x, y: self._cola.put((n, a, x, y)))
        threading.Thread(target=self._despachar, daemon=True).start()

    def encender(self):
        self._teclado.iniciar()
        self._sincronizar_mouse()

    def apagar(self):
        self.detener_todo("cerraste Relevo")
        for r in list(self._corriendo.values()):
            r.join(1)
        self._teclado.detener()
        self._mouse.detener()

    def configurar(self, macros, tecla_detener, tecla_cerrar):
        self.macros, self.tecla_detener, self.tecla_cerrar = macros, tecla_detener, tecla_cerrar
        self._sincronizar_mouse()

    def _sincronizar_mouse(self):
        """El hook de mouse solo se instala si hace falta: asi nunca mete lag al apuntar."""
        atajos = [m["tecla"] for m in self.macros] + [self.tecla_detener, self.tecla_cerrar]
        hace_falta = self._captura or self._grabacion is not None or any(
            t in entrada.BOTONES_MOUSE for a in atajos for t in entrada.separar(a))
        if hace_falta:
            self._mouse.iniciar()
        else:
            self._mouse.detener()
            # Sin hook no llegara el "soltar": no dejar botones pegados en la lista.
            self._sostenidas = [t for t in self._sostenidas if t not in entrada.BOTONES_MOUSE]

    # ---------------------------------------------------------- ejecucion
    def corriendo(self, mid):
        r = self._corriendo.get(mid)
        return r is not None and r.is_alive()

    def pausada(self, mid):
        r = self._corriendo.get(mid)
        return r is not None and r.pausada

    def iniciar(self, macro, origen=None):
        with self._lock:
            if self.corriendo(macro["id"]):
                return
            origen = origen or (f"atajo {macro['tecla']}" if macro["tecla"] else "atajo")
            r = Ejecutor(macro, self.stats, self._termino, self.salida, self.registro, origen)
            self._corriendo[macro["id"]] = r
            r.start()
        self._avisar(macro, True)

    def detener(self, mid, motivo="pulsaste el atajo"):
        r = self._corriendo.get(mid)
        if r:
            r.detener(motivo)

    def alternar(self, macro):
        if self.corriendo(macro["id"]):
            self.detener(macro["id"])
        else:
            self.iniciar(macro)

    def detener_todo(self, motivo="Detener todo"):
        for r in list(self._corriendo.values()):
            r.detener(motivo)

    def _termino(self, ejecutor):
        with self._lock:
            if self._corriendo.get(ejecutor.macro["id"]) is ejecutor:
                del self._corriendo[ejecutor.macro["id"]]
        self._avisar(ejecutor.macro, False)

    def _avisar(self, macro, encendida):
        if self.al_cambiar:
            self.al_cambiar(macro, encendida)

    # -------------------------------------------------------------- atajos
    @staticmethod
    def elegir_atajos(atajos, tecla, sostenidas):
        """Atajos que dispara `tecla`. Otras teclas sostenidas no estorban (WASD del movimiento);
        si hay F1 y Ctrl+F1, gana el mas especifico."""
        candidatos = []
        for valor, combo in atajos:
            partes = entrada.separar(combo)
            if partes and partes[-1].upper() == tecla.upper():
                sostenidas_mayus = {s.upper() for s in sostenidas}
                if all(p.upper() in sostenidas_mayus for p in partes[:-1]):
                    candidatos.append((len(partes), valor))
        if not candidatos:
            return []
        mayor = max(c[0] for c in candidatos)
        return [v for n, v in candidatos if n == mayor]

    def _despachar(self):
        while True:
            nombre, abajo, x, y = self._cola.get()
            try:
                self._procesar(nombre, abajo, x, y)
            except Exception:
                pass  # un fallo en un atajo no debe dejar sin atajos al resto de la sesion

    def _procesar(self, nombre, abajo, x, y):
        if abajo:
            if nombre in self._sostenidas:  # auto-repeticion de Windows
                return
            self._sostenidas.append(nombre)
        elif nombre in self._sostenidas:
            self._sostenidas.remove(nombre)

        if self._captura:
            self._procesar_captura(nombre, abajo)
            return
        if self._grabacion is not None:
            self._registrar(nombre, abajo, x, y)
        if abajo:
            self._al_presionar(nombre)
        else:
            self._al_soltar(nombre)

    def _al_presionar(self, nombre):
        globales = [("detener", self.tecla_detener), ("cerrar", self.tecla_cerrar)]
        for accion in self.elegir_atajos(globales, nombre, self._sostenidas):
            if accion == "detener":
                self.detener_todo()
                if self._grabacion is not None and self.al_detener_grabacion:
                    self.al_detener_grabacion()
            elif self.al_cerrar:
                self.al_cerrar()
            return
        if self.escribiendo or self._grabacion is not None:
            return
        atajos = [(m, m["tecla"]) for m in self.macros]
        for m in self.elegir_atajos(atajos, nombre, self._sostenidas):
            if m["modo"] == "mantener":
                self.iniciar(m)
            else:
                self.alternar(m)

    def _al_soltar(self, nombre):
        for m in self.macros:
            if m["modo"] == "mantener" and nombre.upper() in {p.upper() for p in entrada.separar(m["tecla"])}:
                self.detener(m["id"], "soltaste el atajo")

    # ------------------------------------------------------------- captura
    def capturar(self, al_terminar):
        """Escucha la proxima tecla o combinacion. al_terminar(combo) o (None) con Esc."""
        self._captura = {"fn": al_terminar, "combo": []}
        self._sincronizar_mouse()

    def cancelar_captura(self):
        self._captura = None
        self._sincronizar_mouse()

    def _procesar_captura(self, nombre, abajo):
        c = self._captura
        if abajo:
            if nombre in (entrada.MOUSE_IZQ, entrada.MOUSE_DER):
                return  # son los del click sobre la propia ventana
            if nombre == "Esc" and not c["combo"]:
                self._terminar_captura(None)
            elif nombre not in c["combo"]:
                c["combo"].append(nombre)
            return
        if nombre in c["combo"]:
            # Modificadores primero, sin importar el orden en que se pulsaron.
            combo = sorted(c["combo"], key=lambda t: t not in entrada.MODIFICADORES)
            self._terminar_captura("+".join(combo))

    def _terminar_captura(self, combo):
        fn = self._captura["fn"]
        self._captura = None
        self._sincronizar_mouse()
        fn(combo)

    # ------------------------------------------------------------- grabar
    al_detener_grabacion = None

    def grabar(self):
        self.detener_todo()
        self._grabacion = []
        self._sincronizar_mouse()

    @property
    def grabando(self):
        return self._grabacion is not None

    def terminar_grabacion(self):
        eventos, self._grabacion = self._grabacion or [], None
        self._sincronizar_mouse()
        return eventos_a_pasos(eventos)

    def _registrar(self, nombre, abajo, x, y):
        if nombre.upper() in {p.upper() for p in entrada.separar(self.tecla_detener)}:
            return
        if x is not None and self.rect_propio:
            izq, arr, der, aba = self.rect_propio
            if izq <= x < der and arr <= y < aba:
                return
        self._grabacion.append((time.perf_counter(), nombre, abajo, x, y))


def eventos_a_pasos(eventos):
    """Convierte (t, nombre, abajo, x, y) en pasos: pulsaciones simples donde se pueda."""
    pasos, previo = [], None
    i = 0
    while i < len(eventos):
        t, nombre, abajo, x, y = eventos[i]
        if previo is not None and t - previo >= 0.02:
            pasos.append(nuevo_paso("espera", min=round(t - previo, 3), max=round(t - previo, 3)))
        previo = t
        if x is not None and abajo:
            pasos.append(nuevo_paso("mouse", x=x, y=y, relativo=False))
        sig = eventos[i + 1] if i + 1 < len(eventos) else None
        if abajo and sig and sig[1] == nombre and not sig[2]:
            dur = round(sig[0] - t, 3)
            if x is not None and dur < 0.25:
                pasos.append(nuevo_paso("click", boton=nombre, veces=1, cps=0.0))
            elif x is None:
                dur = dur if dur >= 0.08 else 0.0
                pasos.append(nuevo_paso("tecla", teclas=nombre, min=dur, max=dur))
            else:
                pasos.append(nuevo_paso("estado", accion="presionar", objetivo=nombre))
                pasos.append(nuevo_paso("espera", min=dur, max=dur))
                pasos.append(nuevo_paso("estado", accion="soltar", objetivo=nombre))
            previo = sig[0]
            i += 2
            continue
        pasos.append(nuevo_paso("estado", accion="presionar" if abajo else "soltar", objetivo=nombre))
        i += 1
    return pasos
