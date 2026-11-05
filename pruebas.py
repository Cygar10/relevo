"""Pruebas del motor. No tocan tu teclado ni tu mouse: usan una salida falsa.

Correr con:  python -m unittest pruebas -v
"""
import datetime
import json
import os
import tempfile
import threading
import time
import unittest

import datos
import entrada
from datos import nueva_macro, nuevo_paso
from motor import Ejecutor, Motor, eventos_a_pasos
from registro import Registro


class Falsa:
    def __init__(self):
        self.eventos = []

    def presionar(self, t):
        self.eventos.append(("abajo", t, time.perf_counter()))

    def soltar(self, t):
        self.eventos.append(("arriba", t, time.perf_counter()))

    def mover(self, x, y, rel=False):
        self.eventos.append(("mover", (x, y, rel), time.perf_counter()))

    def rueda(self, n):
        self.eventos.append(("rueda", n, time.perf_counter()))

    def escribir_caracter(self, c):
        self.eventos.append(("char", c, time.perf_counter()))

    def nombres(self, tipo="abajo"):
        return [e[1] for e in self.eventos if e[0] == tipo]


def stats():
    return {"clicks": 0, "teclas": 0, "segundos": 0.0}


def correr(macro, seg=None):
    f, s = Falsa(), stats()
    e = Ejecutor(macro, s, salida=f)
    e.start()
    e.join(seg)
    if e.is_alive():
        e.parar.set()
        e.join(2)
    return f, s


class Ejecucion(unittest.TestCase):
    def test_autoclick_a_4_5_cps(self):
        f, s = correr(nueva_macro(pasos=[nuevo_paso("click", cps=4.5)], variacion=10), 3)
        self.assertAlmostEqual(s["clicks"] / 3, 4.5, delta=0.6)
        self.assertEqual(f.nombres("abajo").count("Mouse Izq"), f.nombres("arriba").count("Mouse Izq"))

    def test_variacion_no_es_robotica(self):
        f, _ = correr(nueva_macro(pasos=[nuevo_paso("click", cps=10)], variacion=20), 2)
        t = [e[2] for e in f.eventos if e[0] == "abajo"]
        difs = [b - a for a, b in zip(t, t[1:])]
        self.assertGreater(max(difs) - min(difs), 0.01)

    def test_apagar_suelta_la_tecla_al_instante(self):
        m = nueva_macro(pasos=[nuevo_paso("aleatoria", lista="W", min=30.0, max=30.0)], variacion=0)
        f, s = Falsa(), stats()
        e = Ejecutor(m, s, salida=f)
        e.start()
        time.sleep(0.2)
        self.assertEqual(f.nombres("abajo"), ["W"])
        inicio = time.perf_counter()
        e.parar.set()
        e.join(1)
        self.assertLess(time.perf_counter() - inicio, 0.15)
        self.assertEqual(f.nombres("arriba"), ["W"])

    def test_mantener_se_suelta_al_terminar(self):
        f, _ = correr(nueva_macro(pasos=[nuevo_paso("estado", accion="presionar", objetivo="Mouse Izq")], repeticiones=1, modo="una_vez"), 2)
        self.assertEqual(f.nombres("arriba"), ["Mouse Izq"])

    def test_repetir_y_repeticiones(self):
        m = nueva_macro(modo="una_vez", repeticiones=2, variacion=0, pasos=[
            nuevo_paso("tecla", teclas="A"), nuevo_paso("repetir", atras=1, veces=2), nuevo_paso("tecla", teclas="B")])
        f, _ = correr(m, 5)
        self.assertEqual(f.nombres(), ["A", "A", "A", "B"] * 2)

    def test_repetir_anidado(self):
        m = nueva_macro(modo="una_vez", variacion=0, pasos=[
            nuevo_paso("tecla", teclas="A"), nuevo_paso("repetir", atras=1, veces=1),
            nuevo_paso("tecla", teclas="B"), nuevo_paso("repetir", atras=3, veces=1)])
        f, _ = correr(m, 5)
        self.assertEqual(f.nombres(), ["A", "A", "B", "A", "A", "B"])

    def test_combo_baja_y_sube_en_orden(self):
        f, _ = correr(nueva_macro(modo="una_vez", pasos=[nuevo_paso("tecla", teclas="Ctrl+C")]), 2)
        self.assertEqual(f.nombres("abajo"), ["Ctrl", "C"])
        self.assertEqual(f.nombres("arriba"), ["C", "Ctrl"])

    def test_probabilidad_cero_y_desactivado(self):
        m = nueva_macro(modo="una_vez", pasos=[nuevo_paso("tecla", teclas="A", prob=0), nuevo_paso("tecla", teclas="B", activo=False), nuevo_paso("tecla", teclas="C")])
        f, _ = correr(m, 2)
        self.assertEqual(f.nombres(), ["C"])

    def test_teclas_invalidas_no_rompen(self):
        m = nueva_macro(modo="una_vez", pasos=[nuevo_paso("aleatoria", lista="@@@ nope", min=0.0, max=0.0), nuevo_paso("tecla", teclas="nada+tampoco"), nuevo_paso("tecla", teclas="C")])
        f, _ = correr(m, 2)
        self.assertEqual(f.nombres(), ["C"])

    def test_otros_pasos(self):
        m = nueva_macro(modo="una_vez", variacion=0, pasos=[
            nuevo_paso("mouse", x=5, y=6, relativo=True), nuevo_paso("rueda", muescas=-2), nuevo_paso("texto", texto="ñé", cps=0.0)])
        f, s = correr(m, 2)
        self.assertEqual(f.nombres("mover"), [(5, 6, True)])
        self.assertEqual(f.nombres("rueda"), [-2])
        self.assertEqual(f.nombres("char"), ["ñ", "é"])

    def test_macro_vacia_termina(self):
        _, s = correr(nueva_macro(), 1)
        self.assertLess(s["segundos"], 0.5)

    def test_velocidad_cambia_en_vivo(self):
        m = nueva_macro(pasos=[nuevo_paso("click", cps=2)], variacion=0)
        f, s = Falsa(), stats()
        e = Ejecutor(m, s, salida=f)
        e.start()
        time.sleep(1)
        antes = s["clicks"]
        m["pasos"][0]["cps"] = 20
        time.sleep(1)
        e.parar.set()
        e.join(1)
        self.assertGreater(s["clicks"] - antes, antes * 3)


class Atajos(unittest.TestCase):
    def setUp(self):
        self.f = Falsa()
        self.m = Motor(stats(), salida=self.f)
        self.click = nueva_macro("c", "F1", [nuevo_paso("click", cps=20)])
        self.mov = nueva_macro("m", "F8", [nuevo_paso("aleatoria", lista="W", min=30.0, max=30.0)], variacion=0)
        self.m.configurar([self.click, self.mov], "F10", "F9")

    def tearDown(self):
        self.m.detener_todo()
        time.sleep(0.1)

    def tecla(self, n, abajo=True):
        self.m._procesar(n, abajo, None, None)

    def test_f1_funciona_con_wasd_presionadas(self):
        """El motivo por el que el original evitaba add_hotkey."""
        self.tecla("W")
        self.tecla("A")
        self.tecla("F1")
        self.assertTrue(self.m.corriendo(self.click["id"]))
        self.tecla("F1", False)
        self.tecla("F1")
        time.sleep(0.15)
        self.assertFalse(self.m.corriendo(self.click["id"]))

    def test_autorepeticion_no_alterna(self):
        self.tecla("F1")
        for _ in range(5):
            self.tecla("F1")
        self.assertTrue(self.m.corriendo(self.click["id"]))

    def test_gana_el_atajo_mas_especifico(self):
        otra = nueva_macro("o", "Ctrl+F1", [nuevo_paso("click", cps=20)])
        self.m.configurar([self.click, otra], "F10", "F9")
        self.tecla("Ctrl")
        self.tecla("F1")
        self.assertTrue(self.m.corriendo(otra["id"]))
        self.assertFalse(self.m.corriendo(self.click["id"]))

    def test_modo_mantener(self):
        self.click["modo"] = "mantener"
        self.tecla("F1")
        self.assertTrue(self.m.corriendo(self.click["id"]))
        self.tecla("F1", False)
        time.sleep(0.15)
        self.assertFalse(self.m.corriendo(self.click["id"]))

    def test_detener_todo_suelta_todo(self):
        self.tecla("F8")
        time.sleep(0.1)
        self.tecla("F10")
        time.sleep(0.15)
        self.assertFalse(self.m.corriendo(self.mov["id"]))
        self.assertEqual(self.f.nombres("arriba"), ["W"])

    def test_cerrar(self):
        cerrado = threading.Event()
        self.m.al_cerrar = cerrado.set
        self.tecla("F9")
        self.assertTrue(cerrado.is_set())

    def test_no_dispara_si_escribes_en_un_campo(self):
        self.m.escribiendo = True
        self.tecla("F1")
        self.assertFalse(self.m.corriendo(self.click["id"]))

    def test_captura_de_combo(self):
        res = []
        self.m._captura = {"fn": res.append, "combo": []}
        self.tecla("F2")
        self.tecla("Ctrl")
        self.tecla("Ctrl", False)
        self.assertEqual(res, ["Ctrl+F2"])
        self.assertFalse(self.m.corriendo(self.click["id"]))

    def test_captura_ignora_macros_y_esc_cancela(self):
        res = []
        self.m._captura = {"fn": res.append, "combo": []}
        self.tecla("Esc")
        self.assertEqual(res, [None])


class Grabar(unittest.TestCase):
    def test_conversion(self):
        ev = [(0.0, "W", True, None, None), (0.5, "W", False, None, None),
              (1.0, "Mouse Izq", True, 10, 20), (1.05, "Mouse Izq", False, 10, 20),
              (1.2, "Ctrl", True, None, None), (1.3, "C", True, None, None), (1.4, "C", False, None, None), (1.5, "Ctrl", False, None, None)]
        tipos = [p["tipo"] for p in eventos_a_pasos(ev)]
        self.assertEqual(tipos, ["tecla", "espera", "mouse", "click", "espera", "estado", "espera", "tecla", "espera", "estado"])
        pasos = eventos_a_pasos(ev)
        self.assertEqual(pasos[0]["min"], 0.5)
        self.assertEqual(pasos[3]["cps"], 0.0)

    def test_pasos_grabados_son_validos(self):
        ev = [(0.0, "Mouse 4", True, 1, 2), (1.0, "Mouse 4", False, 1, 2), (1.5, "A", False, None, None)]
        for p in eventos_a_pasos(ev):
            self.assertEqual(datos.normalizar_paso(p), p)


class Datos(unittest.TestCase):
    def test_primer_arranque_trae_un_perfil_generico(self):
        with tempfile.TemporaryDirectory() as d:
            a = datos.Almacen(os.path.join(d, "x", "c.json"))
            self.assertEqual(a.perfil["nombre"], "Mi perfil")
            self.assertFalse(a.ajustes["encima"])
            m = {x["tecla"]: x for x in a.perfil["macros"]}
            self.assertEqual(m["F1"]["pasos"][0]["cps"], 4.5)
            self.assertEqual(m["F1"]["variacion"], 10)
            self.assertEqual(list(m), ["F1"])
            self.assertEqual(a.ajustes["tecla_cerrar"], "F9")
            a.guardar()
            b = datos.Almacen(a.ruta)
            self.assertEqual(b.perfiles, a.perfiles)

    def test_archivo_danado_se_conserva(self):
        with tempfile.TemporaryDirectory() as d:
            r = os.path.join(d, "c.json")
            with open(r, "w") as f:
                f.write("{roto")
            a = datos.Almacen(r)
            self.assertTrue(a.perfiles)
            self.assertTrue(os.path.exists(r + ".danado"))

    def test_importar_valores_absurdos(self):
        with tempfile.TemporaryDirectory() as d:
            r = os.path.join(d, "p.json")
            with open(r, "w") as f:
                json.dump({"perfil": {"nombre": "x", "macros": [
                    {"nombre": "m", "modo": "raro", "variacion": 9999, "velocidad": -1, "pasos": [
                        {"tipo": "click", "cps": "mucho", "veces": -5}, {"tipo": "virus"}, "basura",
                        {"tipo": "repetir", "atras": 0, "veces": 0}]}, 7]}}, f)
            p = datos.importar(r)
            m = p["macros"][0]
            self.assertEqual((m["modo"], m["variacion"], m["velocidad"]), ("alternar", 50, 0.1))
            self.assertEqual([x["tipo"] for x in m["pasos"]], ["click", "repetir"])
            self.assertEqual(m["pasos"][0]["veces"], 1)
            self.assertEqual(m["pasos"][1]["atras"], 1)

    def test_cuenta_atras(self):
        self.assertEqual(nueva_macro()["cuenta"], 3)
        self.assertEqual(datos.normalizar_macro({"nombre": "vieja"})["cuenta"], 3)
        self.assertEqual(datos.normalizar_macro({"cuenta": 0})["cuenta"], 0)
        self.assertEqual(datos.normalizar_macro({"cuenta": -5})["cuenta"], 0)
        self.assertEqual(datos.normalizar_macro({"cuenta": "x"})["cuenta"], 3)

    def test_import_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            r = os.path.join(d, "p.json")
            with open(r, "w") as f:
                f.write("[1,2]")
            with self.assertRaises(ValueError):
                datos.importar(r)


class Logs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ajustes = {"registro": True, "registro_dias": 7}
        self.r = Registro(self.ajustes, self.tmp.name)

    def archivo_viejo(self, mid, dias):
        dia = datetime.date.today() - datetime.timedelta(days=dias)
        os.makedirs(os.path.join(self.tmp.name, mid), exist_ok=True)
        with open(os.path.join(self.tmp.name, mid, f"{dia}.log"), "w") as f:
            f.write("viejo\n")
        return str(dia)

    def test_cada_macro_por_separado(self):
        a, b = nueva_macro("A"), nueva_macro("B")
        self.r.anotar(a, "INICIO", "uno")
        self.r.anotar(b, "INICIO", "dos")
        hoy = self.r.dias(a["id"])[0]
        self.assertIn("uno", self.r.leer(a["id"], hoy)[0])
        self.assertNotIn("dos", "".join(self.r.leer(a["id"], hoy)))
        self.assertIn("dos", self.r.leer(b["id"], hoy)[0])

    def test_conserva_solo_los_ultimos_7_dias(self):
        conservado = self.archivo_viejo("m", 6)
        borrado = self.archivo_viejo("m", 7)
        self.r.limpiar()
        self.assertEqual(self.r.dias("m"), [conservado])
        self.assertNotIn(borrado, self.r.dias("m"))

    def test_macro_sin_logs_no_deja_carpeta(self):
        self.archivo_viejo("m", 30)
        self.r.limpiar()
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_escribir_el_numero_de_dias_no_borra(self):
        conservado = self.archivo_viejo("m", 5)
        self.r.anotar(nueva_macro("A"), "INICIO")
        self.ajustes["registro_dias"] = 1
        self.r.anotar(nueva_macro("A"), "INICIO")
        self.assertIn(conservado, self.r.dias("m"))

    def test_apagado_no_escribe(self):
        self.ajustes["registro"] = False
        self.r.anotar(nueva_macro("A"), "INICIO")
        self.assertEqual(os.listdir(self.tmp.name), [])

    def test_id_no_sale_de_la_carpeta(self):
        self.r.anotar({"id": "..\\..\\fuera", "nombre": "x"}, "INICIO")
        self.assertTrue(os.path.commonpath([self.r.ruta("..\\..\\fuera"), self.tmp.name]) == self.tmp.name)
        self.assertEqual(len(os.listdir(self.tmp.name)), 1)

    def correr_con_registro(self, macro, motivo=None):
        f = Falsa()
        e = Ejecutor(macro, stats(), salida=f, registro=self.r.anotar, origen="atajo F1")
        e.start()
        if motivo:
            time.sleep(0.2)
            e.detener(motivo)
        e.join(3)
        return self.r.leer(macro["id"], self.r.dias(macro["id"])[0])

    def test_inicio_y_fin_con_conteo(self):
        m = nueva_macro("Auto", pasos=[nuevo_paso("click", cps=20)])
        lineas = self.correr_con_registro(m, "pulsaste el atajo")
        self.assertIn("INICIO", lineas[1])
        self.assertIn("con atajo F1", lineas[1])
        self.assertIn("FIN", lineas[0])
        self.assertIn("pulsaste el atajo", lineas[0])
        self.assertRegex(lineas[0], r"[1-9]\d* clicks")

    def test_fin_por_repeticiones(self):
        m = nueva_macro("Una", modo="una_vez", pasos=[nuevo_paso("tecla", teclas="A")])
        self.assertIn("completó las repeticiones", self.correr_con_registro(m)[0])

    def test_no_guarda_lo_que_escribe_la_macro(self):
        m = nueva_macro("Txt", modo="una_vez", pasos=[nuevo_paso("texto", texto="secreto123", cps=0.0)])
        self.assertNotIn("secreto123", "".join(self.correr_con_registro(m)))

    def test_error_queda_anotado_y_suelta_todo(self):
        class Rota(Falsa):
            def rueda(self, n):
                raise RuntimeError("boom")
        m = nueva_macro("Mal", modo="una_vez", pasos=[nuevo_paso("estado", accion="presionar", objetivo="A"), nuevo_paso("rueda")])
        f = Rota()
        e = Ejecutor(m, stats(), salida=f, registro=self.r.anotar)
        e.start()
        e.join(3)
        lineas = self.r.leer(m["id"], self.r.dias(m["id"])[0])
        self.assertIn("ERROR", lineas[1])
        self.assertIn("boom", lineas[1])
        self.assertIn("se detuvo por un error", lineas[0])
        self.assertEqual(f.nombres("arriba"), ["A"])


class Teclas(unittest.TestCase):
    def test_nombres_ida_y_vuelta(self):
        for n in ["W", "F1", "F24", "Espacio", "Arriba", "Num5", "Shift", "Ctrl", "Enter", "7"]:
            self.assertEqual(entrada.nombre_de_vk(entrada.vk_de_nombre(n)), n)

    def test_izquierda_derecha_iguales(self):
        self.assertEqual(entrada.nombre_de_vk(0xA0), "Shift")
        self.assertEqual(entrada.nombre_de_vk(0xA3), "Ctrl")

    def test_tecla_extendida(self):
        self.assertIn(entrada.vk_de_nombre("Arriba"), entrada.VK_EXTENDIDAS)
        self.assertNotIn(entrada.vk_de_nombre("W"), entrada.VK_EXTENDIDAS)
        self.assertNotIn(entrada.vk_de_nombre("Num8"), entrada.VK_EXTENDIDAS)

    def test_tamano_estructura(self):
        import ctypes
        self.assertEqual(ctypes.sizeof(entrada._INPUT), 40)


if __name__ == "__main__":
    unittest.main()
