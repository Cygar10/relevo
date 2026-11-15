"""Pruebas de la ventana. Abren Relevo unos segundos con una configuracion temporal y lo manejan con
clicks y teclas simulados dentro del programa: no tocan tu teclado, tu mouse ni tus macros.

Correr con:  python -m unittest pruebas_ui -v
"""
import os
import tempfile
import time
import traceback
import unittest

import customtkinter as ctk

import datos
from datos import Almacen, nueva_macro, nuevo_paso
from motor import Motor
from ui import App


class MotorSinGanchos(Motor):
    """El motor de verdad, pero sin escuchar el teclado ni el mouse de Windows."""

    def encender(self):
        pass

    def _sincronizar_mouse(self):
        pass


class Ventana(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.carpeta = tempfile.TemporaryDirectory()
        cls.a = Almacen(os.path.join(cls.carpeta.name, "config.json"))
        cls.errores = []
        cls.root = ctk.CTk()
        cls.root.report_callback_exception = lambda *e: cls.errores.append("".join(traceback.format_exception(*e)))
        cls.motor = MotorSinGanchos(cls.a.stats)
        cls.app = App(cls.root, cls.a, cls.motor)
        cls.esperar(0.5)

    @classmethod
    def tearDownClass(cls):
        cls.app.cerrar()
        cls.carpeta.cleanup()

    @classmethod
    def esperar(cls, segundos=0.15):
        fin = time.time() + segundos
        while time.time() < fin:
            cls.root.update()
            time.sleep(0.01)

    def setUp(self):
        """Cada prueba empieza con dos macros conocidas y el editor abierto."""
        self.errores.clear()
        self.motor.detener_todo()
        self.a.perfil["macros"][:] = [nueva_macro("Todos", "F1", [nuevo_paso(t) for t in datos.PASOS], cuenta=0), nueva_macro("Otra", "F2")]
        self.app.sel = self.app.macros[0]["id"]
        self.app._aplicar_motor()
        self.app.ir_a("editor")
        self.esperar()
        self.pasos = self.app.pasos_ui

    def tearDown(self):
        self.assertEqual(self.errores, [], "hubo errores dentro de la ventana")

    # ------------------------------------------------------------- ayudas
    def clic(self, lienzo, x, y):
        for evento in ("<Motion>", "<ButtonPress-1>", "<ButtonRelease-1>"):
            lienzo.event_generate(evento, x=x, y=y)
        self.esperar(0.05)

    def textos(self, lienzo):
        return [lienzo.itemcget(i, "text") for i in lienzo.find_all() if lienzo.type(i) == "text"]

    def pulsar(self, lienzo, texto):
        """Click sobre el texto dibujado que contiene `texto`."""
        for item in lienzo.find_all():
            if lienzo.type(item) == "text" and texto in lienzo.itemcget(item, "text"):
                x0, y0, x1, y1 = lienzo.bbox(item)
                return self.clic(lienzo, (x0 + x1) // 2 - int(lienzo.canvasx(0)), (y0 + y1) // 2 - int(lienzo.canvasy(0)))
        self.fail(f"no se ve {texto!r} entre {self.textos(lienzo)}")

    def escribir(self, campo, texto):
        campo.focus_force()
        campo.delete(0, "end")
        campo.insert(0, texto)
        campo.event_generate("<KeyRelease>", keysym="a")
        self.esperar()

    def widgets(self, w=None):
        w = w or self.root
        return 1 + sum(self.widgets(h) for h in w.winfo_children())

    # ------------------------------------------------------------ pruebas
    def test_abre_visible_y_con_pocos_widgets(self):
        self.assertEqual(float(self.root.attributes("-alpha")), 1.0)
        # Cada widget es una ventana que Windows repinta por separado: con cientos, la interfaz se
        # veia cargar por partes. Si esto falla, algo volvio a crear un widget por control.
        self.assertLess(self.widgets(), 40)

    def test_cada_tipo_de_paso_abre_su_editor(self):
        for i, tipo in enumerate(datos.PASOS):
            self.pasos.abrir(i)
            self.esperar(0.03)
            self.assertGreater(self.pasos.editor.alto_contenido, 30, tipo)
        self.assertLess(self.widgets(), 60)

    def test_patron_se_edita_y_avisa_de_errores(self):
        i = list(datos.PASOS).index("patron")
        paso = self.app.macro["pasos"][i]
        self.pasos.abrir(i)
        self.esperar()
        campo = self.pasos.editor._campos[("patron", id(paso))]
        self.escribir(campo, "W 2, nope 3")
        self.assertEqual(paso["patron"], "W 2, nope 3")
        self.assertTrue(campo.error)
        self.escribir(campo, "A 3, D 5")
        self.assertFalse(campo.error)
        self.pulsar(self.pasos.editor, "En orden")
        self.assertIsNotNone(self.app._menu)
        self.pulsar(self.app._menu, "Ida y vuelta")
        self.assertEqual(paso["orden"], "vaiven")
        self.assertIsNone(self.app._menu)
        self.escribir(self.pasos.editor._campos[("num", id(paso), "veces")], "3")
        self.assertEqual(paso["veces"], 3)

    def test_fila_de_paso_apagar_duplicar_borrar_y_abrir(self):
        lienzo, medio = self.pasos.lienzo, self.pasos.px(22)
        ancho, pasos = lienzo.winfo_width(), self.app.macro["pasos"]
        total = len(pasos)
        self.clic(lienzo, ancho - self.pasos.px(88), medio)
        self.assertFalse(pasos[0]["activo"])
        self.clic(lienzo, ancho - self.pasos.px(52), medio)
        self.assertEqual(len(pasos), total + 1)
        self.clic(lienzo, ancho - self.pasos.px(24), medio)
        self.assertEqual(len(pasos), total)
        self.clic(lienzo, 200, medio)
        self.assertEqual(self.pasos.abierto, 0)

    def test_agregar_paso_y_cambiar_nombre_y_modo(self):
        app = self.app
        botones = [w for w in app.principal.winfo_children() if w not in (app.cab, self.pasos)][0]
        self.pulsar(botones, "Patrón de teclas")
        self.assertEqual(app.macro["pasos"][-1]["tipo"], "patron")
        self.pulsar(app.cab, "Mantener")
        self.assertEqual(app.macro["modo"], "mantener")
        nombre = app.cab._campos[("nombre", app.macro["id"])]
        self.escribir(nombre, "Renombrada")
        nombre.event_generate("<Return>")
        self.esperar()
        self.assertEqual(app.macro["nombre"], "Renombrada")
        self.assertIn("Renombrada", self.textos(app.lista))

    def test_capturar_atajo(self):
        self.pulsar(self.app.cab, "F1")
        self.assertIsNotNone(self.motor._captura)
        for tecla, abajo in (("Ctrl", True), ("F6", True), ("F6", False)):
            self.motor._procesar(tecla, abajo, None, None)
        self.esperar(0.2)
        self.assertEqual(self.app.macro["tecla"], "Ctrl+F6")

    def test_iniciar_y_detener_con_dos_clicks_seguidos(self):
        """El segundo click llega a Tk como "doble click": no debe perderse."""
        macro = self.app.macro
        macro["pasos"][:] = [nuevo_paso("espera", min=5.0, max=5.0)]
        self.pulsar(self.app.cab, "Iniciar")
        self.esperar(0.3)
        self.assertTrue(self.motor.corriendo(macro["id"]))
        self.pulsar(self.app.cab, "Detener")
        self.esperar(0.3)
        self.assertFalse(self.motor.corriendo(macro["id"]))

    def test_todas_las_vistas_y_temas(self):
        app = self.app
        app.ir_a("plantillas")
        self.esperar()
        self.pulsar(app.principal.winfo_children()[0], "A tres segundos")
        self.assertEqual(app.macro["pasos"][0]["patron"], "A 3, D 5")
        for vista in ("ajustes", "registro", "editor"):
            app.ir_a(vista)
            self.esperar(0.1)
        for tema in ("Papel", "Grafito", "Bosque", "Noche"):
            app._cambiar_tema(tema)
            self.esperar(0.05)
        app._alternar_compacto()
        self.esperar(0.1)
        self.assertEqual(self.root.winfo_width(), app.px(300))
        app._alternar_compacto()
        self.esperar(0.1)

    def test_dialogo_crea_un_perfil(self):
        app = self.app
        app._perfil_nuevo()
        self.esperar(0.2)
        capa = [w for w in self.root.winfo_children() if w.winfo_class() == "Label"][0]
        campo = capa.winfo_children()[0]._campos["valor"]
        campo.delete(0, "end")
        campo.insert(0, "Trabajo")
        self.root.event_generate("<Return>")
        self.esperar(0.2)
        self.assertEqual(app.perfil["nombre"], "Trabajo")
        app._perfil_eliminar()
        self.esperar(0.2)
        app._dlg["aceptar"]()
        self.esperar(0.2)
        self.assertEqual(len(self.a.perfiles), 1)

    def test_cambiar_de_tamano_no_rompe_nada(self):
        ancho, alto = self.root.winfo_width(), self.root.winfo_height()
        self.pasos.abrir(3)
        for i in list(range(1, 12)) + list(range(11, -1, -1)):
            self.root.wm_geometry(f"{ancho + 12 * i}x{alto + 5 * i}")
            self.root.update()
        self.assertEqual(self.pasos.abierto, 3)


if __name__ == "__main__":
    unittest.main()
