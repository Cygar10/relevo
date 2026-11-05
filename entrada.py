"""Teclado y mouse a bajo nivel en Windows: enviar entrada y escuchar teclas.

Envia con SendInput usando scan codes (lo que muchos programas si leen)
y escucha con hooks WH_*_LL. No depende de librerias externas.
"""
import ctypes
import threading
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# ---------------------------------------------------------------- nombres

MOUSE_IZQ, MOUSE_DER, MOUSE_MEDIO, MOUSE_4, MOUSE_5 = "Mouse Izq", "Mouse Der", "Mouse Medio", "Mouse 4", "Mouse 5"
BOTONES_MOUSE = [MOUSE_IZQ, MOUSE_DER, MOUSE_MEDIO, MOUSE_4, MOUSE_5]

_VK_NOMBRE = {
    0x08: "Retroceso", 0x09: "Tab", 0x0D: "Enter", 0x10: "Shift", 0x11: "Ctrl", 0x12: "Alt",
    0x13: "Pausa", 0x14: "BloqMayus", 0x1B: "Esc", 0x20: "Espacio", 0x21: "RePag", 0x22: "AvPag",
    0x23: "Fin", 0x24: "Inicio", 0x25: "Izquierda", 0x26: "Arriba", 0x27: "Derecha", 0x28: "Abajo",
    0x2C: "ImprPant", 0x2D: "Insert", 0x2E: "Supr", 0x5B: "Win", 0x5D: "Menu", 0x6A: "Num*",
    0x6B: "NumMas", 0x6D: "Num-", 0x6E: "Num.", 0x6F: "Num/", 0x90: "BloqNum", 0x91: "BloqDespl",
    0xBB: "Mas",
}
_VK_NOMBRE.update({0x30 + i: str(i) for i in range(10)})
_VK_NOMBRE.update({0x41 + i: chr(0x41 + i) for i in range(26)})
_VK_NOMBRE.update({0x60 + i: f"Num{i}" for i in range(10)})
_VK_NOMBRE.update({0x70 + i: f"F{i + 1}" for i in range(24)})
_NOMBRE_VK = {n.upper(): vk for vk, n in _VK_NOMBRE.items()}

# Izquierda/derecha cuentan como la misma tecla para atajos y grabaciones.
_VK_NORMAL = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11, 0xA4: 0x12, 0xA5: 0x12, 0x5C: 0x5B}
MODIFICADORES = {"Shift", "Ctrl", "Alt", "Win"}


def nombre_de_vk(vk):
    vk = _VK_NORMAL.get(vk, vk)
    if vk in _VK_NOMBRE:
        return _VK_NOMBRE[vk]
    caracter = user32.MapVirtualKeyW(vk, 2) & 0xFFFF  # MAPVK_VK_TO_CHAR
    if 32 < caracter < 0xD800 and chr(caracter) != "+":
        return chr(caracter).upper()
    return f"VK{vk}"


def vk_de_nombre(nombre):
    """Devuelve el codigo de una tecla por su nombre, o None si no existe."""
    n = nombre.strip().upper()
    if n in _NOMBRE_VK:
        return _NOMBRE_VK[n]
    if n.startswith("VK") and n[2:].isdigit():
        return int(n[2:])
    if len(n) == 1:
        r = user32.VkKeyScanW(n)
        if r != -1 and (r & 0xFF) != 0xFF:
            return r & 0xFF
    return None


def separar(combo):
    """'Ctrl+Shift+F1' -> ['Ctrl', 'Shift', 'F1']"""
    return [p.strip() for p in (combo or "").split("+") if p.strip()]


def es_valida(tecla):
    return tecla in BOTONES_MOUSE or vk_de_nombre(tecla) is not None


# --------------------------------------------------------------- SendInput

ULONG_PTR = ctypes.c_size_t
LRESULT = ctypes.c_ssize_t


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD)]


class _UNION(ctypes.Union):
    _fields_ = [("mi", _MOUSEINPUT), ("ki", _KEYBDINPUT), ("hi", _HARDWAREINPUT)]


class _INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
user32.VkKeyScanW.restype = ctypes.c_short
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowRect.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.RECT))

# Comparten scan code con el teclado numerico: sin esta bandera la flecha arriba seria Num8.
VK_EXTENDIDAS = {0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28, 0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90}

_KEYUP, _SCANCODE, _EXTENDED, _UNICODE = 0x2, 0x8, 0x1, 0x4
_MOVE, _ABSOLUTO, _RUEDA, _VIRTUAL = 0x1, 0x8000, 0x800, 0x4000
_BANDERAS_BOTON = {
    MOUSE_IZQ: (0x2, 0x4, 0), MOUSE_DER: (0x8, 0x10, 0), MOUSE_MEDIO: (0x20, 0x40, 0),
    MOUSE_4: (0x80, 0x100, 1), MOUSE_5: (0x80, 0x100, 2),
}


def _enviar_raton(dx=0, dy=0, datos=0, banderas=0):
    i = _INPUT(type=0)
    i.u.mi = _MOUSEINPUT(dx, dy, datos & 0xFFFFFFFF, banderas, 0, 0)
    return user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def _enviar_tecla(scan, banderas, vk=0):
    i = _INPUT(type=1)
    i.u.ki = _KEYBDINPUT(vk, scan, banderas, 0, 0)
    return user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(_INPUT))


def _tecla(nombre, abajo):
    vk = vk_de_nombre(nombre)
    if vk is None:
        return
    sc = user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC
    banderas = _SCANCODE | (0 if abajo else _KEYUP)
    if vk in VK_EXTENDIDAS:
        banderas |= _EXTENDED
    _enviar_tecla(sc & 0xFF, banderas)


def presionar(nombre):
    if nombre in _BANDERAS_BOTON:
        baja, _, x = _BANDERAS_BOTON[nombre]
        _enviar_raton(datos=x, banderas=baja)
    else:
        _tecla(nombre, True)


def soltar(nombre):
    if nombre in _BANDERAS_BOTON:
        _, sube, x = _BANDERAS_BOTON[nombre]
        _enviar_raton(datos=x, banderas=sube)
    else:
        _tecla(nombre, False)


def mover(x, y, relativo=False):
    if relativo:
        _enviar_raton(int(x), int(y), banderas=_MOVE)
        return
    # Coordenadas normalizadas a 0-65535 sobre todos los monitores.
    izq, arr = user32.GetSystemMetrics(76), user32.GetSystemMetrics(77)
    ancho, alto = max(user32.GetSystemMetrics(78), 1), max(user32.GetSystemMetrics(79), 1)
    nx = int((int(x) - izq) * 65535 / max(ancho - 1, 1))
    ny = int((int(y) - arr) * 65535 / max(alto - 1, 1))
    _enviar_raton(nx, ny, banderas=_MOVE | _ABSOLUTO | _VIRTUAL)


def rueda(muescas):
    _enviar_raton(datos=int(muescas) * 120, banderas=_RUEDA)


def escribir_caracter(c):
    datos = c.encode("utf-16-le")
    for i in range(0, len(datos), 2):
        unidad = int.from_bytes(datos[i:i + 2], "little")
        _enviar_tecla(unidad, _UNICODE)
        _enviar_tecla(unidad, _UNICODE | _KEYUP)


def posicion_mouse():
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def titulo_ventana_activa():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    buf = ctypes.create_unicode_buffer(512)
    user32.GetWindowTextW(hwnd, buf, 512)
    return buf.value


# ------------------------------------------------------------------- hooks

_WM_QUIT = 0x0012
_INYECTADA_TECLADO = 0x10
_INYECTADA_MOUSE = 0x01
_TECLA_ABAJO, _TECLA_ARRIBA = {0x100, 0x104}, {0x101, 0x105}
_EVENTOS_MOUSE = {
    0x201: (MOUSE_IZQ, True), 0x202: (MOUSE_IZQ, False),
    0x204: (MOUSE_DER, True), 0x205: (MOUSE_DER, False),
    0x207: (MOUSE_MEDIO, True), 0x208: (MOUSE_MEDIO, False),
}


class _KBDLL(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


class _MSLL(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD), ("flags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]


_HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.SetWindowsHookExW.argtypes = (ctypes.c_int, _HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
user32.SetWindowsHookExW.restype = wintypes.HHOOK
user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
user32.CallNextHookEx.restype = LRESULT
user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class _Gancho:
    """Hook de bajo nivel en su propio hilo. Ignora la entrada simulada por programas."""

    def __init__(self, tipo, traducir):
        self._tipo, self._traducir = tipo, traducir
        self._hilo = None
        self._tid = 0
        self._listo = threading.Event()

    def _proc(self, codigo, wparam, lparam):
        if codigo == 0:
            try:
                self._traducir(wparam, lparam)
            except Exception:
                pass  # un error aqui nunca debe trabar el teclado de todo Windows
        return user32.CallNextHookEx(None, codigo, wparam, lparam)

    def _bucle(self):
        self._tid = kernel32.GetCurrentThreadId()
        proc = _HOOKPROC(self._proc)
        gancho = user32.SetWindowsHookExW(self._tipo, proc, kernel32.GetModuleHandleW(None), 0)
        self._listo.set()
        if not gancho:
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            pass
        user32.UnhookWindowsHookEx(gancho)

    @property
    def activo(self):
        return self._hilo is not None and self._hilo.is_alive()

    def iniciar(self):
        if self.activo:
            return
        self._listo.clear()
        self._hilo = threading.Thread(target=self._bucle, daemon=True)
        self._hilo.start()
        self._listo.wait(2)

    def detener(self):
        if self.activo:
            user32.PostThreadMessageW(self._tid, _WM_QUIT, 0, 0)
            self._hilo.join(1)
        self._hilo = None


def gancho_teclado(al_evento):
    """al_evento(nombre, abajo) por cada tecla fisica."""
    def traducir(wparam, lparam):
        d = ctypes.cast(lparam, ctypes.POINTER(_KBDLL)).contents
        if d.flags & _INYECTADA_TECLADO:
            return
        if wparam in _TECLA_ABAJO:
            al_evento(nombre_de_vk(d.vkCode), True)
        elif wparam in _TECLA_ARRIBA:
            al_evento(nombre_de_vk(d.vkCode), False)
    return _Gancho(13, traducir)


def gancho_mouse(al_evento):
    """al_evento(nombre, abajo, x, y) por cada boton fisico. Ignora el movimiento."""
    def traducir(wparam, lparam):
        if wparam == 0x200:  # movimiento: salir cuanto antes para no meter lag
            return
        d = ctypes.cast(lparam, ctypes.POINTER(_MSLL)).contents
        if d.flags & _INYECTADA_MOUSE:
            return
        if wparam in _EVENTOS_MOUSE:
            nombre, abajo = _EVENTOS_MOUSE[wparam]
        elif wparam in (0x20B, 0x20C):
            nombre, abajo = (MOUSE_4 if (d.mouseData >> 16) == 1 else MOUSE_5), wparam == 0x20B
        else:
            return
        al_evento(nombre, abajo, d.pt.x, d.pt.y)
    return _Gancho(14, traducir)
