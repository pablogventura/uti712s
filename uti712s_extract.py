#!/usr/bin/env python3
"""Extract a UNI-T UTi712S BMP and build the official Celsius matrix.

Usage:
    uti712s-extract 'IMG 0001.bmp'
    python3 uti712s_extract.py 'IMG 0001.bmp'

The Celsius matrix follows the two-segment scale in ImageFile.dll. It is not
the sensor radiometric reading: the file only stores 8-bit intensities and
three spot temperatures.
"""
import csv
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

OFFICIAL_SCALE_NOTE = (
    "Celsius matrix from the UNI-T two-segment scale. "
    "This is not the sensor radiometric reading. The curve pixel "
    "matches the center temperature; every other pixel is interpolated."
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
            raise ValueError("The point is outside the image")
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
    """Read the BMP and prepare the matrix. Does not write files."""
    data = path.read_bytes()
    if len(data) < 26 or data[:2] != b"BM":
        raise ValueError("The file has no BMP header")
    bitmap_length = struct.unpack_from("<I", data, 2)[0]
    width, height = struct.unpack_from("<ii", data, 18)
    if width <= 0 or height <= 0:
        raise ValueError("The BMP geometry is not recognized")
    payload = data[bitmap_length:]
    # 3 pad bytes, 1 intensity byte per pixel,
    # 256 RGB565 colors, and a 26-byte footer.
    expected = 3 + width * height + 512 + 26
    if len(payload) != expected or payload[:3] != b"\x00\x00\x00":
        raise ValueError(
            f"Unrecognized structure: {len(payload)} extra bytes; expected {expected}"
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
        "file": path.name,
        "exported_resolution": [width, height],
        "file_unit": capture.unit_name,
        "orientation_mode": capture.mode,
        "maximum_temperature": capture.maximum_raw / 10,
        "minimum_temperature": capture.minimum_raw / 10,
        "center_temperature": capture.center_raw / 10,
        "emissivity": capture.emissivity_raw / 100,
        "cold_anchor_intensity": capture.cold_anchor,
        "hot_anchor_intensity": capture.hot_anchor,
        "minimum_point_xy": list(capture.minimum_point),
        "maximum_point_xy": list(capture.maximum_point),
        "center_point_xy": list(capture.center_point),
        "curve_pixel_xy": [curve_x, curve_y],
        "curve_intensity": capture.curve_level,
        "cross_intensity": capture.level_at(cross_x, cross_y),
        "curve_celsius": celsius_rows[curve_y][curve_x],
        "cross_celsius": celsius_rows[cross_y][cross_x],
        "minimum_intensity": min(capture.levels),
        "maximum_intensity": max(capture.levels),
        "warning": OFFICIAL_SCALE_NOTE,
    }

    base = path.with_suffix("")
    meta_path = base.with_name(base.name + "_metadata.json")
    intensity_path = base.with_name(base.name + "_intensities.csv")
    celsius_path = base.with_name(base.name + "_celsius.csv")
    meta_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    _write_rows(intensity_path, [
        list(capture.levels[y * width:(y + 1) * width]) for y in range(height)
    ])
    _write_rows(celsius_path, [[_format_celsius(value) for value in row] for row in celsius_rows])
    info["exports"] = [str(meta_path), str(intensity_path), str(celsius_path)]

    try:
        from PIL import Image
    except ImportError:
        return info

    gray = Image.frombytes("L", (width, height), capture.levels)
    gray_path = base.with_name(base.name + "_intensities.png")
    gray.save(gray_path)
    info["exports"].append(str(gray_path))

    indexed = Image.frombytes("P", (width, height), capture.levels)
    indexed.putpalette(capture.palette_rgb)
    color_path = base.with_name(base.name + "_thermal_no_overlay.png")
    indexed.convert("RGB").save(color_path)
    info["exports"].append(str(color_path))
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
    # The official expansion is a bit shift, not *255/31.
    rgb = bytearray(256 * 3)
    for index, (color,) in enumerate(struct.iter_unpack("<H", palette)):
        rgb[index * 3] = ((color >> 11) & 31) << 3
        rgb[index * 3 + 1] = ((color >> 5) & 63) << 2
        rgb[index * 3 + 2] = (color & 31) << 3
    return bytes(rgb)


def _reorder_levels(levels: bytes, width: int, height: int, mode: int) -> bytes:
    # Modes 1, 2, and 5 reorder the map before conversion. Mode 7, the one
    # in these captures, keeps the file order.
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
    # The software ignores the center stored in the footer.
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
    # Below the curve intensity, the segment joins the cold anchor to the
    # center. From that intensity up, it joins the center to the hot anchor.
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
    return f"unknown ({unit})"


def _format_celsius(value: float) -> str:
    return f"{value:.8f}"


def _write_rows(path: Path, rows: list) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.writer(handle).writerows(rows)


def main() -> None:
    command = Path(sys.argv[0]).name
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {command} file.bmp")
    print(json.dumps(extract(Path(sys.argv[1])), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
