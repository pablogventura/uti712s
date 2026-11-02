# UTi712S

Extract the thermal matrix from BMP files saved by the UNI-T UTi712S, convert it to degrees Celsius with the same scale the camera software uses, and look up the temperature of each point in a viewer.

The file does not contain the sensor reading. It contains the 8-bit screen image and three spot temperatures (minimum, maximum, and center). The Celsius matrix is the interpolation `ImageFile.dll` builds from those values. It reproduces what the official program shows. It does not improve the measurement.

## The camera

The UTi712S stores captures as BMP files. The sensor is 120 x 90. The screen is 320 x 240, and the file comes out at 240 x 320, the same frame turned upright. The range published by UNI-T is -20 °C to 400 °C, with an accuracy of ±2 °C or ±2 %, whichever is greater. The factory emissivity is 0.95.

Those three figures (range, accuracy, emissivity) describe the spots the camera measures. They do not describe the byte of each pixel.

## Installation

Python 3.10 or newer is required. The package is on [PyPI](https://pypi.org/project/uti712s/). With [pipx](https://pipx.pypa.io/):

```bash
pipx install uti712s
```

That installs two commands: `uti712s-extract` and `uti712s-view`.

Pillow is optional. Without it the tool writes the JSON and the CSV files, and skips the PNG files. The extra is named `png`. Inside the pipx environment:

```bash
pipx inject uti712s pillow
```

The viewer uses tkinter, which is not installed by pip. On Debian or Ubuntu: `sudo apt install python3-tk`. It has to be available to the same Python that pipx uses.

From the repository, without going through PyPI:

```bash
pipx install git+https://github.com/pablogventura/uti712s.git
```

Or, from a local copy:

```bash
pipx install .
```

## Usage

```bash
uti712s-extract 'images/IMG 0001.bmp'
```

Without installing, from the repository:

```bash
python3 uti712s_extract.py 'images/IMG 0001.bmp'
```

The files are written next to the BMP:

| File | Contents |
|---|---|
| `IMG 0001_metadata.json` | Spot temperatures, anchors, mode, and control pixels |
| `IMG 0001_intensities.csv` | 8-bit matrix, one image row per line, no header |
| `IMG 0001_celsius.csv` | The same grid in °C, eight decimal places |
| `IMG 0001_intensities.png` | The matrix in gray, without the camera interface |
| `IMG 0001_thermal_no_overlay.png` | The same matrix colored with the embedded palette |

Row 0 is the top edge. In mode 7, which is the mode of the captures in `images/`, the order is the file order.

The metadata JSON uses these fields:

| Field | Meaning |
|---|---|
| `file` | BMP file name |
| `exported_resolution` | `[width, height]` |
| `file_unit` | Unit stored in the file (`°C` or `°F`) |
| `orientation_mode` | Orientation byte |
| `maximum_temperature`, `minimum_temperature`, `center_temperature` | Footer spots, in the file unit, already divided by 10 |
| `emissivity` | Footer byte divided by 100 |
| `cold_anchor_intensity`, `hot_anchor_intensity` | Intensities tied to the minimum and the maximum |
| `minimum_point_xy`, `maximum_point_xy` | Footer coordinates after the orientation transform |
| `center_point_xy` | Center the software draws |
| `curve_pixel_xy` | Pixel that anchors the two-segment scale |
| `curve_intensity`, `cross_intensity` | Intensity at the curve pixel and at the drawn center |
| `curve_celsius`, `cross_celsius` | Those two pixels in °C |
| `minimum_intensity`, `maximum_intensity` | Lowest and highest byte in the matrix |
| `warning` | What the Celsius matrix is, and what it is not |
| `exports` | Paths written next to the BMP |

## From Python

`read_capture` reads the BMP and does not write files. `celsius_at` computes one point with the two-segment scale. `extract` writes the JSON, the CSV files, and, when Pillow is installed, the PNG files.

```python
from pathlib import Path
from uti712s_extract import read_capture, extract

capture = read_capture(Path("images/IMG 0001.bmp"))
print(capture.celsius_at(119, 159))
extract(Path("images/IMG 0001.bmp"))
```

## Viewer

Opens the thermal scene without the camera interface and shows the estimated temperature of each pixel. It uses the embedded palette and the same scale as the CSV. Opening a BMP does not write files.

```bash
uti712s-view
uti712s-view 'images/IMG 0001.bmp'
```

Without installing, from the repository: `python3 uti712s_view.py` and `python3 uti712s_view.py 'images/IMG 0001.bmp'`.

File, Open loads another BMP. The mouse wheel over the image changes the zoom from 1 to 6. Each source pixel stays a solid block. The wheel over the panel scrolls the text when it does not fit in the window.

The panel has three blocks.

**Under the pointer.** The temperature in °C, to one decimal place, of the pixel under the pointer. It also shows the column and the row. Columns count from the left and rows from the top. Brightness is the byte from 0 to 255 stored in the file. The temperature is the Celsius estimate. When the pointer is off the image, the block asks you to move it onto the image.

**Pinned point.** A click keeps that reading in place while the pointer moves. Another click, or Escape, releases it. The point is drawn with a pink square, slightly larger than the pixel.

**Camera readings.** The three footer values, the emissivity, and the mode.

- Minimum and maximum: the coldest and hottest spots the camera measured. They are not drawn on the image. Those coordinates sometimes fall outside the frame, and they do not always match the coldest or hottest byte.
- Center: the center reading. The cyan square lands on that value. Every other pixel is estimated from these three.
- Emissivity: the value set on the camera. In these captures it is 0.95, the factory setting.
- Mode 7: the photo is not rotated. The top stays the top.

There are two fixed marks. The cyan square is the curve pixel. In these captures it is column 119, row 159, and its temperature is the center reading. The yellow cross is the center drawn by the software, at column 120, row 160. In mode 7 they are different pixels. When the pointer lands on one of them, the panel says which one.

## What is in the BMP

The 32 captures in `images/` are 230995 bytes and share this shape: a 16-bit BMP, 240 x 320, uncompressed, plus an extra block of 77341 bytes.

The official program does not read the width or height from the header. It fixes 240 x 320 and starts the thermal area at offset `0x25839` (153657). This script reads the size from the header and enters at `bfSize + 3`. In a 16-bit 240 x 320 BMP, `bfSize` is 153654 (54 header bytes plus 153600 pixel bytes), so `bfSize + 3` lands on the same byte. It also requires the extra block to be `3 + width*height + 512 + 26` bytes and to start with three zeros.

```text
0            BMP header and 16-bit pixels            153654 bytes
153654       00 00 00                                3 bytes
153657       intensities, 1 byte per pixel           240 * 320 = 76800
230457       RGB565 palette, 256 colors              512
230969       footer                                  26
230995       end
```

The visible BMP is the screen: crosshair, labels, battery, date, and color bar. The 8-bit matrix is the thermal scene without that interface. The vertical origin matches the photo: the top is the top.

The embedded palette does not reproduce the BMP pixels. On these captures the exact match is effectively none. The screen draws the interface on top and uses a different color stretch. The PNG without the overlay shows the clean scene, with the file palette, not a copy of the screen.

## Palette

256 colors, 16 bits, little-endian, RGB565:

| Channel | Bits | Expansion used by the software |
|---|---|---|
| Red | 15..11 | the 5 bits, shifted left by 3 (maximum 248) |
| Green | 10..5 | the 6 bits, shifted left by 2 |
| Blue | 4..0 | the 5 bits, shifted left by 3 |

The index is the raw intensity byte, not stretched to the scene range.

## 26-byte footer

Little-endian. Temperatures are signed integers, in tenths. Coordinates are unsigned integers.

| Offset | Type | Field |
|---|---|---|
| 0 | uint8 | Unit. 0 is °C, 1 is °F |
| 1 | int16 | Maximum temperature x 10 |
| 3 | int16 | Minimum temperature x 10 |
| 5 | uint8 | Hot anchor: intensity the software treats as the maximum |
| 6 | uint8 | Cold anchor: intensity the software treats as the minimum |
| 7 | int16 | Center temperature x 10 |
| 9 | uint8 | Emissivity x 100 |
| 10 | uint8 | Orientation mode |
| 11 | 3 bytes | Unread by the software. In these captures they are 0 |
| 14 | uint16 | Minimum X |
| 16 | uint16 | Minimum Y |
| 18 | uint16 | Maximum X |
| 20 | uint16 | Maximum Y |
| 22 | uint16 | Stored center X |
| 24 | uint16 | Stored center Y |

Across the 32 captures: unit °C, emissivity 0.95, mode 7, cold anchor 0, hot anchor equal to the maximum of the matrix, stored center at (120, 160).

Bytes 5 and 6 together look like an int16. They are separate fields. The software reads them one byte at a time. Because byte 6 is 0, that int16 matches the maximum intensity, which is why an earlier parse treated it as "the matrix maximum" packed into a single field.

## Orientation mode

The mode is byte 10. It changes the matrix order before conversion, and also how the minimum and maximum coordinates are interpreted. The drawn center does not come from the footer: the software fixes it from the mode.

| Mode | Matrix | Minimum and maximum | Drawn center |
|---|---|---|---|
| 1 | `output[row, col] = source[height * (width - col - 1) + row]` | `x' = width - y - 1`, `y' = x - 1` | `(height/2 - 1, width/2 - 1)` = (159, 119) |
| 2 and 5 | the buffer reversed | `x' = width - x - 1`, `y' = height - y - 1` | `(width/2 - 1, height/2 - 1)` = (119, 159) |
| any other, including 7 | left as stored | left as stored | `(width/2, height/2)` = (120, 160) |

All 32 captures are mode 7. Modes 1, 2, and 5 are implemented as in the DLL, but this set does not contain them.

Minimum and maximum coordinates can fall outside the raster. These photos include `x = 240` or `y = 321`. The software stores them anyway, without clipping. Sometimes the marker is a few pixels from the intensity extreme, and sometimes tens of pixels away. The spot temperature and the coldest or hottest byte are different data: the byte has already been through contrast enhancement.

## Celsius scale

The curve pixel is separate from the crosshair. After reordering, the software takes intensity `Ic` at `(width/2 - 1, height/2 - 1)`. At 240 x 320 that is (119, 159), one pixel up and to the left of the crosshair (120, 160).

With temperatures still in tenths:

- if intensity `p` is greater than or equal to `Ic`, the line joins `(hot anchor, maximum)` to `(Ic, center)`;
- if it is lower, the line joins `(Ic, center)` to `(cold anchor, minimum)`.

```text
raw = p * (Tb - Ta) / (Ib - Ia) + (Ta * Ib - Tb * Ia) / (Ib - Ia)
°C  = raw / 10
```

`(Ia, Ta)` is the first point of the segment and `(Ib, Tb)` the second. When the file is in Fahrenheit, this script converts the result to Celsius with `(°F - 32) / 1.8`. The official program, in that case, keeps the first matrix in the file unit and builds another with `value * 1.8 + 32`. The captures in `images/` are in °C, so the CSV matches the program's matrix.

By construction, the curve pixel equals the center temperature. The crosshair does not. In `IMG 0001.bmp`:

| | Intensity | °C |
|---|---|---|
| Curve (119, 159) | 17 | 13.3 |
| Crosshair (120, 160) | 16 | 12.84705882 |
| Cold anchor | 0 | 5.6 |
| Coldest pixel in that photo | 1 | 6.05294118 |
| Hot anchor | 253 | 21.6 |

The footer minimum is 5.6 °C and the maximum is 21.6 °C. The coldest pixel does not reach 5.6 °C because the cold anchor is intensity 0 and that pixel is 1.

## What cannot be recovered

The sensor delivers much more than 8 bits. Before saving, the camera enhances contrast and stretches the result to 240 x 320. Many different temperatures land on the same byte, and the table for that enhancement is not in the file. Three measured points can pin the curve to the minimum, the maximum, and the center. Any other pixel remains an estimate, and another curve through the same three points is not a better measurement.

The error follows the span of the scene. With less than 2 °C of difference, as in `IMG 0008.bmp` or `IMG 0031.bmp`, it stays under 0.1 °C. In `IMG 0001.bmp` the crosshair already differs by 0.45 °C from the center measurement. In a scene of hundreds of degrees the difference is tens of degrees.

`IMG 0003.bmp` stores a maximum of 431.7 °C and the screen shows OL. `IMG 0004.bmp` stores 429.6 °C, above the -20 °C to 400 °C range published for this camera. Those maxima are in the file, and the camera does not treat them as a normal reading.

For a point that matters, the reading to trust is the spot tool on the camera.

## Official software and other parsers

UNI-T publishes the UTi712S PC Software (June 2022, a Windows `Setup.exe` inside the zip). The logic for this format is in `ImageFile.dll`, in `refreshParam` and in the intensity-to-temperature step. This repository does not include that installer.

The official program uses this same two-segment scale. It does not hide a radiometric plane.

[UNI-T Thermal Utilities](https://github.com/Santi-hr/UNI-T-Thermal-Utilities) documents a similar BMP, the one from the UTi260B. It does not apply to these files: that camera stores 24-bit BMPs, without the 3 pad bytes, and lists the maximum point first. The author describes the same limit in [temperature_issue.md](https://github.com/Santi-hr/UNI-T-Thermal-Utilities/blob/main/docs/temperature_issue.md): the embedded image is already contrast-enhanced, and after the fact only the minimum, the maximum, and the center can be trusted.

## Samples

`images/` contains 32 BMPs taken with a UTi712S, from September 2020 to August 2026. All of them match the format above, in mode 7 and in °C. They are there to check the parser and the scale. They are not a calibration.
