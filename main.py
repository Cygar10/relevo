"""Relevo: tus manos descansan, el sigue."""
import ctypes
import subprocess
import sys

import customtkinter as ctk

from datos import Almacen
from motor import Motor
from ui import App


def reabrir_como_admin():
    """Pide permisos si el usuario lo activo. Si dice que no, sigue abriendo sin ellos."""
    argumentos = sys.argv[1:] if getattr(sys, "frozen", False) else sys.argv
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, subprocess.list2cmdline(argumentos), None, 1) > 32


def main():
    almacen = Almacen()
    if almacen.ajustes["admin"] and not ctypes.windll.shell32.IsUserAnAdmin() and reabrir_como_admin():
        return 0
    # Dos copias pelearian por los mismos atajos.
    ctypes.windll.kernel32.CreateMutexW(None, False, "Relevo-una-sola-instancia")
    if ctypes.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        ctypes.windll.user32.MessageBoxW(None, "Relevo ya está abierto.", "Relevo", 0x40)
        return 0
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Relevo.App")

    motor = Motor(almacen.stats)
    root = ctk.CTk()
    App(root, almacen, motor)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
