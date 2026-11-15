@echo off
cd /d "%~dp0"
rem Usa el lanzador "py" si existe: en algunos Windows "python" solo abre la tienda.
set PY=python
where py >nul 2>nul && set PY=py
echo Instalando dependencias...
%PY% -m pip install --upgrade pyinstaller customtkinter pillow
echo.
echo Creando el ejecutable...
%PY% -m PyInstaller --noconfirm --distpath . Relevo.spec
echo.
echo Listo. Relevo.exe quedo en esta misma carpeta.
pause
