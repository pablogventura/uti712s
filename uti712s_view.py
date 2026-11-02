#!/usr/bin/env python3
"""Viewer for a UNI-T UTi712S BMP: Celsius temperature of each pixel.

Usage:
    uti712s-view
    uti712s-view 'IMG 0001.bmp'

The temperature is the ImageFile.dll two-segment scale, the same one
uti712s_extract.py writes. Opening a file does not export JSON or CSV.
"""
import sys
from pathlib import Path

try:
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, messagebox
except ImportError:
    sys.exit("tkinter is required. On Debian or Ubuntu: sudo apt install python3-tk")

from uti712s_extract import read_capture

_MIN_SCALE = 1
_MAX_SCALE = 6
_DEFAULT_SCALE = 2
_CURVE_COLOR = "#5ec8ff"
_CROSS_COLOR = "#ffd166"
_PIN_COLOR = "#ff4d6d"


class ThermalViewer:
    def __init__(self, path: Path | None) -> None:
        self.root = tk.Tk()
        self.root.title("UTi712S")
        self.root.minsize(760, 520)
        self.capture = None
        self.scale = _DEFAULT_SCALE
        self.pinned = None
        self._source_image = None
        self._display_image = None

        self._file_name = tk.StringVar(value="No file")
        self._cursor_temperature = tk.StringVar(value="")
        self._cursor_detail = tk.StringVar(
            value="Move the pointer over the image to read that pixel's temperature."
        )
        self._pinned_temperature = tk.StringVar(value="")
        self._pinned_detail = tk.StringVar(
            value="No point pinned. Click the image to mark one."
        )
        self._spots = tk.StringVar(value="")
        self._marks = tk.StringVar(value="")

        self._build_widgets()
        self.root.bind("<Control-o>", self._open_dialog)
        self.root.bind("<Control-O>", self._open_dialog)
        self.root.bind("<Escape>", self._unpin)
        self._fit_window()
        if path is not None:
            self.load_path(path)

    def run(self) -> None:
        self.root.mainloop()

    def load_path(self, path: Path) -> None:
        try:
            capture = read_capture(path)
        except (OSError, ValueError) as error:
            messagebox.showerror("Could not open", str(error), parent=self.root)
            return
        self.capture = capture
        self.pinned = None
        self._source_image = self._build_source_image()
        self._fill_summary()
        self._clear_cursor()
        self._fill_pin()
        self.root.title(f"UTi712S - {path.name}")
        self._refresh_display()
        self.root.after_idle(self._center_on_cross)

    def _build_widgets(self) -> None:
        menu = tk.Menu(self.root)
        file_menu = tk.Menu(menu, tearoff=0)
        file_menu.add_command(label="Open...", command=self._open_dialog, accelerator="Ctrl+O")
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.root.destroy)
        menu.add_cascade(label="File", menu=file_menu)
        self.root.config(menu=menu)

        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        view = tk.Frame(self.root)
        view.grid(row=0, column=0, sticky="nsew")
        view.grid_columnconfigure(0, weight=1)
        view.grid_rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            view,
            width=480,
            height=640,
            background="#1c1c1c",
            highlightthickness=0,
            xscrollcommand=self._sync_xscroll,
            yscrollcommand=self._sync_yscroll,
        )
        self.x_scroll = tk.Scrollbar(view, orient="horizontal", command=self.canvas.xview)
        self.y_scroll = tk.Scrollbar(view, orient="vertical", command=self.canvas.yview)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.y_scroll.grid(row=0, column=1, sticky="ns")
        self.x_scroll.grid(row=1, column=0, sticky="ew")
        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Leave>", self._on_leave)
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<Button-4>", self._on_wheel)
        self.canvas.bind("<Button-5>", self._on_wheel)

        # Wrap by character count, not a fixed pixel width. A short wraplength
        # splits every sentence when the font is large.
        digit_width = tkfont.nametofont("TkDefaultFont").measure("0")
        wraplength = digit_width * 28
        panel_width = wraplength + 16

        holder = tk.Frame(self.root)
        holder.grid(row=0, column=1, sticky="ns")
        holder.grid_rowconfigure(0, weight=1)
        self.panel_canvas = tk.Canvas(
            holder,
            width=panel_width,
            height=640,
            highlightthickness=0,
            yscrollcommand=self._sync_panel_scroll,
        )
        self.panel_scroll = tk.Scrollbar(holder, orient="vertical", command=self.panel_canvas.yview)
        self.panel_canvas.grid(row=0, column=0, sticky="ns")
        self.panel_scroll.grid(row=0, column=1, sticky="ns")

        panel = tk.Frame(self.panel_canvas, padx=12, pady=12)
        self.panel = panel
        self._panel_window = self.panel_canvas.create_window((0, 0), window=panel, anchor="nw")
        panel.bind("<Configure>", self._on_panel_configure)
        self.panel_canvas.bind("<Configure>", self._on_panel_canvas_configure)

        tk.Label(panel, textvariable=self._file_name, anchor="w", justify="left", wraplength=wraplength).grid(
            row=0, column=0, sticky="ew"
        )
        self._add_section(panel, 1, "Under the pointer", wraplength)
        tk.Label(panel, textvariable=self._cursor_temperature, anchor="w", font=("TkDefaultFont", 18)).grid(
            row=2, column=0, sticky="w", pady=(4, 0)
        )
        tk.Label(panel, textvariable=self._cursor_detail, anchor="w", justify="left", wraplength=wraplength).grid(
            row=3, column=0, sticky="ew"
        )
        self._add_section(panel, 4, "Pinned point", wraplength)
        tk.Label(panel, textvariable=self._pinned_temperature, anchor="w", font=("TkDefaultFont", 14)).grid(
            row=5, column=0, sticky="w", pady=(4, 0)
        )
        tk.Label(panel, textvariable=self._pinned_detail, anchor="w", justify="left", wraplength=wraplength).grid(
            row=6, column=0, sticky="ew"
        )
        self._add_section(panel, 7, "Camera readings", wraplength)
        tk.Label(panel, textvariable=self._spots, anchor="w", justify="left", wraplength=wraplength).grid(
            row=8, column=0, sticky="ew", pady=(4, 0)
        )
        tk.Label(panel, textvariable=self._marks, anchor="w", justify="left", wraplength=wraplength).grid(
            row=9, column=0, sticky="ew", pady=(12, 0)
        )
        tk.Label(
            panel,
            text=(
                "Mouse wheel over the image: zoom in or out, keeping each pixel a block. "
                "Click to pin the reading. Click again, or press Escape, to release it."
            ),
            anchor="w",
            justify="left",
            wraplength=wraplength,
        ).grid(row=10, column=0, sticky="ew", pady=(12, 0))
        tk.Label(panel, text=_VIEWER_NOTE, anchor="w", justify="left", wraplength=wraplength).grid(
            row=11, column=0, sticky="ew", pady=(12, 0)
        )
        self._bind_panel_wheel(panel)
        self._bind_panel_wheel(self.panel_canvas)

    def _add_section(self, panel: tk.Frame, row: int, text: str, wraplength: int) -> None:
        tk.Label(
            panel,
            text=text,
            anchor="w",
            justify="left",
            wraplength=wraplength,
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=row, column=0, sticky="ew", pady=(14, 0))

    def _fit_window(self) -> None:
        self.root.update_idletasks()
        screen_h = self.root.winfo_screenheight()
        # 960 fits a 1080 px screen. A taller screen shows more of the text.
        height_cap = 1600 if screen_h > 1400 else 960
        available_h = min(max(520, screen_h - 160), height_cap)
        content_h = self.panel.winfo_reqheight()
        self.panel_canvas.configure(height=min(max(content_h, 640), available_h))
        self.root.update_idletasks()
        width = min(self.root.winfo_reqwidth(), max(760, self.root.winfo_screenwidth() - 40))
        height = min(self.root.winfo_reqheight(), available_h)
        self.root.geometry(f"{width}x{height}")

    def _on_panel_configure(self, _event: tk.Event) -> None:
        self.panel_canvas.configure(scrollregion=self.panel_canvas.bbox("all"))

    def _on_panel_canvas_configure(self, event: tk.Event) -> None:
        self.panel_canvas.itemconfigure(self._panel_window, width=event.width)

    def _bind_panel_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_panel_wheel)
        widget.bind("<Button-4>", self._on_panel_wheel)
        widget.bind("<Button-5>", self._on_panel_wheel)
        for child in widget.winfo_children():
            self._bind_panel_wheel(child)

    def _on_panel_wheel(self, event: tk.Event):
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            self.panel_canvas.yview_scroll(-3, "units")
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            self.panel_canvas.yview_scroll(3, "units")
        return "break"

    def _sync_panel_scroll(self, first: str, last: str) -> None:
        self.panel_scroll.set(first, last)

    def _open_dialog(self, _event=None) -> None:
        if self.capture is not None:
            initial = self.capture.path.parent
        else:
            images = Path(__file__).resolve().parent / "images"
            initial = images if images.is_dir() else Path.cwd()
        selected = filedialog.askopenfilename(
            title="Open BMP",
            initialdir=str(initial),
            filetypes=[("BMP", "*.bmp"), ("All files", "*.*")],
            parent=self.root,
        )
        if selected:
            self.load_path(Path(selected))

    def _unpin(self, _event=None) -> None:
        if self.pinned is None:
            return
        self.pinned = None
        self._fill_pin()
        self._draw_marks()

    def _fill_summary(self) -> None:
        capture = self.capture
        emissivity = f"{capture.emissivity_raw / 100:.2f}"
        self._file_name.set(capture.path.name)
        if capture.emissivity_raw == 95:
            emissivity_text = (
                f"Emissivity {emissivity}. The value set on the camera. "
                "0.95 is the factory setting."
            )
        else:
            emissivity_text = f"Emissivity {emissivity}. The value set on the camera."
        minimum = _format_measurement(capture.minimum_raw / 10, capture.unit_name)
        maximum = _format_measurement(capture.maximum_raw / 10, capture.unit_name)
        center = _format_measurement(capture.center_raw / 10, capture.unit_name)
        self._spots.set("\n\n".join((
            f"Minimum {minimum}. The coldest spot the camera measured.",
            f"Maximum {maximum}. The hottest spot the camera measured.",
            (
                f"Center {center}. The center reading. The cyan square "
                "lands on this value. Every other pixel is estimated from these three."
            ),
            emissivity_text,
            _mode_sentence(capture.mode),
        )))
        self._marks.set(_marks_text(capture))

    def _clear_cursor(self) -> None:
        self._cursor_temperature.set("")
        self._cursor_detail.set("Move the pointer over the image to read that pixel's temperature.")

    def _fill_pin(self) -> None:
        if self.capture is None or self.pinned is None:
            self._pinned_temperature.set("")
            self._pinned_detail.set("No point pinned. Click the image to mark one.")
            return
        x, y = self.pinned
        level = self.capture.level_at(x, y)
        lines = [
            _point_text(x, y),
            _brightness_text(level),
        ]
        role = _role_text(self.capture, x, y)
        if role:
            lines.append(role)
        self._pinned_temperature.set(_format_celsius(self.capture.celsius_at(x, y)))
        self._pinned_detail.set("\n".join(lines))

    def _build_source_image(self) -> tk.PhotoImage:
        capture = self.capture
        photo = tk.PhotoImage(width=capture.width, height=capture.height)
        palette = capture.palette_rgb
        levels = capture.levels
        for y in range(capture.height):
            row_start = y * capture.width
            colors = []
            for x in range(capture.width):
                offset = levels[row_start + x] * 3
                red = palette[offset]
                green = palette[offset + 1]
                blue = palette[offset + 2]
                colors.append(f"#{red:02x}{green:02x}{blue:02x}")
            # Brace each color. Otherwise Tk treats # as a comment and leaves
            # the rest of the row black.
            row = "{" + " ".join("{" + color + "}" for color in colors) + "}"
            photo.put(row, to=(0, y))
        return photo

    def _refresh_display(self) -> None:
        if self._source_image is None or self.capture is None:
            return
        if self.scale == 1:
            self._display_image = self._source_image
        else:
            self._display_image = self._source_image.zoom(self.scale, self.scale)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self._display_image, anchor="nw", tags="scene")
        width = self.capture.width * self.scale
        height = self.capture.height * self.scale
        self.canvas.configure(scrollregion=(0, 0, width, height))
        self._draw_marks()

    def _draw_marks(self) -> None:
        self.canvas.delete("mark")
        if self.capture is None:
            return
        curve_x, curve_y = self.capture.curve_point
        cross_x, cross_y = self.capture.center_point
        self._draw_square(curve_x, curve_y, _CURVE_COLOR, outset=0)
        self._draw_cross(cross_x, cross_y)
        if self.pinned is not None:
            pin_x, pin_y = self.pinned
            self._draw_square(pin_x, pin_y, _PIN_COLOR, outset=3)

    def _draw_square(self, x: int, y: int, color: str, outset: int) -> None:
        scale = self.scale
        left = x * scale - outset
        top = y * scale - outset
        right = (x + 1) * scale + outset
        bottom = (y + 1) * scale + outset
        self.canvas.create_rectangle(
            left,
            top,
            right,
            bottom,
            outline=color,
            width=2 if scale >= 2 else 1,
            tags="mark",
        )

    def _draw_cross(self, x: int, y: int) -> None:
        scale = self.scale
        center_x = x * scale + scale / 2
        center_y = y * scale + scale / 2
        arm = max(scale, 3)
        width = 2 if scale >= 2 else 1
        self.canvas.create_line(
            center_x - arm, center_y, center_x + arm, center_y, fill=_CROSS_COLOR, width=width, tags="mark"
        )
        self.canvas.create_line(
            center_x, center_y - arm, center_x, center_y + arm, fill=_CROSS_COLOR, width=width, tags="mark"
        )

    def _center_on_cross(self) -> None:
        if self.capture is None:
            return
        x, y = self.capture.center_point
        scale = self.scale
        self._scroll_point_to_widget(
            x * scale + scale / 2,
            y * scale + scale / 2,
            self.canvas.winfo_width() / 2,
            self.canvas.winfo_height() / 2,
        )

    def _on_motion(self, event: tk.Event) -> None:
        point = self._point_at(event)
        if point is None or self.capture is None:
            self._clear_cursor()
            return
        x, y = point
        lines = [_point_text(x, y), _brightness_text(self.capture.level_at(x, y))]
        role = _role_text(self.capture, x, y)
        if role:
            lines.append(role)
        self._cursor_temperature.set(_format_celsius(self.capture.celsius_at(x, y)))
        self._cursor_detail.set("\n".join(lines))

    def _on_leave(self, _event: tk.Event) -> None:
        self._clear_cursor()

    def _on_click(self, event: tk.Event) -> None:
        if self.capture is None:
            return
        if self.pinned is not None:
            self.pinned = None
        else:
            point = self._point_at(event)
            if point is None:
                return
            self.pinned = point
        self._fill_pin()
        self._draw_marks()

    def _on_wheel(self, event: tk.Event) -> None:
        if self.capture is None:
            return
        if event.num == 4 or getattr(event, "delta", 0) > 0:
            step = 1
        elif event.num == 5 or getattr(event, "delta", 0) < 0:
            step = -1
        else:
            return
        new_scale = min(_MAX_SCALE, max(_MIN_SCALE, self.scale + step))
        if new_scale == self.scale:
            return
        canvas_x = self.canvas.canvasx(event.x)
        canvas_y = self.canvas.canvasy(event.y)
        source_x = canvas_x / self.scale
        source_y = canvas_y / self.scale
        self.scale = new_scale
        self._refresh_display()
        self._scroll_point_to_widget(source_x * new_scale, source_y * new_scale, event.x, event.y)

    def _point_at(self, event: tk.Event) -> tuple[int, int] | None:
        if self.capture is None:
            return None
        x = int(self.canvas.canvasx(event.x) // self.scale)
        y = int(self.canvas.canvasy(event.y) // self.scale)
        if not (0 <= x < self.capture.width and 0 <= y < self.capture.height):
            return None
        return x, y

    def _scroll_point_to_widget(self, canvas_x: float, canvas_y: float, widget_x: float, widget_y: float) -> None:
        if self.capture is None:
            return
        width = self.capture.width * self.scale
        height = self.capture.height * self.scale
        view_width = self.canvas.winfo_width()
        view_height = self.canvas.winfo_height()
        left = canvas_x - widget_x
        top = canvas_y - widget_y
        max_left = max(0, width - view_width)
        max_top = max(0, height - view_height)
        left = min(max(0.0, left), max_left)
        top = min(max(0.0, top), max_top)
        if width <= view_width:
            self.canvas.xview_moveto(0)
        else:
            self.canvas.xview_moveto(left / width)
        if height <= view_height:
            self.canvas.yview_moveto(0)
        else:
            self.canvas.yview_moveto(top / height)

    def _sync_xscroll(self, first: str, last: str) -> None:
        self.x_scroll.set(first, last)

    def _sync_yscroll(self, first: str, last: str) -> None:
        self.y_scroll.set(first, last)


def _format_celsius(value: float) -> str:
    return _format_measurement(value, "°C")


def _format_measurement(value: float, unit_name: str) -> str:
    return f"{value:.1f} {unit_name}"


_VIEWER_NOTE = (
    "The number is not the raw sensor reading. The file stores an 8-bit image "
    "and three temperatures: minimum, maximum, and center. Each pixel is "
    "estimated with the same scale the UNI-T software uses."
)


def _point_text(x: int, y: int) -> str:
    return f"Column {x}, row {y}. Columns count from the left and rows from the top."


def _brightness_text(level: int) -> str:
    return f"Brightness {level} of 255. This is the byte stored in the file. The temperature is the Celsius estimate."


def _mode_sentence(mode: int) -> str:
    if mode == 1:
        return "Mode 1. The camera stored the photo in another orientation, and the viewer puts it back."
    if mode in (2, 5):
        return f"Mode {mode}. The photo is rotated 180 degrees from the file order."
    if mode == 7:
        return "Mode 7. Photo orientation. This mode does not rotate the image: the top stays the top."
    return f"Mode {mode}. Photo orientation. The file order is kept."


def _marks_text(capture) -> str:
    curve_x, curve_y = capture.curve_point
    cross_x, cross_y = capture.center_point
    if (curve_x, curve_y) == (cross_x, cross_y):
        return (
            f"In this photo the cyan square and the yellow cross land on the same pixel, "
            f"column {curve_x}, row {curve_y}. That temperature is the center reading."
        )
    return (
        f"Cyan square: curve pixel, column {curve_x}, row {curve_y}. "
        "Its temperature is the center reading.\n"
        f"Yellow cross: center drawn by the software, column {cross_x}, row {cross_y}. "
        "It is a different pixel and can show a different temperature."
    )


def _role_text(capture, x: int, y: int) -> str:
    on_curve = (x, y) == capture.curve_point
    on_cross = (x, y) == capture.center_point
    if on_curve and on_cross:
        return "This pixel is both the curve pixel and the software center."
    if on_curve:
        return "This is the curve pixel: its temperature is the center reading."
    if on_cross:
        return "This is the center drawn by the software. It is not the curve pixel."
    return ""


def main() -> None:
    command = Path(sys.argv[0]).name
    if len(sys.argv) > 2:
        sys.exit(f"Usage: {command} [file.bmp]")
    path = Path(sys.argv[1]) if len(sys.argv) == 2 else None
    ThermalViewer(path).run()


if __name__ == "__main__":
    main()
