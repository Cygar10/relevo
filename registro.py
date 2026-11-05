"""Registro de cada macro: un archivo por macro y por dia, borrados al pasar los dias elegidos.

Guarda cuando empieza y termina, por que y cuanto hizo; nunca el texto de los pasos "Escribir".
"""
import datetime
import os
import re
import shutil
import threading

DIAS_BASE = 7


class Registro:
    def __init__(self, ajustes, carpeta):
        self.ajustes, self.carpeta = ajustes, carpeta
        self._lock = threading.Lock()
        self._ultimo_dia = None

    def _carpeta_de(self, mid):
        # El id viene del archivo de configuracion: que nunca pueda salir de la carpeta de logs.
        return os.path.join(self.carpeta, re.sub(r"[^A-Za-z0-9_-]", "_", str(mid)))

    def _dias_a_guardar(self):
        try:
            return max(int(self.ajustes.get("registro_dias", DIAS_BASE)), 1)
        except (TypeError, ValueError):
            return DIAS_BASE

    def anotar(self, macro, tipo, texto=""):
        """Nunca lanza errores: un disco lleno no debe frenar una macro."""
        if not self.ajustes.get("registro", True):
            return
        ahora = datetime.datetime.now()
        hoy = ahora.date()
        linea = f"{ahora:%Y-%m-%d %H:%M:%S}  {tipo:<7} {macro['nombre']}" + (f"  |  {texto}" if texto else "") + "\n"
        with self._lock:
            try:
                if self._ultimo_dia != hoy:
                    self._ultimo_dia = hoy
                    self._limpiar(hoy)
                carpeta = self._carpeta_de(macro["id"])
                os.makedirs(carpeta, exist_ok=True)
                with open(os.path.join(carpeta, f"{hoy:%Y-%m-%d}.log"), "a", encoding="utf-8") as f:
                    f.write(linea)
            except OSError:
                pass

    def limpiar(self):
        with self._lock:
            self._limpiar(datetime.date.today())

    def _limpiar(self, hoy):
        """Se llama al abrir Relevo y al cambiar de dia, no al escribir el numero de dias:
        teclear "14" pasa por "1" y no debe borrar nada."""
        if not os.path.isdir(self.carpeta):
            return
        limite = hoy - datetime.timedelta(days=self._dias_a_guardar() - 1)
        for sub in os.scandir(self.carpeta):
            if not sub.is_dir():
                continue
            for arch in os.scandir(sub.path):
                dia = _dia_de_archivo(arch.name)
                if dia and dia < limite:
                    try:
                        os.remove(arch.path)
                    except OSError:
                        pass
            try:
                os.rmdir(sub.path)  # solo si quedo vacia
            except OSError:
                pass

    def ruta(self, mid):
        return self._carpeta_de(mid)

    def dias(self, mid):
        """Dias con registro de esa macro, del mas reciente al mas antiguo."""
        carpeta = self._carpeta_de(mid)
        if not os.path.isdir(carpeta):
            return []
        return sorted((n[:-4] for n in os.listdir(carpeta) if _dia_de_archivo(n)), reverse=True)

    def leer(self, mid, dia):
        """Lineas de ese dia, las mas recientes primero."""
        if not _dia_de_archivo(f"{dia}.log"):
            return []
        try:
            with open(os.path.join(self._carpeta_de(mid), f"{dia}.log"), encoding="utf-8", errors="replace") as f:
                return f.read().splitlines()[::-1]
        except OSError:
            return []

    def borrar(self, mid):
        with self._lock:
            shutil.rmtree(self._carpeta_de(mid), ignore_errors=True)


def _dia_de_archivo(nombre):
    if not nombre.endswith(".log"):
        return None
    try:
        return datetime.date.fromisoformat(nombre[:-4])
    except ValueError:
        return None
