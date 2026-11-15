"""Controles dibujados en un lienzo.

Cada widget de Tk es una ventana de Windows, y Windows las repinta una por una: con cientos, abrir el
programa o cambiarle el tamaño se ve cargar por partes. Una Escena dibuja textos, botones, interruptores
y deslizadores como figuras de un solo lienzo. Solo los campos donde se escribe son widgets reales.
"""
import tkinter as tk
import weakref
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

LETRA, ICONOS, MONO = "Segoe UI", "Segoe MDL2 Assets", "Consolas"
I_CHEVRON = ""


def _aplanar(im, sobre):
    """Pega la imagen sobre su color de fondo. Tk pinta muy lento las imagenes con transparencia."""
    fondo = Image.new("RGB", im.size, sobre)
    fondo.paste(im, mask=im.split()[3])
    return fondo


class Recursos:
    """Fuentes e imagenes compartidas por todas las escenas de un tema."""

    def __init__(self, raiz):
        self.raiz, self.fuentes, self.imagenes, self.esquinas = raiz, {}, {}, {}
        self.cajas = weakref.WeakValueDictionary()  # se liberan solas cuando ninguna escena las usa

    def fuente(self, familia, px, negrita=False):
        clave = (familia, px, negrita)
        if clave not in self.fuentes:
            self.fuentes[clave] = tkfont.Font(root=self.raiz, family=familia, size=-px, weight="bold" if negrita else "normal")
        return self.fuentes[clave]

    def cortar(self, texto, ancho, fuente):
        """Recorta con puntos suspensivos lo que no cabe."""
        if fuente.measure(texto) <= ancho:
            return texto
        while texto and fuente.measure(texto + "...") > ancho:
            texto = texto[:max(int(len(texto) * 0.9), len(texto) - 8) - 1]
        return texto + "..."

    def imagen(self, clave, crear):
        if clave not in self.imagenes:
            self.imagenes[clave] = ImageTk.PhotoImage(crear(), master=self.raiz)
        return self.imagenes[clave]

    def caja(self, w, h, color, sobre, r, borde, g):
        """Imagen de un rectangulo redondeado, suavizado contra el color que tiene debajo (`sobre`).
        Una sola imagen por caja: Tk tarda segun cuantas figuras pinta, no segun su tamaño."""
        clave = (w, h, color, sobre, r, borde, g)
        foto = self.cajas.get(clave)
        if foto is None:
            im = Image.new("RGB", (w, h), color)
            if borde:
                ImageDraw.Draw(im).rectangle((0, 0, w - 1, h - 1), outline=borde, width=g)
            if r:
                for esquina, donde in zip(self._esquinas(r, color, borde, g, sobre), ((0, 0), (w - r, 0), (0, h - r), (w - r, h - r))):
                    im.paste(esquina, donde)
            foto = self.cajas[clave] = ImageTk.PhotoImage(im, master=self.raiz)
        return foto

    def _esquinas(self, r, color, borde, g, sobre):
        """Las cuatro esquinas, dibujadas en grande y reducidas: Tk dibuja las curvas con dientes."""
        clave = (r, color, borde, g, sobre)
        if clave not in self.esquinas:
            s = 4
            im = Image.new("RGBA", (2 * r * s, 2 * r * s), (0, 0, 0, 0))
            ImageDraw.Draw(im).ellipse((0, 0, 2 * r * s - 1, 2 * r * s - 1), fill=color, outline=borde, width=g * s if borde else 0)
            im = _aplanar(im.resize((2 * r, 2 * r), Image.BOX), sobre)
            self.esquinas[clave] = [im.crop(c) for c in ((0, 0, r, r), (r, 0, 2 * r, r), (0, r, r, 2 * r), (r, r, 2 * r, 2 * r))]
        return self.esquinas[clave]

    def disco(self, d, color, sobre, borde=None, g=0):
        def crear():
            s = 4
            im = Image.new("RGBA", (d * s, d * s), (0, 0, 0, 0))
            ImageDraw.Draw(im).ellipse((0, 0, d * s - 1, d * s - 1), fill=color, outline=borde, width=g * s)
            return _aplanar(im.resize((d, d), Image.BOX), sobre)
        return self.imagen(("disco", d, color, borde, g, sobre), crear)

    def interruptor(self, a, b, encendido, t, sobre):
        def crear():
            s = 4
            im = Image.new("RGBA", (a * s, b * s), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, a * s - 1, b * s - 1), radius=b * s // 2, fill=t["acento"] if encendido else t["borde"])
            m, x = 2 * s, (a - b) * s if encendido else 0
            d.ellipse((x + m, m, x + b * s - m, b * s - m), fill=t["sobre"] if encendido else t["tenue"])
            return _aplanar(im.resize((a, b), Image.BOX), sobre)
        return self.imagen(("interruptor", a, b, encendido, t["acento"], t["borde"], sobre), crear)


def caja(c, rec, x, y, w, h, color, sobre, r=10, borde=None, g=1):
    """Dibuja un rectangulo redondeado en el lienzo `c`, que debe tener un dict `imagenes`."""
    w, h = max(int(w), 1), max(int(h), 1)
    k = dict(w=w, h=h, sobre=sobre, r=max(0, min(r, w // 2, h // 2)), g=g, con_borde=bool(borde))
    k["item"] = c.create_image(int(x), int(y), anchor="nw", image=_foto(c, rec, k, color, borde))
    return k


def recolorear(c, rec, k, color, borde=None):
    c.itemconfigure(k["item"], image=_foto(c, rec, k, color, borde if k["con_borde"] else None))


def _foto(c, rec, k, color, borde):
    foto = rec.caja(k["w"], k["h"], color, k["sobre"], k["r"], borde, k["g"])
    c.imagenes[id(foto)] = foto  # Tk no la guarda: sin esta referencia se borraria de la pantalla
    return foto


class Barra(tk.Canvas):
    """Barra de desplazamiento fina y dibujada: una sola linea que se arrastra."""

    def __init__(self, padre, app, comando, fondo):
        self.e = app._escala()
        self.ancho = round(10 * self.e)
        super().__init__(padre, width=self.ancho, bg=fondo, highlightthickness=0, bd=0)
        self.comando, self.lo, self.hi, self._agarre = comando, 0.0, 1.0, 0.0
        self.pulgar = self.create_line(0, 0, 0, 0, width=round(5 * self.e), capstyle="round", fill=app.t["borde"])
        self.bind("<Configure>", lambda _: self._colocar())
        self.bind("<Enter>", lambda _: self.itemconfigure(self.pulgar, fill=app.t["tenue"]))
        self.bind("<Leave>", lambda _: self.itemconfigure(self.pulgar, fill=app.t["borde"]))
        self.bind("<ButtonPress-1>", self._presionar)
        self.bind("<B1-Motion>", self._arrastrar)

    def set(self, lo, hi):
        lo, hi = float(lo), float(hi)
        if (lo, hi) != (self.lo, self.hi):
            self.lo, self.hi = lo, hi
            self._colocar()

    def _tramo(self):
        m = self.ancho // 2
        return m, max(self.winfo_height() - 2 * m, 1)

    def _colocar(self):
        m, largo = self._tramo()
        y0 = m + self.lo * largo
        self.coords(self.pulgar, m, y0, m, max(m + self.hi * largo, y0 + 14 * self.e))

    def _presionar(self, e):
        m, largo = self._tramo()
        punto = (e.y - m) / largo
        self._agarre = punto - self.lo if self.lo <= punto <= self.hi else (self.hi - self.lo) / 2
        self._arrastrar(e)

    def _arrastrar(self, e):
        m, largo = self._tramo()
        self.comando("moveto", (e.y - m) / largo - self._agarre)


class Desplazamiento:
    """Rueda suave. Quien lo use define self.lienzo, alto_total() y, si quiere, al_desplazar()."""
    _objetivo = None
    _animando = False

    def al_desplazar(self):
        pass

    def rueda(self, delta):
        tope = max(self.alto_total() - self.lienzo.winfo_height(), 0)
        if tope == 0:
            return
        base = self._objetivo if self._animando else self.lienzo.canvasy(0)
        self._objetivo = min(max(base - delta / 120 * 90 * self.e, 0), tope)
        if not self._animando:
            self._animando = True
            self._animar()

    def _animar(self):
        if not self._animando or not self.lienzo.winfo_exists():
            self._animando = False
            return
        total = max(self.alto_total(), 1)
        actual = self.lienzo.canvasy(0)
        resta = self._objetivo - actual
        if abs(resta) < 1:
            self.lienzo.yview_moveto(self._objetivo / total)
            self._animando = False
        else:
            self.lienzo.yview_moveto((actual + resta * 0.45) / total)
            self.lienzo.after(10, self._animar)
        self.al_desplazar()


class Zona:
    """Rectangulo que responde al mouse dentro de una escena."""

    def __init__(self, x0, y0, x1, y1, **acciones):
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x1, y1
        self.clic = self.entrar = self.salir = self.presionar = self.arrastrar = self.soltar = self.doble = self.ayuda = None
        self.cursor = "hand2"
        self.__dict__.update(acciones)

    def contiene(self, x, y):
        return self.x0 <= x < self.x1 and self.y0 <= y < self.y1


class Escena(Desplazamiento, tk.Canvas):
    """Lienzo que se dibuja con una funcion: dibujar(escena, ancho, alto) -> alto del contenido.

    Se vuelve a dibujar entera al cambiar de tamaño o al llamar repintar(): son pocas figuras y tarda
    milisegundos, asi que los controles no guardan estado; leen el dato cada vez.
    """

    def __init__(self, padre, app, dibujar, fondo=None, desplazable=False, **kw):
        self.app, self.rec, self.e = app, app.rec, app._escala()
        self.fondo = fondo or app.t["fondo"]
        kw.setdefault("highlightthickness", 0)
        super().__init__(padre, bg=self.fondo, bd=0, yscrollincrement=1, **kw)
        self.lienzo = self
        self._dibujar, self.desplazable = dibujar, desplazable
        self._zonas, self._hover, self._presionada = [], None, None
        self._campos, self._vivos = {}, set()
        self.imagenes = {}
        self._pintado = None
        self.alto_contenido = 0
        self.barra = None
        if desplazable:
            self.barra = Barra(self, app, self._yview, self.fondo)
            self.configure(yscrollcommand=self.barra.set)
        else:
            self.rueda = None  # la rueda sigue subiendo hasta encontrar quien si se desplace
        self.bind("<Configure>", self._al_configurar)
        self.bind("<Motion>", self._al_mover)
        self.bind("<Leave>", lambda _: self._presionada or self._fijar_hover(None))
        self.bind("<ButtonPress-1>", self._al_presionar)
        self.bind("<B1-Motion>", self._al_arrastrar)
        self.bind("<ButtonRelease-1>", self._al_soltar)
        self.bind("<Double-Button-1>", self._al_doble)

    @property
    def t(self):
        return self.app.t

    def px(self, v):
        return round(v * self.e)

    # --------------------------------------------------------------- pintar
    def _al_configurar(self, e):
        if (e.width, e.height) != self._pintado:
            self.repintar(e.width, e.height)

    def repintar(self, ancho=None, alto=None):
        ancho = ancho or self.winfo_width()
        alto = alto or self.winfo_height()
        if ancho < 8:
            return
        self._pintado = (ancho, alto)
        anteriores, self.imagenes = self.imagenes, {}  # siguen vivas hasta acabar: casi todas se reutilizan
        # Se borra todo menos los campos: quitar y volver a poner un widget real es lo mas lento.
        self.addtag_withtag("viejo", "all")
        self.dtag("campo", "viejo")
        self.delete("viejo")
        self._zonas, self._hover, self._vivos = [], None, set()
        self.sobre = self.fondo  # color bajo lo que se dibuje; quien pinta una tarjeta lo cambia
        util = ancho - (self.px(14) if self.desplazable else 0)
        self.alto_contenido = self._dibujar(self, util, alto) or alto
        for clave in [k for k in self._campos if k not in self._vivos]:
            en = self._campos.pop(clave)
            self.delete(en.item)
            en.destroy()
        if self.desplazable:
            self.configure(scrollregion=(0, 0, ancho, max(self.alto_contenido, alto)))
            if self.alto_contenido > alto:
                self.barra.place(relx=1, x=-self.px(1), rely=0, relheight=1, anchor="ne")
            else:
                self.barra.place_forget()
        del anteriores
        self._hover_bajo_puntero()

    def alto_total(self):
        return self.alto_contenido

    def medir_alto(self, ancho):
        """Alto que necesita el contenido con ese ancho; la deja ya dibujada asi."""
        if not self._pintado or self._pintado[0] != ancho:
            self.repintar(ancho, 1)
            self._pintado = (ancho, self.alto_contenido)
        return self.alto_contenido

    def _yview(self, *args):
        self._animando = False
        self.yview(*args)

    # ---------------------------------------------------------------- mouse
    def _punto(self, e):
        return self.canvasx(e.x), self.canvasy(e.y)

    def _zona_en(self, x, y):
        for z in reversed(self._zonas):
            if z.contiene(x, y):
                return z
        return None

    def _hover_bajo_puntero(self):
        px, py = self.winfo_pointerxy()
        try:
            encima = self.winfo_containing(px, py)
        except (KeyError, tk.TclError):
            return
        if encima is self:
            self._fijar_hover(self._zona_en(self.canvasx(px - self.winfo_rootx()), self.canvasy(py - self.winfo_rooty())))

    def _fijar_hover(self, z):
        if z is self._hover:
            return
        if self._hover and self._hover.salir:
            self._hover.salir()
        self._hover = z
        if z and z.entrar:
            z.entrar()
        self.configure(cursor=z.cursor if z else "")
        self.app.ayuda(self, z)

    def _al_mover(self, e):
        if not self._presionada:
            self._fijar_hover(None if self.app.en_borde(e) else self._zona_en(*self._punto(e)))

    def _al_presionar(self, e):
        self.app.ayuda(self, None)
        if self.app.en_borde(e):
            return
        z = self._presionada = self._zona_en(*self._punto(e))
        if z and z.presionar:
            z.presionar(*self._punto(e))

    def _al_arrastrar(self, e):
        z = self._presionada
        if z and z.arrastrar:
            z.arrastrar(*self._punto(e))

    def _al_soltar(self, e):
        z, self._presionada = self._presionada, None
        if not z:
            return
        x, y = self._punto(e)
        if z.soltar:
            z.soltar(x, y)
        if z.clic and z.contiene(x, y):
            z.clic()

    def _al_doble(self, e):
        """Tk entrega el segundo click rapido como "doble" y no como otro click: sin esto se perderia."""
        z = self._zona_en(*self._punto(e))
        if z and z.doble and not self.app.en_borde(e):
            z.doble()
        else:
            self._al_presionar(e)

    def zona(self, x, y, w, h, **acciones):
        z = Zona(x, y, x + w, y + h, **acciones)
        self._zonas.append(z)
        return z

    # -------------------------------------------------------------- figuras
    def texto(self, x, y, texto, tam=12, negrita=False, color=None, ancla="w", ancho=None, familia=LETRA, envolver=None):
        px = self.px(tam)
        if ancho is not None:
            texto = self.rec.cortar(texto, ancho, self.rec.fuente(familia, px, negrita))
        return self.create_text(x, y, text=texto, anchor=ancla, fill=color or self.t["texto"], width=envolver or 0,
                                font=(familia, -px, "bold" if negrita else "normal"))

    def medir(self, texto, tam=12, negrita=False, familia=LETRA):
        return self.rec.fuente(familia, self.px(tam), negrita).measure(texto)

    def icono(self, x, y, glifo, tam=12, color=None, ancla="center"):
        return self.create_text(x, y, text=glifo, anchor=ancla, fill=color or self.t["tenue"], font=(ICONOS, -self.px(tam)))

    def caja(self, x, y, w, h, color, r=10, borde=None):
        return caja(self, self.rec, x, y, w, h, color, self.sobre, self.px(r), borde, max(self.px(1), 1))

    def tarjeta(self, x, y, w, h, color, r=10, borde=None):
        """Caja sobre la que se dibujan otros controles a continuacion."""
        k = self.caja(x, y, w, h, color, r, borde)
        self.sobre = color
        return k

    def disco(self, x, y, d, color, ancla="center", borde=None, g=0):
        return self.create_image(x, y, anchor=ancla, image=self.rec.disco(d, color, self.sobre, borde, g))

    def recolorear(self, k, color, borde=None):
        recolorear(self, self.rec, k, color, borde)

    def boton(self, x, y, w, h, texto, comando, primario=False, color=None, hover=None, color_texto=None, tam=12,
              negrita=True, icono=False, r=7, borde=None, ayuda=None, izquierda=False, familia=LETRA):
        """Boton con texto o con un icono. Sin `color` toma el del fondo y solo se nota al pasar el mouse."""
        t = self.t
        if primario:
            color, hover, color_texto = color or t["acento"], hover or t["hover"], color_texto or t["sobre"]
        hover = hover or t["suave"]
        k = self.caja(x, y, w, h, color or hover, r, borde)
        if not color:
            self.itemconfigure(k["item"], state="hidden")
        fuente = ICONOS if icono else familia
        if izquierda:
            self.create_text(x + self.px(12), y + h // 2, text=texto, anchor="w", fill=color_texto or t["texto"],
                             font=(fuente, -self.px(tam), "bold" if negrita and not icono else "normal"))
        else:
            self.create_text(x + w // 2, y + h // 2, text=texto, anchor="center", fill=color_texto or (t["tenue"] if icono else t["texto"]),
                             font=(fuente, -self.px(tam), "bold" if negrita and not icono else "normal"))
        def resaltar(encima):
            if color:
                self.recolorear(k, hover if encima else color, borde)
            else:
                self.itemconfigure(k["item"], state="normal" if encima else "hidden")
        return self.zona(x, y, w, h, clic=comando, ayuda=ayuda, entrar=lambda: resaltar(True), salir=lambda: resaltar(False))

    def interruptor(self, x, y, encendido, comando, ayuda=None):
        """(x, y) es el centro del borde derecho."""
        a, b = self.px(34), self.px(17)
        self.create_image(x - a, y, anchor="w", image=self.rec.interruptor(a, b, bool(encendido), self.t, self.sobre))
        self.zona(x - a - self.px(4), y - b, a + self.px(8), 2 * b, clic=comando, ayuda=ayuda)

    def deslizador(self, x, y, w, valor, desde, hasta, al_mover, formato=None, paso=0.5, tipo=float):
        """Linea con un boton que se arrastra; y es su centro. Con `formato` muestra el valor a la derecha."""
        t = self.t
        etiqueta = None
        if formato:
            etiqueta = self.texto(x + w, y, formato(valor), 11, True, ancla="e")
            w -= self.px(62)
        d, grosor = self.px(16), self.px(4)
        x0, x1 = x + d // 2, x + w - d // 2

        def pos(v):
            return x0 + (x1 - x0) * (min(max(v, desde), hasta) - desde) / (hasta - desde)
        self.create_line(x0, y, x1, y, fill=t["borde"], width=grosor, capstyle="round")
        avance = self.create_line(x0, y, pos(valor), y, fill=t["acento"], width=grosor, capstyle="round")
        boton = self.create_image(pos(valor), y, anchor="center", image=self.rec.disco(d, t["acento"], self.sobre))

        def mover(mx, _):
            v = desde + (hasta - desde) * min(max((mx - x0) / max(x1 - x0, 1), 0), 1)
            v = tipo(round(round(v / paso) * paso, 6))
            self.coords(avance, x0, y, pos(v), y)
            self.coords(boton, pos(v), y)
            if etiqueta:
                self.itemconfigure(etiqueta, text=formato(v))
            al_mover(v)
        self.zona(x, y - d, w, 2 * d, presionar=mover, arrastrar=mover)

    def segmentado(self, x, y, w, h, opciones, actual, comando):
        """Varias opciones en una sola barra; `opciones` es {texto visible: valor}."""
        t = self.t
        self.caja(x, y, w, h, t["panel"], 6)
        debajo, self.sobre = self.sobre, t["panel"]
        cada = w / len(opciones)
        for i, (nombre, valor) in enumerate(opciones.items()):
            cx = round(x + cada * i)
            if valor == actual:
                self.caja(cx + self.px(2), y + self.px(2), round(cada) - self.px(4), h - self.px(4), t["seleccion"], 5)
            self.texto(cx + round(cada / 2), y + h // 2, nombre, 11, True, ancla="center")
            if valor != actual:
                self.zona(cx, y, round(cada), h, clic=lambda v=valor: comando(v))
        self.sobre = debajo

    def selector(self, x, y, w, h, actual, valores, comando, extra=None, fondo=None):
        """Desplegable: muestra el valor y abre el menu de la app al pulsarlo."""
        t = self.t
        k = self.caja(x, y, w, h, fondo or t["tarjeta"], 7, t["borde"])
        self.texto(x + self.px(10), y + h // 2, actual, 12, ancho=w - self.px(36))
        self.icono(x + w - self.px(15), y + h // 2, I_CHEVRON, 9)
        self.zona(x, y, w, h, clic=lambda: self.app.abrir_menu(self, (x, y, w, h), valores, actual, comando, extra),
                  entrar=lambda: self.recolorear(k, fondo or t["tarjeta"], t["tenue"]),
                  salir=lambda: self.recolorear(k, fondo or t["tarjeta"], t["borde"]))

    # --------------------------------------------------------------- campos
    def campo(self, clave, x, y, w, h, valor, al_cambiar=None, al_salir=None, al_enter=None, centrado=False, tam=12,
              negrita=False, familia=LETRA, marcador="", fondo=None, error=False):
        """Campo de texto real. Sobrevive a los repintados: no se pierde lo que estas escribiendo."""
        t = self.t
        fondo = fondo or t["panel"]
        en = self._campos.get(clave)
        if en is None:
            en = self._campos[clave] = tk.Entry(
                self, bd=0, relief="flat", highlightthickness=0, bg=fondo, fg=t["texto"], insertbackground=t["texto"],
                selectbackground=t["acento"], selectforeground=t["sobre"], justify="center" if centrado else "left",
                font=(familia, -self.px(tam), "bold" if negrita else "normal"))
            en.marcador, en.vacio, en.item, en.sitio = marcador, False, None, None
            en.insert(0, valor)
            self._marcar(en)
            en.bind("<KeyRelease>", lambda _: en.acciones[0] and en.acciones[0](en.get()))
            en.bind("<FocusIn>", lambda _: self._foco_campo(en, True))
            en.bind("<FocusOut>", lambda _: self._foco_campo(en, False))
            en.bind("<Return>", lambda _: en.acciones[2](en.get()) if en.acciones[2] else self.app.root.focus_set())
            en.bind("<Button-1>", lambda _: en.focus_force(), add="+")
        en.acciones, en.error = (al_cambiar, al_salir, al_enter), error
        self._vivos.add(clave)
        en.caja = self.caja(x, y, w, h, fondo, 6, self._borde_campo(en))
        m = self.px(4 if centrado else 9)
        sitio = (x + m, y + h // 2, w - 2 * m, h - self.px(8))
        if en.item is None:
            en.item = self.create_window(sitio[0], sitio[1], anchor="w", window=en, width=sitio[2], height=sitio[3], tags="campo")
        elif sitio != en.sitio:
            self.coords(en.item, sitio[0], sitio[1])
            self.itemconfigure(en.item, width=sitio[2], height=sitio[3])
        en.sitio = sitio
        return en

    def _borde_campo(self, en):
        if en.error:
            return "#EF5350"
        try:
            enfocado = self.focus_get() is en
        except (KeyError, tk.TclError):
            enfocado = False
        return self.t["acento"] if enfocado else self.t["borde"]

    def _marcar(self, en):
        """Muestra el texto de ayuda de un campo vacio."""
        if en.marcador and not en.get():
            en.vacio = True
            en.insert(0, en.marcador)
            en.configure(fg=self.t["tenue"])

    def _foco_campo(self, en, entra):
        if entra and en.vacio:
            en.vacio = False
            en.delete(0, "end")
            en.configure(fg=self.t["texto"])
        if not entra:
            if en.acciones[1]:
                en.acciones[1](en.get())
            self._marcar(en)
        try:
            self.recolorear(en.caja, en.cget("bg"), self._borde_campo(en))
        except tk.TclError:
            pass  # el campo se estaba destruyendo

    def fijar_campo(self, clave, valor):
        en = self._campos.get(clave)
        if en and en.winfo_exists() and en.get() != valor:
            en.vacio = False
            en.configure(fg=self.t["texto"])
            en.delete(0, "end")
            en.insert(0, valor)
            self._marcar(en)

    def error_campo(self, clave, error):
        en = self._campos.get(clave)
        if en:
            en.error = error
            self.recolorear(en.caja, en.cget("bg"), self._borde_campo(en))

    def enfocar(self, clave):
        en = self._campos.get(clave)
        if en:
            en.focus_force()
            en.select_range(0, "end")
