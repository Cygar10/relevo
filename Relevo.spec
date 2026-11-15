# Receta de PyInstaller para Relevo.exe (la usa crear_exe.bat).
from PyInstaller.utils.hooks import collect_all

datos, binarios, ocultos = collect_all("customtkinter")
a = Analysis(["main.py"], datas=datos + [("relevo.ico", ".")], binaries=binarios, hiddenimports=ocultos)

# Tcl trae cientos de archivos de zonas horarias y de traducciones que Relevo no usa. El .exe los
# desempaqueta uno por uno cada vez que abre: sin ellos arranca bastante antes.
SOBRAN = ("_tcl_data/tzdata/", "_tcl_data/msgs/", "_tk_data/msgs/", "_tk_data/images/", "_tcl_data/http1.0/", "_tcl_data/opt0.4/")
a.datas = [d for d in a.datas if not d[0].replace("\\", "/").startswith(SOBRAN)]

exe = EXE(PYZ(a.pure), a.scripts, a.binaries, a.datas, name="Relevo", icon="relevo.ico", console=False, upx=False)
