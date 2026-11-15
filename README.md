# Relevo

Automatiza clicks y teclas repetitivas en Windows para que tus manos, tu mouse y tu teclado descansen.
Como en una carrera de relevos: le pasas el testigo y él sigue.

**[Descargar la última versión](../../releases/latest)** (solo Windows, no hace falta instalar nada)

## Qué puede hacer

- **Macros a tu medida:** crea las que quieras, cada una con su atajo global (`F1`, `Ctrl+F1`, botones laterales del mouse...).
- **Pasos combinables:** clicks, teclas y combinaciones, tecla al azar, patrones de teclas, esperas, mantener o soltar, mover el mouse, rueda, escribir texto y repetir pasos.
- **Patrones de teclas:** escribe `A 3, D 5` y mantiene A tres segundos y luego D cinco. Cada tecla con su tiempo, en orden, ida y vuelta o al azar.
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

## Patrones de teclas

El paso **Patrón de teclas** recibe una línea de texto con las teclas separadas por comas:

| Escribes | Qué hace |
| --- | --- |
| `A 3, D 5` | Mantiene A 3 segundos y luego D 5 segundos |
| `W 0.5-2` | Mantiene W entre medio segundo y 2, distinto cada vez |
| `Ctrl+C` | Un toque de la combinación |
| `Espacio x3` | Tres toques seguidos |
| `espera 1.5` | Pausa sin tocar nada |
| `Mouse Izq 2` | También sirven los botones del mouse |

Además puedes elegir el orden (en orden, ida y vuelta, barajado o una al azar), cuántas veces se repite, cuánto duran las teclas que no tienen tiempo propio y la pausa entre una y otra.

## Avisos al abrirlo

- **Permisos de administrador:** no hacen falta por defecto. Si un programa ignora las teclas, activa Ajustes → Abrir como administrador.
- **SmartScreen o Defender:** pueden avisarte porque el programa no está firmado y simula teclado y mouse. El código está aquí para que lo revises; si confías, agrégalo como excepción.
- **Reglas de cada programa:** algunos programas y servicios prohíben la automatización. Revísalas antes de usarlo en una cuenta que te importe.

Tu configuración se guarda en `%APPDATA%\Relevo`.

## Compilar desde el código

Necesitas Python 3 con tkinter. Ejecuta `crear_exe.bat` y `Relevo.exe` quedará en la misma carpeta (la receta está en `Relevo.spec`).

Para correr las pruebas (no tocan tu teclado ni tu mouse):

```bash
python -m unittest pruebas
```

```bash
python -m unittest pruebas_ui
```

Las primeras prueban el motor. Las segundas abren la ventana unos segundos con una configuración temporal y la manejan con clicks simulados.
