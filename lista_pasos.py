"""Lista de pasos dibujada en un solo lienzo.

Las filas son dibujos y solo se dibujan las que se ven (y un poco mas), asi que mil pasos se mueven
igual de suave que diez. El unico widget real es el editor del paso abierto.
"""
import copy
import tkinter as tk

import patron
from datos import PASOS
from lienzo import ICONOS, LETRA, Barra, Desplazamiento, caja, recolorear

ALTO_FILA, SEPARACION = 44, 4
I_COPIAR, I_BORRAR = "", ""


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
        texto = p["teclas"] + (f" · mantener {_tiempo(p['min'], p['max'])}" if max(p["min"], p["max"]) > 0 else " · un toque")
    elif t == "aleatoria":
        texto = f"{p['lista']} · {_tiempo(p['min'], p['max'])}"
    elif t == "patron":
        texto = patron.describir(p["patron"]) or "Escribe las teclas"
        if p["orden"] != "seguido":
            texto += f" · {patron.ORDENES[p['orden']].lower()}"
        if p["veces"] > 1:
            texto += f" · {p['veces']} veces"
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


class ListaPasos(Desplazamiento, tk.Frame):
    def __init__(self, padre, app, macro):
        super().__init__(padre, bg=app.t["fondo"])
        self.app, self.macro, self.t, self.rec = app, macro, app.t, app.rec
        self.e = app._escala()
        self.pasos = macro["pasos"]
        self.lienzo = tk.Canvas(self, bg=self.t["fondo"], highlightthickness=0, bd=0, yscrollincrement=1)
        self.lienzo.imagenes = {}
        self.barra = Barra(self, app, self._yview, self.t["fondo"])
        self.lienzo.configure(yscrollcommand=self.barra.set)
        self.lienzo.pack(side="left", fill="both", expand=True)
        self._barra_visible = False
        self.abierto = None
        self.editor = None
        self._hover = None
        self._arrastre = None
        self._filas = []       # posicion de todas las filas
        self._dibujadas = {}   # figuras de las filas que se ven
        self._tramo = (0, 0)   # franja del lienzo que esta dibujada
        self._ancho = 0
        self._f_titulo = (LETRA, -self.px(12), "bold")
        self._f_num = (LETRA, -self.px(11), "bold")
        self._f_resumen = self.rec.fuente(LETRA, self.px(11))
        self._f_icono = (ICONOS, -self.px(14))
        self._f_accion = (ICONOS, -self.px(11))
        c = self.lienzo
        c.bind("<Configure>", self._al_redimensionar)
        c.bind("<Motion>", self._al_mover)
        c.bind("<Leave>", lambda _: self._marcar_hover(None))
        c.bind("<ButtonPress-1>", self._al_presionar)
        c.bind("<B1-Motion>", self._al_arrastrar)
        c.bind("<ButtonRelease-1>", self._al_soltar)

    def px(self, v):
        return round(v * self.e)

    # -------------------------------------------------------------- dibujo
    def pintar(self):
        """El contenido cambio: recalcula donde va cada fila y dibuja las que se ven."""
        self._animando = False  # el destino del desplazamiento ya no vale
        ancho = self.lienzo.winfo_width()
        self._filas = []
        if ancho < 20:
            return
        alto_fila, sep = self.px(ALTO_FILA), self.px(SEPARACION)
        y = 0
        for i in range(len(self.pasos)):
            alto = alto_fila
            if i == self.abierto and self.editor:
                alto += self.editor.medir_alto(ancho - self.px(28)) + self.px(10)
            self._filas.append(dict(y=y, fin=y + alto))
            y += alto + sep
        self.lienzo.configure(scrollregion=(0, 0, ancho, max(y - sep, 1)))
        self._ajustar_barra()
        self._dibujar_visibles()

    def alto_total(self):
        return max(self._filas[-1]["fin"], 1) if self._filas else 1

    def _dibujar_visibles(self):
        c, t = self.lienzo, self.t
        anteriores, c.imagenes = c.imagenes, {}  # vivas hasta acabar: casi todas se reutilizan
        c.delete("all")
        self._dibujadas, self._hover = {}, None
        ancho, alto_vista = c.winfo_width(), c.winfo_height()
        arriba = c.canvasy(0)
        self._tramo = (arriba - alto_vista // 2, arriba + alto_vista + alto_vista // 2)
        if not self.pasos:
            c.create_text(ancho // 2, self.px(60), text="Sin pasos todavía. Agrega uno abajo o pulsa Grabar acciones.",
                          font=self._f_resumen, fill=t["tenue"])
            return
        alto_fila = self.px(ALTO_FILA)
        arrastrando = self._arrastre["i"] if self._arrastre and self._arrastre["activo"] else None
        der_borrar, der_copiar, der_switch = ancho - self.px(24), ancho - self.px(52), ancho - self.px(88)
        x_resumen, fin_resumen = self.px(210), der_switch - self.px(26)
        a, b = self.px(30), self.px(16)
        for i, f in enumerate(self._filas):
            if f["fin"] < self._tramo[0] or f["y"] > self._tramo[1]:
                continue
            p, y = self.pasos[i], f["y"]
            borde = t["acento"] if i == arrastrando or i == self.abierto else None
            fondo = caja(c, self.rec, 0, y, ancho, f["fin"] - y, t["tarjeta"], t["fondo"], self.px(10), borde, max(self.px(1), 1))
            medio = y + alto_fila // 2
            activo = p.get("activo", True)
            titulo, icono = PASOS[p["tipo"]][0], PASOS[p["tipo"]][1]
            c.create_text(self.px(14), medio, anchor="w", text=f"{i + 1:02d}", font=self._f_num, fill=t["tenue"])
            c.create_text(self.px(42), medio, anchor="w", text=icono, font=self._f_icono, fill=t["acento"] if activo else t["tenue"])
            c.create_text(self.px(68), medio, anchor="w", text=titulo, font=self._f_titulo, fill=t["texto"] if activo else t["tenue"])
            res = c.create_text(x_resumen, medio, anchor="w", font=self._f_resumen, fill=t["tenue"],
                                text=self.rec.cortar(resumen(p), fin_resumen - x_resumen, self._f_resumen))
            boton = c.create_image(der_switch, medio, anchor="center", image=self.rec.interruptor(a, b, activo, t, t["tarjeta"]))
            c.create_text(der_copiar, medio, anchor="center", text=I_COPIAR, font=self._f_accion, fill=t["tenue"])
            c.create_text(der_borrar, medio, anchor="center", text=I_BORRAR, font=self._f_accion, fill=t["tenue"])
            if i == self.abierto and self.editor:
                c.create_window(self.px(14), y + alto_fila, anchor="nw", window=self.editor, width=ancho - self.px(28),
                                height=f["fin"] - y - alto_fila - self.px(10))
            self._dibujadas[i] = dict(fondo=fondo, resumen=res, borde=borde, boton=boton, activo=activo)
        del anteriores

    def al_desplazar(self):
        """Al moverse la vista, dibuja mas filas antes de que se acaben las ya dibujadas."""
        arriba = self.lienzo.canvasy(0)
        abajo = arriba + self.lienzo.winfo_height()
        if (arriba < self._tramo[0] and self._tramo[0] > 0) or (abajo > self._tramo[1] and self._tramo[1] < self.alto_total()):
            self._dibujar_visibles()

    def _yview(self, *args):
        self._animando = False
        self.lienzo.yview(*args)
        self.al_desplazar()

    def _ajustar_barra(self):
        hace_falta = self.alto_total() > self.lienzo.winfo_height()
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
            self._ajustar_barra()
            self._dibujar_visibles()

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
        d = self._dibujadas.get(self.abierto)
        if d:
            ancho = self.lienzo.winfo_width() - self.px(88) - self.px(26) - self.px(210)
            self.lienzo.itemconfigure(d["resumen"], text=self.rec.cortar(resumen(self.pasos[self.abierto]), ancho, self._f_resumen))

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
        self._dibujar_visibles()

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
            d = self._dibujadas.get(j)
            if d and j != self.abierto:
                recolorear(self.lienzo, self.rec, d["fondo"], color, d["borde"])
                self.lienzo.itemconfigure(d["boton"], image=self.rec.interruptor(self.px(30), self.px(16), d["activo"], self.t, color))
        self._hover = i

    def _al_mover(self, e):
        if self.app.en_borde(e):
            return
        i = self._fila_en(self.lienzo.canvasy(e.y))
        self._marcar_hover(i)
        self.lienzo.configure(cursor="hand2" if i is not None else "")

    def _al_presionar(self, e):
        i = None if self.app.en_borde(e) else self._fila_en(self.lienzo.canvasy(e.y))
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
            self._dibujar_visibles()
        else:
            self.al_desplazar()

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

    def _mostrar_fila(self, i):
        self.update_idletasks()
        if i >= len(self._filas):
            return
        f = self._filas[i]
        total = self.alto_total()
        arriba, alto = self.lienzo.canvasy(0), self.lienzo.winfo_height()
        if f["y"] < arriba:
            self.lienzo.yview_moveto(f["y"] / total)
        elif f["fin"] > arriba + alto:
            self.lienzo.yview_moveto(max(f["fin"] - alto, 0) / total)
        self.al_desplazar()
