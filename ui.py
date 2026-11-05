"""Interfaz de Relevo: ventana sin marco de Windows, editor de macros y ajustes."""
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
from datos import MODOS, PASOS, PLANTILLAS
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
I_UP, I_DOWN, I_PLAY, I_STOP = "", "", "", ""
I_GEAR, I_MIN, I_CLOSE, I_COMPACT, I_EXPAND = "", "", "", "", ""
I_LOG, I_MAX, I_RESTORE, I_CHEVRON = "\uE81C", "\uE922", "\uE923", "\uE70D"
I_IMPORT, I_EXPORT, I_REC, I_BACK ="", "", "", ""

ANCHO_COMPACTO, MIN_ANCHO, MIN_ALTO = 300, 980, 520
BORDE_REDIMENSION = 5
CURSORES = {"n": "sb_v_double_arrow", "s": "sb_v_double_arrow", "e": "sb_h_double_arrow", "w": "sb_h_double_arrow",
            "nw": "size_nw_se", "se": "size_nw_se", "ne": "size_ne_sw", "sw": "size_ne_sw"}


def fuente(tam=12, negrita=False):
    return ("Segoe UI", tam, "bold" if negrita else "normal")


def f_icono(tam=12):
    return ("Segoe MDL2 Assets", tam)


def f_tecla(tam=11):
    return ("Consolas", tam, "bold")


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


class Selector(ctk.CTkFrame):
    """Desplegable propio: el de CustomTkinter usa el menu antiguo de Windows."""

    def __init__(self, app, padre, valores, actual, comando, ancho=None, alto=30, fondo=None, extra=None):
        t = app.t
        self.app, self.valores, self.actual, self.comando, self.extra = app, valores, actual, comando, extra
        self.fondo = fondo or t["tarjeta"]
        super().__init__(padre, fg_color=self.fondo, corner_radius=7, height=alto, border_width=1, border_color=t["borde"], **({"width": ancho} if ancho else {}))
        self.pack_propagate(False)
        self.lbl = ctk.CTkLabel(self, text=actual, font=fuente(12), text_color=t["texto"], anchor="w", height=alto - 4)
        self.lbl.pack(side="left", fill="x", expand=True, padx=(10, 2), pady=2)
        self.chev = ctk.CTkLabel(self, text=I_CHEVRON, font=f_icono(9), text_color=t["tenue"], width=22, height=alto - 4)
        self.chev.pack(side="right", padx=(0, 4), pady=2)
        for w in (self, self.lbl, self.chev):
            w.bind("<ButtonRelease-1>", lambda _: self.abrir())
            w.bind("<Enter>", lambda _: self.configure(border_color=t["tenue"]))
            w.bind("<Leave>", lambda _: self.configure(border_color=t["borde"]))

    def abrir(self):
        def elegir(v):
            self.set(v)
            self.comando(v)
        self.app.abrir_menu(self, self.valores, self.actual, elegir, self.extra)

    def set(self, valor):
        self.actual = valor
        self.lbl.configure(text=valor)


class Aviso:
    """Tooltip para los botones que solo tienen icono."""

    def __init__(self, widget, texto, tema):
        self.widget, self.texto, self.tema = widget, texto, tema
        self.ventana = self.tarea = None
        widget.bind("<Enter>", self._programar, add="+")
        widget.bind("<Leave>", self._ocultar, add="+")
        widget.bind("<Button-1>", self._ocultar, add="+")

    def _programar(self, _):
        self.tarea = self.widget.after(450, self._mostrar)

    def _mostrar(self):
        if not self.widget.winfo_exists():
            return
        v = self.ventana = tk.Toplevel(self.widget)
        v.overrideredirect(True)
        v.attributes("-topmost", True)
        tk.Label(v, text=self.texto, bg=self.tema["tarjeta"], fg=self.tema["texto"], font=fuente(9), padx=8, pady=3,
                 highlightthickness=1, highlightbackground=self.tema["borde"]).pack()
        v.geometry(f"+{self.widget.winfo_rootx()}+{self.widget.winfo_rooty() + self.widget.winfo_height() + 4}")

    def _ocultar(self, _=None):
        if self.tarea:
            self.widget.after_cancel(self.tarea)
            self.tarea = None
        if self.ventana:
            self.ventana.destroy()
            self.ventana = None


class App:
    def __init__(self, root, almacen, motor):
        self.root, self.a, self.motor = root, almacen, motor
        self.vista = "editor"
        self.sel = None
        self.filas = {}
        self.cola = queue.SimpleQueue()
        self._guardado = None
        self._estado_filas = {}
        self._cuenta_atras = None
        self._boton_capturando = None
        self._ultimo_guardado_stats = 0
        self.t = {}
        self.pasos_ui = None
        self._pantalla = None       # None, "max" o "completa"
        self._geom_normal = None
        self._redim = None
        self._redim_tarea = None
        self._zona = ""
        self._oculta = False
        self._menu = self._menu_ancla = None
        self._dlg = None
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

    def _aplicar_motor(self):
        aj = self.a.ajustes
        self.motor.configurar(self.macros, aj["tecla_detener"], aj["tecla_cerrar"])

    def _confirmar_nombre(self):
        pendiente, self._nombre_pendiente = getattr(self, "_nombre_pendiente", None), None
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

    # ---------------------------------------------------- ventana sin marco
    def _quitar_marco(self):
        """Quita la barra blanca de Windows (y su menu) dejando el icono en la barra de tareas."""
        self.root.overrideredirect(True)
        self.root.update_idletasks()
        u = entrada.user32
        self.hwnd = u.GetParent(self.root.winfo_id())
        u.SetWindowLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t)
        u.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes = (ctypes.c_void_p, ctypes.c_int)
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        self.root.withdraw()
        self.root.after(30, self._mostrar_ventana)
        self.root.after(300, self._fijar_iconos)

    def _mostrar_ventana(self):
        self.root.deiconify()
        self.root.update_idletasks()
        self._estilo_ventana()
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

    def _minimizar(self):
        # Oculta antes de minimizar: al volver, Tk redibuja cada widget y se veria cargar por partes.
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
        final = max(self.a.ajustes["opacidad"], 40) / 100
        pasos = (0.5, 0.8, 1)
        if self._oculta:
            return
        self.root.attributes("-alpha", final * pasos[paso])
        if paso < 2:
            self.root.after(15, lambda: self._revelar(paso + 1))

    def _inicio_arrastre(self, e):
        self._arrastre = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def _arrastrar(self, e):
        if self._pantalla or self._redim:
            return
        dx, dy = self._arrastre
        tk.Tk.geometry(self.root, f"+{e.x_root - dx}+{e.y_root - dy}")

    def _aplicar_ventana(self):
        aj = self.a.ajustes
        self.root.attributes("-topmost", bool(aj["encima"]))
        if not self._oculta:
            self.root.attributes("-alpha", max(aj["opacidad"], 40) / 100)
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
        elif self.btn_max.winfo_exists():
            self.btn_max.configure(text=I_RESTORE if self._pantalla else I_MAX)
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
                self._redim_tarea = self.root.after(16, self._aplicar_redim)

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
        if self.pasos_ui and str(e.widget).startswith(str(self.pasos_ui.lienzo)):
            self.pasos_ui.rueda(e.delta)

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

    # ------------------------------------------------------------ desplegable
    def abrir_menu(self, ancla, valores, actual, al_elegir, extra=None):
        if self._menu_ancla is ancla:
            self._cerrar_menu()
            return
        self._cerrar_menu()
        t = self.t
        esc = self._escala()
        ancho = max(round(ancla.winfo_width() / esc), 150)
        m = ctk.CTkFrame(self.marco, fg_color=t["tarjeta"], corner_radius=10, border_width=1, border_color=t["borde"])
        contenedor = m
        if len(valores) > 8:
            contenedor = ctk.CTkScrollableFrame(m, fg_color="transparent", width=ancho - 30, height=8 * 34,
                                                scrollbar_button_color=t["borde"], scrollbar_button_hover_color=t["tenue"])
            contenedor.pack(padx=4, pady=4)

        def fila(padre, texto, comando, seleccionado=False, color=None):
            b = ctk.CTkButton(padre, text=texto, anchor="w", height=32, width=ancho - 12, corner_radius=7, font=fuente(12, seleccionado),
                              fg_color=t["suave"] if seleccionado else "transparent", hover_color=t["suave"],
                              text_color=color or t["texto"], command=comando)
            b.pack(padx=5, pady=1)

        def elegir(v):
            self._cerrar_menu()
            al_elegir(v)
        for v in valores:
            fila(contenedor, v, lambda x=v: elegir(x), v == actual)
        if extra:
            ctk.CTkFrame(m, fg_color=t["borde"], height=1, corner_radius=0).pack(fill="x", padx=8, pady=3)
            for texto, fn in extra:
                fila(m, texto, lambda f=fn: (self._cerrar_menu(), f()), color=t["acento"] if t["modo"] == "dark" else t["texto"])
        ctk.CTkFrame(m, fg_color="transparent", height=4, width=1).pack()
        m.update_idletasks()
        x = ancla.winfo_rootx() - self.marco.winfo_rootx()
        y = ancla.winfo_rooty() - self.marco.winfo_rooty() + ancla.winfo_height() + round(4 * esc)
        if y + m.winfo_reqheight() > self.marco.winfo_height():
            y = max(ancla.winfo_rooty() - self.marco.winfo_rooty() - m.winfo_reqheight() - round(4 * esc), 0)
        x = min(x, self.marco.winfo_width() - m.winfo_reqwidth() - round(4 * esc))
        m.place(x=x / esc, y=y / esc)
        m.lift()
        self._menu, self._menu_ancla = m, ancla

    def _cerrar_menu(self):
        if self._menu and self._menu.winfo_exists():
            self._menu.destroy()
        self._menu = self._menu_ancla = None

    def _cerrar_menu_si_afuera(self, e):
        if not self._menu:
            return
        w = str(e.widget)
        if w.startswith(str(self._menu)) or (self._menu_ancla.winfo_exists() and w.startswith(str(self._menu_ancla))):
            return
        self._cerrar_menu()

    def _quitar_foco(self, e):
        if not isinstance(e.widget, (tk.Entry, str)):
            try:
                self.root.focus_set()
            except tk.TclError:
                pass

    # ----------------------------------------------------------- construir
    def construir(self):
        self._confirmar_nombre()
        tema = TEMAS.get(self.a.ajustes["tema"], TEMAS["Noche"])
        acento = self.a.ajustes["acento"]
        self.t = dict(tema, acento=acento, sobre=sobre(acento), hover=mezclar(acento, tema["fondo"], 0.18),
                      suave=mezclar(tema["tarjeta"], tema["texto"], 0.08))
        ctk.set_appearance_mode(tema["modo"])
        self._menu = self._menu_ancla = self._dlg = self.pasos_ui = None
        for w in self.root.winfo_children():
            w.destroy()
        self.root.configure(fg_color=self.t["borde"])

        self.marco = ctk.CTkFrame(self.root, fg_color=self.t["fondo"], corner_radius=0)
        self.marco.pack(fill="both", expand=True, padx=1, pady=1)
        self._barra_titulo()
        cuerpo = ctk.CTkFrame(self.marco, fg_color="transparent", corner_radius=0)
        cuerpo.pack(fill="both", expand=True)
        self.lateral = ctk.CTkFrame(cuerpo, fg_color=self.t["panel"], corner_radius=0, width=ANCHO_COMPACTO - 2)
        self.lateral.pack(side="left", fill="y")
        self.lateral.pack_propagate(False)
        self.principal = ctk.CTkFrame(cuerpo, fg_color="transparent", corner_radius=0)
        if not self.a.ajustes["compacto"]:
            self.principal.pack(side="left", fill="both", expand=True)
        self._construir_lateral()
        self.pintar_principal()
        self._aplicar_ventana()

    def _boton_icono(self, padre, icono, comando, ayuda=None, tam=12, ancho=30, alto=30, color=None, hover=None, texto=None):
        b = ctk.CTkButton(padre, text=icono, font=f_icono(tam), width=ancho, height=alto, corner_radius=6,
                          fg_color=color or "transparent", hover_color=hover or self.t["suave"],
                          text_color=texto or self.t["tenue"], command=comando)
        if ayuda:
            Aviso(b, ayuda, self.t)
        return b

    def _boton(self, padre, texto, comando, primario=False, **kw):
        estilo = dict(fg_color=self.t["acento"], hover_color=self.t["hover"], text_color=self.t["sobre"]) if primario else \
            dict(fg_color=self.t["suave"], hover_color=self.t["borde"], text_color=self.t["texto"])
        estilo.update(kw)
        estilo.setdefault("height", 32)
        estilo.setdefault("corner_radius", 7)
        estilo.setdefault("font", fuente(12, True))
        return ctk.CTkButton(padre, text=texto, command=comando, **estilo)

    def _texto(self, padre, texto, tam=12, negrita=False, color=None, **kw):
        return ctk.CTkLabel(padre, text=texto, font=fuente(tam, negrita), text_color=color or self.t["texto"], **kw)

    def _barra_titulo(self):
        barra = ctk.CTkFrame(self.marco, fg_color=self.t["panel"], corner_radius=0, height=40)
        barra.pack(fill="x")
        barra.pack_propagate(False)
        grande = dibujar_logo(88, self.t["acento"], self.t["sobre"])
        logo = ctk.CTkLabel(barra, text="", image=ctk.CTkImage(grande, grande, size=(22, 22)))
        logo.pack(side="left", padx=(12, 8))
        nombre = self._texto(barra, datos.APP, 13, True)
        nombre.pack(side="left")
        self.lbl_aviso = self._texto(barra, "", 11, color=self.t["tenue"])
        self.lbl_aviso.pack(side="left", padx=12)

        cerrar = self._boton_icono(barra, I_CLOSE, self.cerrar, tam=10, ancho=44, alto=40, hover=ROJO)
        cerrar.configure(corner_radius=0)
        cerrar.pack(side="right")
        self.btn_max = self._boton_icono(barra, I_RESTORE if self._pantalla else I_MAX, lambda: self._alternar_pantalla(self._pantalla or "max"),
                                         "Maximizar (F11: pantalla completa)", tam=10, ancho=44, alto=40)
        self.btn_max.configure(corner_radius=0)
        self.btn_max.pack(side="right")
        mini = self._boton_icono(barra, I_MIN, self._minimizar, tam=10, ancho=44, alto=40)
        mini.configure(corner_radius=0)
        mini.pack(side="right")
        compacto = self.a.ajustes["compacto"]
        cmp_b = self._boton_icono(barra, I_EXPAND if compacto else I_COMPACT, self._alternar_compacto,
                                  "Ver completo" if compacto else "Modo compacto", tam=11, ancho=44, alto=40)
        cmp_b.configure(corner_radius=0)
        cmp_b.pack(side="right")
        for w in (barra, nombre, logo, self.lbl_aviso):
            w.bind("<Button-1>", self._inicio_arrastre)
            w.bind("<B1-Motion>", self._arrastrar)
            w.bind("<Double-Button-1>", lambda _: self._alternar_pantalla(self._pantalla or "max"))

    def aviso(self, texto, color=None, ms=3500):
        self.lbl_aviso.configure(text=texto, text_color=color or self.t["tenue"])
        if getattr(self, "_aviso_tarea", None):
            self.root.after_cancel(self._aviso_tarea)
        self._aviso_tarea = self.root.after(ms, lambda: self.lbl_aviso.winfo_exists() and self.lbl_aviso.configure(text="")) if ms else None

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
        cab = ctk.CTkFrame(self.lateral, fg_color="transparent")
        cab.pack(fill="x", padx=12, pady=(12, 0))
        self._texto(cab, "PERFIL", 10, True, self.t["tenue"]).pack(anchor="w")
        nombres = self._nombres_perfiles()
        actual = next(n for n, pid in nombres.items() if pid == self.perfil["id"])
        Selector(self, cab, list(nombres), actual, lambda n: self._cambiar_perfil(nombres[n]), alto=34,
                 extra=[("+  Nuevo perfil", self._perfil_nuevo)]).pack(fill="x", pady=(2, 4))
        acciones = ctk.CTkFrame(cab, fg_color="transparent")
        acciones.pack(fill="x")
        for icono, fn, ayuda in ((I_ADD, self._perfil_nuevo, "Nuevo perfil"), (I_EDIT, self._perfil_renombrar, "Renombrar"),
                                 (I_COPY, self._perfil_duplicar, "Duplicar"), (I_DEL, self._perfil_eliminar, "Eliminar"),
                                 (I_IMPORT, self._perfil_importar, "Importar archivo"), (I_EXPORT, self._perfil_exportar, "Exportar para compartir")):
            self._boton_icono(acciones, icono, fn, ayuda, tam=11).pack(side="left", padx=(0, 4))

        cab2 = ctk.CTkFrame(self.lateral, fg_color="transparent")
        cab2.pack(fill="x", padx=12, pady=(14, 2))
        self._texto(cab2, "MACROS", 10, True, self.t["tenue"]).pack(side="left")
        self._texto(cab2, "arrastra para ordenar", 10, color=self.t["tenue"]).pack(side="left", padx=8)
        self._boton_icono(cab2, I_ADD, lambda: self.ir_a("plantillas"), "Nueva macro", tam=11, ancho=26, alto=26,
                          texto=self.t["acento"]).pack(side="right")

        pie = ctk.CTkFrame(self.lateral, fg_color="transparent")
        pie.pack(side="bottom", fill="x", padx=12, pady=12)
        self.lbl_stats = self._texto(pie, "", 11, color=self.t["tenue"], justify="left", anchor="w")
        self.lbl_stats.pack(fill="x", pady=(0, 8))
        fila = ctk.CTkFrame(pie, fg_color="transparent")
        fila.pack(fill="x")
        self._boton(fila, "Detener todo", self.motor.detener_todo).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._boton_icono(fila, I_GEAR, lambda: self.ir_a("ajustes"), "Ajustes", tam=14, ancho=34, alto=32,
                          color=self.t["suave"], hover=self.t["borde"], texto=self.t["texto"]).pack(side="right")

        self.lista = ctk.CTkScrollableFrame(self.lateral, fg_color="transparent", corner_radius=0,
                                            scrollbar_button_color=self.t["borde"], scrollbar_button_hover_color=self.t["tenue"])
        self.lista.pack(fill="both", expand=True, padx=(6, 2))
        self.pintar_lista()

    def _nombres_perfiles(self):
        return {f"{p['nombre']}" + (f" ({i})" if any(q["nombre"] == p["nombre"] for q in self.a.perfiles[:i]) else ""): p["id"]
                for i, p in enumerate(self.a.perfiles)}

    def pintar_lista(self):
        for w in self.lista.winfo_children():
            w.destroy()
        self.filas = {}
        self._estado_filas = {}
        if not self.macros:
            self._texto(self.lista, "Sin macros todavía.\nCrea la primera con +", 12, color=self.t["tenue"]).pack(pady=30)
        for m in self.macros:
            self._fila_macro(m)

    def _fila_macro(self, m):
        t = self.t
        activa = m["id"] == self.sel and self.vista == "editor" and not self.a.ajustes["compacto"]
        fila = ctk.CTkFrame(self.lista, fg_color=t["suave"] if activa else "transparent", corner_radius=8, height=48)
        fila.pack(fill="x", pady=1, padx=(0, 4))
        fila.pack_propagate(False)
        punto = ctk.CTkFrame(fila, width=8, height=8, corner_radius=4, fg_color=t["borde"])
        punto.pack(side="left", padx=(10, 8))
        centro = ctk.CTkFrame(fila, fg_color="transparent")
        centro.pack(side="left", fill="both", expand=True)
        nombre = self._texto(centro, m["nombre"], 12, True, anchor="w", height=18)
        nombre.pack(fill="x", pady=(6, 0))
        tecla = ctk.CTkLabel(centro, text=m["tecla"] or "sin atajo", font=f_tecla(10), text_color=t["tenue"], anchor="w", height=14)
        tecla.pack(fill="x")
        boton = self._boton_icono(fila, I_PLAY, lambda: self._alternar_desde_ui(m), "Iniciar o detener", tam=11, ancho=30, alto=30)
        boton.pack(side="right", padx=8)
        self.filas[m["id"]] = dict(marco=fila, punto=punto, nombre=nombre, tecla=tecla, boton=boton)
        for w in (fila, centro, nombre, tecla, punto):
            w.bind("<ButtonPress-1>", lambda e, x=m: self._fila_presionar(e, x))
            w.bind("<B1-Motion>", self._fila_arrastrar)
            w.bind("<ButtonRelease-1>", self._fila_soltar)

    # Un click selecciona; mantener y mover reordena.
    def _fila_presionar(self, e, m):
        self._fila_mov = dict(m=m, y0=e.y_root, activo=False)

    def _fila_arrastrar(self, e):
        a = getattr(self, "_fila_mov", None)
        if not a:
            return
        if not a["activo"]:
            if abs(e.y_root - a["y0"]) < 6 * self._escala():
                return
            a["activo"] = True
            self.filas[a["m"]["id"]]["marco"].configure(border_width=1, border_color=self.t["acento"], fg_color=self.t["suave"])
            tk.Tk.configure(self.root, cursor="fleur")
        lienzo = self.lista._parent_canvas
        y_lista = e.y_root - lienzo.winfo_rooty()
        if y_lista < 20:
            lienzo.yview_scroll(-1, "units")
        elif y_lista > lienzo.winfo_height() - 20:
            lienzo.yview_scroll(1, "units")
        i = self.macros.index(a["m"])
        for j, otra in enumerate(self.macros):
            f = self.filas[otra["id"]]["marco"]
            if j != i and f.winfo_rooty() <= e.y_root < f.winfo_rooty() + f.winfo_height():
                self.macros.insert(j, self.macros.pop(i))
                for x in self.macros:
                    self.filas[x["id"]]["marco"].pack_forget()
                for x in self.macros:
                    self.filas[x["id"]]["marco"].pack(fill="x", pady=1, padx=(0, 4))
                break

    def _fila_soltar(self, e):
        a, self._fila_mov = getattr(self, "_fila_mov", None), None
        if not a:
            return
        if a["activo"]:
            tk.Tk.configure(self.root, cursor="")
            self._guardar_pronto()
            self.pintar_lista()
        else:
            self.seleccionar(a["m"]["id"])

    def seleccionar(self, mid):
        self.sel = mid
        self.vista = "editor"
        if self.a.ajustes["compacto"]:
            self.a.ajustes["compacto"] = False
            self.construir()
        else:
            self.pintar_lista()
            self.pintar_principal()

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
            p = {"id": datos.nuevo_id(), "nombre": nombre, "macros": []}
            self.a.perfiles.append(p)
            self._cambiar_perfil(p["id"])
        self.dialogo("Nuevo perfil", "Un perfil agrupa las macros de una tarea.", crear, valor="Nuevo perfil")

    def _perfil_renombrar(self):
        def renombrar(nombre):
            self.perfil["nombre"] = nombre
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
            datos.exportar(self.perfil, ruta)
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
        t = self.t
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
        caja = ctk.CTkFrame(capa, fg_color=t["tarjeta"], bg_color=color_fondo, border_color=t["borde"], border_width=1, corner_radius=14)
        caja.place(relx=.5, rely=.40, anchor="center")
        self._texto(caja, titulo, 16, True).pack(anchor="w", padx=22, pady=(20, 2))
        if texto:
            self._texto(caja, texto, 12, color=t["tenue"], wraplength=300, justify="left").pack(anchor="w", padx=22)
        campo = None
        if valor is not None:
            campo = ctk.CTkEntry(caja, width=300, height=36, font=fuente(12), **self._estilo_campo())
            campo.insert(0, valor)
            campo.pack(padx=22, pady=(12, 0))

        def cerrar():
            self._dlg = None
            if capa.winfo_exists():
                capa.destroy()

        def aceptar():
            resultado = campo.get().strip() if campo else True
            if campo and not resultado:
                return
            cerrar()
            al_aceptar(resultado)
        botones = ctk.CTkFrame(caja, fg_color="transparent", width=300, height=34)
        botones.pack(fill="x", padx=22, pady=(18, 20))
        self._boton(botones, "Cancelar", cerrar, width=88, height=34).pack(side="right")
        extra = dict(fg_color=ROJO, hover_color=mezclar(ROJO, "#000000", .2), text_color="#FFFFFF") if peligro else {}
        self._boton(botones, confirmar, aceptar, primario=True, width=100, height=34, **extra).pack(side="right", padx=(0, 8))
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
        if campo:
            campo.after(40, lambda: campo.winfo_exists() and (campo.focus_force(), campo.select_range(0, "end")))
        else:
            capa.focus_set()

    # ----------------------------------------------------------- principal
    def pintar_principal(self):
        self._confirmar_nombre()
        for w in self.principal.winfo_children():
            w.destroy()
        self.cancelar_captura()
        self._cerrar_menu()
        self.pasos_ui = None
        self.btn_probar = None
        if self.a.ajustes["compacto"]:
            return
        if self.vista == "plantillas":
            self._vista_plantillas()
        elif self.vista == "ajustes":
            self._vista_ajustes()
        elif self.vista == "registro" and self.macro:
            self._vista_registro()
        elif self.macro:
            self._vista_editor()
        else:
            self._vista_vacia()

    def _vista_vacia(self):
        caja = ctk.CTkFrame(self.principal, fg_color="transparent")
        caja.place(relx=.5, rely=.42, anchor="center")
        self._texto(caja, "Este perfil está vacío", 18, True).pack()
        self._texto(caja, "Crea una macro y deja que tus manos descansen.", 12, color=self.t["tenue"]).pack(pady=(4, 14))
        self._boton(caja, "Nueva macro", lambda: self.ir_a("plantillas"), primario=True).pack()

    def _encabezado_vista(self, titulo, subtitulo):
        cab = ctk.CTkFrame(self.principal, fg_color="transparent")
        cab.pack(fill="x", padx=22, pady=(18, 10))
        if self.macro:
            self._boton_icono(cab, I_BACK, lambda: self.ir_a("editor"), "Volver", tam=13).pack(side="left", padx=(0, 8))
        txt = ctk.CTkFrame(cab, fg_color="transparent")
        txt.pack(side="left")
        self._texto(txt, titulo, 19, True, anchor="w").pack(anchor="w")
        self._texto(txt, subtitulo, 12, color=self.t["tenue"], anchor="w").pack(anchor="w")

    def _vista_plantillas(self):
        self._encabezado_vista("Nueva macro", "Elige un punto de partida. Todo se puede cambiar después.")
        grid = ctk.CTkFrame(self.principal, fg_color="transparent")
        grid.pack(fill="both", expand=True, padx=22)
        grid.grid_columnconfigure((0, 1), weight=1, uniform="p")
        for i, (nombre, desc, fabrica) in enumerate(PLANTILLAS):
            tarjeta = ctk.CTkFrame(grid, fg_color=self.t["tarjeta"], corner_radius=10, border_width=1, border_color=self.t["borde"], height=92)
            tarjeta.grid(row=i // 2, column=i % 2, sticky="ew", padx=5, pady=5)
            tarjeta.pack_propagate(False)
            a = self._texto(tarjeta, nombre, 14, True, anchor="w")
            a.pack(fill="x", padx=16, pady=(14, 0))
            b = self._texto(tarjeta, desc, 12, color=self.t["tenue"], anchor="w", justify="left", wraplength=290)
            b.pack(fill="x", padx=16)
            crear = lambda _=None, f=fabrica: self._crear_macro(f())
            for w in (tarjeta, a, b):
                w.bind("<Button-1>", crear)
                w.configure(cursor="hand2")
            tarjeta.bind("<Enter>", lambda _, c=tarjeta: c.configure(border_color=self.t["acento"]))
            tarjeta.bind("<Leave>", lambda _, c=tarjeta: c.configure(border_color=self.t["borde"]))

    def _crear_macro(self, m):
        usados = {x["tecla"] for x in self.macros}
        if m["tecla"] in usados:
            m["tecla"] = ""
        self.macros.append(m)
        self.seleccionar(m["id"])
        self._guardar_pronto()

    # -------------------------------------------------------------- editor
    def _vista_editor(self):
        m = self.macro
        t = self.t
        cab = ctk.CTkFrame(self.principal, fg_color="transparent")
        cab.pack(fill="x", padx=22, pady=(16, 8))
        nombre = ctk.CTkEntry(cab, font=fuente(17, True), height=36, width=270, fg_color="transparent", border_width=1, border_color=t["borde"], text_color=t["texto"])
        nombre.insert(0, m["nombre"])
        nombre.pack(side="left")
        boton_nombre = self._boton(cab, "Guardar", None, width=74, height=30, font=fuente(11, True))
        boton_nombre.pack(side="left", padx=(8, 0))

        def revisar(_=None):
            pendiente = nombre.get().strip() != m["nombre"]
            boton_nombre.configure(state="normal" if pendiente else "disabled", text_color_disabled=t["tenue"],
                                   fg_color=t["acento"] if pendiente else t["suave"], hover_color=t["hover"] if pendiente else t["suave"],
                                   text_color=t["sobre"] if pendiente else t["tenue"])

        def guardar(_=None):
            valor = nombre.get().strip()
            if not valor:
                nombre.insert(0, m["nombre"])
            elif valor != m["nombre"]:
                self._cambiar_nombre(m, valor)
                self.aviso("Nombre guardado")
            revisar()
            self.root.focus_set()

        def confirmar_sin_aviso():
            # Cambiar de vista sin pulsar Guardar no debe perder lo escrito.
            valor = nombre.get().strip()
            if valor and valor != m["nombre"]:
                self._cambiar_nombre(m, valor)
        self._nombre_pendiente = (nombre, confirmar_sin_aviso)
        boton_nombre.configure(command=guardar)
        nombre.bind("<KeyRelease>", revisar)
        nombre.bind("<Return>", guardar, add="+")
        nombre.bind("<Button-1>", lambda _: nombre.focus_force(), add="+")
        revisar()
        self.btn_probar = self._boton(cab, "", lambda: self._alternar_desde_ui(m), primario=True, width=112, height=34)
        self.btn_probar.pack(side="right", padx=(8, 0))
        for icono, fn, ayuda in ((I_DEL, self._macro_eliminar, "Eliminar macro"), (I_COPY, self._macro_duplicar, "Duplicar macro"),
                                 (I_LOG, lambda: self.ir_a("registro"), "Ver registro de esta macro")):
            self._boton_icono(cab, icono, fn, ayuda, tam=12, ancho=32, alto=32).pack(side="right", padx=(2, 0))

        self._tarjeta_ajustes_macro(m)

        cab2 = ctk.CTkFrame(self.principal, fg_color="transparent")
        cab2.pack(fill="x", padx=22, pady=(12, 4))
        self._texto(cab2, "PASOS", 10, True, t["tenue"]).pack(side="left")
        self._texto(cab2, "se ejecutan en orden y luego vuelven a empezar", 11, color=t["tenue"]).pack(side="left", padx=8)
        self.btn_grabar = self._boton(cab2, "Grabar acciones", self._alternar_grabacion, height=28, font=fuente(11, True))
        self.btn_grabar.pack(side="right")

        rejilla = ctk.CTkFrame(self.principal, fg_color="transparent")
        rejilla.pack(side="bottom", fill="x", padx=22, pady=(6, 14))
        rejilla.grid_columnconfigure(tuple(range(5)), weight=1, uniform="a")
        for i, (tipo, (titulo, icono, desc, _)) in enumerate(PASOS.items()):
            b = ctk.CTkButton(rejilla, text=f"{icono}", font=f_icono(12), width=30, height=30, fg_color=t["tarjeta"], hover_color=t["suave"],
                              text_color=t["acento"], corner_radius=7, anchor="w", command=lambda x=tipo: self._agregar_paso(x))
            b.configure(text=f"+  {titulo}", font=fuente(11, True), text_color=t["texto"])
            b.grid(row=i // 5, column=i % 5, sticky="ew", padx=2, pady=2)
            Aviso(b, desc, t)

        self.pasos_ui = ListaPasos(self.principal, self, m)
        self.pasos_ui.pack(fill="both", expand=True, padx=(22, 14))

    def _tarjeta_ajustes_macro(self, m):
        t = self.t
        c = ctk.CTkFrame(self.principal, fg_color=t["tarjeta"], corner_radius=10)
        c.pack(fill="x", padx=22)
        c.grid_columnconfigure((0, 1, 2), weight=1, uniform="c")

        def celda(col, fila, titulo):
            f = ctk.CTkFrame(c, fg_color="transparent")
            f.grid(row=fila, column=col, sticky="ew", padx=14, pady=(10 if fila == 0 else 2, 10 if fila else 2))
            self._texto(f, titulo, 11, color=t["tenue"], anchor="w", height=18).pack(fill="x")
            return f

        f = celda(0, 0, "Atajo global")
        fila = ctk.CTkFrame(f, fg_color="transparent")
        fila.pack(fill="x")

        def fijar_tecla(combo):
            m["tecla"] = combo
            self._aplicar_motor()
            self._guardar_pronto()
            if m["id"] in self.filas:
                self.filas[m["id"]]["tecla"].configure(text=combo or "sin atajo")
            self._revisar_conflicto(m)
        self._captura(fila, lambda: m["tecla"], fijar_tecla, vacio="Sin atajo").pack(side="left", fill="x", expand=True)
        self._boton_icono(fila, I_CLOSE, lambda: self._limpiar_tecla(fijar_tecla), "Quitar atajo", tam=9, ancho=28, alto=30).pack(side="left", padx=(4, 0))
        self.lbl_conflicto = self._texto(f, "", 10, color=AMBAR, anchor="w", height=14)

        f = celda(1, 0, "Al pulsar el atajo")
        etiquetas = {"Alternar": "alternar", "Mantener": "mantener", "Una vez": "una_vez"}
        seg = self._segmentado(f, list(etiquetas), lambda v: self._cambiar_modo(m, etiquetas[v]))
        seg.set(next(k for k, v in etiquetas.items() if v == m["modo"]))
        seg.pack(fill="x")

        f = ctk.CTkFrame(c, fg_color="transparent")
        f.grid(row=0, column=2, sticky="ew", padx=14, pady=(10, 2))
        f.grid_columnconfigure(0, weight=3, uniform="r")
        f.grid_columnconfigure(1, weight=2, uniform="r")
        self._texto(f, "Veces (0 = sin fin)", 11, color=t["tenue"], anchor="w", height=18).grid(row=0, column=0, sticky="ew")
        etiqueta = self._texto(f, "Inicia en (s)", 11, color=t["tenue"], anchor="w", height=18)
        etiqueta.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        self._num(f, m, "repeticiones", int, 0, 1000000, ancho=60).grid(row=1, column=0, sticky="ew")
        cuenta = self._num(f, m, "cuenta", int, 0, 3600, ancho=50)
        cuenta.grid(row=1, column=1, sticky="ew", padx=(8, 0))
        ayuda = "Cuenta atrás al iniciar desde la ventana (0 = al instante). Con el atajo siempre empieza al instante."
        Aviso(etiqueta, ayuda, t)
        Aviso(cuenta, ayuda, t)

        f = celda(0, 1, "Variación natural")
        self._deslizador(f, m, "variacion", 0, 50, lambda v: f"±{v:.0f}%", paso=1, tipo=int).pack(fill="x")
        f = celda(1, 1, "Velocidad de toda la macro")
        self._deslizador(f, m, "velocidad", 0.25, 4, lambda v: f"×{v:.2f}", paso=0.05).pack(fill="x")
        f = celda(2, 1, "Solo si la ventana se llama")
        e = ctk.CTkEntry(f, height=30, font=fuente(12), placeholder_text="cualquier ventana", **self._estilo_campo())
        if m["ventana"]:
            e.insert(0, m["ventana"])
        self._vincular(e, lambda v: self._fijar(m, "ventana", v))
        e.pack(fill="x")
        self._revisar_conflicto(m)

    def _estilo_campo(self):
        return dict(fg_color=self.t["panel"], border_color=self.t["borde"], border_width=1, text_color=self.t["texto"],
                    placeholder_text_color=self.t["tenue"], corner_radius=6)

    def _segmentado(self, padre, valores, comando):
        t = self.t
        # CustomTkinter usa un solo color de texto: el seleccionado va atenuado para que se lea.
        seleccion = mezclar(t["acento"], t["panel"], 0.55)
        return ctk.CTkSegmentedButton(padre, values=valores, command=comando, height=30, font=fuente(11, True),
                                      fg_color=t["panel"], selected_color=seleccion, selected_hover_color=seleccion,
                                      unselected_color=t["panel"], unselected_hover_color=t["suave"], text_color=t["texto"],
                                      text_color_disabled=t["tenue"], corner_radius=6)

    def _fijar(self, obj, clave, valor):
        obj[clave] = valor
        self._guardar_pronto()

    def _limpiar_tecla(self, fijar):
        self.cancelar_captura()
        fijar("")
        self.pintar_principal()

    def _cambiar_nombre(self, m, v):
        m["nombre"] = v[:60] or "Macro"
        if m["id"] in self.filas:
            self.filas[m["id"]]["nombre"].configure(text=m["nombre"])
        self._guardar_pronto()

    def _cambiar_modo(self, m, modo):
        self.motor.detener(m["id"])
        self._fijar(m, "modo", modo)

    def _revisar_conflicto(self, m):
        lbl = getattr(self, "lbl_conflicto", None)
        if not lbl or not lbl.winfo_exists():
            return
        tecla, msg = m["tecla"].upper(), ""
        if tecla:
            aj = self.a.ajustes
            otra = next((x["nombre"] for x in self.macros if x is not m and x["tecla"].upper() == tecla), None)
            if otra:
                msg = f"También lo usa \"{otra}\""
            elif tecla == aj["tecla_detener"].upper():
                msg = "Choca con Detener todo"
            elif tecla == aj["tecla_cerrar"].upper():
                msg = "Choca con Cerrar"
        lbl.configure(text=msg)
        if msg:
            lbl.pack(fill="x")
        else:
            lbl.pack_forget()

    # --------------------------------------------------------------- pasos
    def pintar_pasos(self):
        if self.pasos_ui:
            self.pasos_ui.reconstruir()

    def _editor_paso(self, padre, p):
        """Campos del paso abierto. Es lo unico de la lista hecho con widgets reales."""
        f = ctk.CTkFrame(padre, fg_color=self.t["tarjeta"], corner_radius=0)
        cuerpo = ctk.CTkFrame(f, fg_color="transparent")
        cuerpo.pack(fill="x", pady=(0, 6))
        getattr(self, "_campos_" + p["tipo"])(cuerpo, p)
        if p["tipo"] != "repetir":
            fila = ctk.CTkFrame(f, fg_color="transparent")
            fila.pack(fill="x")
            self._etq(fila, "Probabilidad de que ocurra (%)")
            self._num(fila, p, "prob", int, 0, 100, ancho=48).pack(side="left")
        return f

    def _etq(self, padre, texto, izq=0):
        self._texto(padre, texto, 11, color=self.t["tenue"]).pack(side="left", padx=(izq, 5))

    def _rango(self, padre, p, etiqueta="Dura entre", izq=0):
        self._etq(padre, etiqueta, izq)
        self._num(padre, p, "min", float, 0, 86400).pack(side="left")
        self._etq(padre, "y", 5)
        self._num(padre, p, "max", float, 0, 86400).pack(side="left")
        self._etq(padre, "segundos", 5)

    def _campos_click(self, f, p):
        self._etq(f, "Botón")
        Selector(self, f, entrada.BOTONES_MOUSE, p["boton"], lambda v: self._fijar(p, "boton", v), ancho=118, alto=28, fondo=self.t["panel"]).pack(side="left")
        self._etq(f, "Veces", 12)
        self._num(f, p, "veces", int, 1, 10000).pack(side="left")
        self._etq(f, "Por segundo", 12)
        self._deslizador(f, p, "cps", 0, 30, lambda v: f"{v:.1f}" if v > 0 else "sin pausa", paso=0.5).pack(side="left", fill="x", expand=True)

    def _campos_tecla(self, f, p):
        self._captura(f, lambda: p["teclas"], lambda c: self._fijar(p, "teclas", c or p["teclas"]), ancho=130).pack(side="left", padx=(0, 12))
        self._rango(f, p, "Mantener entre")
        self._etq(f, "(0 = toque)", 2)

    def _campos_aleatoria(self, f, p):
        self._etq(f, "Teclas")
        e = ctk.CTkEntry(f, width=150, height=28, font=f_tecla(11), **self._estilo_campo())
        e.insert(0, p["lista"])

        def cambiar(v):
            self._fijar(p, "lista", v)
            malas = [x for x in v.replace(",", " ").split() if not entrada.es_valida(x)]
            e.configure(border_color=ROJO if malas or not v.strip() else self.t["borde"])
        self._vincular(e, cambiar)
        e.pack(side="left", padx=(0, 12))
        self._rango(f, p)

    def _campos_espera(self, f, p):
        self._rango(f, p, "Entre")

    def _campos_estado(self, f, p):
        seg = self._segmentado(f, ["Presionar", "Soltar"], lambda v: self._fijar(p, "accion", v.lower()))
        seg.set(p["accion"].capitalize())
        seg.pack(side="left", padx=(0, 12))
        b = self._captura(f, lambda: p["objetivo"], lambda c: self._fijar(p, "objetivo", c.split("+")[-1] if c else p["objetivo"]), ancho=120)
        b.pack(side="left")

        def elegir(v):
            self._fijar(p, "objetivo", v)
            b.configure(text=v)
        Selector(self, f, entrada.BOTONES_MOUSE, "o mouse", elegir, ancho=110, alto=28, fondo=self.t["panel"]).pack(side="left", padx=(8, 0))

    def _campos_mouse(self, f, p):
        self._etq(f, "X")
        cx = self._num(f, p, "x", int, -100000, 100000, ancho=70)
        cx.pack(side="left")
        self._etq(f, "Y", 8)
        cy = self._num(f, p, "y", int, -100000, 100000, ancho=70)
        cy.pack(side="left")
        sw = ctk.CTkSwitch(f, text="Relativo a donde está", font=fuente(11), text_color=self.t["tenue"], switch_width=30, switch_height=15,
                           progress_color=self.t["acento"], fg_color=self.t["borde"], command=lambda: self._fijar(p, "relativo", not p["relativo"]))
        if p["relativo"]:
            sw.select()
        sw.pack(side="left", padx=12)

        def capturar(boton, n=3):
            if not boton.winfo_exists():
                return
            if n > 0:
                boton.configure(text=f"Apunta... {n}")
                self.root.after(1000, lambda: capturar(boton, n - 1))
                return
            x, y = entrada.posicion_mouse()
            p["x"], p["y"], p["relativo"] = x, y, False
            self._guardar_pronto()
            self.pintar_pasos()
        b = self._boton(f, "Capturar punto", None, height=28, font=fuente(11, True), width=110)
        b.configure(command=lambda: capturar(b))
        b.pack(side="left")

    def _campos_rueda(self, f, p):
        self._etq(f, "Muescas")
        self._num(f, p, "muescas", int, -100, 100).pack(side="left")
        self._etq(f, "positivo sube, negativo baja", 8)

    def _campos_texto(self, f, p):
        e = ctk.CTkEntry(f, height=28, font=fuente(12), **self._estilo_campo())
        e.insert(0, p["texto"])
        self._vincular(e, lambda v: self._fijar(p, "texto", v))
        e.pack(side="left", fill="x", expand=True)
        self._etq(f, "Letras por segundo", 12)
        self._num(f, p, "cps", float, 0, 100).pack(side="left")

    def _campos_repetir(self, f, p):
        self._etq(f, "Volver")
        self._num(f, p, "atras", int, 1, 1000).pack(side="left")
        self._etq(f, "pasos atrás y repetirlos", 5)
        self._num(f, p, "veces", int, 1, 10000).pack(side="left")
        self._etq(f, "veces más", 5)

    def _agregar_paso(self, tipo):
        self.pasos_ui.agregar(datos.nuevo_paso(tipo))
        self._guardar_pronto()

    # ----------------------------------------------------- campos genericos
    def _vincular(self, campo, fn):
        campo.bind("<KeyRelease>", lambda _: fn(campo.get()))
        campo.bind("<FocusOut>", lambda _: fn(campo.get()), add="+")
        campo.bind("<Button-1>", lambda _: campo.focus_force(), add="+")

    def _num(self, padre, obj, clave, tipo, minimo, maximo, ancho=56, alto=28):
        e = ctk.CTkEntry(padre, width=ancho, height=alto, font=fuente(12), justify="center", **self._estilo_campo())
        formato = lambda v: f"{v:g}"
        e.insert(0, formato(obj[clave]))

        def escribir(_=None):
            try:
                v = tipo(float(e.get().replace(",", ".")))
            except ValueError:
                return
            obj[clave] = max(minimo, min(maximo, v))
            self._guardar_pronto()

        def salir(_):
            escribir()
            e.delete(0, "end")
            e.insert(0, formato(obj[clave]))
        e.bind("<KeyRelease>", escribir)
        e.bind("<FocusOut>", salir, add="+")
        e.bind("<Button-1>", lambda _: e.focus_force(), add="+")
        return e

    def _deslizador(self, padre, obj, clave, desde, hasta, formato, paso=0.5, tipo=float):
        t = self.t
        f = ctk.CTkFrame(padre, fg_color="transparent")
        lbl = ctk.CTkLabel(f, text=formato(obj[clave]), font=fuente(11, True), text_color=t["texto"], width=58, anchor="e")
        lbl.pack(side="right")

        def mover(v):
            v = tipo(round(v / paso) * paso)
            obj[clave] = v
            lbl.configure(text=formato(v))
            self._guardar_pronto()
        s = ctk.CTkSlider(f, from_=desde, to=hasta, command=mover, height=16, progress_color=t["acento"], button_color=t["acento"],
                          button_hover_color=t["hover"], fg_color=t["borde"])
        s.set(obj[clave])
        s.pack(side="left", fill="x", expand=True, pady=7)
        return f

    def _captura(self, padre, obtener, fijar, vacio="Elegir", ancho=None):
        b = ctk.CTkButton(padre, text=obtener() or vacio, font=f_tecla(11), height=30, corner_radius=6, fg_color=self.t["panel"], hover_color=self.t["suave"],
                          text_color=self.t["acento"] if self.t["modo"] == "dark" else self.t["texto"], border_width=1, border_color=self.t["borde"], **({"width": ancho} if ancho else {}))

        def terminar(combo):
            self._boton_capturando = None
            if combo is not None:
                fijar(combo)
            if b.winfo_exists():
                b.configure(text=obtener() or vacio, border_color=self.t["borde"])

        def empezar():
            self.cancelar_captura()
            b.configure(text="Pulsa... (Esc cancela)" if not ancho else "Pulsa...", border_color=self.t["acento"])
            self._boton_capturando = (b, obtener() or vacio)
            self.motor.capturar(lambda combo: self.cola.put(lambda: terminar(combo)))
        b.configure(command=empezar)
        return b

    def cancelar_captura(self):
        if self._boton_capturando:
            b, texto = self._boton_capturando
            self._boton_capturando = None
            self.motor.cancelar_captura()
            if b.winfo_exists():
                b.configure(text=texto, border_color=self.t["borde"])

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
            self.aviso(f"\"{m['nombre']}\" empieza en {n}...", self.t["acento"], ms=0)
            self._cuenta_atras = self.root.after(1000, lambda: contar(n - 1))
        contar(m["cuenta"])

    # ------------------------------------------------------------ registro
    def _vista_registro(self):
        t = self.t
        m = self.macro
        aj = self.a.ajustes
        estado = f"Se guardan los últimos {aj['registro_dias']} días." if aj["registro"] else "El registro está apagado. Actívalo en Ajustes."
        self._encabezado_vista(f"Registro de {m['nombre']}", estado)

        barra = ctk.CTkFrame(self.principal, fg_color="transparent")
        barra.pack(fill="x", padx=22, pady=(0, 8))
        caja = ctk.CTkTextbox(self.principal, font=("Consolas", 11), fg_color=t["tarjeta"], text_color=t["texto"], corner_radius=10,
                              wrap="none", scrollbar_button_color=t["borde"], scrollbar_button_hover_color=t["tenue"])
        caja.pack(fill="both", expand=True, padx=22, pady=(0, 16))

        def mostrar(dia):
            lineas = self.registro.leer(m["id"], dia) if dia else []
            caja.configure(state="normal")
            caja.delete("1.0", "end")
            caja.insert("1.0", "\n".join(lineas) or "Todavía no hay nada aquí. Aparecerá cuando uses esta macro.")
            caja.configure(state="disabled")

        dias = self.registro.dias(m["id"])
        Selector(self, barra, dias or ["Sin registros"], dias[0] if dias else "Sin registros", mostrar, ancho=150).pack(side="left")
        self._boton(barra, "Actualizar", self.pintar_principal, width=86, height=30, font=fuente(11, True)).pack(side="left", padx=(8, 0))

        def borrar():
            def confirmar(_):
                self.registro.borrar(m["id"])
                self.pintar_principal()
            self.dialogo("Borrar registro", f"Se borra todo el registro de \"{m['nombre']}\".", confirmar, confirmar="Borrar", peligro=True)

        def abrir():
            os.makedirs(self.registro.ruta(m["id"]), exist_ok=True)
            os.startfile(self.registro.ruta(m["id"]))
        self._boton(barra, "Borrar", borrar, width=70, height=30, font=fuente(11, True)).pack(side="right")
        self._boton(barra, "Abrir carpeta", abrir, width=100, height=30, font=fuente(11, True)).pack(side="right", padx=(0, 8))
        mostrar(dias[0] if dias else None)

    def _al_cambiar_macro(self, macro, encendida):
        if self.a.ajustes["sonido"]:
            threading.Thread(target=winsound.Beep, args=(1046 if encendida else 660, 70), daemon=True).start()

    # ------------------------------------------------------------- grabar
    def _alternar_grabacion(self):
        if self.motor.grabando:
            self._terminar_grabacion()
            return
        self.motor.grabar()
        self.btn_grabar.configure(text="Terminar grabación", fg_color=ROJO, hover_color=ROJO, text_color="#FFFFFF")
        tecla = self.a.ajustes["tecla_detener"]
        self.aviso(f"Grabando teclas y clicks. Termina con {tecla} o aqui." if tecla else "Grabando. Termina aqui.", ROJO, ms=0)

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
    def _vista_ajustes(self):
        t = self.t
        aj = self.a.ajustes
        self._encabezado_vista("Ajustes", "Cómo se ve y cómo responde Relevo.")
        cuerpo = ctk.CTkScrollableFrame(self.principal, fg_color="transparent", corner_radius=0, scrollbar_button_color=t["borde"], scrollbar_button_hover_color=t["tenue"])
        cuerpo.pack(fill="both", expand=True, padx=(16, 8), pady=(0, 12))

        def seccion(titulo):
            self._texto(cuerpo, titulo, 10, True, t["tenue"], anchor="w").pack(fill="x", padx=8, pady=(10, 3))
            c = ctk.CTkFrame(cuerpo, fg_color=t["tarjeta"], corner_radius=10)
            c.pack(fill="x", padx=6)
            return c

        def fila(c, titulo, detalle=""):
            f = ctk.CTkFrame(c, fg_color="transparent")
            f.pack(fill="x", padx=14, pady=8)
            txt = ctk.CTkFrame(f, fg_color="transparent")
            txt.pack(side="left")
            self._texto(txt, titulo, 12, True, anchor="w", height=18).pack(anchor="w")
            if detalle:
                self._texto(txt, detalle, 11, color=t["tenue"], anchor="w", height=16).pack(anchor="w")
            return f

        c = seccion("APARIENCIA")
        f = fila(c, "Tema")
        seg = self._segmentado(f, list(TEMAS), self._cambiar_tema)
        seg.set(aj["tema"])
        seg.pack(side="right")

        f = fila(c, "Color de acento")
        otro = self._boton(f, "Otro...", self._acento_libre, height=26, width=60, font=fuente(11, True))
        otro.pack(side="right", padx=(8, 0))
        for color in reversed(ACENTOS):
            ctk.CTkButton(f, text="", width=26, height=26, corner_radius=13, fg_color=color, hover_color=color,
                          border_width=2, border_color=t["texto"] if color.upper() == aj["acento"].upper() else color,
                          command=lambda x=color: self._cambiar_acento(x)).pack(side="right", padx=2)

        f = fila(c, "Opacidad", "Para ver lo que hay detrás de la ventana")

        def opacidad(v):
            aj["opacidad"] = int(round(v))
            self.root.attributes("-alpha", aj["opacidad"] / 100)
            lbl.configure(text=f"{aj['opacidad']}%")
            self._guardar_pronto()
        lbl = self._texto(f, f"{aj['opacidad']}%", 11, True, width=40, anchor="e")
        lbl.pack(side="right")
        s = ctk.CTkSlider(f, from_=40, to=100, width=200, height=16, command=opacidad, progress_color=t["acento"], button_color=t["acento"], button_hover_color=t["hover"], fg_color=t["borde"])
        s.set(aj["opacidad"])
        s.pack(side="right", padx=6)

        self._interruptor(fila(c, "Siempre encima", "La ventana queda sobre los demás programas"), "encima", self._aplicar_ventana)
        self._interruptor(fila(c, "Sonido al encender o apagar", "Útil cuando la ventana está minimizada"), "sonido")

        c = seccion("ATAJOS GENERALES")
        for clave, titulo, detalle in (("tecla_detener", "Detener todo", "Para todas las macros y suelta todo al instante"),
                                       ("tecla_cerrar", "Cerrar Relevo", "Sale del programa desde cualquier ventana")):
            f = fila(c, titulo, detalle)

            def fijar(combo, k=clave):
                aj[k] = combo
                self._aplicar_motor()
                self._guardar_pronto()
            self._captura(f, lambda k=clave: aj[k], fijar, vacio="Sin atajo", ancho=130).pack(side="right")

        c = seccion("REGISTRO DE MACROS")
        self._interruptor(fila(c, "Guardar registro", "Cuándo empezó y terminó cada macro, y cuánto hizo"), "registro")
        f = fila(c, "Días que se conservan", "Lo más antiguo se borra al abrir Relevo o al cambiar de día")
        self._num(f, aj, "registro_dias", int, 1, 365).pack(side="right")

        c = seccion("TUS DATOS")
        f = fila(c, "Carpeta de configuración", os.path.dirname(self.a.ruta))
        self._boton(f, "Abrir", lambda: os.startfile(os.path.dirname(self.a.ruta)), width=70, height=28, font=fuente(11, True)).pack(side="right")
        f = fila(c, "Contadores", "Clicks, teclas y tiempo que Relevo hizo por ti")

        def reiniciar():
            for k in self.a.stats:
                self.a.stats[k] = 0
            self._guardar_pronto()
        self._boton(f, "Reiniciar", reiniciar, width=70, height=28, font=fuente(11, True)).pack(side="right")

        admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
        c = seccion("PERMISOS")
        f = fila(c, "Abrir como administrador" + (" (activo ahora)" if admin else ""),
                 "Solo si un programa ignora las teclas. Mientras esté al frente, Lightshot no puede capturar.")
        self._interruptor(f, "admin", lambda: self.aviso("Se aplica la próxima vez que abras Relevo"))

    def _interruptor(self, f, clave, despues=None):
        def cambiar():
            self.a.ajustes[clave] = not self.a.ajustes[clave]
            self._guardar_pronto()
            if despues:
                despues()
        sw = ctk.CTkSwitch(f, text="", width=36, switch_width=34, switch_height=17, progress_color=self.t["acento"], fg_color=self.t["borde"], command=cambiar)
        if self.a.ajustes[clave]:
            sw.select()
        sw.pack(side="right")

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
        self._vigilar_minimizado()
        self.root.after(30, self._bombear)

    def _refrescar(self):
        t = self.t
        escribiendo = False
        try:
            foco = self.root.focus_get()
            escribiendo = isinstance(foco, tk.Entry) and entrada.user32.GetForegroundWindow() == self.hwnd
        except (KeyError, tk.TclError):
            pass
        self.motor.escribiendo = escribiendo
        self.motor.rect_propio = (self.root.winfo_rootx(), self.root.winfo_rooty(),
                                  self.root.winfo_rootx() + self.root.winfo_width(), self.root.winfo_rooty() + self.root.winfo_height())

        for mid, w in self.filas.items():
            on = self.motor.corriendo(mid)
            estado = "pausa" if on and self.motor.pausada(mid) else on
            if self._estado_filas.get(mid) != estado:
                self._estado_filas[mid] = estado
                w["punto"].configure(fg_color=AMBAR if estado == "pausa" else t["acento"] if on else t["borde"])
                w["boton"].configure(text=I_STOP if on else I_PLAY, text_color=t["acento"] if on else t["tenue"])
        if self.btn_probar and self.btn_probar.winfo_exists() and self.macro:
            on = self.motor.corriendo(self.macro["id"])
            texto = "Detener" if on else "Iniciar"
            if self.btn_probar.cget("text") != texto:
                self.btn_probar.configure(text=texto, fg_color=ROJO if on else t["acento"], hover_color=ROJO if on else t["hover"],
                                          text_color="#FFFFFF" if on else t["sobre"])
        s = self.a.stats
        horas = s["segundos"] / 3600
        tiempo = f"{horas:.1f} h" if horas >= 1 else f"{s['segundos'] / 60:.0f} min"
        self.lbl_stats.configure(text=f"Te ahorraste {int(s['clicks']):,} clicks y {int(s['teclas']):,} teclas\nRelevo trabajó {tiempo} por ti".replace(",", "."))
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
