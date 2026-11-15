"""Interfaz de Relevo: ventana sin marco de Windows, editor de macros y ajustes.

Casi todo se dibuja en unos pocos lienzos (ver lienzo.py) en vez de usar un widget por control:
asi la ventana abre y cambia de tamaño sin verse cargar por partes.
"""
import copy
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
import winsound
from ctypes import wintypes
from tkinter import colorchooser, filedialog

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFilter, ImageTk

import datos
import entrada
import patron
from datos import PASOS, PLANTILLAS
from lienzo import LETRA, MONO, Barra, Escena, Recursos
from lista_pasos import ListaPasos
from registro import Registro

TEMAS = {
    "Noche": dict(fondo="#0E1013", panel="#15181D", tarjeta="#1C2026", borde="#2C313A", texto="#EEF0F3", tenue="#929AA8", modo="dark"),
    "Grafito": dict(fondo="#121212", panel="#1A1A1A", tarjeta="#232323", borde="#353535", texto="#F0F0F0", tenue="#9C9C9C", modo="dark"),
    "Bosque": dict(fondo="#0B1310", panel="#111C18", tarjeta="#17251F", borde="#27392F", texto="#ECF3EF", tenue="#8FA399", modo="dark"),
    "Papel": dict(fondo="#EFEDE7", panel="#F8F6F1", tarjeta="#FFFFFF", borde="#D9D5CA", texto="#1D1C19", tenue="#6B685F", modo="light"),
}
ACENTOS = ["#C8F04B", "#4BD6F0", "#FF7A59", "#A78BFA", "#F472B6", "#FBBF24"]
ROJO, AMBAR = "#EF5350", "#F5B841"

I_ADD, I_EDIT, I_COPY, I_DEL = "", "", "", ""
I_PLAY, I_STOP, I_GEAR, I_BACK = "", "", "", ""
I_MIN, I_MAX, I_RESTORE, I_CLOSE, I_COMPACT, I_EXPAND = "", "", "", "", "", ""
I_LOG, I_IMPORT, I_EXPORT = "", "", ""

ANCHO_COMPACTO, MIN_ANCHO, MIN_ALTO = 300, 980, 520
BORDE_REDIMENSION = 5
CURSORES = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow", "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
            "nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw"}
MODOS_CORTOS = {"Alternar": "alternar", "Mantener": "mantener", "Una vez": "una_vez"}
AYUDA_PATRON = "Tecla y segundos, separadas por comas. Ejemplo: A 3, D 5, W 1-2, Espacio x3, espera 1.5"


def _rgb(c):
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def mezclar(a, b, t):
    ra, rb = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(x + (y - x) * t) for x, y in zip(ra, rb))


def sobre(color):
    """Color de texto legible sobre un fondo dado."""
    r, g, b = _rgb(color)
    return "#101114" if 0.299 * r + 0.587 * g + 0.114 * b > 140 else "#FFFFFF"


def dibujar_logo(px, fondo, baston):
    """El testigo de una carrera de relevos, dibujado en grande y reducido para que quede suave."""
    s = px * 8
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, s - 1, s - 1), radius=s * 0.24, fill=fondo)
    grosor = s * 0.2
    a, b = (s * 0.3, s * 0.7), (s * 0.7, s * 0.3)
    d.line((a, b), fill=baston, width=int(grosor))
    for x, y in (a, b):
        d.ellipse((x - grosor / 2, y - grosor / 2, x + grosor / 2, y + grosor / 2), fill=baston)
    return im.resize((px, px), Image.LANCZOS)


def recurso(nombre):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, nombre)


def captura_ventana(hwnd):
    """Imagen de lo que muestra la ventana, aunque otra la tape. None si Windows no la entrega."""
    u, g = ctypes.windll.user32, ctypes.windll.gdi32
    vp = ctypes.c_void_p
    u.GetDC.argtypes, u.GetDC.restype = (vp,), vp
    u.ReleaseDC.argtypes = (vp, vp)
    u.PrintWindow.argtypes = (vp, vp, ctypes.c_uint)
    g.CreateCompatibleDC.argtypes, g.CreateCompatibleDC.restype = (vp,), vp
    g.CreateCompatibleBitmap.argtypes, g.CreateCompatibleBitmap.restype = (vp, ctypes.c_int, ctypes.c_int), vp
    g.SelectObject.argtypes, g.SelectObject.restype = (vp, vp), vp
    g.DeleteObject.argtypes = (vp,)
    g.DeleteDC.argtypes = (vp,)
    g.GetDIBits.argtypes = (vp, vp, ctypes.c_uint, ctypes.c_uint, vp, vp, ctypes.c_uint)
    caja = wintypes.RECT()
    entrada.user32.GetWindowRect(hwnd, ctypes.byref(caja))
    ancho, alto = caja.right - caja.left, caja.bottom - caja.top
    if ancho <= 0 or alto <= 0:
        return None
    dc = u.GetDC(hwnd)
    mem = g.CreateCompatibleDC(dc)
    mapa = g.CreateCompatibleBitmap(dc, ancho, alto)
    viejo = g.SelectObject(mem, mapa)
    try:
        if not u.PrintWindow(hwnd, mem, 2):  # PW_RENDERFULLCONTENT
            return None
        cabecera = (ctypes.c_uint32 * 10)(40, ancho, (-alto) & 0xFFFFFFFF, 1 | (32 << 16), 0, 0, 0, 0, 0, 0)
        datos_px = ctypes.create_string_buffer(ancho * alto * 4)
        if not g.GetDIBits(mem, mapa, 0, alto, datos_px, cabecera, 0):
            return None
        return Image.frombuffer("RGB", (ancho, alto), datos_px, "raw", "BGRX", 0, 1).copy()
    finally:
        g.SelectObject(mem, viejo)
        g.DeleteObject(mapa)
        g.DeleteDC(mem)
        u.ReleaseDC(hwnd, dc)


class Flujo:
    """Coloca etiquetas y campos de izquierda a derecha, por renglones, dentro de una escena."""

    def __init__(self, app, s, ancho):
        self.app, self.s, self.ancho = app, s, ancho
        self.x = self.y = 0
        self.alto = s.px(34)

    @property
    def medio(self):
        return self.y + self.alto // 2

    @property
    def resto(self):
        return self.ancho - self.x

    def etq(self, texto, izq=0, color=None):
        self.x += self.s.px(izq)
        item = self.s.texto(self.x, self.medio, texto, 11, color=color or self.app.t["tenue"])
        self.x += self.s.medir(texto, 11) + self.s.px(6)
        return item

    def num(self, obj, clave, tipo, minimo, maximo, ancho=56):
        self.app._num(self.s, self.x, self.y + self.s.px(3), self.s.px(ancho), self.s.px(28), obj, clave, tipo, minimo, maximo)
        self.x += self.s.px(ancho + 6)

    def rango(self, p, etiqueta, a="min", b="max", final="segundos"):
        self.etq(etiqueta)
        self.num(p, a, float, 0, 86400)
        self.etq("y")
        self.num(p, b, float, 0, 86400)
        self.etq(final)

    def hueco(self, ancho):
        """Reserva `ancho` para un control y devuelve donde empieza."""
        x, self.x = self.x, self.x + ancho + self.s.px(8)
        return x, self.y + self.s.px(3)

    def salto(self):
        self.x, self.y = 0, self.y + self.alto

    def fin(self):
        return self.y + self.alto


class App:
    def __init__(self, root, almacen, motor):
        self.root, self.a, self.motor = root, almacen, motor
        self.vista = "editor"
        self.sel = None
        self.cola = queue.SimpleQueue()
        self._guardado = None
        self._estado_macros = None
        self._cuenta_atras = None
        self._captura_ui = None
        self._apuntando = None
        self._ultimo_guardado_stats = 0
        self.t = {}
        self.rec = None
        self.pasos_ui = self.cab = self.lista = self.lat_pie = self.barra = None
        self._pantalla = None       # None, "max" o "completa"
        self._geom_normal = None
        self._redim = None
        self._redim_tarea = None
        self._zona = ""
        self._oculta = False
        self._arrancando = True
        self._menu = self._menu_ancla = None
        self._dlg = None
        self._aviso = ("", None)
        self._aviso_tarea = None
        self._ayuda_tarea = self._ayuda_ventana = None
        self._fila_mov = None
        self._nombre_pendiente = None
        self._nombre_sucio = False
        self._registro_dia = None
        self._id_stats = None
        self.registro = Registro(almacen.ajustes, os.path.join(os.path.dirname(almacen.ruta), "logs"))
        self.registro.limpiar()
        motor.registro = self.registro.anotar

        motor.al_cerrar = lambda: self.cola.put(self.cerrar)
        motor.al_cambiar = self._al_cambiar_macro
        motor.al_detener_grabacion = lambda: self.cola.put(self._terminar_grabacion)

        root.title(datos.APP)
        try:
            root.iconbitmap(recurso("relevo.ico"))
        except tk.TclError:
            pass
        root.protocol("WM_DELETE_WINDOW", self.cerrar)
        self._quitar_marco()

        self._aplicar_motor()
        if self.macros:
            self.sel = self.macros[0]["id"]
        self.construir()
        root.bind_all("<Button-1>", self._quitar_foco, add="+")
        root.bind_all("<Button-1>", self._press_global, add="+")
        root.bind_all("<Motion>", self._mover_global, add="+")
        root.bind_all("<B1-Motion>", self._arrastre_global, add="+")
        root.bind_all("<ButtonRelease-1>", self._soltar_global, add="+")
        root.bind_all("<MouseWheel>", self._rueda_global, add="+")
        root.bind("<F11>", lambda _: self._alternar_pantalla("completa"))
        root.bind("<Escape>", self._al_escape)
        root.bind("<Return>", self._al_enter)
        motor.encender()
        self._bombear()
        self._refrescar()

    # ------------------------------------------------------------ accesos
    @property
    def perfil(self):
        return self.a.perfil

    @property
    def macros(self):
        return self.perfil["macros"]

    @property
    def macro(self):
        return next((m for m in self.macros if m["id"] == self.sel), None)

    def px(self, v):
        return round(v * self._escala())

    def _aplicar_motor(self):
        aj = self.a.ajustes
        self.motor.configurar(self.macros, aj["tecla_detener"], aj["tecla_cerrar"])

    def _confirmar_nombre(self):
        pendiente, self._nombre_pendiente = self._nombre_pendiente, None
        if pendiente and pendiente[0].winfo_exists():
            pendiente[1]()

    def _guardar_pronto(self):
        if self._guardado:
            self.root.after_cancel(self._guardado)
        self._guardado = self.root.after(400, self._guardar)
        if self.pasos_ui:
            self.pasos_ui.actualizar_resumen()

    def _guardar(self):
        self._guardado = None
        try:
            self.a.guardar()
        except OSError as e:
            self.aviso(f"No se pudo guardar: {e}", ROJO)

    def _fijar(self, obj, clave, valor):
        obj[clave] = valor
        self._guardar_pronto()

    # ---------------------------------------------------- ventana sin marco
    def _quitar_marco(self):
        """Quita la barra blanca de Windows (y su menu) dejando el icono en la barra de tareas."""
        self.root.overrideredirect(True)
        self.root.attributes("-alpha", 0)  # invisible hasta que todo este dibujado
        self.root.update_idletasks()
        u = entrada.user32
        self.hwnd = u.GetParent(self.root.winfo_id())
        u.SetWindowLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int)
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self._sin_repintado_total()
        self.root.withdraw()
        self.root.after(30, self._mostrar_ventana)
        self.root.after(300, self._fijar_iconos)

    def _sin_repintado_total(self):
        """Tk pide a Windows repintar la ventana entera cada vez que cambia de tamaño, y despues Tk
        vuelve a pintar lo que cambio: el doble de trabajo. Sin esas dos banderas Windows solo pide
        pintar la parte nueva, y cambiar el tamaño va mas del doble de rapido."""
        u = entrada.user32
        u.GetClassLongPtrW.argtypes, u.GetClassLongPtrW.restype = (ctypes.c_void_p, ctypes.c_int), ctypes.c_size_t
        u.SetClassLongPtrW.argtypes, u.SetClassLongPtrW.restype = (ctypes.c_void_p, ctypes.c_int, ctypes.c_size_t), ctypes.c_size_t
        for ventana in (self.hwnd, self.root.winfo_id()):  # la clase de la ventana y la de todo lo de adentro
            estilo = u.GetClassLongPtrW(ventana, -26)       # GCL_STYLE
            u.SetClassLongPtrW(ventana, -26, estilo & ~0x3)  # sin CS_HREDRAW ni CS_VREDRAW

    def _mostrar_ventana(self):
        self.root.deiconify()
        self.root.update_idletasks()
        self._estilo_ventana()
        self.root.update_idletasks()
        self.root.after(30, self._terminar_arranque)

    def _terminar_arranque(self):
        self._arrancando = False
        self._revelar(0)
        self.root.focus_force()

    def _estilo_ventana(self):
        """Tk rehace estos estilos al mostrar la ventana, asi que se aplican despues."""
        u = entrada.user32
        ex = u.GetWindowLongPtrW(self.hwnd, -20)
        nuevo = (ex & ~0x80) | 0x40000  # sin TOOLWINDOW, con APPWINDOW
        est = u.GetWindowLongPtrW(self.hwnd, -16)
        u.SetWindowLongPtrW(self.hwnd, -16, est | 0x20000)  # WS_MINIMIZEBOX
        if nuevo != ex:
            u.SetWindowLongPtrW(self.hwnd, -20, nuevo)
            u.ShowWindow(self.hwnd, 0)  # la barra de tareas solo lo nota al volver a mostrarla
            u.ShowWindow(self.hwnd, 5)

    def _fijar_iconos(self):
        """Da a Windows cada tamano nativo; si no, estira el de 16 px en la barra de tareas."""
        u = entrada.user32
        u.LoadImageW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_uint)
        u.LoadImageW.restype = ctypes.c_void_p
        u.SendMessageW.argtypes = (ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_void_p)
        u.SendMessageW.restype = ctypes.c_ssize_t
        for tipo, metrica_x, metrica_y in ((0, 49, 50), (1, 11, 12)):  # ICON_SMALL, ICON_BIG
            icono = u.LoadImageW(None, recurso("relevo.ico"), 1, u.GetSystemMetrics(metrica_x), u.GetSystemMetrics(metrica_y), 0x10)
            if icono:
                u.SendMessageW(self.hwnd, 0x80, tipo, icono)  # WM_SETICON

    def _escala(self):
        return ctk.ScalingTracker.get_window_scaling(self.root)

    def _opacidad(self):
        return max(self.a.ajustes["opacidad"], 40) / 100

    def _minimizar(self):
        # Oculta antes de minimizar: al volver se muestra de una vez, ya dibujada.
        self.root.attributes("-alpha", 0)
        self._oculta = True
        entrada.user32.ShowWindow(self.hwnd, 6)  # SW_MINIMIZE

    def _vigilar_minimizado(self):
        minimizada = bool(entrada.user32.IsIconic(self.hwnd))
        if minimizada and not self._oculta:
            self.root.attributes("-alpha", 0)  # minimizada desde la barra de tareas
            self._oculta = True
        elif not minimizada and self._oculta:
            self._oculta = False
            self.root.update_idletasks()
            self.root.after(15, lambda: self._revelar(0))

    def _revelar(self, paso):
        pasos = (0.5, 0.8, 1)
        if self._oculta:
            return
        self.root.attributes("-alpha", self._opacidad() * pasos[paso])
        if paso < 2:
            self.root.after(15, lambda: self._revelar(paso + 1))

    def _aplicar_ventana(self):
        aj = self.a.ajustes
        self.root.attributes("-topmost", bool(aj["encima"]))
        if not self._oculta and not self._arrancando:
            self.root.attributes("-alpha", self._opacidad())
        if self._pantalla:
            return
        e = self._escala()
        try:
            ancho, alto = max(int(aj["ancho"]), MIN_ANCHO), max(int(aj["alto"]), MIN_ALTO)
        except (TypeError, ValueError):
            ancho, alto = datos.AJUSTES_BASE["ancho"], datos.AJUSTES_BASE["alto"]
        if aj["compacto"]:
            ancho = ANCHO_COMPACTO
        x, y = self.root.winfo_x(), self.root.winfo_y()
        tk.Tk.geometry(self.root, f"{round(ancho * e)}x{round(alto * e)}" + (f"+{x}+{y}" if x > 0 or y > 0 else ""))

    def _alternar_pantalla(self, modo):
        if self._dlg:
            return
        if self._pantalla == modo:
            self._pantalla = None
            tk.Tk.geometry(self.root, self._geom_normal)
        else:
            if not self._pantalla:
                self._geom_normal = tk.Tk.geometry(self.root)
            self._pantalla = modo
            izq, arr, der, aba = self._rect_monitor(modo == "completa")
            tk.Tk.geometry(self.root, f"{der - izq}x{aba - arr}+{izq}+{arr}")
        if self.a.ajustes["compacto"] and self._pantalla:
            self.a.ajustes["compacto"] = False
            self.construir()
        else:
            self.barra.repintar()
        self._zona = ""
        tk.Tk.configure(self.root, cursor="")

    def _rect_monitor(self, completo):
        class INFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        u = entrada.user32
        u.MonitorFromWindow.argtypes, u.MonitorFromWindow.restype = (ctypes.c_void_p, wintypes.DWORD), ctypes.c_void_p
        u.GetMonitorInfoW.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        info = INFO(cbSize=ctypes.sizeof(INFO))
        u.GetMonitorInfoW(u.MonitorFromWindow(self.hwnd, 2), ctypes.byref(info))
        r = info.rcMonitor if completo else info.rcWork
        return r.left, r.top, r.right, r.bottom

    # ------------------------------------ eventos de toda la ventana
    def _zona_de(self, e):
        """Borde de la ventana bajo el puntero, sin tapar los botones de la barra de titulo."""
        if self._pantalla or self._dlg or self._menu:
            return ""
        esc = self._escala()
        b = round(BORDE_REDIMENSION * esc)
        x, y = e.x_root - self.root.winfo_rootx(), e.y_root - self.root.winfo_rooty()
        w, h = self.root.winfo_width(), self.root.winfo_height()
        if not (0 <= x < w and 0 <= y < h):
            return ""
        z = ""
        if y < b and x < w - round(190 * esc):
            z = "n"
        elif y >= h - b:
            z = "s"
        if not self.a.ajustes["compacto"]:
            if x < b:
                z += "w"
            elif x >= w - b:
                z += "e"
        return z

    def en_borde(self, e):
        """Las escenas preguntan esto para no robarle el click al borde que cambia el tamaño."""
        return bool(self._redim or self._zona_de(e))

    def _mover_global(self, e):
        if self._redim:
            return
        z = self._zona_de(e)
        if z != self._zona:
            self._zona = z
            tk.Tk.configure(self.root, cursor=CURSORES.get(z, ""))

    def _press_global(self, e):
        self._cerrar_menu_si_afuera(e)
        z = self._zona_de(e)
        if z:
            self._redim = dict(z=z, x=e.x_root, y=e.y_root, rx=self.root.winfo_rootx(), ry=self.root.winfo_rooty(),
                               w=self.root.winfo_width(), h=self.root.winfo_height(), ultimo=None)

    def _arrastre_global(self, e):
        if self._redim:
            self._redim["ultimo"] = (e.x_root, e.y_root)
            if not self._redim_tarea:
                self._redim_tarea = self.root.after(12, self._aplicar_redim)

    def _aplicar_redim(self):
        self._redim_tarea = None
        r = self._redim
        if not r or not r["ultimo"]:
            return
        esc = self._escala()
        min_w = round((ANCHO_COMPACTO if self.a.ajustes["compacto"] else MIN_ANCHO) * esc)
        min_h = round(MIN_ALTO * esc)
        dx, dy = r["ultimo"][0] - r["x"], r["ultimo"][1] - r["y"]
        x, y, w, h = r["rx"], r["ry"], r["w"], r["h"]
        if "e" in r["z"]:
            w = max(r["w"] + dx, min_w)
        if "s" in r["z"]:
            h = max(r["h"] + dy, min_h)
        if "w" in r["z"]:
            w = max(r["w"] - dx, min_w)
            x = r["rx"] + r["w"] - w
        if "n" in r["z"]:
            h = max(r["h"] - dy, min_h)
            y = r["ry"] + r["h"] - h
        tk.Tk.geometry(self.root, f"{w}x{h}+{x}+{y}")
        self.root.update_idletasks()  # dibuja ya: si no, los eventos del mouse se adelantan al dibujo

    def _soltar_global(self, e):
        if not self._redim:
            return
        self._aplicar_redim()
        self._redim = None
        esc = self._escala()
        aj = self.a.ajustes
        if not aj["compacto"]:
            aj["ancho"] = round(self.root.winfo_width() / esc)
        aj["alto"] = round(self.root.winfo_height() / esc)
        self._guardar_pronto()

    def _rueda_global(self, e):
        w = e.widget
        while w is not None and not isinstance(w, str):
            if callable(getattr(w, "rueda", None)):
                w.rueda(e.delta)
                return
            w = getattr(w, "master", None)

    def _al_escape(self, _=None):
        if self._menu:
            self._cerrar_menu()
        elif self._dlg:
            self._dlg["cancelar"]()
        elif self._pantalla == "completa":
            self._alternar_pantalla("completa")

    def _al_enter(self, _=None):
        if self._dlg:
            self._dlg["aceptar"]()

    def _quitar_foco(self, e):
        if not isinstance(e.widget, (tk.Entry, tk.Text, str)):
            try:
                self.root.focus_set()
            except tk.TclError:
                pass

    # --------------------------------------------------- ayuda al pasar
    def ayuda(self, escena, zona):
        """Programa el texto de ayuda de la zona bajo el mouse, u oculta el que haya."""
        if self._ayuda_tarea:
            self.root.after_cancel(self._ayuda_tarea)
            self._ayuda_tarea = None
        if self._ayuda_ventana:
            self._ayuda_ventana.destroy()
            self._ayuda_ventana = None
        if zona is not None and zona.ayuda:
            self._ayuda_tarea = self.root.after(450, lambda: self._mostrar_ayuda(escena, zona))

    def _mostrar_ayuda(self, escena, zona):
        self._ayuda_tarea = None
        if not escena.winfo_exists() or escena._hover is not zona:
            return
        v = self._ayuda_ventana = tk.Toplevel(self.root)
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        tk.Label(v, text=zona.ayuda, bg=self.t["tarjeta"], fg=self.t["texto"], font=(LETRA, -self.px(12)), padx=8, pady=3,
                 highlightthickness=1, highlightbackground=self.t["borde"]).pack()
        v.update_idletasks()
        x = escena.winfo_rootx() + int(zona.x0 - escena.canvasx(0))
        y = escena.winfo_rooty() + int(zona.y1 - escena.canvasy(0)) + 4
        v.geometry(f"+{max(min(x, v.winfo_screenwidth() - v.winfo_reqwidth() - 4), 0)}+{y}")

    # ------------------------------------------------------------ desplegable
    def abrir_menu(self, escena, caja, valores, actual, al_elegir, extra=None):
        """Menu bajo un selector. `caja` es (x, y, ancho, alto) del selector dentro de su escena."""
        ancla = (escena, caja)
        repetido = self._menu_ancla == ancla
        self._cerrar_menu()
        if repetido:
            return
        t = self.t
        fila = self.px(34)
        extra = extra or []
        x, y, w, h = caja
        ancho = max(w, self.px(150))
        filas = len(valores) + len(extra)
        alto = min(filas, 9) * fila + self.px(8) + (self.px(7) if extra else 0)

        def elegir(fn, *args):
            self._cerrar_menu()
            fn(*args)
            if escena.winfo_exists():
                escena.repintar()

        def dibujar(s, an, _):
            yy = self.px(4)
            for v in valores:
                s.boton(self.px(4), yy + 1, an - self.px(8), fila - 2, v, lambda v=v: elegir(al_elegir, v), izquierda=True,
                        negrita=v == actual, color=t["suave"] if v == actual else None)
                yy += fila
            if extra:
                s.create_rectangle(self.px(8), yy + self.px(3), an - self.px(8), yy + self.px(3) + 1, fill=t["borde"], width=0)
                yy += self.px(7)
            for texto, fn in extra:
                s.boton(self.px(4), yy + 1, an - self.px(8), fila - 2, texto, lambda fn=fn: elegir(fn), izquierda=True, negrita=False,
                        color_texto=t["acento"] if t["modo"] == "dark" else t["texto"])
                yy += fila
            return yy + self.px(4)
        m = Escena(self.marco, self, dibujar, fondo=t["tarjeta"], desplazable=filas > 9, highlightthickness=1, highlightbackground=t["borde"])
        mx = escena.winfo_rootx() - self.marco.winfo_rootx() + int(x - escena.canvasx(0))
        my = escena.winfo_rooty() - self.marco.winfo_rooty() + int(y - escena.canvasy(0))
        abajo = my + h + self.px(4)
        if abajo + alto > self.marco.winfo_height():
            abajo = max(my - alto - self.px(4), 0)
        m.place(x=max(min(mx, self.marco.winfo_width() - ancho - self.px(4)), 0), y=abajo, width=ancho, height=alto)
        tk.Misc.lift(m)  # en un lienzo, lift() a secas sube figuras, no el widget
        self._menu, self._menu_ancla = m, ancla

    def _cerrar_menu(self):
        if self._menu and self._menu.winfo_exists():
            self._menu.destroy()
        self._menu = self._menu_ancla = None

    def _cerrar_menu_si_afuera(self, e):
        if not self._menu:
            return
        if str(e.widget).startswith(str(self._menu)):
            return
        escena, (x, y, w, h) = self._menu_ancla
        if e.widget is escena and escena.winfo_exists():
            cx, cy = escena.canvasx(e.x), escena.canvasy(e.y)
            if x <= cx < x + w and y <= cy < y + h:
                return  # el propio selector lo cierra al soltar
        self._cerrar_menu()

    # ----------------------------------------------------------- construir
    def construir(self):
        self._confirmar_nombre()
        self.cancelar_captura()
        tema = TEMAS.get(self.a.ajustes["tema"], TEMAS["Noche"])
        acento = self.a.ajustes["acento"]
        self.t = dict(tema, acento=acento, sobre=sobre(acento), hover=mezclar(acento, tema["fondo"], 0.18),
                      suave=mezclar(tema["tarjeta"], tema["texto"], 0.08), seleccion=mezclar(acento, tema["panel"], 0.55))
        ctk.set_appearance_mode(tema["modo"])
        self.rec = Recursos(self.root)
        self._menu = self._menu_ancla = self._dlg = self.pasos_ui = self.cab = None
        self._ayuda_tarea = self._ayuda_ventana = None
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(fg_color=self.t["borde"])

        t, px = self.t, self.px
        self.marco = tk.Frame(self.root, bg=t["fondo"])
        self.marco.pack(fill="both", expand=True, padx=1, pady=1)
        self.barra = Escena(self.marco, self, self._dibujar_barra, fondo=t["panel"], height=px(40))
        self.barra.pack(fill="x")
        cuerpo = tk.Frame(self.marco, bg=t["fondo"])
        cuerpo.pack(fill="both", expand=True)
        self.lateral = tk.Frame(cuerpo, bg=t["panel"], width=px(ANCHO_COMPACTO - 2))
        self.lateral.pack(side="left", fill="y")
        self.lateral.pack_propagate(False)
        self.principal = tk.Frame(cuerpo, bg=t["fondo"])
        if not self.a.ajustes["compacto"]:
            self.principal.pack(side="left", fill="both", expand=True)
        self._construir_lateral()
        self.pintar_principal()
        self._aplicar_ventana()

    def _dibujar_barra(self, s, w, h):
        t, px = self.t, s.px
        s.zona(0, 0, w, h, cursor="", presionar=self._inicio_arrastre, arrastrar=self._arrastrar,
               doble=lambda: self._alternar_pantalla(self._pantalla or "max"))
        logo = self.rec.imagen(("logo", px(22), t["acento"]), lambda: dibujar_logo(px(22), t["acento"], t["sobre"]))
        s.create_image(px(12), h // 2, anchor="w", image=logo)
        s.texto(px(42), h // 2, datos.APP, 13, True)
        compacto = self.a.ajustes["compacto"]
        botones = ((I_CLOSE, self.cerrar, None, ROJO, 10),
                   (I_RESTORE if self._pantalla else I_MAX, lambda: self._alternar_pantalla(self._pantalla or "max"),
                    "Maximizar (F11: pantalla completa)", None, 10),
                   (I_MIN, self._minimizar, None, None, 10),
                   (I_EXPAND if compacto else I_COMPACT, self._alternar_compacto, "Ver completo" if compacto else "Modo compacto", None, 11))
        x = w
        for icono, fn, ayuda, hover, tam in botones:
            x -= px(44)
            s.boton(x, 0, px(44), h, icono, fn, icono=True, tam=tam, r=0, hover=hover, ayuda=ayuda)
        inicio = px(42) + s.medir(datos.APP, 13, True) + px(12)
        texto, color = self._aviso
        if texto and x - inicio > px(40):
            s.texto(inicio, h // 2, texto, 11, color=color or t["tenue"], ancho=x - inicio - px(8))

    def _inicio_arrastre(self, *_):
        px, py = self.root.winfo_pointerxy()
        self._arrastre = (px - self.root.winfo_x(), py - self.root.winfo_y())

    def _arrastrar(self, *_):
        if self._pantalla or self._redim:
            return
        px, py = self.root.winfo_pointerxy()
        tk.Tk.geometry(self.root, f"+{px - self._arrastre[0]}+{py - self._arrastre[1]}")

    def aviso(self, texto, color=None, ms=3500):
        self._aviso = (texto, color)
        self.barra.repintar()
        if self._aviso_tarea:
            self.root.after_cancel(self._aviso_tarea)
        self._aviso_tarea = self.root.after(ms, lambda: self.aviso("", ms=0)) if ms and texto else None

    def _alternar_compacto(self):
        if self._pantalla:
            self._alternar_pantalla(self._pantalla)
        self.a.ajustes["compacto"] = not self.a.ajustes["compacto"]
        self._guardar_pronto()
        self.construir()

    # ------------------------------------------------------------- lateral
    def _construir_lateral(self):
        for w in self.lateral.winfo_children():
            w.destroy()
        panel = self.t["panel"]
        Escena(self.lateral, self, self._dibujar_lateral_arriba, fondo=panel, height=self.px(146)).pack(fill="x")
        self.lat_pie = Escena(self.lateral, self, self._dibujar_lateral_abajo, fondo=panel, height=self.px(96))
        self.lat_pie.pack(side="bottom", fill="x")
        self.lista = Escena(self.lateral, self, self._dibujar_lista, fondo=panel, desplazable=True)
        self.lista.pack(fill="both", expand=True)
        self._estado_macros = self._id_stats = None

    def _nombres_perfiles(self):
        return {f"{p['nombre']}" + (f" ({i})" if any(q["nombre"] == p["nombre"] for q in self.a.perfiles[:i]) else ""): p["id"]
                for i, p in enumerate(self.a.perfiles)}

    def _dibujar_lateral_arriba(self, s, w, h):
        t, px = self.t, s.px
        s.texto(px(12), px(20), "PERFIL", 10, True, t["tenue"])
        nombres = self._nombres_perfiles()
        actual = next(n for n, pid in nombres.items() if pid == self.perfil["id"])
        s.selector(px(12), px(32), w - px(24), px(34), actual, list(nombres), lambda n: self._cambiar_perfil(nombres[n]),
                   extra=[("+  Nuevo perfil", self._perfil_nuevo)])
        x = px(12)
        for icono, fn, ayuda in ((I_ADD, self._perfil_nuevo, "Nuevo perfil"), (I_EDIT, self._perfil_renombrar, "Renombrar"),
                                 (I_COPY, self._perfil_duplicar, "Duplicar"), (I_DEL, self._perfil_eliminar, "Eliminar"),
                                 (I_IMPORT, self._perfil_importar, "Importar archivo"), (I_EXPORT, self._perfil_exportar, "Exportar para compartir")):
            s.boton(x, px(72), px(30), px(30), icono, fn, icono=True, tam=11, ayuda=ayuda)
            x += px(34)
        s.texto(px(12), px(128), "MACROS", 10, True, t["tenue"])
        s.texto(px(20) + s.medir("MACROS", 10, True), px(128), "arrastra para ordenar", 10, color=t["tenue"])
        s.boton(w - px(38), px(115), px(26), px(26), I_ADD, lambda: self.ir_a("plantillas"), icono=True, tam=11,
                color_texto=t["acento"] if t["modo"] == "dark" else t["texto"], ayuda="Nueva macro")

    def _dibujar_lista(self, s, w, h):
        t, px = self.t, s.px
        if not self.macros:
            s.texto(w // 2, px(46), "Sin macros todavía.\nCrea la primera con +", 12, color=t["tenue"], ancla="center")
            return 0
        alto, paso = px(48), px(50)
        mov = self._fila_mov if self._fila_mov and self._fila_mov["activo"] else None
        for i, m in enumerate(self.macros):
            y = i * paso
            activa = m["id"] == self.sel and self.vista == "editor" and not self.a.ajustes["compacto"]
            moviendo = bool(mov and mov["m"] is m)
            on = self.motor.corriendo(m["id"])
            pausa = on and self.motor.pausada(m["id"])
            if activa or moviendo:
                s.tarjeta(px(6), y, w - px(6), alto, t["suave"], 8, t["acento"] if moviendo else None)
                s.zona(px(6), y, w - px(6), alto, presionar=lambda _, yy, m=m: self._fila_presionar(m, yy),
                       arrastrar=self._fila_arrastrar, soltar=self._fila_soltar)
            else:
                # La fila normal no tiene fondo: aparece al pasar el mouse.
                z = s.boton(px(6), y, w - px(6), alto, "", None, r=8, hover=mezclar(t["panel"], t["texto"], 0.05))
                z.presionar, z.arrastrar, z.soltar = (lambda _, yy, m=m: self._fila_presionar(m, yy)), self._fila_arrastrar, self._fila_soltar
            s.disco(px(20), y + alto // 2, px(8), AMBAR if pausa else t["acento"] if on else t["borde"])
            s.texto(px(34), y + px(16), m["nombre"], 12, True, ancho=w - px(34) - px(48))
            s.texto(px(34), y + px(33), m["tecla"] or "sin atajo", 10, True, t["tenue"], familia=MONO, ancho=w - px(34) - px(48))
            s.boton(w - px(40), y + px(9), px(30), px(30), I_STOP if on else I_PLAY, lambda m=m: self._alternar_desde_ui(m), icono=True,
                    tam=11, hover=t["borde"], color_texto=t["acento"] if on and t["modo"] == "dark" else None, ayuda="Iniciar o detener")
            s.sobre = s.fondo
        return len(self.macros) * paso

    def _dibujar_lateral_abajo(self, s, w, h):
        t, px = self.t, s.px
        self._id_stats = s.texto(px(12), px(22), self._texto_stats(), 11, color=t["tenue"])
        s.boton(px(12), px(52), w - px(64), px(32), "Detener todo", self.motor.detener_todo, color=t["suave"], hover=t["borde"])
        s.boton(w - px(46), px(52), px(34), px(32), I_GEAR, lambda: self.ir_a("ajustes"), icono=True, tam=14, color=t["suave"],
                hover=t["borde"], color_texto=t["texto"], ayuda="Ajustes")

    def _texto_stats(self):
        s = self.a.stats
        horas = s["segundos"] / 3600
        tiempo = f"{horas:.1f} h" if horas >= 1 else f"{s['segundos'] / 60:.0f} min"
        return f"Te ahorraste {int(s['clicks']):,} clicks y {int(s['teclas']):,} teclas\nRelevo trabajó {tiempo} por ti".replace(",", ".")

    def pintar_lista(self):
        self.lista.repintar()

    # Un click selecciona; mantener y mover reordena.
    def _fila_presionar(self, m, y):
        self._fila_mov = dict(m=m, y0=y, activo=False)

    def _fila_arrastrar(self, _, y):
        a, s = self._fila_mov, self.lista
        if not a:
            return
        if not a["activo"]:
            if abs(y - a["y0"]) < self.px(6):
                return
            a["activo"] = True
            s.repintar()
        vista = y - s.canvasy(0)
        if vista < self.px(20):
            s.yview_scroll(-self.px(8), "units")
        elif vista > s.winfo_height() - self.px(20):
            s.yview_scroll(self.px(8), "units")
        i = self.macros.index(a["m"])
        destino = min(max(int(y // self.px(50)), 0), len(self.macros) - 1)
        if destino != i:
            self.macros.insert(destino, self.macros.pop(i))
            s.repintar()

    def _fila_soltar(self, *_):
        a, self._fila_mov = self._fila_mov, None
        if not a:
            return
        if a["activo"]:
            self._guardar_pronto()
            self.pintar_lista()
        else:
            self.seleccionar(a["m"]["id"])

    def seleccionar(self, mid):
        self.sel = mid
        self.ir_a("editor")

    def ir_a(self, vista):
        self.vista = vista
        if self.a.ajustes["compacto"]:
            self.a.ajustes["compacto"] = False
            self.construir()
        else:
            self.pintar_lista()
            self.pintar_principal()

    # ------------------------------------------------------------ perfiles
    def _cambiar_perfil(self, pid):
        self.motor.detener_todo("cambiaste de perfil")
        self.a.ajustes["perfil"] = pid
        self.sel = self.macros[0]["id"] if self.macros else None
        self.vista = "editor"
        self._aplicar_motor()
        self._guardar_pronto()
        self._construir_lateral()
        self.pintar_principal()

    def _perfil_nuevo(self):
        def crear(nombre):
            p = {"id": datos.nuevo_id(), "nombre": nombre[:40], "macros": []}
            self.a.perfiles.append(p)
            self._cambiar_perfil(p["id"])
        self.dialogo("Nuevo perfil", "Un perfil agrupa las macros de una tarea.", crear, valor="Nuevo perfil")

    def _perfil_renombrar(self):
        def renombrar(nombre):
            self.perfil["nombre"] = nombre[:40]
            self._guardar_pronto()
            self._construir_lateral()
        self.dialogo("Renombrar perfil", "", renombrar, valor=self.perfil["nombre"])

    def _perfil_duplicar(self):
        p = copy.deepcopy(self.perfil)
        p["id"] = datos.nuevo_id()
        p["nombre"] = (p["nombre"] + " copia")[:40]
        for m in p["macros"]:
            m["id"] = datos.nuevo_id()
        self.a.perfiles.append(p)
        self._cambiar_perfil(p["id"])

    def _perfil_eliminar(self):
        p = self.perfil
        unico = len(self.a.perfiles) == 1

        def borrar(_):
            if unico:
                # Siempre debe existir un perfil: el nuevo ya queda creado aunque canceles el nombre.
                nuevo = {"id": datos.nuevo_id(), "nombre": "Nuevo perfil", "macros": []}
                self.a.perfiles.append(nuevo)
                self.a.perfiles.remove(p)
                self._cambiar_perfil(nuevo["id"])
                self.root.after(120, self._pedir_nombre_perfil)
            else:
                self.a.perfiles.remove(p)
                self._cambiar_perfil(self.a.perfiles[0]["id"])
        aviso = " Es tu único perfil: después crearás uno nuevo." if unico else ""
        self.dialogo("Eliminar perfil", f"Se borra \"{p['nombre']}\" con todas sus macros.{aviso}", borrar, confirmar="Eliminar", peligro=True)

    def _pedir_nombre_perfil(self):
        def nombrar(nombre):
            self.perfil["nombre"] = nombre[:40]
            self._guardar_pronto()
            self._construir_lateral()
        self.dialogo("Crea tu nuevo perfil", "Ponle el nombre de la tarea.", nombrar, valor="Nuevo perfil", confirmar="Crear")

    def _perfil_exportar(self):
        ruta = filedialog.asksaveasfilename(parent=self.root, defaultextension=".json", initialfile=f"{self.perfil['nombre']}.relevo.json",
                                            filetypes=[("Perfil de Relevo", "*.json")])
        if ruta:
            try:
                datos.exportar(self.perfil, ruta)
            except OSError as e:
                self.aviso(f"No se pudo exportar: {e}", ROJO)
                return
            self.aviso("Perfil exportado")

    def _perfil_importar(self):
        ruta = filedialog.askopenfilename(parent=self.root, filetypes=[("Perfil de Relevo", "*.json")])
        if not ruta:
            return
        try:
            p = datos.importar(ruta)
        except (OSError, ValueError) as e:
            self.aviso(f"No se pudo importar: {e}", ROJO)
            return
        self.a.perfiles.append(p)
        self._cambiar_perfil(p["id"])
        self.aviso(f"Importado: {p['nombre']}")

    # ------------------------------------------------------------- dialogo
    def dialogo(self, titulo, texto, al_aceptar, valor=None, confirmar="Aceptar", peligro=False):
        """Ventana emergente sobre la app difuminada. Esc o click afuera cancelan."""
        self._cerrar_menu()
        if self._dlg:
            self._dlg["cancelar"]()
        t, px = self.t, self.px
        self.root.update_idletasks()
        foto = captura_ventana(self.hwnd)
        capa = tk.Label(self.root, bd=0, highlightthickness=0, bg=t["fondo"])
        fotogramas, color_fondo = [], t["fondo"]
        if foto:
            difuminada = Image.blend(foto.filter(ImageFilter.GaussianBlur(round(12 * self._escala()))),
                                     Image.new("RGB", foto.size, t["fondo"]), 0.45)
            fotogramas = [ImageTk.PhotoImage(Image.blend(foto, difuminada, a), master=self.root) for a in (0.45, 0.8, 1)]
            color_fondo = "#%02X%02X%02X" % difuminada.getpixel((foto.width // 2, foto.height // 3))
            capa.configure(image=fotogramas[0])
            capa.fotogramas = fotogramas
        capa.place(x=0, y=0, relwidth=1, relheight=1)
        capa.lift()

        def cerrar():
            self._dlg = None
            if capa.winfo_exists():
                capa.destroy()

        def aceptar():
            resultado = caja._campos["valor"].get().strip() if valor is not None else True
            if valor is not None and not resultado:
                return
            cerrar()
            al_aceptar(resultado)

        def dibujar(s, w, _):
            alto_texto = 0
            if texto:
                prueba = s.texto(0, 0, texto, 12, ancla="nw", envolver=w - px(44))
                alto_texto = s.bbox(prueba)[3] + px(4)
                s.delete(prueba)
            total = px(54) + alto_texto + (px(48) if valor is not None else 0) + px(72)
            s.tarjeta(0, 0, w, total, t["tarjeta"], 14, t["borde"])
            s.texto(px(22), px(32), titulo, 16, True)
            y = px(50)
            if texto:
                s.texto(px(22), y, texto, 12, color=t["tenue"], ancla="nw", envolver=w - px(44))
                y += alto_texto
            if valor is not None:
                s.campo("valor", px(22), y + px(10), w - px(44), px(36), valor)
                y += px(48)
            y += px(18)
            s.boton(w - px(22) - px(88), y, px(88), px(34), "Cancelar", cerrar, color=t["suave"], hover=t["borde"])
            rojo = dict(color=ROJO, hover=mezclar(ROJO, "#000000", .2), color_texto="#FFFFFF") if peligro else {}
            s.boton(w - px(22) - px(88) - px(8) - px(100), y, px(100), px(34), confirmar, aceptar, primario=True, **rojo)
            return total
        caja = Escena(capa, self, dibujar, fondo=color_fondo)
        ancho = px(344)
        caja.place(relx=.5, rely=.40, anchor="center", width=ancho, height=caja.medir_alto(ancho))
        capa.bind("<Button-1>", lambda _: cerrar())
        self._dlg = dict(aceptar=aceptar, cancelar=cerrar)

        def animar(i=1):
            if not capa.winfo_exists():
                return
            caja.place_configure(rely=.40 - .02 * min(i, 2) / 2)
            if i < len(fotogramas):
                capa.configure(image=fotogramas[i])
            if i < 2:
                capa.after(16, lambda: animar(i + 1))
        animar()
        if valor is not None:
            caja.after(40, lambda: caja.winfo_exists() and caja.enfocar("valor"))
        else:
            capa.focus_set()

    # ----------------------------------------------------------- principal
    def pintar_principal(self):
        self._confirmar_nombre()
        for w in self.principal.winfo_children():
            w.destroy()
        self.cancelar_captura()
        self._cerrar_menu()
        self.pasos_ui = self.cab = None
        self._nombre_sucio = False
        if self.a.ajustes["compacto"]:
            return
        if self.vista == "plantillas":
            self._vista(self._dibujar_plantillas)
        elif self.vista == "ajustes":
            self._vista(self._dibujar_ajustes)
        elif self.vista == "registro" and self.macro:
            self._vista_registro()
        elif self.macro:
            self._vista_editor()
        else:
            self._vista(self._dibujar_vacia)

    def _vista(self, dibujar):
        Escena(self.principal, self, dibujar, desplazable=True).pack(fill="both", expand=True)

    def _dibujar_vacia(self, s, w, h):
        t, px = self.t, s.px
        y = round(h * .42)
        s.texto(w // 2, y - px(30), "Este perfil está vacío", 18, True, ancla="center")
        s.texto(w // 2, y, "Crea una macro y deja que tus manos descansen.", 12, color=t["tenue"], ancla="center")
        s.boton(w // 2 - px(60), y + px(24), px(120), px(32), "Nueva macro", lambda: self.ir_a("plantillas"), primario=True)

    def _encabezado(self, s, titulo, subtitulo):
        """Titulo de una vista, con flecha para volver al editor. Devuelve donde sigue el contenido."""
        px, x = s.px, s.px(22)
        if self.macro:
            s.boton(x, px(22), px(30), px(30), I_BACK, lambda: self.ir_a("editor"), icono=True, tam=13, ayuda="Volver")
            x += px(38)
        s.texto(x, px(30), titulo, 19, True)
        s.texto(x, px(53), subtitulo, 12, color=self.t["tenue"])
        return px(76)

    def _dibujar_plantillas(self, s, w, h):
        t, px = self.t, s.px
        y0 = self._encabezado(s, "Nueva macro", "Elige un punto de partida. Todo se puede cambiar después.")
        ancho, alto, sep = (w - px(44) - px(10)) // 2, px(92), px(10)
        for i, (nombre, desc, fabrica) in enumerate(PLANTILLAS):
            x, y = px(22) + (i % 2) * (ancho + sep), y0 + (i // 2) * (alto + sep)
            k = s.caja(x, y, ancho, alto, t["tarjeta"], 10, t["borde"])
            s.texto(x + px(16), y + px(28), nombre, 14, True)
            s.texto(x + px(16), y + px(42), desc, 12, color=t["tenue"], ancla="nw", envolver=ancho - px(32))
            s.zona(x, y, ancho, alto, clic=lambda f=fabrica: self._crear_macro(f()),
                   entrar=lambda k=k: s.recolorear(k, t["tarjeta"], t["acento"]), salir=lambda k=k: s.recolorear(k, t["tarjeta"], t["borde"]))
        return y0 + ((len(PLANTILLAS) + 1) // 2) * (alto + sep) + px(8)

    def _crear_macro(self, m):
        usados = {x["tecla"] for x in self.macros}
        if m["tecla"] in usados:
            m["tecla"] = ""
        self.macros.append(m)
        self._aplicar_motor()
        self.seleccionar(m["id"])
        self._guardar_pronto()

    # -------------------------------------------------------------- editor
    def _vista_editor(self):
        m = self.macro
        px = self.px
        self.cab = Escena(self.principal, self, lambda s, w, h: self._dibujar_cabecera(s, w, m), height=px(232))
        self.cab.pack(fill="x")
        Escena(self.principal, self, self._dibujar_botones_paso, height=px(88)).pack(side="bottom", fill="x")
        self.pasos_ui = ListaPasos(self.principal, self, m)
        self.pasos_ui.pack(fill="both", expand=True, padx=(px(22), px(14)))

    def _dibujar_cabecera(self, s, w, m):
        """Nombre, botones de la macro y la tarjeta con sus ajustes."""
        t, px = self.t, s.px
        clave = ("nombre", m["id"])

        def cambio(v):
            sucio = v.strip() != m["nombre"]
            if sucio != self._nombre_sucio:
                self._nombre_sucio = sucio
                s.repintar()

        def guardar(_=None):
            valor = campo.get().strip()
            if not valor:
                s.fijar_campo(clave, m["nombre"])
            elif valor != m["nombre"]:
                self._cambiar_nombre(m, valor)
                self.aviso("Nombre guardado")
            self._nombre_sucio = False
            self.root.focus_set()
            s.repintar()

        def confirmar_sin_aviso():
            # Cambiar de vista sin pulsar Guardar no debe perder lo escrito.
            valor = campo.get().strip()
            if valor and valor != m["nombre"]:
                self._cambiar_nombre(m, valor)
        campo = s.campo(clave, px(22), px(16), px(270), px(36), m["nombre"], cambio, al_enter=guardar, tam=17, negrita=True, fondo=t["fondo"])
        self._nombre_pendiente = (campo, confirmar_sin_aviso)
        if self._nombre_sucio:
            s.boton(px(300), px(19), px(74), px(30), "Guardar", guardar, primario=True, tam=11)
        else:
            s.caja(px(300), px(19), px(74), px(30), t["suave"], 7)
            s.texto(px(337), px(34), "Guardar", 11, True, t["tenue"], ancla="center")

        on = self.motor.corriendo(m["id"])
        rojo = dict(color=ROJO, hover=mezclar(ROJO, "#000000", .15), color_texto="#FFFFFF") if on else {}
        x = w - px(22) - px(112)
        s.boton(x, px(17), px(112), px(34), "Detener" if on else "Iniciar", lambda: self._alternar_desde_ui(m), primario=True, **rojo)
        for icono, fn, ayuda in ((I_DEL, self._macro_eliminar, "Eliminar macro"), (I_COPY, self._macro_duplicar, "Duplicar macro"),
                                 (I_LOG, lambda: self.ir_a("registro"), "Ver registro de esta macro")):
            x -= px(36)
            s.boton(x, px(18), px(32), px(32), icono, fn, icono=True, ayuda=ayuda)

        cx, cy, cw, ch = px(22), px(60), w - px(44), px(124)
        s.tarjeta(cx, cy, cw, ch, t["tarjeta"], 10)
        col = cw / 3
        f1, f2 = cy + px(19), cy + px(77)       # renglones de etiquetas
        c1, c2 = cy + px(31), cy + px(89)       # renglones de controles

        def celda(i):
            return cx + round(col * i) + px(14), round(col) - px(28)

        x, a = celda(0)
        s.texto(x, f1, "Atajo global", 11, color=t["tenue"])
        conflicto = self._conflicto(m)
        if conflicto:
            ini = x + s.medir("Atajo global", 11) + px(8)
            s.texto(ini, f1, conflicto, 10, color=AMBAR, ancho=x + a - ini)

        def fijar_tecla(combo):
            m["tecla"] = combo
            self._aplicar_motor()
            self._guardar_pronto()
            self.pintar_lista()
        self._boton_captura(s, ("atajo", m["id"]), x, c1, a - px(32), px(30), lambda: m["tecla"], fijar_tecla, vacio="Sin atajo")
        s.boton(x + a - px(28), c1, px(28), px(30), I_CLOSE, lambda: (self.cancelar_captura(), fijar_tecla(""), s.repintar()),
                icono=True, tam=9, ayuda="Quitar atajo")
        s.texto(x, f2, "Variación natural", 11, color=t["tenue"])
        s.deslizador(x, c2 + px(15), a, m["variacion"], 0, 50, lambda v: self._fijar(m, "variacion", v), lambda v: f"±{v:.0f}%", paso=1, tipo=int)

        x, a = celda(1)
        s.texto(x, f1, "Al pulsar el atajo", 11, color=t["tenue"])
        s.segmentado(x, c1, a, px(30), MODOS_CORTOS, m["modo"], lambda v: (self._cambiar_modo(m, v), s.repintar()))
        s.texto(x, f2, "Velocidad de toda la macro", 11, color=t["tenue"])
        s.deslizador(x, c2 + px(15), a, m["velocidad"], 0.25, 4, lambda v: self._fijar(m, "velocidad", v), lambda v: f"×{v:.2f}", paso=0.05)

        x, a = celda(2)
        a1 = round((a - px(8)) * 0.6)
        s.texto(x, f1, "Veces (0 = sin fin)", 11, color=t["tenue"], ancho=a1)
        self._num(s, x, c1, a1, px(30), m, "repeticiones", int, 0, 1000000)
        x2, a2 = x + a1 + px(8), a - a1 - px(8)
        s.texto(x2, f1, "Inicia en (s)", 11, color=t["tenue"], ancho=a2)
        self._num(s, x2, c1, a2, px(30), m, "cuenta", int, 0, 3600)
        s.zona(x2, f1 - px(9), a2, px(18), cursor="",
               ayuda="Cuenta atrás al iniciar desde la ventana (0 = al instante). Con el atajo siempre empieza al instante.")
        s.texto(x, f2, "Solo si la ventana se llama", 11, color=t["tenue"])
        s.campo(("ventana", m["id"]), x, c2, a, px(30), m["ventana"], lambda v: self._fijar(m, "ventana", v), marcador="cualquier ventana")

        y = cy + ch + px(26)
        s.sobre = s.fondo
        s.texto(px(22), y, "PASOS", 10, True, t["tenue"])
        s.texto(px(30) + s.medir("PASOS", 10, True), y, "se ejecutan en orden y luego vuelven a empezar", 11, color=t["tenue"])
        if self.motor.grabando:
            s.boton(w - px(22) - px(150), y - px(14), px(150), px(28), "Terminar grabación", self._alternar_grabacion, tam=11,
                    color=ROJO, hover=mezclar(ROJO, "#000000", .15), color_texto="#FFFFFF")
        else:
            s.boton(w - px(22) - px(130), y - px(14), px(130), px(28), "Grabar acciones", self._alternar_grabacion, tam=11,
                    color=t["suave"], hover=t["borde"])
        return px(232)

    def _dibujar_botones_paso(self, s, w, h):
        """Un boton por cada tipo de paso que se puede agregar."""
        t, px = self.t, s.px
        sep = px(4)
        ancho = (w - px(44) - 4 * sep) / 5
        for i, (tipo, (titulo, _, desc, _)) in enumerate(PASOS.items()):
            x = px(22) + round((i % 5) * (ancho + sep))
            s.boton(x, px(6) + (i // 5) * px(34), round(ancho), px(30), f"+  {titulo}", lambda x=tipo: self._agregar_paso(x),
                    color=t["tarjeta"], tam=11, izquierda=True, ayuda=desc)

    def _conflicto(self, m):
        tecla = m["tecla"].upper()
        if not tecla:
            return ""
        aj = self.a.ajustes
        otra = next((x["nombre"] for x in self.macros if x is not m and x["tecla"].upper() == tecla), None)
        if otra:
            return f"también lo usa \"{otra}\""
        if tecla == aj["tecla_detener"].upper():
            return "choca con Detener todo"
        if tecla == aj["tecla_cerrar"].upper():
            return "choca con Cerrar"
        return ""

    def _cambiar_nombre(self, m, v):
        m["nombre"] = v[:60] or "Macro"
        self.pintar_lista()
        self._guardar_pronto()

    def _cambiar_modo(self, m, modo):
        self.motor.detener(m["id"])
        self._fijar(m, "modo", modo)

    # --------------------------------------------------------------- pasos
    def pintar_pasos(self):
        if self.pasos_ui:
            self.pasos_ui.reconstruir()

    def _editor_paso(self, padre, p):
        """Campos del paso abierto, dentro de su fila en la lista."""
        def dibujar(s, w, _):
            f = Flujo(self, s, w)
            getattr(self, "_campos_" + p["tipo"])(f, p)
            if p["tipo"] != "repetir":
                f.salto()
                f.etq("Probabilidad de que ocurra (%)")
                f.num(p, "prob", int, 0, 100, 48)
            return f.fin()
        return Escena(padre, self, dibujar, fondo=self.t["tarjeta"])

    def _campos_click(self, f, p):
        s = f.s
        f.etq("Botón")
        x, y = f.hueco(s.px(118))
        s.selector(x, y, s.px(118), s.px(28), p["boton"], entrada.BOTONES_MOUSE, lambda v: self._fijar(p, "boton", v), fondo=self.t["panel"])
        f.etq("Veces", 6)
        f.num(p, "veces", int, 1, 10000)
        f.etq("Por segundo", 6)
        s.deslizador(f.x, f.medio, f.resto, p["cps"], 0, 30, lambda v: self._fijar(p, "cps", v),
                     lambda v: f"{v:.1f}" if v > 0 else "sin pausa", paso=0.5)

    def _campos_tecla(self, f, p):
        s = f.s
        x, y = f.hueco(s.px(130))
        self._boton_captura(s, ("tecla", id(p)), x, y, s.px(130), s.px(28), lambda: p["teclas"], lambda c: self._fijar(p, "teclas", c or p["teclas"]))
        f.rango(p, "Mantenerla entre", final="segundos (0 = un toque)")

    def _campos_aleatoria(self, f, p):
        s = f.s
        f.etq("Teclas")
        clave = ("lista", id(p))

        def malas(v):
            return not v.strip() or any(not entrada.es_valida(x) for x in v.replace(",", " ").split())

        def cambiar(v):
            self._fijar(p, "lista", v)
            s.error_campo(clave, malas(v))
        x, y = f.hueco(s.px(150))
        s.campo(clave, x, y, s.px(150), s.px(28), p["lista"], cambiar, familia=MONO, negrita=True, tam=11, error=malas(p["lista"]))
        f.rango(p, "Dura entre")

    def _campos_patron(self, f, p):
        s, t = f.s, self.t
        clave = ("patron", id(p))

        def estado(v):
            errores = patron.leer(v)[1]
            return (" · ".join(errores), AMBAR) if errores else (AYUDA_PATRON, t["tenue"])

        def cambiar(v):
            self._fijar(p, "patron", v)
            texto, color = estado(v)
            s.itemconfigure(nota, text=self.rec.cortar(texto, f.ancho, self.rec.fuente(LETRA, s.px(11))), fill=color)
            s.error_campo(clave, color == AMBAR)
        f.etq("Teclas y tiempos")
        texto, color = estado(p["patron"])
        s.campo(clave, f.x, f.y + s.px(3), f.resto, s.px(28), p["patron"], cambiar, familia=MONO, negrita=True, tam=11, error=color == AMBAR)
        f.salto()
        nota = s.texto(0, f.y + s.px(12), texto, 11, color=color, ancho=f.ancho)
        f.y += s.px(26)
        f.x = 0
        f.etq("Orden")
        nombres = {v: k for k, v in patron.ORDENES.items()}
        x, y = f.hueco(s.px(140))
        s.selector(x, y, s.px(140), s.px(28), patron.ORDENES[p["orden"]], list(nombres), lambda n: self._fijar(p, "orden", nombres[n]),
                   fondo=t["panel"])
        f.etq("Repetir el patrón", 6)
        f.num(p, "veces", int, 1, 10000)
        f.etq("veces por pasada")
        f.salto()
        f.rango(p, "Las teclas sin tiempo propio duran entre", final="segundos (0 = un toque)")
        f.salto()
        f.rango(p, "Pausa entre una tecla y la siguiente: entre", "pausa_min", "pausa_max")

    def _campos_espera(self, f, p):
        f.rango(p, "Entre")

    def _campos_estado(self, f, p):
        s = f.s
        x, y = f.hueco(s.px(170))
        s.segmentado(x, y, s.px(170), s.px(28), {"Presionar": "presionar", "Soltar": "soltar"}, p["accion"],
                     lambda v: (self._fijar(p, "accion", v), s.repintar()))
        x, y = f.hueco(s.px(120))
        self._boton_captura(s, ("objetivo", id(p)), x, y, s.px(120), s.px(28), lambda: p["objetivo"],
                            lambda c: self._fijar(p, "objetivo", c.split("+")[-1] if c else p["objetivo"]))
        x, y = f.hueco(s.px(110))
        s.selector(x, y, s.px(110), s.px(28), "o mouse", entrada.BOTONES_MOUSE, lambda v: self._fijar(p, "objetivo", v), fondo=self.t["panel"])

    def _campos_mouse(self, f, p):
        s = f.s
        f.etq("X")
        f.num(p, "x", int, -100000, 100000, 70)
        f.etq("Y", 4)
        f.num(p, "y", int, -100000, 100000, 70)
        x, _ = f.hueco(s.px(34))
        s.interruptor(x + s.px(38), f.medio, p["relativo"], lambda: (self._fijar(p, "relativo", not p["relativo"]), s.repintar()))
        f.etq("Relativo a donde está", 6)

        def capturar(n=3):
            if not s.winfo_exists():
                self._apuntando = None
                return
            if n > 0:
                self._apuntando = (id(p), n)
                s.repintar()
                self.root.after(1000, lambda: capturar(n - 1))
                return
            self._apuntando = None
            p["x"], p["y"], p["relativo"] = *entrada.posicion_mouse(), False
            self._guardar_pronto()
            self.pintar_pasos()
        contando = self._apuntando and self._apuntando[0] == id(p)
        x, y = f.hueco(s.px(116))
        s.boton(x + s.px(6), y, s.px(110), s.px(28), f"Apunta... {self._apuntando[1]}" if contando else "Capturar punto",
                None if contando else capturar, tam=11, color=self.t["suave"], hover=self.t["borde"])

    def _campos_rueda(self, f, p):
        f.etq("Muescas")
        f.num(p, "muescas", int, -100, 100)
        f.etq("positivo sube, negativo baja", 4)

    def _campos_texto(self, f, p):
        s = f.s
        ancho = f.resto - s.medir("Letras por segundo", 11) - s.px(56 + 30)
        x, y = f.hueco(ancho)
        s.campo(("texto", id(p)), x, y, ancho, s.px(28), p["texto"], lambda v: self._fijar(p, "texto", v))
        f.etq("Letras por segundo", 6)
        f.num(p, "cps", float, 0, 100)

    def _campos_repetir(self, f, p):
        f.etq("Volver")
        f.num(p, "atras", int, 1, 1000)
        f.etq("pasos atrás y repetirlos")
        f.num(p, "veces", int, 1, 10000)
        f.etq("veces más")

    def _agregar_paso(self, tipo):
        self.pasos_ui.agregar(datos.nuevo_paso(tipo))
        self._guardar_pronto()

    # ----------------------------------------------------- campos genericos
    def _num(self, s, x, y, w, h, obj, clave, tipo, minimo, maximo):
        """Campo para un numero: guarda mientras escribes y lo acomoda al salir."""
        k = ("num", id(obj), clave)

        def escribir(v):
            try:
                n = tipo(float(v.replace(",", ".")))
            except (ValueError, OverflowError):
                return
            obj[clave] = max(minimo, min(maximo, n))
            self._guardar_pronto()

        def salir(v):
            escribir(v)
            s.fijar_campo(k, f"{obj[clave]:g}")
        s.campo(k, x, y, w, h, f"{obj[clave]:g}", escribir, salir, centrado=True)

    def _boton_captura(self, s, clave, x, y, w, h, obtener, fijar, vacio="Elegir"):
        """Boton que escucha la proxima tecla o combinacion que pulses."""
        t = self.t
        activo = bool(self._captura_ui and self._captura_ui["clave"] == clave)
        texto = ("Pulsa... (Esc cancela)" if w > s.px(170) else "Pulsa...") if activo else (obtener() or vacio)

        def empezar():
            self.cancelar_captura()
            self._captura_ui = dict(clave=clave, escena=s)

            def terminar(combo):
                if not self._captura_ui or self._captura_ui["clave"] != clave:
                    return
                self._captura_ui = None
                if combo is not None:
                    fijar(combo)
                if s.winfo_exists():
                    s.repintar()
            self.motor.capturar(lambda combo: self.cola.put(lambda: terminar(combo)))
            s.repintar()
        s.boton(x, y, w, h, texto, empezar, color=t["panel"], borde=t["acento"] if activo else t["borde"], tam=11, familia=MONO,
                color_texto=t["acento"] if t["modo"] == "dark" else t["texto"])

    def cancelar_captura(self):
        c, self._captura_ui = self._captura_ui, None
        if c:
            self.motor.cancelar_captura()
            if c["escena"].winfo_exists():
                c["escena"].repintar()

    # -------------------------------------------------------------- macros
    def _macro_eliminar(self):
        m = self.macro

        def borrar(_):
            self.motor.detener(m["id"])
            self.macros.remove(m)
            self.sel = self.macros[0]["id"] if self.macros else None
            self._aplicar_motor()
            self._guardar_pronto()
            self.pintar_lista()
            self.pintar_principal()
        self.dialogo("Eliminar macro", f"Se borra \"{m['nombre']}\" y sus pasos.", borrar, confirmar="Eliminar", peligro=True)

    def _macro_duplicar(self):
        m = copy.deepcopy(self.macro)
        m["id"], m["tecla"] = datos.nuevo_id(), ""
        m["nombre"] = (m["nombre"] + " copia")[:60]
        self.macros.insert(self.macros.index(self.macro) + 1, m)
        self._aplicar_motor()
        self.seleccionar(m["id"])
        self._guardar_pronto()

    def _alternar_desde_ui(self, m):
        """Desde la ventana da tiempo de ir al programa; asi el primer click no cae sobre el boton."""
        if self.motor.corriendo(m["id"]):
            self.motor.detener(m["id"], "botón de la ventana")
            return
        if self._cuenta_atras:
            self.root.after_cancel(self._cuenta_atras)
            self._cuenta_atras = None
            self.aviso("Cancelado")
            return
        if not any(p["activo"] for p in m["pasos"]):
            self.aviso("La macro no tiene pasos activos", AMBAR)
            return

        def contar(n):
            if n == 0:
                self._cuenta_atras = None
                self.aviso("")
                self.motor.iniciar(m, "botón de la ventana")
                return
            self.aviso(f"\"{m['nombre']}\" empieza en {n}...", self.t["acento"] if self.t["modo"] == "dark" else None, ms=0)
            self._cuenta_atras = self.root.after(1000, lambda: contar(n - 1))
        contar(m["cuenta"])

    # ------------------------------------------------------------ registro
    def _vista_registro(self):
        t, px = self.t, self.px
        m = self.macro
        aj = self.a.ajustes
        dias = self.registro.dias(m["id"])
        if self._registro_dia not in dias:
            self._registro_dia = dias[0] if dias else None

        def mostrar():
            lineas = self.registro.leer(m["id"], self._registro_dia) if self._registro_dia else []
            caja.configure(state="normal")
            caja.delete("1.0", "end")
            caja.insert("1.0", "\n".join(lineas) or "Todavía no hay nada aquí. Aparecerá cuando uses esta macro.")
            caja.configure(state="disabled")

        def elegir(dia):
            self._registro_dia = dia if dia in dias else None
            mostrar()

        def borrar():
            def confirmar(_):
                self.registro.borrar(m["id"])
                self.pintar_principal()
            self.dialogo("Borrar registro", f"Se borra todo el registro de \"{m['nombre']}\".", confirmar, confirmar="Borrar", peligro=True)

        def abrir():
            os.makedirs(self.registro.ruta(m["id"]), exist_ok=True)
            os.startfile(self.registro.ruta(m["id"]))

        def dibujar(s, w, h):
            estado = f"Se guardan los últimos {aj['registro_dias']} días." if aj["registro"] else "El registro está apagado. Actívalo en Ajustes."
            y = self._encabezado(s, f"Registro de {m['nombre']}", estado) + px(2)
            s.selector(px(22), y, px(150), px(30), self._registro_dia or "Sin registros", dias or ["Sin registros"], elegir)
            s.boton(px(180), y, px(86), px(30), "Actualizar", self.pintar_principal, tam=11, color=t["suave"], hover=t["borde"])
            s.boton(w - px(22) - px(70), y, px(70), px(30), "Borrar", borrar, tam=11, color=t["suave"], hover=t["borde"])
            s.boton(w - px(22) - px(178), y, px(100), px(30), "Abrir carpeta", abrir, tam=11, color=t["suave"], hover=t["borde"])
        Escena(self.principal, self, dibujar, height=px(118)).pack(fill="x")
        marco = tk.Frame(self.principal, bg=t["tarjeta"])
        marco.pack(fill="both", expand=True, padx=px(22), pady=(0, px(16)))
        caja = tk.Text(marco, font=(MONO, -px(12)), bg=t["tarjeta"], fg=t["texto"], bd=0, highlightthickness=0, wrap="none",
                       padx=px(14), pady=px(12), selectbackground=t["acento"], selectforeground=t["sobre"], cursor="arrow")
        barra = Barra(marco, self, caja.yview, t["tarjeta"])
        caja.configure(yscrollcommand=barra.set)
        barra.pack(side="right", fill="y", pady=px(6), padx=(0, px(2)))
        caja.pack(side="left", fill="both", expand=True)
        mostrar()

    def _al_cambiar_macro(self, macro, encendida):
        if self.a.ajustes["sonido"]:
            threading.Thread(target=winsound.Beep, args=(1046 if encendida else 660, 70), daemon=True).start()

    # ------------------------------------------------------------- grabar
    def _alternar_grabacion(self):
        if self.motor.grabando:
            self._terminar_grabacion()
            return
        self.motor.grabar()
        if self.cab:
            self.cab.repintar()
        tecla = self.a.ajustes["tecla_detener"]
        self.aviso(f"Grabando teclas y clicks. Termina con {tecla} o aquí." if tecla else "Grabando. Termina aquí.", ROJO, ms=0)

    def _terminar_grabacion(self):
        if not self.motor.grabando:
            return
        pasos = self.motor.terminar_grabacion()
        self.aviso(f"{len(pasos)} pasos agregados")
        if self.macro:
            self.macro["pasos"].extend(pasos)
            self._guardar_pronto()
        if self.vista == "editor" and not self.a.ajustes["compacto"]:
            self.pintar_principal()

    # ------------------------------------------------------------- ajustes
    def _dibujar_ajustes(self, s, w, h):
        t, px = self.t, s.px
        aj = self.a.ajustes
        y = self._encabezado(s, "Ajustes", "Cómo se ve y cómo responde Relevo.") - px(8)
        der = w - px(36)

        def interruptor(clave, despues=None):
            def cambiar():
                aj[clave] = not aj[clave]
                self._guardar_pronto()
                if despues:
                    despues()
                s.repintar()
            return lambda yc: s.interruptor(der, yc, aj[clave], cambiar)

        def boton(texto, fn):
            return lambda yc: s.boton(der - px(70), yc - px(14), px(70), px(28), texto, fn, tam=11, color=t["suave"], hover=t["borde"])

        def tema(yc):
            s.segmentado(der - px(290), yc - px(15), px(290), px(30), {n: n for n in TEMAS}, aj["tema"], self._cambiar_tema)

        def acento(yc):
            s.boton(der - px(60), yc - px(13), px(60), px(26), "Otro...", self._acento_libre, tam=11, color=t["suave"], hover=t["borde"])
            x = der - px(72)
            for color in reversed(ACENTOS):
                elegido = color.upper() == aj["acento"].upper()
                s.disco(x, yc, px(26), color, "e", t["texto"] if elegido else None, max(px(2), 1))
                s.zona(x - px(26), yc - px(13), px(26), px(26), clic=lambda c=color: self._cambiar_acento(c))
                x -= px(30)

        def opacidad(yc):
            def mover(v):
                aj["opacidad"] = v
                self.root.attributes("-alpha", v / 100)
                self._guardar_pronto()
            s.deslizador(der - px(250), yc, px(250), aj["opacidad"], 40, 100, mover, lambda v: f"{v}%", paso=1, tipo=int)

        def atajo(clave):
            def fijar(combo):
                aj[clave] = combo
                self._aplicar_motor()
                self._guardar_pronto()
            return lambda yc: self._boton_captura(s, ("ajuste", clave), der - px(130), yc - px(15), px(130), px(30), lambda: aj[clave], fijar, vacio="Sin atajo")

        def reiniciar():
            for k in self.a.stats:
                self.a.stats[k] = 0
            self._guardar_pronto()

        carpeta = os.path.dirname(self.a.ruta)
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        secciones = (
            ("APARIENCIA", (
                ("Tema", "", tema),
                ("Color de acento", "", acento),
                ("Opacidad", "Para ver lo que hay detrás de la ventana", opacidad),
                ("Siempre encima", "La ventana queda sobre los demás programas", interruptor("encima", self._aplicar_ventana)),
                ("Sonido al encender o apagar", "Útil cuando la ventana está minimizada", interruptor("sonido")))),
            ("ATAJOS GENERALES", (
                ("Detener todo", "Para todas las macros y suelta todo al instante", atajo("tecla_detener")),
                ("Cerrar Relevo", "Sale del programa desde cualquier ventana", atajo("tecla_cerrar")))),
            ("REGISTRO DE MACROS", (
                ("Guardar registro", "Cuándo empezó y terminó cada macro, y cuánto hizo", interruptor("registro")),
                ("Días que se conservan", "Lo más antiguo se borra al abrir Relevo o al cambiar de día",
                 lambda yc: self._num(s, der - px(56), yc - px(14), px(56), px(28), aj, "registro_dias", int, 1, 365)))),
            ("TUS DATOS", (
                ("Carpeta de configuración", carpeta, boton("Abrir", lambda: os.startfile(carpeta))),
                ("Contadores", "Clicks, teclas y tiempo que Relevo hizo por ti", boton("Reiniciar", reiniciar)))),
            ("PERMISOS", (
                ("Abrir como administrador" + (" (activo ahora)" if admin else ""),
                 "Solo si un programa ignora las teclas. Mientras esté al frente, Lightshot no puede capturar.",
                 interruptor("admin", lambda: self.aviso("Se aplica la próxima vez que abras Relevo"))),)),
        )
        for titulo, filas in secciones:
            s.texto(px(30), y + px(18), titulo, 10, True, t["tenue"])
            y += px(30)
            alto = sum(px(54 if detalle else 46) for _, detalle, _ in filas)
            s.tarjeta(px(22), y, w - px(44), alto, t["tarjeta"], 10)
            for nombre, detalle, control in filas:
                yc = y + px(27 if detalle else 23)
                s.texto(px(36), yc - (px(9) if detalle else 0), nombre, 12, True)
                if detalle:
                    s.texto(px(36), yc + px(9), detalle, 11, color=t["tenue"], ancho=w - px(72) - px(150))
                control(yc)
                y += px(54 if detalle else 46)
            s.sobre = s.fondo
        return y + px(16)

    def _cambiar_tema(self, nombre):
        self.a.ajustes["tema"] = nombre
        self._guardar_pronto()
        self.construir()

    def _cambiar_acento(self, color):
        self.a.ajustes["acento"] = color
        self._guardar_pronto()
        self.construir()

    def _acento_libre(self):
        color = colorchooser.askcolor(color=self.a.ajustes["acento"], parent=self.root)[1]
        if color:
            self._cambiar_acento(color.upper())

    # --------------------------------------------------------------- ciclo
    def _bombear(self):
        while True:
            try:
                self.cola.get_nowait()()
            except queue.Empty:
                break
        if not self._arrancando:
            self._vigilar_minimizado()
        self.root.after(30, self._bombear)

    def _refrescar(self):
        escribiendo = False
        try:
            foco = self.root.focus_get()
            escribiendo = isinstance(foco, tk.Entry) and entrada.user32.GetForegroundWindow() == self.hwnd
        except (KeyError, tk.TclError):
            pass
        self.motor.escribiendo = escribiendo
        self.motor.rect_propio = (self.root.winfo_rootx(), self.root.winfo_rooty(),
                                  self.root.winfo_rootx() + self.root.winfo_width(), self.root.winfo_rooty() + self.root.winfo_height())

        # Las macros se encienden y apagan desde otro hilo: aqui se nota y se redibuja lo justo.
        estado = tuple((m["id"], self.motor.corriendo(m["id"]), self.motor.pausada(m["id"])) for m in self.macros)
        if estado != self._estado_macros:
            self._estado_macros = estado
            self.lista.repintar()
            if self.cab and self.cab.winfo_exists():
                self.cab.repintar()
        texto = self._texto_stats()
        if self._id_stats and self.lat_pie.itemcget(self._id_stats, "text") != texto:
            self.lat_pie.itemconfigure(self._id_stats, text=texto)
        self._ultimo_guardado_stats += 1
        if self._ultimo_guardado_stats >= 300:  # cada 30 s
            self._ultimo_guardado_stats = 0
            self._guardar_pronto()
        self.root.after(100, self._refrescar)

    def cerrar(self):
        self._confirmar_nombre()
        self.motor.apagar()
        try:
            self.a.guardar()
        except OSError:
            pass
        self.root.destroy()
