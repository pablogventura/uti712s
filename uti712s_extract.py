#!/usr/bin/env python3
"""Extrae el BMP de UNI-T UTi712S y arma la matriz en °C del software oficial.

Uso:
    uti712s-extract 'IMG 0001.bmp'
    python3 uti712s_extract.py 'IMG 0001.bmp'

La matriz en °C sigue la escala de dos tramos de ImageFile.dll. No es la
lectura radiométrica del sensor: el archivo solo guarda intensidades de 8 bits
y tres temperaturas puntuales.
"""
import csv
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

OFFICIAL_SCALE_NOTE = (
    "Matriz en °C con la escala de dos tramos del software de UNI-T. "
    "No es la lectura radiométrica del sensor. El píxel de la curva "
    "queda en la temperatura central; el resto es interpolado."
)


@dataclass(frozen=True)
class Capture:
    path: Path
    width: int
    height: int
    levels: bytes
    palette_rgb: bytes
    unit: int
    unit_name: str
    mode: int
    minimum_raw: int
    maximum_raw: int
    center_raw: int
    cold_anchor: int
    hot_anchor: int
    emissivity_raw: int
    minimum_point: tuple[int, int]
    maximum_point: tuple[int, int]
    center_point: tuple[int, int]
    curve_point: tuple[int, int]
    curve_level: int

    def level_at(self, x: int, y: int) -> int:
        if not (0 <= x < self.width and 0 <= y < self.height):
            raise ValueError("El punto cae fuera de la imagen")
        return self.levels[y * self.width + x]

    def celsius_at(self, x: int, y: int) -> float:
        return _level_to_celsius(
            self.level_at(x, y),
            self.curve_level,
            self.minimum_raw,
            self.maximum_raw,
            self.center_raw,
            self.cold_anchor,
            self.hot_anchor,
            self.unit,
        )


def read_capture(path: Path) -> Capture:
    """Lee el BMP y deja la matriz lista. No escribe archivos."""
    data = path.read_bytes()
    if len(data) < 26 or data[:2] != b"BM":
        raise ValueError("El archivo no tiene cabecera BMP")
    bitmap_length = struct.unpack_from("<I", data, 2)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    if width <= 0 or height <= 0:
        raise ValueError("No se reconoce la geometría del BMP")
    payload = data[bitmap_length:]
    # 3 bytes de relleno, 1 byte de intensidad por píxel,
    # 256 colores RGB565 y el pie de 26 bytes.
    expected = 3 + width * height + 512 + 26
    if len(payload) != expected or payload[:3] != b"\x00\x00\x00":
        raise ValueError(
            f"Estructura no reconocida: {len(payload)} bytes adicionales; esperados {expected}"
        )

    levels = payload[3:3 + width * height]
    palette = payload[3 + width * height:3 + width * height + 512]
    header = _read_footer(payload[-26:])
    ordered = _reorder_levels(levels, width, height, header["mode"])
    curve_x = width // 2 - 1
    curve_y = height // 2 - 1
    return Capture(
        path=path,
        width=width,
        height=height,
        levels=ordered,
        palette_rgb=_expand_palette(palette),
        unit=header["unit"],
        unit_name=_unit_name(header["unit"]),
        mode=header["mode"],
        minimum_raw=header["minimum_raw"],
        maximum_raw=header["maximum_raw"],
        center_raw=header["center_raw"],
        cold_anchor=header["cold_anchor"],
        hot_anchor=header["hot_anchor"],
        emissivity_raw=header["emissivity_raw"],
        minimum_point=_map_point(
            header["minimum_x"], header["minimum_y"], width, height, header["mode"]
        ),
        maximum_point=_map_point(
            header["maximum_x"], header["maximum_y"], width, height, header["mode"]
        ),
        center_point=_marker_center(width, height, header["mode"]),
        curve_point=(curve_x, curve_y),
        curve_level=ordered[curve_y * width + curve_x],
    )


def extract(path: Path) -> dict:
    capture = read_capture(path)
    width = capture.width
    height = capture.height
    celsius_rows = [
        [capture.celsius_at(x, y) for x in range(width)]
        for y in range(height)
    ]
    curve_x, curve_y = capture.curve_point
    cross_x, cross_y = capture.center_point
    info = {
        "archivo": path.name,
        "resolucion_exportada": [width, height],
        "unidad_archivo": capture.unit_name,
        "modo_orientacion": capture.mode,
        "temperatura_maxima": capture.maximum_raw / 10,
        "temperatura_minima": capture.minimum_raw / 10,
        "temperatura_central": capture.center_raw / 10,
        "emisividad": capture.emissivity_raw / 100,
        "ancla_fria_intensidad": capture.cold_anchor,
        "ancla_caliente_intensidad": capture.hot_anchor,
        "punto_minimo_xy": list(capture.minimum_point),
        "punto_maximo_xy": list(capture.maximum_point),
        "punto_central_xy": list(capture.center_point),
        "pixel_curva_xy": [curve_x, curve_y],
        "intensidad_curva": capture.curve_level,
        "intensidad_cruz": capture.level_at(cross_x, cross_y),
        "celsius_curva": celsius_rows[curve_y][curve_x],
        "celsius_cruz": celsius_rows[cross_y][cross_x],
        "intensidad_minima": min(capture.levels),
        "intensidad_maxima": max(capture.levels),
        "advertencia": OFFICIAL_SCALE_NOTE,
    }

    base = path.with_suffix("")
    meta_path = base.with_name(base.name + "_metadatos.json")
    intensity_path = base.with_name(base.name + "_intensidades.csv")
    celsius_path = base.with_name(base.name + "_celsius.csv")
    meta_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_rows(intensity_path, [
        list(capture.levels[y * width:(y + 1) * width]) for y in range(height)
    ])
    _write_rows(celsius_path, [[_format_celsius(value) for value in row] for row in celsius_rows])
    info["exportaciones"] = [str(meta_path), str(intensity_path), str(celsius_path)]

    try:
        from PIL import Image
    except ImportError:
        return info

    gray = Image.frombytes("L", (width, height), capture.levels)
    gray_path = base.with_name(base.name + "_intensidades.png")
    gray.save(gray_path)
    info["exportaciones"].append(str(gray_path))

    indexed = Image.frombytes("P", (width, height), capture.levels)
    indexed.putpalette(capture.palette_rgb)
    color_path = base.with_name(base.name + "_termica_sin_indicadores.png")
    indexed.convert("RGB").save(color_path)
    info["exportaciones"].append(str(color_path))
    return info


def _read_footer(footer: bytes) -> dict:
    maximum_raw, minimum_raw = struct.unpack_from("<hh", footer, 1)
    center_raw = struct.unpack_from("<h", footer, 7)[0]
    minimum_x, minimum_y, maximum_x, maximum_y, center_x, center_y = struct.unpack_from("<6H", footer, 14)
    return {
        "unit": footer[0],
        "maximum_raw": maximum_raw,
        "minimum_raw": minimum_raw,
        "hot_anchor": footer[5],
        "cold_anchor": footer[6],
        "center_raw": center_raw,
        "emissivity_raw": footer[9],
        "mode": footer[10],
        "minimum_x": minimum_x,
        "minimum_y": minimum_y,
        "maximum_x": maximum_x,
        "maximum_y": maximum_y,
        "stored_center_x": center_x,
        "stored_center_y": center_y,
    }


def _expand_palette(palette: bytes) -> bytes:
    # La expansión del software es un desplazamiento, no *255/31.
    rgb = bytearray(256 * 3)
    for index, (color,) in enumerate(struct.iter_unpack("<H", palette)):
        rgb[index * 3] = ((color >> 11) & 31) << 3
        rgb[index * 3 + 1] = ((color >> 5) & 63) << 2
        rgb[index * 3 + 2] = (color & 31) << 3
    return bytes(rgb)


def _reorder_levels(levels: bytes, width: int, height: int, mode: int) -> bytes:
    # Modos 1, 2 y 5 reordenan el mapa antes de convertir. El 7, el de
    # estas capturas, lo deja en el orden del archivo.
    if mode == 1:
        ordered = bytearray(width * height)
        for row in range(height):
            for column in range(width):
                source = height * (width - column - 1) + row
                ordered[row * width + column] = levels[source]
        return bytes(ordered)
    if mode in (2, 5):
        return levels[::-1]
    return levels


def _map_point(x: int, y: int, width: int, height: int, mode: int) -> tuple[int, int]:
    if mode == 1:
        return width - y - 1, x - 1
    if mode in (2, 5):
        return width - x - 1, height - y - 1
    return x, y


def _marker_center(width: int, height: int, mode: int) -> tuple[int, int]:
    # El software no usa el centro guardado en el pie.
    if mode == 1:
        return height // 2 - 1, width // 2 - 1
    if mode in (2, 5):
        return width // 2 - 1, height // 2 - 1
    return width // 2, height // 2


def _level_to_celsius(
    level: int,
    curve_level: int,
    minimum_raw: int,
    maximum_raw: int,
    center_raw: int,
    cold_anchor: int,
    hot_anchor: int,
    unit: int,
) -> float:
    # Por debajo de la intensidad de la curva, el tramo une la ancla fría
    # con el centro. Desde esa intensidad, une el centro con la ancla caliente.
    if level >= curve_level:
        intensity_a = hot_anchor
        temperature_a = maximum_raw
        intensity_b = curve_level
        temperature_b = center_raw
    else:
        intensity_a = curve_level
        temperature_a = center_raw
        intensity_b = cold_anchor
        temperature_b = minimum_raw
    span = float(intensity_b - intensity_a)
    raw = (
        level * (temperature_b - temperature_a)
        + (temperature_a * intensity_b - temperature_b * intensity_a)
    ) / span
    measured = raw / 10.0
    if unit == 1:
        return (measured - 32.0) / 1.8
    return measured


def _unit_name(unit: int) -> str:
    if unit == 0:
        return "°C"
    if unit == 1:
        return "°F"
    return f"desconocida ({unit})"


def _format_celsius(value: float) -> str:
    return f"{value:.8f}"


def _write_rows(path: Path, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def main() -> None:
    command = Path(sys.argv[0]).name
    if len(sys.argv) != 2:
        sys.exit(f"Uso: {command} archivo.bmp")
    print(json.dumps(extract(Path(sys.argv[1])), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
