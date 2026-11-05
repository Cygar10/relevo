@echo off
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install --upgrade pyinstaller customtkinter pillow
echo.
echo Creando el ejecutable...
python -m PyInstaller --noconfirm --onefile --noconsole --name "Relevo" --icon relevo.ico --add-data "relevo.ico;." --collect-all customtkinter --distpath . main.py
echo.
echo Listo. Relevo.exe quedo en esta misma carpeta.
pause
