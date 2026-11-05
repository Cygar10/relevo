"""Lista de pasos dibujada en un solo lienzo.

Con una tarjeta de widgets por paso, Windows repinta decenas de ventanas al desplazar y se ve
cortado. Aqui las filas son dibujos, asi que mil pasos se mueven igual de suave; solo el paso
abierto usa widgets reales.
"""
import copy
import tkinter as tk
from tkinter import font as tkfont

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageTk

from datos import PASOS

ALTO_FILA, SEPARACION = 44, 4


def _tiempo(a, b):
    a, b = sorted((a, b))
    return f"{a:g} s" if a == b else f"{a:g} a {b:g} s"


def resumen(p):
    """Una linea que dice que hace el paso, para no tener que abrirlo."""
    t = p["tipo"]
    if t == "click":
        texto = f"{p['boton']} · " + (f"{p['cps']:g} por segundo" if p["cps"] > 0 else "sin pausa")
        if p["veces"] > 1:
            texto += f" · {p['veces']} veces"
    elif t == "tecla":
        texto = p["teclas"] + (f" · {_tiempo(p['min'], p['max'])}" if max(p["min"], p["max"]) > 0 else "")
    elif t == "aleatoria":
        texto = f"{p['lista']} · {_tiempo(p['min'], p['max'])}"
    elif t == "espera":
        texto = _tiempo(p["min"], p["max"])
    elif t == "estado":
        texto = f"{p['accion'].capitalize()} {p['objetivo']}"
    elif t == "mouse":
        texto = f"{p['x']:+d}, {p['y']:+d} desde donde está" if p["relativo"] else f"Ir a {p['x']}, {p['y']}"
    elif t == "rueda":
        texto = f"{'Sube' if p['muescas'] >= 0 else 'Baja'} {abs(p['muescas'])}"
    elif t == "texto":
        texto = f"\"{p['texto']}\""
    else:
        texto = f"Vuelve {p['atras']} pasos atrás · {p['veces']} veces más"
    if t != "repetir" and p["prob"] < 100:
        texto += f" · {p['prob']}% de probabilidad"
    return texto


class ListaPasos(ctk.CTkFrame):
    def __init__(self, padre, app, macro):
        super().__init__(padre, fg_color="transparent", corner_radius=0)
        self.app, self.macro, self.t = app, macro, app.t
        self.e = app._escala()
        self.pasos = macro["pasos"]
        self.lienzo = tk.Canvas(self, bg=self.t["fondo"], highlightthickness=0, bd=0, yscrollincrement=1)
        self.barra = ctk.CTkScrollbar(self, command=self.lienzo.yview, fg_color="transparent", width=12,
                                      button_color=self.t["borde"], button_hover_color=self.t["tenue"])
        self.lienzo.configure(yscrollcommand=self.barra.set)
        self.lienzo.pack(side="left", fill="both", expand=True)
        self._barra_visible = False
        self.abierto = None
        self.editor = None
        self._hover = None
        self._arrastre = None
        self._filas = []
        self._imagenes = {}
        self._ancho = 0
        self._objetivo = None
        self._animando = False
        self._f_titulo = ("Segoe UI", -self.px(12), "bold")
        self._f_num = ("Segoe UI", -self.px(11), "bold")
        self._f_resumen = tkfont.Font(root=self.lienzo, family="Segoe UI", size=-self.px(11))
        self._f_icono = ("Segoe MDL2 Assets", -self.px(14))
        self._f_accion = ("Segoe MDL2 Assets", -self.px(11))
        c = self.lienzo
        c.bind("<Configure>", self._al_redimensionar)
        c.bind("<Motion>", self._al_mover)
        c.bind("<Leave>", lambda _: self._marcar_hover(None))
        c.bind("<ButtonPress-1>", self._al_presionar)
        c.bind("<B1-Motion>", self._al_arrastrar)
        c.bind("<ButtonRelease-1>", self._al_soltar)

    def px(self, v):
        return round(v * self.e)

    # ------------------------------------------------------------ imagenes
    def _rect(self, ancho, alto, color, borde=None):
        """Rectangulo redondeado suavizado: el lienzo de Tk dibuja las curvas con dientes."""
        clave = (ancho, alto, color, borde)
        if clave not in self._imagenes:
            s = 3
            im = Image.new("RGBA", (ancho * s, alto * s), (0, 0, 0, 0))
            ImageDraw.Draw(im).rounded_rectangle((0, 0, ancho * s - 1, alto * s - 1), radius=self.px(10) * s, fill=color,
                                                 outline=borde, width=(self.px(1) * s + 1) if borde else 0)
            self._imagenes[clave] = ImageTk.PhotoImage(im.resize((ancho, alto), Image.LANCZOS), master=self.lienzo)
        return self._imagenes[clave]

    def _interruptor(self, encendido):
        clave = ("sw", encendido)
        if clave not in self._imagenes:
            s, a, b = 4, self.px(30), self.px(16)
            im = Image.new("RGBA", (a * s, b * s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, a * s - 1, b * s - 1), radius=b * s // 2, fill=self.t["acento"] if encendido else self.t["borde"])
            m = 2 * s
            x = (a - b) * s if encendido else 0
            d.ellipse((x + m, m, x + b * s - m, b * s - m), fill=self.t["sobre"] if encendido else self.t["tenue"])
            self._imagenes[clave] = ImageTk.PhotoImage(im.resize((a, b), Image.LANCZOS), master=self.lienzo)
        return self._imagenes[clave]

    def _cortar(self, texto, ancho):
        if self._f_resumen.measure(texto) <= ancho:
            return texto
        while texto and self._f_resumen.measure(texto + "...") > ancho:
            texto = texto[:max(int(len(texto) * 0.9), len(texto) - 8) - 1]
        return texto + "..."

    # -------------------------------------------------------------- dibujo
    def pintar(self):
        c, t = self.lienzo, self.t
        self._animando = False  # el contenido cambio: el destino del desplazamiento ya no vale
        c.delete("all")
        self._filas = []
        self._hover = None
        ancho = c.winfo_width()
        if ancho < 20:
            return
        alto_fila, sep = self.px(ALTO_FILA), self.px(SEPARACION)
        arrastrando = self._arrastre["i"] if self._arrastre and self._arrastre["activo"] else None
        der_borrar, der_copiar, der_switch = ancho - self.px(24), ancho - self.px(52), ancho - self.px(88)
        x_resumen, fin_resumen = self.px(210), der_switch - self.px(26)
        y = 0
        for i, p in enumerate(self.pasos):
            extra = 0
            if i == self.abierto and self.editor:
                self.editor.update_idletasks()
                extra = self.editor.winfo_reqheight() + self.px(10)
            alto = alto_fila + extra
            borde = t["acento"] if i == arrastrando or i == self.abierto else None
            fondo = c.create_image(0, y, anchor="nw", image=self._rect(ancho, alto, t["tarjeta"], borde))
            medio = y + alto_fila // 2
            activo = p.get("activo", True)
            color = t["texto"] if activo else t["tenue"]
            titulo, icono = PASOS[p["tipo"]][0], PASOS[p["tipo"]][1]
            c.create_text(self.px(14), medio, anchor="w", text=f"{i + 1:02d}", font=self._f_num, fill=t["tenue"])
            c.create_text(self.px(42), medio, anchor="w", text=icono, font=self._f_icono, fill=t["acento"] if activo else t["tenue"])
            c.create_text(self.px(68), medio, anchor="w", text=titulo, font=self._f_titulo, fill=color)
            res = c.create_text(x_resumen, medio, anchor="w", text=self._cortar(resumen(p), fin_resumen - x_resumen),
                                font=self._f_resumen, fill=t["tenue"])
            c.create_image(der_switch, medio, anchor="center", image=self._interruptor(activo))
            c.create_text(der_copiar, medio, anchor="center", text="", font=self._f_accion, fill=t["tenue"])
            c.create_text(der_borrar, medio, anchor="center", text="", font=self._f_accion, fill=t["tenue"])
            if extra:
                c.create_window(self.px(14), y + alto_fila, anchor="nw", window=self.editor, width=ancho - self.px(28))
            self._filas.append(dict(y=y, fin=y + alto, fondo=fondo, resumen=res, ancho=ancho, alto=alto, borde=borde))
            y += alto + sep
        if not self.pasos:
            c.create_text(ancho // 2, self.px(60), text="Sin pasos todavía. Agrega uno abajo o pulsa Grabar acciones.",
                          font=self._f_resumen, fill=t["tenue"])
        c.configure(scrollregion=(0, 0, ancho, max(y - sep, 1)))
        self._ajustar_barra(y - sep)

    def _ajustar_barra(self, total):
        hace_falta = total > self.lienzo.winfo_height()
        if hace_falta != self._barra_visible:
            self._barra_visible = hace_falta
            if hace_falta:
                self.barra.pack(side="right", fill="y", padx=(4, 0), before=self.lienzo)
            else:
                self.barra.pack_forget()

    def _al_redimensionar(self, e):
        if e.width != self._ancho:
            self._ancho = e.width
            self.pintar()
        else:
            self._ajustar_barra(self._filas[-1]["fin"] if self._filas else 0)

    # ------------------------------------------------------------- acciones
    def _cerrar_editor(self):
        if self.editor:
            self.editor.destroy()
        self.editor = None
        self.abierto = None

    def abrir(self, i):
        self._cerrar_editor()
        self.abierto = i
        self.editor = self.app._editor_paso(self.lienzo, self.pasos[i])
        self.pintar()
        self._mostrar_fila(i)

    def reconstruir(self):
        """Los datos del paso abierto cambiaron por fuera del editor."""
        if self.abierto is not None and self.abierto < len(self.pasos):
            self.abrir(self.abierto)
        else:
            self.pintar()

    def agregar(self, tipo_paso):
        self.pasos.append(tipo_paso)
        self.abrir(len(self.pasos) - 1)

    def actualizar_resumen(self):
        i = self.abierto
        if i is None or i >= len(self._filas):
            return
        ancho = self.lienzo.winfo_width() - self.px(88) - self.px(26) - self.px(210)
        self.lienzo.itemconfigure(self._filas[i]["resumen"], text=self._cortar(resumen(self.pasos[i]), ancho))

    def _borrar(self, i):
        del self.pasos[i]
        if self.abierto == i:
            self._cerrar_editor()
        elif self.abierto is not None and self.abierto > i:
            self.abierto -= 1
        self.app._guardar_pronto()
        self.pintar()

    def _duplicar(self, i):
        self.pasos.insert(i + 1, copy.deepcopy(self.pasos[i]))
        if self.abierto is not None and self.abierto > i:
            self.abierto += 1
        self.app._guardar_pronto()
        self.pintar()

    def _alternar(self, i):
        self.pasos[i]["activo"] = not self.pasos[i].get("activo", True)
        self.app._guardar_pronto()
        self.pintar()

    # --------------------------------------------------------------- raton
    def _fila_en(self, y):
        for i, f in enumerate(self._filas):
            if f["y"] <= y < f["fin"]:
                return i
        return None

    def _marcar_hover(self, i):
        if i == self._hover:
            return
        for j, color in ((self._hover, self.t["tarjeta"]), (i, self.t["suave"])):
            if j is not None and j < len(self._filas) and j != self.abierto:
                f = self._filas[j]
                self.lienzo.itemconfigure(f["fondo"], image=self._rect(f["ancho"], f["alto"], color, f["borde"]))
        self._hover = i

    def _al_mover(self, e):
        i = self._fila_en(self.lienzo.canvasy(e.y))
        self._marcar_hover(i)
        self.lienzo.configure(cursor="hand2" if i is not None else "")

    def _al_presionar(self, e):
        i = self._fila_en(self.lienzo.canvasy(e.y))
        self._arrastre = dict(i=i, y0=e.y_root, activo=False) if i is not None else None

    def _al_arrastrar(self, e):
        a = self._arrastre
        if not a:
            return
        if not a["activo"]:
            if abs(e.y_root - a["y0"]) < self.px(6):
                return
            a["activo"] = True
            self._cerrar_editor()
            self.lienzo.configure(cursor="fleur")
            self.pintar()
        if e.y < self.px(28):
            self.lienzo.yview_scroll(-self.px(10), "units")
        elif e.y > self.lienzo.winfo_height() - self.px(28):
            self.lienzo.yview_scroll(self.px(10), "units")
        paso = self.px(ALTO_FILA) + self.px(SEPARACION)
        destino = min(max(int(self.lienzo.canvasy(e.y) // paso), 0), len(self.pasos) - 1)
        if destino != a["i"]:
            self.pasos.insert(destino, self.pasos.pop(a["i"]))
            a["i"] = destino
            self.pintar()

    def _al_soltar(self, e):
        a, self._arrastre = self._arrastre, None
        if not a:
            return
        if a["activo"]:
            self.lienzo.configure(cursor="hand2")
            self.app._guardar_pronto()
            self.pintar()
            return
        i = a["i"]
        y = self.lienzo.canvasy(e.y)
        if self._fila_en(y) != i or y >= self._filas[i]["y"] + self.px(ALTO_FILA):
            return
        desde_der = self.lienzo.winfo_width() - e.x
        if desde_der < self.px(38):
            self._borrar(i)
        elif desde_der < self.px(66):
            self._duplicar(i)
        elif desde_der < self.px(108):
            self._alternar(i)
        elif self.abierto == i:
            self._cerrar_editor()
            self.pintar()
        else:
            self.abrir(i)

    # ------------------------------------------------------------ desplazar
    def _mostrar_fila(self, i):
        self.update_idletasks()
        if i >= len(self._filas):
            return
        f = self._filas[i]
        total = max(self._filas[-1]["fin"], 1)
        arriba, alto = self.lienzo.canvasy(0), self.lienzo.winfo_height()
        if f["y"] < arriba:
            self.lienzo.yview_moveto(f["y"] / total)
        elif f["fin"] > arriba + alto:
            self.lienzo.yview_moveto(max(f["fin"] - alto, 0) / total)

    def rueda(self, delta):
        if not self._filas:
            return
        total = max(self._filas[-1]["fin"], 1)
        tope = max(total - self.lienzo.winfo_height(), 0)
        if tope == 0:
            return
        base = self._objetivo if self._animando else self.lienzo.canvasy(0)
        self._objetivo = min(max(base - delta / 120 * self.px(90), 0), tope)
        if not self._animando:
            self._animando = True
            self._animar()

    def _animar(self):
        if not self._animando or not self.lienzo.winfo_exists():
            self._animando = False
            return
        total = max(self._filas[-1]["fin"], 1) if self._filas else 1
        actual = self.lienzo.canvasy(0)
        resta = self._objetivo - actual
        if abs(resta) < 1:
            self.lienzo.yview_moveto(self._objetivo / total)
            self._animando = False
            return
        self.lienzo.yview_moveto((actual + resta * 0.45) / total)
        self.after(10, self._animar)
