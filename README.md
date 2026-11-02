# UTi712S

Extrae la matriz térmica de los BMP que guarda la cámara UNI-T UTi712S, la convierte a grados Celsius con la misma escala que usa el software de la cámara, y permite consultar cada punto en un visor.

El archivo no trae la lectura del sensor. Trae la imagen de pantalla, de 8 bits, y tres temperaturas puntuales (mínima, máxima y central). La matriz en °C es la interpolación que arma `ImageFile.dll` a partir de esos datos. Sirve para reproducir lo que muestra el programa oficial. No mejora la medición.

## La cámara

La UTi712S guarda las capturas en BMP. El sensor es de 120×90. La pantalla es de 320×240 y el archivo sale en 240×320, el mismo recuadro girado a vertical. El rango publicado por UNI-T es de -20 °C a 400 °C, con exactitud de ±2 °C o ±2 %, el que sea mayor. La emisividad de fábrica es 0,95.

Esas tres cifras (rango, exactitud, emisividad) describen los puntos que mide la cámara. No describen el byte de cada píxel.

## Instalación

Hace falta Python 3.10 o posterior. El paquete está en [PyPI](https://pypi.org/project/uti712s/). Con [pipx](https://pipx.pypa.io/):

```bash
pipx install uti712s
```

Quedan dos comandos: `uti712s-extract` y `uti712s-view`.

Pillow es opcional. Sin él se escriben el JSON y los CSV, y no los PNG. El extra se llama `png`. En el entorno de pipx:

```bash
pipx inject uti712s pillow
```

El visor usa tkinter, que no se instala por pip. En Debian o Ubuntu: `sudo apt install python3-tk`. Tiene que estar en el mismo Python que usa pipx.

Desde el repositorio, sin pasar por PyPI:

```bash
pipx install git+https://github.com/pablogventura/uti712s.git
```

O, desde una copia local:

```bash
pipx install .
```

## Uso

```bash
uti712s-extract 'images/IMG 0001.bmp'
```

Sin instalar, desde el repositorio:

```bash
python3 uti712s_extract.py 'images/IMG 0001.bmp'
```

Los archivos salen al lado del BMP:

| Archivo | Contenido |
|---|---|
| `IMG 0001_metadatos.json` | Temperaturas puntuales, anclas, modo y píxeles de control |
| `IMG 0001_intensidades.csv` | Matriz de 8 bits, una fila de imagen por línea, sin encabezado |
| `IMG 0001_celsius.csv` | La misma grilla en °C, ocho decimales |
| `IMG 0001_intensidades.png` | La matriz en gris, sin la interfaz de la cámara |
| `IMG 0001_termica_sin_indicadores.png` | La misma matriz coloreada con la paleta embebida |

La fila 0 es el borde de arriba. En modo 7, que es el de las capturas de `images/`, el orden es el del archivo.

## Desde Python

`read_capture` lee el BMP y no escribe archivos. `celsius_at` calcula un punto con la escala de dos tramos. `extract` escribe el JSON, los CSV y, si Pillow está instalado, los PNG.

```python
from pathlib import Path
from uti712s_extract import read_capture, extract

capture = read_capture(Path("images/IMG 0001.bmp"))
print(capture.celsius_at(119, 159))
extract(Path("images/IMG 0001.bmp"))
```

## Visor

Abre la escena térmica sin la interfaz de la cámara y muestra la temperatura estimada de cada píxel. Usa la paleta embebida y la misma escala que el CSV. Abrir un BMP no escribe archivos.

```bash
uti712s-view
uti712s-view 'images/IMG 0001.bmp'
```

Sin instalar, desde el repositorio: `python3 uti712s_view.py` y `python3 uti712s_view.py 'images/IMG 0001.bmp'`.

Archivo, Abrir, carga otro BMP. La rueda del mouse sobre la imagen cambia el zoom, de 1 a 6. Cada píxel de origen sigue siendo un bloque. La rueda sobre el panel desplaza el texto, si no entra en la ventana.

El panel tiene tres bloques.

**Bajo el mouse.** La temperatura en °C, con un decimal, del píxel que está bajo el puntero. También muestra la columna y la fila. La columna se cuenta desde la izquierda y la fila desde arriba. El brillo es el byte de 0 a 255 guardado en el archivo. La temperatura es la estimación en °C. Si el puntero no está sobre la imagen, el bloque pide pasar el mouse por ella.

**Punto fijado.** Un clic deja esa lectura marcada, aunque el mouse se mueva. Otro clic, o Escape, la suelta. El punto se dibuja con un cuadrado rosa, un poco más grande que el píxel.

**Mediciones de la cámara.** Los tres valores del pie, la emisividad y el modo.

- Mínima y máxima: el punto más frío y el más caliente que midió la cámara. No se marcan en la imagen. Esas coordenadas a veces caen fuera, y no siempre coinciden con el byte más frío o más caliente.
- Central: la lectura del centro. El cuadrado celeste queda en ese valor. Los demás píxeles se estiman a partir de estos tres.
- Emisividad: la que tenía configurada la cámara. En estas capturas es 0,95, el valor de fábrica.
- Modo 7: la foto no se gira. Arriba es arriba.

Hay dos marcas fijas. El cuadrado celeste es el píxel de la curva. En estas capturas está en la columna 119, fila 159, y su temperatura es la central. La cruz amarilla es el centro que dibuja el software, en la columna 120, fila 160. En modo 7 son píxeles distintos. Si el mouse cae en una, el panel lo dice.

## Qué hay en el BMP

Las 32 capturas de `images/` miden 230995 bytes y comparten esta forma: BMP de 16 bits, 240×320, sin compresión, y un bloque extra de 77341 bytes.

El programa oficial no lee el ancho ni el alto del encabezado. Fija 240×320 y empieza la zona térmica en el offset `0x25839` (153657). Este script lee el tamaño en el encabezado y entra en `bfSize + 3`. En un BMP de 16 bits y 240×320, `bfSize` vale 153654 (54 bytes de encabezado más 153600 de píxeles), así que `bfSize + 3` cae en el mismo byte. Además exige que el bloque extra mida `3 + ancho*alto + 512 + 26` y que arranque con tres ceros.

```text
0            encabezado BMP y píxeles de 16 bits     153654 bytes
153654       00 00 00                                3 bytes
153657       intensidades, 1 byte por píxel          240 * 320 = 76800
230457       paleta RGB565, 256 colores              512
230969       pie                                     26
230995       fin
```

El BMP visible es la pantalla: cruz, textos, batería, fecha y barra de color. La matriz de 8 bits es la escena térmica sin esa interfaz. El origen vertical coincide con la foto: arriba es arriba.

La paleta embebida no reproduce los píxeles del BMP. En estas capturas la coincidencia exacta es prácticamente nula. La pantalla lleva la interfaz encima y usa otro estirado de color. El PNG sin indicadores muestra la escena limpia, con la paleta del archivo, no una copia de la pantalla.

## Paleta

Son 256 colores de 16 bits, little-endian, RGB565:

| Canal | Bits | Expansión que usa el software |
|---|---|---|
| Rojo | 15..11 | los 5 bits, desplazados 3 a la izquierda (máximo 248) |
| Verde | 10..5 | los 6 bits, desplazados 2 a la izquierda |
| Azul | 4..0 | los 5 bits, desplazados 3 a la izquierda |

El índice es el byte de intensidad, sin estirar al rango de la escena.

## Pie de 26 bytes

Little-endian. Las temperaturas son enteros con signo, en décimas. Las coordenadas son enteros sin signo.

| Offset | Tipo | Campo |
|---|---|---|
| 0 | uint8 | Unidad. 0 es °C, 1 es °F |
| 1 | int16 | Temperatura máxima × 10 |
| 3 | int16 | Temperatura mínima × 10 |
| 5 | uint8 | Ancla caliente: intensidad que el software iguala a la máxima |
| 6 | uint8 | Ancla fría: intensidad que el software iguala a la mínima |
| 7 | int16 | Temperatura central × 10 |
| 9 | uint8 | Emisividad × 100 |
| 10 | uint8 | Modo de orientación |
| 11 | 3 bytes | El software no los lee. En estas capturas valen 0 |
| 14 | uint16 | X del mínimo |
| 16 | uint16 | Y del mínimo |
| 18 | uint16 | X del máximo |
| 20 | uint16 | Y del máximo |
| 22 | uint16 | X del centro guardado |
| 24 | uint16 | Y del centro guardado |

En las 32 capturas: unidad °C, emisividad 0,95, modo 7, ancla fría 0, ancla caliente igual al máximo de la matriz, centro guardado en (120, 160).

El byte 5 y el byte 6 juntos parecen un int16. No lo son. El software los lee por separado. Como el byte 6 es 0, ese int16 coincide con la intensidad máxima, y por eso un parseo anterior lo veía como "el máximo de la matriz" metido en un solo campo.

## Modo de orientación

El modo es el byte 10. Cambia el orden de la matriz antes de convertir, y también cómo se interpretan las coordenadas de mínimo y máximo. El centro dibujado no sale del pie: el software lo fija según el modo.

| Modo | Matriz | Mínimo y máximo | Centro dibujado |
|---|---|---|---|
| 1 | `salida[fila, col] = origen[alto * (ancho - col - 1) + fila]` | `x' = ancho - y - 1`, `y' = x - 1` | `(alto/2 - 1, ancho/2 - 1)` = (159, 119) |
| 2 y 5 | el buffer al revés | `x' = ancho - x - 1`, `y' = alto - y - 1` | `(ancho/2 - 1, alto/2 - 1)` = (119, 159) |
| otro, incluido el 7 | se deja como está | se dejan como están | `(ancho/2, alto/2)` = (120, 160) |

Las 32 capturas son modo 7. Los modos 1, 2 y 5 están implementados como en el DLL, pero este conjunto no los trae.

Las coordenadas de mínimo y máximo pueden caer fuera del raster. En estas fotos aparece `x = 240` o `y = 321`. El software las guarda igual, sin recortarlas. A veces el marcador cae a unos pocos píxeles del extremo de intensidad, y a veces a decenas. La temperatura puntual y el byte más frío o más caliente no son el mismo dato: el byte ya pasó por el realce de contraste.

## Escala a °C

El píxel de la curva no es la cruz. Después de reordenar, el software toma la intensidad `Ic` en `(ancho/2 - 1, alto/2 - 1)`. En 240×320 eso es (119, 159), un píxel arriba y a la izquierda de la cruz (120, 160).

Con las temperaturas todavía en décimas:

- si la intensidad `p` es mayor o igual que `Ic`, la recta une `(ancla caliente, máxima)` con `(Ic, central)`;
- si es menor, une `(Ic, central)` con `(ancla fría, mínima)`.

```text
raw = p * (Tb - Ta) / (Ib - Ia) + (Ta * Ib - Tb * Ia) / (Ib - Ia)
°C  = raw / 10
```

`(Ia, Ta)` es el primer punto del tramo y `(Ib, Tb)` el segundo. Si el archivo está en Fahrenheit, este script pasa el resultado a Celsius con `(°F - 32) / 1.8`. El programa oficial, en ese caso, deja la primera matriz en la unidad del archivo y arma otra con `valor * 1.8 + 32`. En las capturas de `images/` la unidad es °C, así que el CSV coincide con la matriz del programa.

El píxel de la curva queda, por construcción, en la temperatura central. La cruz no. En `IMG 0001.bmp`:

| | Intensidad | °C |
|---|---|---|
| Curva (119, 159) | 17 | 13,3 |
| Cruz (120, 160) | 16 | 12,84705882 |
| Ancla fría | 0 | 5,6 |
| Píxel más frío de esa foto | 1 | 6,05294118 |
| Ancla caliente | 253 | 21,6 |

La mínima del pie es 5,6 °C y la máxima 21,6 °C. El píxel más frío no llega a 5,6 °C porque la ancla fría está en la intensidad 0 y ese píxel vale 1.

## Lo que no se puede recuperar

El sensor entrega bastante más que 8 bits. Antes de guardar, la cámara realza el contraste y estira el resultado a 240×320. Muchas temperaturas distintas caen en el mismo byte, y la tabla de ese realce no viaja en el archivo. Con tres puntos medidos se puede clavar la curva en la mínima, la máxima y el centro. Cualquier otro píxel sigue siendo una estimación, y otra curva que pase por los mismos tres puntos no está mejor medida.

El error acompaña el rango de la escena. Con menos de 2 °C de diferencia, como en `IMG 0008.bmp` o `IMG 0031.bmp`, queda por debajo de 0,1 °C. En `IMG 0001.bmp` la cruz ya difiere 0,45 °C de la medición central. En una escena de cientos de grados la diferencia es de decenas de grados.

`IMG 0003.bmp` guarda una máxima de 431,7 °C y la pantalla muestra OL. `IMG 0004.bmp` guarda 429,6 °C, por encima del rango de -20 °C a 400 °C publicado para esta cámara. Esos máximos están en el archivo, y la cámara no los trata como una lectura normal.

Para un punto que importe, la lectura que vale es la del puntero en la cámara.

## Software oficial y otros parseos

UNI-T publica el UTi712S PC Software (junio de 2022, un `Setup.exe` de Windows dentro del zip). La lógica de este formato está en `ImageFile.dll`, en `refreshParam` y en el pasaje de intensidad a temperatura. Este repositorio no incluye ese instalador.

El programa oficial hace esta misma escala de dos tramos. No tiene un plano radiométrico escondido.

[UNI-T Thermal Utilities](https://github.com/Santi-hr/UNI-T-Thermal-Utilities) documenta un BMP parecido, el de la UTi260B. No sirve para estos archivos: aquella cámara guarda BMP de 24 bits, sin los 3 bytes de relleno, y ordena primero el punto máximo. El autor describe el mismo límite en [temperature_issue.md](https://github.com/Santi-hr/UNI-T-Thermal-Utilities/blob/main/docs/temperature_issue.md): la imagen embebida ya viene realzada, y en el postproceso solo se pueden fiar la mínima, la máxima y el centro.

## Muestras

`images/` tiene 32 BMP sacados de una UTi712S, de septiembre de 2020 a agosto de 2026. Todas entran en el formato de arriba, en modo 7 y en °C. Sirven para comprobar el parseo y la escala. No son una calibración.
