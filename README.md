# Relevo

Automatiza clicks y teclas repetitivas en Windows para que tus manos, tu mouse y tu teclado descansen.
Como en una carrera de relevos: le pasas el testigo y él sigue.

**[Descargar la última versión](../../releases/latest)** (solo Windows, no hace falta instalar nada)

## Qué puede hacer

- **Macros a tu medida:** crea las que quieras, cada una con su atajo global (`F1`, `Ctrl+F1`, botones laterales del mouse...).
- **Pasos combinables:** clicks, teclas y combinaciones, tecla al azar, esperas, mantener o soltar, mover el mouse, rueda, escribir texto y repetir pasos.
- **Grabar acciones:** haz la tarea una vez y se convierte en pasos editables. Graba teclas, clicks y su posición, no la trayectoria del mouse.
- **Tres modos:** encender y apagar, solo mientras mantienes el atajo, o una sola vez.
- **Control fino:** repeticiones, velocidad, variación natural, probabilidad por paso y cuenta atrás al iniciar desde la ventana.
- **Solo en cierta ventana:** la macro se pausa y suelta todo si cambias a otra ventana.
- **Registro por macro:** cuándo empezó y terminó cada una, por qué y cuánto hizo. Conserva los últimos 7 días, o los que elijas.
- **Perfiles:** uno por cada tarea, y se pueden exportar para compartirlos.
- **Apariencia:** 4 temas, color de acento, opacidad, siempre encima y modo compacto.

Al abrirlo por primera vez trae un perfil de ejemplo, **Mi perfil**, que puedes cambiar o borrar:

| Atajo | Qué hace |
| --- | --- |
| `F1` | Autoclick a 4.5 clicks por segundo, con variación de ±10% |
| `F10` | Detiene todas las macros y suelta todo |
| `F9` | Cierra Relevo |

Todos los atajos se pueden cambiar.

## Avisos al abrirlo

- **Permisos de administrador:** no hacen falta por defecto. Si un programa ignora las teclas, activa Ajustes → Abrir como administrador.
- **SmartScreen o Defender:** pueden avisarte porque el programa no está firmado y simula teclado y mouse. El código está aquí para que lo revises; si confías, agrégalo como excepción.
- **Reglas de cada programa:** algunos programas y servicios prohíben la automatización. Revísalas antes de usarlo en una cuenta que te importe.

Tu configuración se guarda en `%APPDATA%\Relevo`.

## Compilar desde el código

Necesitas Python 3 con tkinter. Ejecuta `crear_exe.bat` y `Relevo.exe` quedará en la misma carpeta.

Para correr las pruebas del motor (no tocan tu teclado ni tu mouse):

```bash
python -m unittest pruebas
```
