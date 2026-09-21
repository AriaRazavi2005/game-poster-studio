"""
poster_studio.gui.main_window
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Master Desktop GUI for Game Poster Studio recreating the visual layout,
controls, and styling workflow of Windows Collage Maker.

Implements a dual-engine architecture:
- Primary Engine: CustomTkinter (Windows 11 Fluent dark-mode UI).
- Fallback Engine: Pure native Tkinter & ttk with dark palette styling.
"""

from __future__ import annotations

import argparse
import logging
import math
from pathlib import Path
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from PIL import Image

from poster_studio.core.processor import PosterConfig
from poster_studio.core.geometry import ASPECT_RATIOS, resolve_canvas_size
from poster_studio.core.palette import (
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
    extract_dominant_colors,
    parse_hex_color,
    rgb_to_hex,
)
from poster_studio.core.watermark import AVAILABLE_FONTS
from poster_studio.gui.preview_engine import (
    CanvasDisplayManager,
    PreviewEngine,
    calculate_preview_dimensions,
)
from poster_studio.gui.export_engine import ExportEngine, prompt_save_path

logger = logging.getLogger("poster_studio.gui.main")

# Check CustomTkinter availability
try:
    import customtkinter as ctk
    HAS_CUSTOMTKINTER = True
except ImportError:
    HAS_CUSTOMTKINTER = False


# ==============================================================================
# Model (Single Source of Truth)
# ==============================================================================

class PosterStudioModel:
    """
    Application State Model managing PosterConfig, source images,
    palette extraction, and preview/export execution.
    """

    def __init__(
        self,
        initial_ratio: str = "4:5",
        initial_image: Optional[Union[str, Path, Image.Image]] = None
    ) -> None:
        self.config = PosterConfig(ratio=initial_ratio)
        self.raw_image: Optional[Image.Image] = None
        self.source_path: Optional[Path] = None
        self.active_palette: Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = None
        self.rendered_preview: Optional[Image.Image] = None

        self._observers: List[Callable[[], None]] = []

        # Headless-safe Preview and Export engines
        self.preview_engine = PreviewEngine()
        self.export_engine = ExportEngine()

        if initial_image is not None:
            self.load_image(initial_image)

    def subscribe(self, observer: Callable[[], None]) -> None:
        """Subscribes an observer callback to model state mutations."""
        if observer not in self._observers:
            self._observers.append(observer)

    def unsubscribe(self, observer: Callable[[], None]) -> None:
        """Unsubscribes an observer callback."""
        if observer in self._observers:
            self._observers.remove(observer)

    def notify(self) -> None:
        """Notifies all registered observers of state mutation."""
        for observer in list(self._observers):
            try:
                observer()
            except Exception as e:
                logger.error("Observer notification error: %s", e, exc_info=True)

    def load_image(self, source: Union[str, Path, Image.Image]) -> None:
        """Loads and validates a new source game poster image."""
        if isinstance(source, (str, Path)):
            src_path = Path(source)
            if not src_path.is_file():
                raise FileNotFoundError(f"Image file not found: {src_path}")
            if src_path.stat().st_size == 0:
                raise ValueError(f"Image file is empty (0 bytes): {src_path}")
            try:
                with Image.open(src_path) as img:
                    img.load()
                    loaded = img.convert("RGB")
                self.source_path = src_path
            except Exception as e:
                raise ValueError(f"Failed to open image {src_path}: {e}") from e
        elif isinstance(source, Image.Image):
            loaded = source.copy().convert("RGB")
            self.source_path = None
        else:
            raise TypeError(f"Invalid image source type: {type(source)}")

        if loaded.width <= 0 or loaded.height <= 0:
            raise ValueError(f"Invalid image dimensions: {loaded.size}")

        self.raw_image = loaded
        self.preview_engine.set_source_image(self.raw_image)

        # Extract vibrant palette
        p_img = self.preview_engine.preview_raw_image or self.raw_image
        self.active_palette = extract_dominant_colors(p_img)

        # Apply auto palette if configured
        if self.config.auto_colors:
            self.config.color1 = self.active_palette[0]
            self.config.color2 = self.active_palette[1]

        self.notify()

    def reset_config(self) -> None:
        """Restores default configuration parameters."""
        saved_c1 = self.active_palette[0] if self.active_palette else None
        saved_c2 = self.active_palette[1] if self.active_palette else None

        self.config = PosterConfig(
            ratio="4:5",
            hd=False,
            margin=50,
            curve=45,
            zoom=1.0,
            auto_colors=True,
            color1=saved_c1,
            color2=saved_c2,
            swap_colors=False,
            angle=135.0,
            drop_shadow=True,
            watermark="BAZYEPC",
            watermark_size=28
        )
        self.notify()

    def set_spacing(self, val: Union[int, float]) -> None:
        """Sets margin / spacing (0-150px)."""
        self.config.margin = max(0, int(round(val)))
        self.notify()

    def set_curve(self, val: Union[int, float]) -> None:
        """Sets corner radius / curve (0-120px)."""
        self.config.curve = max(0, int(round(val)))
        self.notify()

    def set_zoom(self, val: float) -> None:
        """Sets poster zoom (0.5x - 2.0x)."""
        self.config.zoom = max(0.1, min(3.0, round(float(val), 3)))
        self.notify()

    def set_ratio(self, ratio: str, hd: Optional[bool] = None) -> None:
        """Sets aspect ratio preset."""
        if ratio in ASPECT_RATIOS:
            self.config.ratio = ratio
        if hd is not None:
            self.config.hd = bool(hd)
        self.notify()

    def set_hd(self, hd: bool) -> None:
        """Toggles HD resolution mode."""
        self.config.hd = bool(hd)
        self.notify()

    def set_color1(self, color: Union[str, Tuple[int, int, int]]) -> None:
        """Sets gradient start color."""
        self.config.color1 = parse_hex_color(color) if isinstance(color, str) else color
        self.config.auto_colors = False
        self.notify()

    def set_color2(self, color: Union[str, Tuple[int, int, int]]) -> None:
        """Sets gradient end color."""
        self.config.color2 = parse_hex_color(color) if isinstance(color, str) else color
        self.config.auto_colors = False
        self.notify()

    def swap_colors(self) -> None:
        """Inverts gradient start and end colors."""
        c1 = self.config.color1 or (self.active_palette[0] if self.active_palette else DEFAULT_FALLBACK_C1)
        c2 = self.config.color2 or (self.active_palette[1] if self.active_palette else DEFAULT_FALLBACK_C2)
        self.config.color1 = c2
        self.config.color2 = c1
        self.config.auto_colors = False
        self.notify()

    def auto_detect_colors(self) -> None:
        """Re-extracts vibrant dominant colors from loaded image."""
        if self.raw_image is not None:
            p_img = self.preview_engine.preview_raw_image or self.raw_image
            self.active_palette = extract_dominant_colors(p_img)
            self.config.color1 = self.active_palette[0]
            self.config.color2 = self.active_palette[1]
        self.config.auto_colors = True
        self.notify()

    def set_angle(self, angle: float) -> None:
        """Sets gradient rotation angle (0-360 deg)."""
        self.config.angle = float(angle) % 360.0
        self.notify()

    def set_drop_shadow(self, enabled: bool) -> None:
        """Enables or disables 3D Gaussian drop shadow."""
        self.config.drop_shadow = bool(enabled)
        self.notify()

    def set_pan(self, pan_x: float, pan_y: float) -> None:
        """Sets poster pan offset coordinates."""
        self.config.pan_x = float(pan_x)
        self.config.pan_y = float(pan_y)
        self.notify()

    def reset_pan(self) -> None:
        """Resets poster pan offset to center (0, 0)."""
        self.config.pan_x = 0.0
        self.config.pan_y = 0.0
        self.notify()

    def set_watermark_position(self, x: Optional[float], y: Optional[float]) -> None:
        """Sets watermark position (normalized 0.0-1.0 or pixel coordinates)."""
        self.config.watermark_x = x
        self.config.watermark_y = y
        self.notify()

    def reset_watermark_position(self) -> None:
        """Resets watermark position to default bottom-center."""
        self.config.watermark_x = None
        self.config.watermark_y = None
        self.notify()

    def set_watermark_font(self, font_name: Optional[str]) -> None:
        """Sets font family / file name for watermark."""
        self.config.watermark_font = font_name
        self.notify()

    def set_watermark_colors(
        self,
        text_color: Optional[Union[str, Tuple[int, int, int]]] = None,
        stroke_color: Optional[Union[str, Tuple[int, int, int]]] = None,
        stroke_width: Optional[int] = None
    ) -> None:
        """Sets watermark text color, stroke color, and outline width."""
        if text_color is not None:
            self.config.watermark_color = text_color
        if stroke_color is not None:
            self.config.watermark_stroke_color = stroke_color
        if stroke_width is not None:
            self.config.watermark_stroke_width = max(0, min(20, int(stroke_width)))
        self.config.normalize()
        self.notify()

    def set_watermark(
        self,
        text: Optional[str],
        size: Optional[int] = None,
        stroke: Optional[int] = None,
        color: Optional[str] = None
    ) -> None:
        """Updates watermark branding parameters."""
        self.config.watermark = text.strip() if (text and text.strip()) else None
        if size is not None:
            self.config.watermark_size = max(8, min(120, int(size)))
        if stroke is not None:
            self.config.watermark_stroke_width = max(0, min(20, int(stroke)))
        if color is not None:
            self.config.watermark_color = color
        self.config.normalize()
        self.notify()

    def generate_preview_image(
        self,
        viewport_size: Tuple[int, int] = (600, 750)
    ) -> Image.Image:
        """
        Synchronously generates preview image (ideal for headless tests).
        """
        if self.raw_image is None:
            # Generate empty placeholder preview
            pw, ph, _ = calculate_preview_dimensions(
                full_canvas_size=resolve_canvas_size(self.config.ratio, hd=self.config.hd),
                viewport_max_size=viewport_size
            )
            return Image.new("RGB", (pw, ph), (24, 24, 27))

        rendered = self.preview_engine.render_sync(self.config, viewport_size=viewport_size)
        self.rendered_preview = rendered
        return rendered

    def export_poster(
        self,
        output_path: Union[str, Path],
        format: Optional[str] = None,
        quality: Optional[int] = None
    ) -> Tuple[Path, int]:
        """
        Synchronously exports high-resolution poster to disk.
        """
        if self.raw_image is None:
            raise ValueError("No source image loaded to export.")
        return self.export_engine.export_sync(
            raw_image=self.raw_image,
            config=self.config,
            output_path=output_path,
            format=format,
            quality=quality
        )


# ==============================================================================
# View & Controller (Dual-Engine: CustomTkinter / Tkinter)
# ==============================================================================

class MainWindow:
    """
    Main Application Window providing the Collage Maker layout.
    Operates seamlessly under CustomTkinter or dark-themed native Tkinter.
    """

    def __init__(
        self,
        model: Optional[PosterStudioModel] = None,
        force_tkinter: bool = False,
        theme: str = "dark"
    ) -> None:
        self.model = model or PosterStudioModel()
        self.force_tkinter = force_tkinter
        self.use_ctk = (HAS_CUSTOMTKINTER and not force_tkinter)

        # Ensure Tcl/Tk environment paths on Windows if unconfigured
        if sys.platform == "win32":
            import os
            prefix = Path(sys.base_prefix)
            tcl_path = prefix / "tcl" / "tcl8.6"
            tk_path = prefix / "tcl" / "tk8.6"
            if tcl_path.is_dir() and "TCL_LIBRARY" not in os.environ:
                os.environ["TCL_LIBRARY"] = str(tcl_path)
            if tk_path.is_dir() and "TK_LIBRARY" not in os.environ:
                os.environ["TK_LIBRARY"] = str(tk_path)

        # Deferred Tkinter imports
        import tkinter as tk
        from tkinter import ttk, filedialog, messagebox
        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox

        # Initialize root window
        if self.use_ctk:
            ctk.set_appearance_mode(theme)
            ctk.set_default_color_theme("blue")
            self.root = ctk.CTk()
        else:
            self.root = tk.Tk()
            self._apply_dark_ttk_theme()

        self.root.title("Game Poster Studio — Windows Collage Maker")
        self.root.minsize(1120, 760)
        self.root.geometry("1280x820")

        # Configure root grid weights
        self.root.columnconfigure(0, weight=0, minsize=360)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=0, minsize=52)
        self.root.rowconfigure(1, weight=1)
        self.root.rowconfigure(2, weight=0, minsize=28)

        # Internal state
        self._updating_ui = False
        self.active_format = "JPEG"

        # Mouse interaction & dragging state
        self._drag_target: Optional[str] = None  # 'watermark' or 'poster'
        self._drag_start_x: int = 0
        self._drag_start_y: int = 0
        self._has_dragged: bool = False

        # Initialize engines attached to root
        self.preview_engine = PreviewEngine(
            root=self.root,
            on_preview_rendered=self._on_preview_rendered
        )
        self.export_engine = ExportEngine(root=self.root)

        # Build UI layout
        self._build_header()
        self._build_sidebar()
        self._build_viewport()
        self._build_statusbar()

        # Canvas display manager
        self.display_manager = CanvasDisplayManager(self.canvas_preview)

        # Wire model listener
        self.model.subscribe(self._on_model_changed)

        # Bind window resize on canvas
        self.canvas_preview.bind("<Configure>", self._on_canvas_resize)

        # Synchronize initial state
        self._sync_widgets_from_model()

        # If model already has an image, render preview
        if self.model.raw_image is not None:
            self.preview_engine.set_source_image(self.model.raw_image)
            self._request_preview()

    def _apply_dark_ttk_theme(self) -> None:
        """Applies a modern dark palette to native Tkinter / ttk widgets."""
        self.root.configure(bg="#18181b")
        style = self.ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # Dark theme palette
        bg_dark = "#18181b"
        bg_card = "#27272a"
        bg_input = "#1f1f23"
        fg_text = "#f4f4f5"
        fg_muted = "#a1a1aa"
        accent = "#2563eb"

        style.configure(".", background=bg_dark, foreground=fg_text)
        style.configure("TFrame", background=bg_dark)
        style.configure("Card.TFrame", background=bg_card)
        style.configure("TLabel", background=bg_dark, foreground=fg_text, font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=bg_card, foreground=fg_text, font=("Segoe UI", 10))
        style.configure("Header.TLabel", background=bg_dark, foreground=fg_text, font=("Segoe UI", 12, "bold"))
        style.configure("Subheader.TLabel", background=bg_card, foreground=fg_muted, font=("Segoe UI", 9, "bold"))

        style.configure(
            "TButton",
            background=bg_card,
            foreground=fg_text,
            borderwidth=1,
            focuscolor=accent,
            font=("Segoe UI", 9)
        )
        style.map("TButton", background=[("active", accent), ("pressed", "#1d4ed8")])

        style.configure(
            "Primary.TButton",
            background=accent,
            foreground="#ffffff",
            font=("Segoe UI", 10, "bold")
        )
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("pressed", "#1e40af")])

        style.configure("TNotebook", background=bg_dark, borderwidth=0)
        style.configure("TNotebook.Tab", background=bg_card, foreground=fg_muted, padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", "#ffffff")])

        style.configure("TEntry", fieldbackground=bg_input, foreground=fg_text)
        style.configure("TCheckbutton", background=bg_card, foreground=fg_text)

    # --------------------------------------------------------------------------
    # UI Layout Construction
    # --------------------------------------------------------------------------

    def _build_header(self) -> None:
        """Builds top toolbar bar (Row 0)."""
        if self.use_ctk:
            header = ctk.CTkFrame(self.root, height=52, corner_radius=0, fg_color="#18181b")
            header.grid(row=0, column=0, columnspan=2, sticky="new", padx=0, pady=0)

            # App brand
            self.lbl_title = ctk.CTkLabel(
                header,
                text="🎮 GAME POSTER STUDIO",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color="#ffffff"
            )
            self.lbl_title.pack(side="left", padx=16, pady=8)

            # Quick actions
            self.btn_open = ctk.CTkButton(
                header,
                text="📂 Open Image",
                command=self._on_open_image_clicked,
                width=110,
                height=32,
                fg_color="#27272a",
                hover_color="#3f3f46"
            )
            self.btn_open.pack(side="left", padx=8, pady=8)

            self.btn_reset = ctk.CTkButton(
                header,
                text="↺ Reset",
                command=self._on_reset_clicked,
                width=80,
                height=32,
                fg_color="#27272a",
                hover_color="#3f3f46"
            )
            self.btn_reset.pack(side="left", padx=8, pady=8)

            # Export actions
            self.btn_export = ctk.CTkButton(
                header,
                text="💾 Export Poster",
                command=self._on_export_clicked,
                width=120,
                height=32,
                fg_color="#2563eb",
                hover_color="#1d4ed8",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            )
            self.btn_export.pack(side="right", padx=(4, 16), pady=8)

            self.btn_copy = ctk.CTkButton(
                header,
                text="📋 Copy Image",
                command=self._on_copy_clipboard_clicked,
                width=110,
                height=32,
                fg_color="#059669",
                hover_color="#047857",
                font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold")
            )
            self.btn_copy.pack(side="right", padx=4, pady=8)

            self.combo_format = ctk.CTkOptionMenu(
                header,
                values=["JPEG (95%)", "PNG (Lossless)"],
                command=self._on_format_changed,
                width=130,
                height=32,
                fg_color="#27272a",
                button_color="#3f3f46"
            )
            self.combo_format.pack(side="right", padx=4, pady=8)
            self.combo_format.set("JPEG (95%)")

        else:
            # Native Tkinter fallback
            header = self.ttk.Frame(self.root)
            header.grid(row=0, column=0, columnspan=2, sticky="new", padx=0, pady=0)

            self.lbl_title = self.ttk.Label(
                header,
                text="🎮 GAME POSTER STUDIO",
                font=("Segoe UI", 12, "bold")
            )
            self.lbl_title.pack(side="left", padx=16, pady=8)

            self.btn_open = self.ttk.Button(
                header,
                text="📂 Open Image",
                command=self._on_open_image_clicked
            )
            self.btn_open.pack(side="left", padx=8, pady=8)

            self.btn_reset = self.ttk.Button(
                header,
                text="↺ Reset",
                command=self._on_reset_clicked
            )
            self.btn_reset.pack(side="left", padx=8, pady=8)

            self.btn_export = self.ttk.Button(
                header,
                text="💾 Export Poster",
                command=self._on_export_clicked,
                style="Primary.TButton"
            )
            self.btn_export.pack(side="right", padx=(4, 16), pady=8)

            self.btn_copy = self.ttk.Button(
                header,
                text="📋 Copy Image",
                command=self._on_copy_clipboard_clicked
            )
            self.btn_copy.pack(side="right", padx=4, pady=8)

            self.combo_format = self.ttk.Combobox(
                header,
                values=["JPEG (95%)", "PNG (Lossless)"],
                state="readonly",
                width=15
            )
            self.combo_format.pack(side="right", padx=4, pady=8)
            self.combo_format.set("JPEG (95%)")
            self.combo_format.bind("<<ComboboxSelected>>", lambda e: self._on_format_changed(self.combo_format.get()))

    def _build_sidebar(self) -> None:
        """Builds Collage Maker 4-tab control sidebar (Row 1, Col 0)."""
        if self.use_ctk:
            sidebar = ctk.CTkFrame(self.root, width=360, corner_radius=0, fg_color="#1f1f23")
            sidebar.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            sidebar.grid_propagate(False)

            self.tabview = ctk.CTkTabview(sidebar, fg_color="#18181b", segmented_button_selected_color="#2563eb")
            self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

            self.framing_tab = self.tabview.add("Framing")
            self.ratio_tab = self.tabview.add("Aspect Ratio")
            self.background_tab = self.tabview.add("Background")
            self.branding_tab = self.tabview.add("Text / Brand")

            self._populate_framing_tab_ctk(self.framing_tab)
            self._populate_ratio_tab_ctk(self.ratio_tab)
            self._populate_background_tab_ctk(self.background_tab)
            self._populate_branding_tab_ctk(self.branding_tab)

        else:
            sidebar = self.ttk.Frame(self.root, width=360)
            sidebar.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
            sidebar.grid_propagate(False)

            self.tabview = self.ttk.Notebook(sidebar)
            self.tabview.pack(fill="both", expand=True, padx=8, pady=8)

            self.framing_tab = self.ttk.Frame(self.tabview, style="Card.TFrame")
            self.ratio_tab = self.ttk.Frame(self.tabview, style="Card.TFrame")
            self.background_tab = self.ttk.Frame(self.tabview, style="Card.TFrame")
            self.branding_tab = self.ttk.Frame(self.tabview, style="Card.TFrame")

            self.tabview.add(self.framing_tab, text="Framing")
            self.tabview.add(self.ratio_tab, text="Aspect Ratio")
            self.tabview.add(self.background_tab, text="Background")
            self.tabview.add(self.branding_tab, text="Text / Brand")

            self._populate_framing_tab_ttk(self.framing_tab)
            self._populate_ratio_tab_ttk(self.ratio_tab)
            self._populate_background_tab_ttk(self.background_tab)
            self._populate_branding_tab_ttk(self.branding_tab)

    # --- Framing Tab ---
    def _populate_framing_tab_ctk(self, parent: Any) -> None:
        lbl_h = ctk.CTkLabel(parent, text="POSTER FRAMING", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 6))

        # Spacing
        self.lbl_spacing_val = ctk.CTkLabel(parent, text="Spacing (Margin): 50 px", text_color="#f4f4f5")
        self.lbl_spacing_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_spacing = ctk.CTkSlider(
            parent, from_=0, to=150, number_of_steps=150,
            command=self._on_spacing_slider
        )
        self.slider_spacing.pack(fill="x", padx=12, pady=(2, 12))

        # Curve
        self.lbl_curve_val = ctk.CTkLabel(parent, text="Corner Curve: 45 px", text_color="#f4f4f5")
        self.lbl_curve_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_curve = ctk.CTkSlider(
            parent, from_=0, to=120, number_of_steps=120,
            command=self._on_curve_slider
        )
        self.slider_curve.pack(fill="x", padx=12, pady=(2, 12))

        # Zoom
        self.lbl_zoom_val = ctk.CTkLabel(parent, text="Poster Zoom: 1.00x", text_color="#f4f4f5")
        self.lbl_zoom_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_zoom = ctk.CTkSlider(
            parent, from_=0.5, to=3.0, number_of_steps=250,
            command=self._on_zoom_slider
        )
        self.slider_zoom.pack(fill="x", padx=12, pady=(2, 10))

        # Pan Offset & Reset
        self.lbl_pan_val = ctk.CTkLabel(parent, text="Poster Pan: (0, 0) px", text_color="#93c5fd")
        self.lbl_pan_val.pack(anchor="w", padx=12, pady=(4, 0))
        self.btn_reset_pan = ctk.CTkButton(
            parent, text="🔄 Reset Pan & Zoom", command=self._on_reset_pan_clicked,
            height=28, fg_color="#27272a", hover_color="#3f3f46"
        )
        self.btn_reset_pan.pack(fill="x", padx=12, pady=(4, 6))

        ctk.CTkLabel(
            parent,
            text="💡 Mouse: Scroll wheel to zoom, drag poster to pan freely.",
            font=ctk.CTkFont(size=10), text_color="#71717a", wraplength=320, justify="left"
        ).pack(anchor="w", padx=12, pady=(2, 10))

    def _populate_framing_tab_ttk(self, parent: Any) -> None:
        lbl_h = self.ttk.Label(parent, text="POSTER FRAMING", style="Subheader.TLabel")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 6))

        self.lbl_spacing_val = self.ttk.Label(parent, text="Spacing (Margin): 50 px", style="Card.TLabel")
        self.lbl_spacing_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_spacing = self.ttk.Scale(
            parent, from_=0, to=150,
            command=lambda v: self._on_spacing_slider(float(v))
        )
        self.slider_spacing.pack(fill="x", padx=12, pady=(2, 12))

        self.lbl_curve_val = self.ttk.Label(parent, text="Corner Curve: 45 px", style="Card.TLabel")
        self.lbl_curve_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_curve = self.ttk.Scale(
            parent, from_=0, to=120,
            command=lambda v: self._on_curve_slider(float(v))
        )
        self.slider_curve.pack(fill="x", padx=12, pady=(2, 12))

        self.lbl_zoom_val = self.ttk.Label(parent, text="Poster Zoom: 1.00x", style="Card.TLabel")
        self.lbl_zoom_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_zoom = self.ttk.Scale(
            parent, from_=0.5, to=3.0,
            command=lambda v: self._on_zoom_slider(float(v))
        )
        self.slider_zoom.pack(fill="x", padx=12, pady=(2, 10))

        self.lbl_pan_val = self.ttk.Label(parent, text="Poster Pan: (0, 0) px", style="Card.TLabel")
        self.lbl_pan_val.pack(anchor="w", padx=12, pady=(4, 0))
        self.btn_reset_pan = self.ttk.Button(
            parent, text="🔄 Reset Pan & Zoom", command=self._on_reset_pan_clicked
        )
        self.btn_reset_pan.pack(fill="x", padx=12, pady=(4, 6))

        self.ttk.Label(
            parent,
            text="💡 Mouse: Scroll wheel to zoom, drag poster to pan freely.",
            font=("Segoe UI", 8), foreground="#71717a"
        ).pack(anchor="w", padx=12, pady=(2, 10))

    # --- Aspect Ratio Tab ---
    def _populate_ratio_tab_ctk(self, parent: Any) -> None:
        lbl_h = ctk.CTkLabel(parent, text="CANVAS DIMENSIONS", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 8))

        self.segmented_ratio = ctk.CTkSegmentedButton(
            parent,
            values=["4:5", "1:1", "9:16", "16:9", "4:3", "21:9"],
            command=self._on_ratio_selected
        )
        self.segmented_ratio.pack(fill="x", padx=12, pady=(4, 12))
        self.segmented_ratio.set("4:5")

        self.switch_hd = ctk.CTkCheckBox(
            parent,
            text="High-Definition Canvas (e.g. 1440x1800)",
            command=self._on_hd_toggled
        )
        self.switch_hd.pack(anchor="w", padx=12, pady=8)

        self.lbl_dimensions_info = ctk.CTkLabel(
            parent,
            text="Output: 1080 × 1350 px (Instagram / Telegram)",
            text_color="#93c5fd"
        )
        self.lbl_dimensions_info.pack(anchor="w", padx=12, pady=(8, 12))

    def _populate_ratio_tab_ttk(self, parent: Any) -> None:
        lbl_h = self.ttk.Label(parent, text="CANVAS DIMENSIONS", style="Subheader.TLabel")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 8))

        self.ratio_var = self.tk.StringVar(value="4:5")
        ratio_frame = self.ttk.Frame(parent, style="Card.TFrame")
        ratio_frame.pack(fill="x", padx=12, pady=4)

        for r in ["4:5", "1:1", "9:16", "16:9", "4:3", "21:9"]:
            rb = self.ttk.Radiobutton(
                ratio_frame, text=r, value=r, variable=self.ratio_var,
                command=lambda: self._on_ratio_selected(self.ratio_var.get())
            )
            rb.pack(side="left", padx=4, pady=4)

        self.hd_var = self.tk.BooleanVar(value=False)
        self.switch_hd = self.ttk.Checkbutton(
            parent,
            text="High-Definition Canvas (e.g. 1440x1800)",
            variable=self.hd_var,
            command=self._on_hd_toggled
        )
        self.switch_hd.pack(anchor="w", padx=12, pady=8)

        self.lbl_dimensions_info = self.ttk.Label(
            parent,
            text="Output: 1080 × 1350 px (Instagram / Telegram)",
            style="Card.TLabel"
        )
        self.lbl_dimensions_info.pack(anchor="w", padx=12, pady=(8, 12))

    # --- Background Tab ---
    def _populate_background_tab_ctk(self, parent: Any) -> None:
        lbl_h = ctk.CTkLabel(parent, text="GRADIENT BACKDROP", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 6))

        # Color 1 row
        row1 = ctk.CTkFrame(parent, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row1, text="Color 1:", width=60).pack(side="left")
        self.btn_color1_swatch = ctk.CTkButton(
            row1, text="", width=28, height=28, fg_color="#1e1b4b",
            hover_color="#1e1b4b", command=lambda: self._on_pick_color(1)
        )
        self.btn_color1_swatch.pack(side="left", padx=6)
        self.entry_color1 = ctk.CTkEntry(row1, width=100)
        self.entry_color1.pack(side="left", padx=6)
        self.entry_color1.insert(0, "#1e1b4b")
        self.entry_color1.bind("<Return>", lambda e: self._on_hex_entry_changed(1))

        # Color 2 row
        row2 = ctk.CTkFrame(parent, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=4)
        ctk.CTkLabel(row2, text="Color 2:", width=60).pack(side="left")
        self.btn_color2_swatch = ctk.CTkButton(
            row2, text="", width=28, height=28, fg_color="#0284c7",
            hover_color="#0284c7", command=lambda: self._on_pick_color(2)
        )
        self.btn_color2_swatch.pack(side="left", padx=6)
        self.entry_color2 = ctk.CTkEntry(row2, width=100)
        self.entry_color2.pack(side="left", padx=6)
        self.entry_color2.insert(0, "#0284c7")
        self.entry_color2.bind("<Return>", lambda e: self._on_hex_entry_changed(2))

        # Action buttons
        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=8)
        self.btn_autodetect = ctk.CTkButton(
            btn_row, text="⚡ Auto-Detect", width=110, height=28,
            command=self._on_autodetect_clicked
        )
        self.btn_autodetect.pack(side="left", padx=(0, 6))
        self.btn_swap = ctk.CTkButton(
            btn_row, text="⇄ Swap", width=80, height=28,
            command=self._on_swap_clicked
        )
        self.btn_swap.pack(side="left")

        # Angle slider (0-360)
        self.lbl_angle_val = ctk.CTkLabel(parent, text="Gradient Angle: 135°", text_color="#f4f4f5")
        self.lbl_angle_val.pack(anchor="w", padx=12, pady=(8, 0))
        self.slider_angle = ctk.CTkSlider(
            parent, from_=0, to=360, number_of_steps=360,
            command=self._on_angle_slider
        )
        self.slider_angle.pack(fill="x", padx=12, pady=(2, 12))

        # Drop Shadow
        self.chk_shadow = ctk.CTkCheckBox(
            parent, text="Enable 3D Drop Shadow",
            command=self._on_shadow_toggled
        )
        self.chk_shadow.pack(anchor="w", padx=12, pady=6)
        self.chk_shadow.select()

    def _populate_background_tab_ttk(self, parent: Any) -> None:
        lbl_h = self.ttk.Label(parent, text="GRADIENT BACKDROP", style="Subheader.TLabel")
        lbl_h.pack(anchor="w", padx=12, pady=(12, 6))

        row1 = self.ttk.Frame(parent, style="Card.TFrame")
        row1.pack(fill="x", padx=12, pady=4)
        self.ttk.Label(row1, text="Color 1:", width=8, style="Card.TLabel").pack(side="left")
        self.btn_color1_swatch = self.tk.Button(
            row1, width=3, bg="#1e1b4b", relief="flat",
            command=lambda: self._on_pick_color(1)
        )
        self.btn_color1_swatch.pack(side="left", padx=6)
        self.entry_color1 = self.ttk.Entry(row1, width=12)
        self.entry_color1.pack(side="left", padx=6)
        self.entry_color1.insert(0, "#1e1b4b")
        self.entry_color1.bind("<Return>", lambda e: self._on_hex_entry_changed(1))

        row2 = self.ttk.Frame(parent, style="Card.TFrame")
        row2.pack(fill="x", padx=12, pady=4)
        self.ttk.Label(row2, text="Color 2:", width=8, style="Card.TLabel").pack(side="left")
        self.btn_color2_swatch = self.tk.Button(
            row2, width=3, bg="#0284c7", relief="flat",
            command=lambda: self._on_pick_color(2)
        )
        self.btn_color2_swatch.pack(side="left", padx=6)
        self.entry_color2 = self.ttk.Entry(row2, width=12)
        self.entry_color2.pack(side="left", padx=6)
        self.entry_color2.insert(0, "#0284c7")
        self.entry_color2.bind("<Return>", lambda e: self._on_hex_entry_changed(2))

        btn_row = self.ttk.Frame(parent, style="Card.TFrame")
        btn_row.pack(fill="x", padx=12, pady=8)
        self.btn_autodetect = self.ttk.Button(
            btn_row, text="⚡ Auto-Detect", command=self._on_autodetect_clicked
        )
        self.btn_autodetect.pack(side="left", padx=(0, 6))
        self.btn_swap = self.ttk.Button(
            btn_row, text="⇄ Swap", command=self._on_swap_clicked
        )
        self.btn_swap.pack(side="left")

        self.lbl_angle_val = self.ttk.Label(parent, text="Gradient Angle: 135°", style="Card.TLabel")
        self.lbl_angle_val.pack(anchor="w", padx=12, pady=(8, 0))
        self.slider_angle = self.ttk.Scale(
            parent, from_=0, to=360,
            command=lambda v: self._on_angle_slider(float(v))
        )
        self.slider_angle.pack(fill="x", padx=12, pady=(2, 12))

        self.shadow_var = self.tk.BooleanVar(value=True)
        self.chk_shadow = self.ttk.Checkbutton(
            parent, text="Enable 3D Drop Shadow", variable=self.shadow_var,
            command=self._on_shadow_toggled
        )
        self.chk_shadow.pack(anchor="w", padx=12, pady=6)

    # --- Branding Tab ---
    def _populate_branding_tab_ctk(self, parent: Any) -> None:
        lbl_h = ctk.CTkLabel(parent, text="BRANDING & WATERMARK", font=ctk.CTkFont(size=12, weight="bold"), text_color="#a1a1aa")
        lbl_h.pack(anchor="w", padx=12, pady=(10, 4))

        # Watermark text input
        ctk.CTkLabel(parent, text="Watermark Text:").pack(anchor="w", padx=12, pady=(2, 0))
        self.entry_watermark = ctk.CTkEntry(parent)
        self.entry_watermark.pack(fill="x", padx=12, pady=(2, 8))
        self.entry_watermark.insert(0, "BAZYEPC")
        self.entry_watermark.bind("<KeyRelease>", self._on_watermark_text_changed)

        # Gaming font combobox
        ctk.CTkLabel(parent, text="Gaming Font:").pack(anchor="w", padx=12, pady=(2, 0))
        self.combo_font = ctk.CTkComboBox(
            parent,
            values=list(AVAILABLE_FONTS.keys()),
            command=self._on_font_selected,
            height=28
        )
        self.combo_font.pack(fill="x", padx=12, pady=(2, 8))
        self.combo_font.set("Anton (Default Gaming)")

        # Font Size
        self.lbl_watermark_size_val = ctk.CTkLabel(parent, text="Font Size: 28 px")
        self.lbl_watermark_size_val.pack(anchor="w", padx=12, pady=(2, 0))
        self.slider_watermark_size = ctk.CTkSlider(
            parent, from_=12, to=90, number_of_steps=78,
            command=self._on_watermark_size_slider
        )
        self.slider_watermark_size.pack(fill="x", padx=12, pady=(2, 8))

        # Text Fill Color
        lbl_fc = ctk.CTkLabel(parent, text="Text Color:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f4f4f5")
        lbl_fc.pack(anchor="w", padx=12, pady=(4, 0))

        row_fc = ctk.CTkFrame(parent, fg_color="transparent")
        row_fc.pack(fill="x", padx=12, pady=(2, 4))
        self.btn_textcolor_swatch = ctk.CTkButton(
            row_fc, text="", width=26, height=26, fg_color="#ffffff",
            hover_color="#f4f4f5", command=self._on_pick_text_color
        )
        self.btn_textcolor_swatch.pack(side="left", padx=(0, 6))
        self.entry_textcolor = ctk.CTkEntry(row_fc, width=80)
        self.entry_textcolor.pack(side="left", padx=(0, 6))
        self.entry_textcolor.insert(0, "#ffffff")
        self.entry_textcolor.bind("<Return>", lambda e: self._on_text_color_hex(self.entry_textcolor.get()))

        presets_fc = [("#ffffff", "⚪"), ("#facc15", "🟡"), ("#06b6d4", "🔵"), ("#ef4444", "🔴"), ("#22c55e", "🟢")]
        for hex_val, icon in presets_fc:
            b = ctk.CTkButton(
                row_fc, text=icon, width=24, height=24, fg_color="#27272a", hover_color="#3f3f46",
                command=lambda h=hex_val: self._on_set_text_color(h)
            )
            b.pack(side="left", padx=1)

        # Stroke Outline & Color
        self.lbl_stroke_val = ctk.CTkLabel(parent, text="Stroke Width: 3 px", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f4f4f5")
        self.lbl_stroke_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_stroke = ctk.CTkSlider(
            parent, from_=0, to=12, number_of_steps=12,
            command=self._on_stroke_slider
        )
        self.slider_stroke.pack(fill="x", padx=12, pady=(2, 6))

        row_sc = ctk.CTkFrame(parent, fg_color="transparent")
        row_sc.pack(fill="x", padx=12, pady=(2, 6))
        self.btn_strokecolor_swatch = ctk.CTkButton(
            row_sc, text="", width=26, height=26, fg_color="#0f172a",
            hover_color="#1e293b", command=self._on_pick_stroke_color
        )
        self.btn_strokecolor_swatch.pack(side="left", padx=(0, 6))
        self.entry_strokecolor = ctk.CTkEntry(row_sc, width=80)
        self.entry_strokecolor.pack(side="left", padx=(0, 6))
        self.entry_strokecolor.insert(0, "#0f172a")
        self.entry_strokecolor.bind("<Return>", lambda e: self._on_stroke_color_hex(self.entry_strokecolor.get()))

        presets_sc = [("#0f172a", "⚫"), ("#000000", "⬛"), ("#ffffff", "⚪"), ("#7f1d1d", "🟤")]
        for hex_val, icon in presets_sc:
            b = ctk.CTkButton(
                row_sc, text=icon, width=24, height=24, fg_color="#27272a", hover_color="#3f3f46",
                command=lambda h=hex_val: self._on_set_stroke_color(h)
            )
            b.pack(side="left", padx=1)

        # Position Presets & Drag Tip
        ctk.CTkLabel(parent, text="Position Presets:", font=ctk.CTkFont(size=11, weight="bold"), text_color="#f4f4f5").pack(anchor="w", padx=12, pady=(4, 2))
        row_pos = ctk.CTkFrame(parent, fg_color="transparent")
        row_pos.pack(fill="x", padx=12, pady=(2, 6))

        pos_presets = [("⬆️ Top", "top"), ("🌱 Inside", "inside"), ("🖼️ Frame", "frame"), ("🔄 Auto", "reset")]
        for title, key in pos_presets:
            btn = ctk.CTkButton(
                row_pos, text=title, height=26, fg_color="#27272a", hover_color="#3f3f46",
                command=lambda k=key: self._on_set_watermark_preset(k)
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)

        ctk.CTkLabel(
            parent,
            text="💡 Tip: Drag text on canvas with mouse to place anywhere!",
            font=ctk.CTkFont(size=10), text_color="#38bdf8", wraplength=320, justify="left"
        ).pack(anchor="w", padx=12, pady=(4, 8))

    def _populate_branding_tab_ttk(self, parent: Any) -> None:
        lbl_h = self.ttk.Label(parent, text="BRANDING & WATERMARK", style="Subheader.TLabel")
        lbl_h.pack(anchor="w", padx=12, pady=(10, 4))

        self.ttk.Label(parent, text="Watermark Text:", style="Card.TLabel").pack(anchor="w", padx=12, pady=(2, 0))
        self.entry_watermark = self.ttk.Entry(parent)
        self.entry_watermark.pack(fill="x", padx=12, pady=(2, 8))
        self.entry_watermark.insert(0, "BAZYEPC")
        self.entry_watermark.bind("<KeyRelease>", self._on_watermark_text_changed)

        self.ttk.Label(parent, text="Gaming Font:", style="Card.TLabel").pack(anchor="w", padx=12, pady=(2, 0))
        self.combo_font = self.ttk.Combobox(parent, values=list(AVAILABLE_FONTS.keys()), state="readonly")
        self.combo_font.pack(fill="x", padx=12, pady=(2, 8))
        self.combo_font.set("Anton (Default Gaming)")
        self.combo_font.bind("<<ComboboxSelected>>", lambda e: self._on_font_selected(self.combo_font.get()))

        self.lbl_watermark_size_val = self.ttk.Label(parent, text="Font Size: 28 px", style="Card.TLabel")
        self.lbl_watermark_size_val.pack(anchor="w", padx=12, pady=(2, 0))
        self.slider_watermark_size = self.ttk.Scale(
            parent, from_=12, to=90,
            command=lambda v: self._on_watermark_size_slider(float(v))
        )
        self.slider_watermark_size.pack(fill="x", padx=12, pady=(2, 8))

        # Text Color
        self.ttk.Label(parent, text="Text Color:", style="Card.TLabel").pack(anchor="w", padx=12, pady=(4, 0))
        row_fc = self.ttk.Frame(parent, style="Card.TFrame")
        row_fc.pack(fill="x", padx=12, pady=(2, 4))
        self.btn_textcolor_swatch = self.tk.Button(
            row_fc, width=3, bg="#ffffff", relief="flat", command=self._on_pick_text_color
        )
        self.btn_textcolor_swatch.pack(side="left", padx=(0, 6))
        self.entry_textcolor = self.ttk.Entry(row_fc, width=10)
        self.entry_textcolor.pack(side="left", padx=(0, 6))
        self.entry_textcolor.insert(0, "#ffffff")
        self.entry_textcolor.bind("<Return>", lambda e: self._on_text_color_hex(self.entry_textcolor.get()))

        # Stroke Outline
        self.lbl_stroke_val = self.ttk.Label(parent, text="Stroke Width: 3 px", style="Card.TLabel")
        self.lbl_stroke_val.pack(anchor="w", padx=12, pady=(6, 0))
        self.slider_stroke = self.ttk.Scale(
            parent, from_=0, to=12,
            command=lambda v: self._on_stroke_slider(float(v))
        )
        self.slider_stroke.pack(fill="x", padx=12, pady=(2, 6))

        row_sc = self.ttk.Frame(parent, style="Card.TFrame")
        row_sc.pack(fill="x", padx=12, pady=(2, 6))
        self.btn_strokecolor_swatch = self.tk.Button(
            row_sc, width=3, bg="#0f172a", relief="flat", command=self._on_pick_stroke_color
        )
        self.btn_strokecolor_swatch.pack(side="left", padx=(0, 6))
        self.entry_strokecolor = self.ttk.Entry(row_sc, width=10)
        self.entry_strokecolor.pack(side="left", padx=(0, 6))
        self.entry_strokecolor.insert(0, "#0f172a")
        self.entry_strokecolor.bind("<Return>", lambda e: self._on_stroke_color_hex(self.entry_strokecolor.get()))

        # Position presets
        row_pos = self.ttk.Frame(parent, style="Card.TFrame")
        row_pos.pack(fill="x", padx=12, pady=(4, 6))
        pos_presets = [("Top", "top"), ("Inside", "inside"), ("Frame", "frame"), ("Auto", "reset")]
        for title, key in pos_presets:
            btn = self.ttk.Button(
                row_pos, text=title, command=lambda k=key: self._on_set_watermark_preset(k)
            )
            btn.pack(side="left", fill="x", expand=True, padx=2)

        self.ttk.Label(
            parent,
            text="💡 Tip: Drag text on canvas with mouse to place anywhere!",
            font=("Segoe UI", 8), foreground="#38bdf8"
        ).pack(anchor="w", padx=12, pady=(4, 8))

    # --- Central Viewport ---
    def _build_viewport(self) -> None:
        """Builds central interactive preview canvas (Row 1, Col 1)."""
        viewport_container = (
            ctk.CTkFrame(self.root, fg_color="#121214", corner_radius=0)
            if self.use_ctk
            else self.ttk.Frame(self.root)
        )
        viewport_container.grid(row=1, column=1, sticky="nsew", padx=0, pady=0)
        viewport_container.rowconfigure(0, weight=1)
        viewport_container.columnconfigure(0, weight=1)

        self.canvas_preview = self.tk.Canvas(
            viewport_container,
            bg="#121214",
            highlightthickness=0,
            borderwidth=0
        )
        self.canvas_preview.grid(row=0, column=0, sticky="nsew", padx=16, pady=16)

        # Centered placeholder prompt
        self._show_placeholder_prompt()

        # Full Interactive Mouse Bindings: Drag Text, Pan Poster, Mouse Wheel Zoom
        self.canvas_preview.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas_preview.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas_preview.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas_preview.bind("<Motion>", self._on_canvas_hover)
        self.canvas_preview.bind("<MouseWheel>", self._on_canvas_mousewheel)
        self.canvas_preview.bind("<Button-4>", lambda e: self._on_canvas_mousewheel_step(1))
        self.canvas_preview.bind("<Button-5>", lambda e: self._on_canvas_mousewheel_step(-1))
        self.canvas_preview.bind("<Double-Button-1>", self._on_canvas_double_click)

    def _show_placeholder_prompt(self) -> None:
        """Draws initial click-to-open placeholder instructions on canvas."""
        self.canvas_preview.delete("all")
        cx = max(200, self.canvas_preview.winfo_width() // 2)
        cy = max(200, self.canvas_preview.winfo_height() // 2)

        self.canvas_preview.create_text(
            cx, cy - 20,
            text="🖼️ No Image Loaded",
            fill="#71717a",
            font=("Segoe UI", 16, "bold"),
            tags="placeholder"
        )
        self.canvas_preview.create_text(
            cx, cy + 15,
            text="Click here or 'Open Image' to load a game poster",
            fill="#52525b",
            font=("Segoe UI", 11),
            tags="placeholder"
        )

    # --- Status Bar ---
    def _build_statusbar(self) -> None:
        """Builds bottom status and metadata footer (Row 2)."""
        if self.use_ctk:
            statusbar = ctk.CTkFrame(self.root, height=28, corner_radius=0, fg_color="#18181b")
            statusbar.grid(row=2, column=0, columnspan=2, sticky="sew", padx=0, pady=0)

            self.label_status = ctk.CTkLabel(
                statusbar, text="Ready", font=ctk.CTkFont(size=10), text_color="#a1a1aa"
            )
            self.label_status.pack(side="left", padx=16, pady=4)

            self.label_dimensions = ctk.CTkLabel(
                statusbar, text="Canvas: 1080 × 1350 px", font=ctk.CTkFont(size=10), text_color="#71717a"
            )
            self.label_dimensions.pack(side="right", padx=16, pady=4)
        else:
            statusbar = self.ttk.Frame(self.root)
            statusbar.grid(row=2, column=0, columnspan=2, sticky="sew", padx=0, pady=0)

            self.label_status = self.ttk.Label(statusbar, text="Ready", font=("Segoe UI", 9))
            self.label_status.pack(side="left", padx=16, pady=4)

            self.label_dimensions = self.ttk.Label(
                statusbar, text="Canvas: 1080 × 1350 px", font=("Segoe UI", 9)
            )
            self.label_dimensions.pack(side="right", padx=16, pady=4)

    # --------------------------------------------------------------------------
    # Event Handlers & Controllers
    # --------------------------------------------------------------------------

    def _on_canvas_clicked(self, event: Any) -> None:
        """Canvas click opens file dialog if no image loaded."""
        if self.model.raw_image is None:
            self._on_open_image_clicked()

    def _on_canvas_resize(self, event: Any) -> None:
        """Handles window / canvas resize for proper letterboxing."""
        if self.model.raw_image is not None:
            self._request_preview()
        else:
            self._show_placeholder_prompt()

    def _on_open_image_clicked(self) -> None:
        """Prompts user to select an image from disk."""
        filetypes = [
            ("Image Files (*.jpg;*.jpeg;*.png;*.webp;*.bmp)", "*.jpg;*.jpeg;*.png;*.webp;*.bmp"),
            ("JPEG Image (*.jpg;*.jpeg)", "*.jpg;*.jpeg"),
            ("PNG Image (*.png)", "*.png"),
            ("All Files (*.*)", "*.*")
        ]
        chosen = self.filedialog.askopenfilename(
            parent=self.root,
            title="Open Game Poster Image",
            filetypes=filetypes
        )
        if chosen:
            self.load_image_file(chosen)

    def load_image_file(self, path: Union[str, Path]) -> None:
        """Loads image file and triggers preview refresh."""
        self._set_status(f"Loading {Path(path).name}...")
        try:
            self.model.load_image(path)
            self.preview_engine.set_source_image(self.model.raw_image)
            self._set_status(f"Loaded {Path(path).name} ({self.model.raw_image.width}x{self.model.raw_image.height})")
            self._request_preview()
        except Exception as e:
            logger.error("Failed loading image: %s", e)
            self.messagebox.showerror("Error Opening Image", str(e))
            self._set_status("Error loading image")

    def _on_reset_clicked(self) -> None:
        """Resets controls to default configuration."""
        self.model.reset_config()
        self._set_status("Configuration reset to defaults")
        self._request_preview()

    def _on_format_changed(self, choice: str) -> None:
        """Toggles between JPEG and PNG export format."""
        if "PNG" in choice.upper():
            self.active_format = "PNG"
        else:
            self.active_format = "JPEG"
        self._set_status(f"Export format: {self.active_format}")

    def _on_export_clicked(self) -> None:
        """Initiates high-quality poster export."""
        if self.model.raw_image is None:
            self.messagebox.showwarning("No Image", "Please open an image first before exporting.")
            return

        save_path = prompt_save_path(
            parent=self.root,
            source_image_path=self.model.source_path,
            default_format=self.active_format
        )
        if not save_path:
            return

        self._set_status(f"Exporting to {save_path.name}...")
        self.btn_export.configure(state="disabled")

        def _on_progress(msg: str) -> None:
            self._set_status(msg)

        def _on_success(path: Path, size: int) -> None:
            self.btn_export.configure(state="normal")
            size_mb = size / (1024 * 1024)
            self._set_status(f"Saved: {path.name} ({size_mb:.2f} MB)")
            self.messagebox.showinfo(
                "Export Complete",
                f"Poster successfully saved!\n\nFile: {path}\nSize: {size_mb:.2f} MB"
            )

        def _on_error(exc: Exception) -> None:
            self.btn_export.configure(state="normal")
            self._set_status("Export failed")
            self.messagebox.showerror("Export Failed", f"An error occurred while saving:\n{exc}")

        self.export_engine.export_async(
            raw_image=self.model.raw_image,
            config=self.model.config,
            output_path=save_path,
            format=self.active_format,
            quality=95,
            on_progress=_on_progress,
            on_success=_on_success,
            on_error=_on_error
        )

    # --- Slider Handlers ---
    def _on_spacing_slider(self, val: float) -> None:
        val_int = int(round(val))
        self.lbl_spacing_val.configure(text=f"Spacing (Margin): {val_int} px")
        if not self._updating_ui:
            self.model.set_spacing(val_int)
            self._request_preview()

    def _on_curve_slider(self, val: float) -> None:
        val_int = int(round(val))
        self.lbl_curve_val.configure(text=f"Corner Curve: {val_int} px")
        if not self._updating_ui:
            self.model.set_curve(val_int)
            self._request_preview()

    def _on_zoom_slider(self, val: float) -> None:
        val_flt = round(float(val), 2)
        self.lbl_zoom_val.configure(text=f"Poster Zoom: {val_flt:.2f}x")
        if not self._updating_ui:
            self.model.set_zoom(val_flt)
            self._request_preview()

    def _on_ratio_selected(self, ratio: str) -> None:
        if not self._updating_ui:
            self.model.set_ratio(ratio)
            self._update_dimensions_summary()
            self._request_preview()

    def _on_hd_toggled(self) -> None:
        if self.use_ctk:
            is_hd = bool(self.switch_hd.get())
        else:
            is_hd = bool(self.hd_var.get())
        if not self._updating_ui:
            self.model.set_hd(is_hd)
            self._update_dimensions_summary()
            self._request_preview()

    def _on_pick_color(self, slot: int) -> None:
        from tkinter import colorchooser
        init_hex = (
            rgb_to_hex(self.model.config.color1 or (30, 27, 75))
            if slot == 1
            else rgb_to_hex(self.model.config.color2 or (2, 132, 199))
        )
        picked = colorchooser.askcolor(color=init_hex, title=f"Choose Gradient Color {slot}")
        if picked and picked[1]:
            hex_val = picked[1].lower()
            if slot == 1:
                self.model.set_color1(hex_val)
            else:
                self.model.set_color2(hex_val)
            self._sync_color_widgets()
            self._request_preview()

    def _on_hex_entry_changed(self, slot: int) -> None:
        entry = self.entry_color1 if slot == 1 else self.entry_color2
        raw_val = entry.get().strip()
        try:
            parsed = parse_hex_color(raw_val)
            if slot == 1:
                self.model.set_color1(parsed)
            else:
                self.model.set_color2(parsed)
            self._sync_color_widgets()
            self._request_preview()
        except Exception:
            # Revert invalid entry
            self._sync_color_widgets()

    def _on_autodetect_clicked(self) -> None:
        self.model.auto_detect_colors()
        self._sync_color_widgets()
        self._set_status("Auto-detected vibrant dominant colors")
        self._request_preview()

    def _on_swap_clicked(self) -> None:
        self.model.swap_colors()
        self._sync_color_widgets()
        self._set_status("Swapped gradient background colors")
        self._request_preview()

    def _on_angle_slider(self, val: float) -> None:
        angle_deg = float(val) % 360.0
        self.lbl_angle_val.configure(text=f"Gradient Angle: {int(round(angle_deg))}°")
        if not self._updating_ui:
            self.model.set_angle(angle_deg)
            self._request_preview()

    def _on_shadow_toggled(self) -> None:
        if self.use_ctk:
            enabled = bool(self.chk_shadow.get())
        else:
            enabled = bool(self.shadow_var.get())
        if not self._updating_ui:
            self.model.set_drop_shadow(enabled)
            self._request_preview()

    def _on_watermark_text_changed(self, event: Any = None) -> None:
        text = self.entry_watermark.get()
        if not self._updating_ui:
            self.model.set_watermark(text=text)
            self._request_preview()

    def _on_watermark_size_slider(self, val: float) -> None:
        size_int = int(round(val))
        self.lbl_watermark_size_val.configure(text=f"Font Size: {size_int} px")
        if not self._updating_ui:
            self.model.set_watermark(
                text=self.model.config.watermark,
                size=size_int
            )
            self._request_preview()

    def _on_stroke_slider(self, val: float) -> None:
        stroke_int = int(round(val))
        self.lbl_stroke_val.configure(text=f"Stroke Width: {stroke_int} px")
        if not self._updating_ui:
            self.model.set_watermark_colors(stroke_width=stroke_int)
            self._request_preview()

    def _on_reset_pan_clicked(self) -> None:
        """Resets pan to (0, 0) and zoom to 1.0x."""
        self.model.reset_pan()
        self.model.set_zoom(1.0)
        if hasattr(self, "slider_zoom"):
            self.slider_zoom.set(1.0)
        if hasattr(self, "lbl_zoom_val"):
            self.lbl_zoom_val.configure(text="Poster Zoom: 1.00x")
        if hasattr(self, "lbl_pan_val"):
            self.lbl_pan_val.configure(text="Poster Pan: (0, 0) px")
        self._set_status("Reset pan and zoom to center")
        self._request_preview()

    def _on_font_selected(self, font_name: str) -> None:
        """Updates watermark font family."""
        self.model.set_watermark_font(font_name)
        self._set_status(f"Font changed to: {font_name}")
        self._request_preview()

    def _on_pick_text_color(self) -> None:
        """Color picker dialog for watermark text fill color."""
        from tkinter import colorchooser
        init_hex = self.model.config.watermark_color or "#ffffff"
        picked = colorchooser.askcolor(color=init_hex, title="Choose Watermark Text Color")
        if picked and picked[1]:
            hex_val = picked[1].lower()
            self._on_set_text_color(hex_val)

    def _on_pick_stroke_color(self) -> None:
        """Color picker dialog for watermark stroke/outline color."""
        from tkinter import colorchooser
        init_hex = self.model.config.watermark_stroke_color or "#0f172a"
        picked = colorchooser.askcolor(color=init_hex, title="Choose Watermark Stroke Color")
        if picked and picked[1]:
            hex_val = picked[1].lower()
            self._on_set_stroke_color(hex_val)

    def _on_text_color_hex(self, hex_code: str) -> None:
        """Applies text color from hex text entry."""
        try:
            rgb = parse_hex_color(hex_code.strip())
            hex_clean = rgb_to_hex(rgb)
            self._on_set_text_color(hex_clean)
        except Exception:
            pass

    def _on_stroke_color_hex(self, hex_code: str) -> None:
        """Applies stroke color from hex text entry."""
        try:
            rgb = parse_hex_color(hex_code.strip())
            hex_clean = rgb_to_hex(rgb)
            self._on_set_stroke_color(hex_clean)
        except Exception:
            pass

    def _on_set_text_color(self, hex_val: str) -> None:
        """Sets watermark text fill color."""
        self.model.set_watermark_colors(text_color=hex_val)
        if hasattr(self, "btn_textcolor_swatch"):
            if self.use_ctk:
                self.btn_textcolor_swatch.configure(fg_color=hex_val, hover_color=hex_val)
            else:
                self.btn_textcolor_swatch.configure(bg=hex_val)
        if hasattr(self, "entry_textcolor"):
            cur = self.entry_textcolor.get()
            if cur.strip().lower() != hex_val.lower():
                self.entry_textcolor.delete(0, "end")
                self.entry_textcolor.insert(0, hex_val)
        self._request_preview()

    def _on_set_stroke_color(self, hex_val: str) -> None:
        """Sets watermark stroke color."""
        self.model.set_watermark_colors(stroke_color=hex_val)
        if hasattr(self, "btn_strokecolor_swatch"):
            if self.use_ctk:
                self.btn_strokecolor_swatch.configure(fg_color=hex_val, hover_color=hex_val)
            else:
                self.btn_strokecolor_swatch.configure(bg=hex_val)
        if hasattr(self, "entry_strokecolor"):
            cur = self.entry_strokecolor.get()
            if cur.strip().lower() != hex_val.lower():
                self.entry_strokecolor.delete(0, "end")
                self.entry_strokecolor.insert(0, hex_val)
        self._request_preview()

    def _on_set_watermark_preset(self, preset: str) -> None:
        """Sets watermark position preset (top, center, inside, frame, reset)."""
        if preset == "top":
            self.model.set_watermark_position(0.5, 0.06)
            self._set_status("Watermark placed at Top")
        elif preset == "center":
            self.model.set_watermark_position(0.5, 0.5)
            self._set_status("Watermark placed at Center")
        elif preset == "inside":
            self.model.set_watermark_position(0.5, 0.905)
            self._set_status("Watermark placed inside poster card")
        elif preset == "frame":
            self.model.set_watermark_position(0.5, 0.965)
            self._set_status("Watermark placed on frame backdrop")
        elif preset == "bottom":
            self.model.reset_watermark_position()
            self._set_status("Watermark placed at smart bottom")
        elif preset == "reset":
            self.model.reset_watermark_position()
            self._set_status("Watermark position reset to Auto")
        self._request_preview()

    def _on_copy_clipboard_clicked(self) -> None:
        """Copies full resolution rendered poster directly to Windows clipboard."""
        if self.model.raw_image is None:
            self.messagebox.showwarning("No Image", "Please open an image first before copying.")
            return

        import tempfile
        import subprocess

        self._set_status("Rendering poster to clipboard...")
        try:
            # Render full poster image using PosterProcessor
            from poster_studio.core.processor import PosterProcessor
            proc = PosterProcessor()
            result_img = proc.process(self.model.raw_image, self.model.config)

            # Save temporary PNG
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = Path(tmp.name)
            result_img.save(tmp_path, "PNG")

            if sys.platform == "win32":
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Windows.Forms; "
                    f"[System.Windows.Forms.Clipboard]::SetImage("
                    f"[System.Drawing.Image]::FromFile('{tmp_path.resolve()}'))"
                )
                res = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
                if res.returncode == 0:
                    self._set_status("Poster successfully copied to clipboard! 📋")
                else:
                    self._set_status(f"Clipboard notice: {res.stderr.strip()[:60]}")
            else:
                self._set_status("Clipboard copy only supported on Windows desktop")

            # Clean up temp file safely after a short delay
            def _cleanup():
                time.sleep(2)
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            import threading
            threading.Thread(target=_cleanup, daemon=True).start()

        except Exception as err:
            logger.error("Clipboard copy failed: %s", err)
            self._set_status(f"Failed to copy to clipboard: {err}")

    # --- Canvas Interactive Mouse Controls ---

    def _get_preview_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """Returns (x0, y0, x1, y1) of the rendered poster on the canvas."""
        if not hasattr(self, "display_manager") or self.display_manager.current_image is None:
            return None
        return self.display_manager.bounds

    def _get_watermark_screen_pos(self) -> Optional[Tuple[int, int]]:
        """Returns approximate center (cx, cy) of watermark on canvas in canvas coordinates."""
        bounds = self._get_preview_bounds()
        if bounds is None:
            return None
        x0, y0, x1, y1 = bounds
        pw = x1 - x0
        ph = y1 - y0

        cfg = self.model.config
        if cfg.watermark_x is not None and cfg.watermark_y is not None:
            wx, wy = cfg.watermark_x, cfg.watermark_y
        else:
            wx, wy = 0.5, 0.94

        cx = x0 + int(round(wx * pw))
        cy = y0 + int(round(wy * ph))
        return (cx, cy)

    def _on_canvas_press(self, event: Any) -> None:
        """Handles mouse press: detects watermark click or poster pan initiation."""
        if self.model.raw_image is None:
            self._on_open_image_clicked()
            return

        bounds = self._get_preview_bounds()
        if bounds is None:
            return

        x0, y0, x1, y1 = bounds
        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._has_dragged = False

        # Check if click is near watermark
        wm_pos = self._get_watermark_screen_pos()
        if wm_pos is not None:
            wm_cx, wm_cy = wm_pos
            if math.hypot(event.x - wm_cx, event.y - wm_cy) <= 65:
                self._drag_target = "watermark"
                self.canvas_preview.configure(cursor="fleur")
                return

        # Check if click is inside the preview poster bounding box
        if x0 <= event.x <= x1 and y0 <= event.y <= y1:
            self._drag_target = "poster"
            self.canvas_preview.configure(cursor="fleur")
        else:
            self._drag_target = None

    def _on_canvas_drag(self, event: Any) -> None:
        """Handles mouse drag for either watermark positioning or poster panning."""
        if self.model.raw_image is None or self._drag_target is None:
            return

        bounds = self._get_preview_bounds()
        if bounds is None:
            return

        x0, y0, x1, y1 = bounds
        pw = max(1, x1 - x0)
        ph = max(1, y1 - y0)
        self._has_dragged = True

        if self._drag_target == "watermark":
            # Reposition watermark text
            clamped_x = max(x0, min(x1, event.x))
            clamped_y = max(y0, min(y1, event.y))
            norm_x = (clamped_x - x0) / pw
            norm_y = (clamped_y - y0) / ph
            self.model.set_watermark_position(norm_x, norm_y)
            self._request_preview()

        elif self._drag_target == "poster":
            # Pan poster image inside frame
            dx = event.x - self._drag_start_x
            dy = event.y - self._drag_start_y
            self._drag_start_x = event.x
            self._drag_start_y = event.y

            full_w, _ = resolve_canvas_size(ratio=self.model.config.ratio, hd=self.model.config.hd)
            scale = pw / max(1, full_w)
            full_dx = dx / max(0.001, scale)
            full_dy = dy / max(0.001, scale)

            new_px = self.model.config.pan_x + full_dx
            new_py = self.model.config.pan_y + full_dy
            self.model.set_pan(new_px, new_py)
            if hasattr(self, "lbl_pan_val"):
                self.lbl_pan_val.configure(text=f"Poster Pan: ({int(round(new_px))}, {int(round(new_py))}) px")
            self._request_preview()

    def _on_canvas_release(self, event: Any) -> None:
        """Handles mouse button release."""
        self._drag_target = None
        self._on_canvas_hover(event)

    def _on_canvas_hover(self, event: Any) -> None:
        """Dynamically updates cursor when hovering over interactive elements."""
        if self.model.raw_image is None:
            self.canvas_preview.configure(cursor="")
            return

        bounds = self._get_preview_bounds()
        if bounds is None:
            self.canvas_preview.configure(cursor="")
            return

        x0, y0, x1, y1 = bounds
        wm_pos = self._get_watermark_screen_pos()

        if wm_pos is not None and math.hypot(event.x - wm_pos[0], event.y - wm_pos[1]) <= 65:
            self.canvas_preview.configure(cursor="fleur")
        elif x0 <= event.x <= x1 and y0 <= event.y <= y1:
            self.canvas_preview.configure(cursor="hand2")
        else:
            self.canvas_preview.configure(cursor="")

    def _on_canvas_mousewheel(self, event: Any) -> None:
        """Handles mouse wheel scrolling to smoothly zoom the poster in/out."""
        if self.model.raw_image is None:
            return
        delta = 0.05 if getattr(event, "delta", 0) > 0 else -0.05
        self._adjust_zoom_step(delta)

    def _on_canvas_mousewheel_step(self, step: int) -> None:
        """Handles Linux Button-4 (scroll up) and Button-5 (scroll down)."""
        if self.model.raw_image is None:
            return
        delta = 0.05 if step > 0 else -0.05
        self._adjust_zoom_step(delta)

    def _adjust_zoom_step(self, delta: float) -> None:
        current_zoom = self.model.config.zoom
        new_zoom = max(0.5, min(3.0, round(current_zoom + delta, 2)))
        self.model.set_zoom(new_zoom)
        if hasattr(self, "slider_zoom"):
            self.slider_zoom.set(new_zoom)
        if hasattr(self, "lbl_zoom_val"):
            self.lbl_zoom_val.configure(text=f"Poster Zoom: {new_zoom:.2f}x")
        self._request_preview()

    def _on_canvas_double_click(self, event: Any) -> None:
        """Double clicking canvas resets pan and zoom to default."""
        if self.model.raw_image is None:
            return
        self._on_reset_pan_clicked()

    # --------------------------------------------------------------------------
    # Model Synchronization & Preview Dispatch
    # --------------------------------------------------------------------------

    def _request_preview(self) -> None:
        """Dispatches preview rendering request to PreviewEngine."""
        if self.model.raw_image is None:
            return

        cw = max(200, self.canvas_preview.winfo_width())
        ch = max(200, self.canvas_preview.winfo_height())
        self.preview_engine.viewport_max_size = (cw, ch)
        self.preview_engine.trigger_preview(self.model.config)

    def _on_preview_rendered(self, image: Image.Image) -> None:
        """Callback invoked on Tkinter main thread with newly rendered preview."""
        self.display_manager.update_image(image)

    def _on_model_changed(self) -> None:
        """Observer callback invoked when Model state mutates."""
        self._sync_widgets_from_model()

    def _sync_widgets_from_model(self) -> None:
        """Updates View controls to reflect current Model parameters."""
        self._updating_ui = True
        try:
            cfg = self.model.config

            # Spacing
            if hasattr(self, "slider_spacing"):
                self.slider_spacing.set(cfg.margin)
                self.lbl_spacing_val.configure(text=f"Spacing (Margin): {cfg.margin} px")

            # Curve
            if hasattr(self, "slider_curve"):
                self.slider_curve.set(cfg.curve)
                self.lbl_curve_val.configure(text=f"Corner Curve: {cfg.curve} px")

            # Zoom
            if hasattr(self, "slider_zoom"):
                self.slider_zoom.set(cfg.zoom)
                self.lbl_zoom_val.configure(text=f"Poster Zoom: {cfg.zoom:.2f}x")

            # Pan
            if hasattr(self, "lbl_pan_val"):
                self.lbl_pan_val.configure(text=f"Poster Pan: ({int(round(cfg.pan_x))}, {int(round(cfg.pan_y))}) px")

            # Ratio & HD
            if hasattr(self, "segmented_ratio"):
                self.segmented_ratio.set(cfg.ratio)
            elif hasattr(self, "ratio_var"):
                self.ratio_var.set(cfg.ratio)

            if hasattr(self, "switch_hd"):
                if self.use_ctk:
                    if cfg.hd:
                        self.switch_hd.select()
                    else:
                        self.switch_hd.deselect()
                elif hasattr(self, "hd_var"):
                    self.hd_var.set(cfg.hd)

            # Angle
            if hasattr(self, "slider_angle"):
                self.slider_angle.set(cfg.angle)
                self.lbl_angle_val.configure(text=f"Gradient Angle: {int(round(cfg.angle))}°")

            # Shadow
            if hasattr(self, "chk_shadow"):
                if self.use_ctk:
                    if cfg.drop_shadow:
                        self.chk_shadow.select()
                    else:
                        self.chk_shadow.deselect()
                elif hasattr(self, "shadow_var"):
                    self.shadow_var.set(cfg.drop_shadow)

            # Watermark Text
            if hasattr(self, "entry_watermark"):
                cur_text = self.entry_watermark.get()
                model_text = cfg.watermark or ""
                if cur_text != model_text:
                    self.entry_watermark.delete(0, "end")
                    self.entry_watermark.insert(0, model_text)

            # Watermark Font
            if hasattr(self, "combo_font"):
                font_name = "Anton (Default Gaming)"
                for k, v in AVAILABLE_FONTS.items():
                    if k == cfg.watermark_font or v == cfg.watermark_font or k.lower().startswith(str(cfg.watermark_font).lower()):
                        font_name = k
                        break
                self.combo_font.set(font_name)

            # Watermark Size
            if hasattr(self, "slider_watermark_size") and cfg.watermark_size is not None:
                self.slider_watermark_size.set(cfg.watermark_size)
                self.lbl_watermark_size_val.configure(text=f"Font Size: {cfg.watermark_size} px")

            # Watermark Stroke
            if hasattr(self, "slider_stroke"):
                self.slider_stroke.set(cfg.watermark_stroke_width)
                self.lbl_stroke_val.configure(text=f"Stroke Width: {cfg.watermark_stroke_width} px")

            # Watermark Text Color
            tc = (
                rgb_to_hex(cfg.watermark_color)
                if isinstance(cfg.watermark_color, tuple)
                else (cfg.watermark_color or "#ffffff")
            )
            if hasattr(self, "btn_textcolor_swatch"):
                if self.use_ctk:
                    self.btn_textcolor_swatch.configure(fg_color=tc, hover_color=tc)
                else:
                    self.btn_textcolor_swatch.configure(bg=tc)
            if hasattr(self, "entry_textcolor"):
                cur = self.entry_textcolor.get()
                if cur.strip().lower() != tc.lower():
                    self.entry_textcolor.delete(0, "end")
                    self.entry_textcolor.insert(0, tc)

            # Watermark Stroke Color
            sc = (
                rgb_to_hex(cfg.watermark_stroke_color)
                if isinstance(cfg.watermark_stroke_color, tuple)
                else (cfg.watermark_stroke_color or "#0f172a")
            )
            if hasattr(self, "btn_strokecolor_swatch"):
                if self.use_ctk:
                    self.btn_strokecolor_swatch.configure(fg_color=sc, hover_color=sc)
                else:
                    self.btn_strokecolor_swatch.configure(bg=sc)
            if hasattr(self, "entry_strokecolor"):
                cur = self.entry_strokecolor.get()
                if cur.strip().lower() != sc.lower():
                    self.entry_strokecolor.delete(0, "end")
                    self.entry_strokecolor.insert(0, sc)

            self._sync_color_widgets()
            self._update_dimensions_summary()

        finally:
            self._updating_ui = False

    def _sync_color_widgets(self) -> None:
        """Synchronizes color swatch buttons and hex entries."""
        cfg = self.model.config
        c1 = cfg.color1 or (self.model.active_palette[0] if self.model.active_palette else DEFAULT_FALLBACK_C1)
        c2 = cfg.color2 or (self.model.active_palette[1] if self.model.active_palette else DEFAULT_FALLBACK_C2)

        hex1 = rgb_to_hex(c1)
        hex2 = rgb_to_hex(c2)

        if hasattr(self, "btn_color1_swatch"):
            if self.use_ctk:
                self.btn_color1_swatch.configure(fg_color=hex1, hover_color=hex1)
                self.btn_color2_swatch.configure(fg_color=hex2, hover_color=hex2)
            else:
                self.btn_color1_swatch.configure(bg=hex1)
                self.btn_color2_swatch.configure(bg=hex2)

        if hasattr(self, "entry_color1"):
            self.entry_color1.delete(0, "end")
            self.entry_color1.insert(0, hex1)
            self.entry_color2.delete(0, "end")
            self.entry_color2.insert(0, hex2)

    def _update_dimensions_summary(self) -> None:
        """Updates canvas dimension labels."""
        cfg = self.model.config
        w, h = resolve_canvas_size(ratio=cfg.ratio, hd=cfg.hd)
        dim_str = f"Output: {w} × {h} px"
        if hasattr(self, "lbl_dimensions_info"):
            self.lbl_dimensions_info.configure(text=dim_str)
        if hasattr(self, "label_dimensions"):
            self.label_dimensions.configure(text=dim_str)

    def _set_status(self, msg: str) -> None:
        """Updates status footer text."""
        if hasattr(self, "label_status"):
            self.label_status.configure(text=msg)

    def run(self) -> None:
        """Starts Tkinter event loop."""
        self.root.mainloop()


# ==============================================================================
# CLI Entry Point
# ==============================================================================

def launch_gui(argv: Optional[List[str]] = None) -> int:
    """
    Primary entry point for the desktop GUI application.
    Parses CLI arguments, sets theme, initializes MainWindow, and runs event loop.
    """
    parser = argparse.ArgumentParser(
        prog="game-poster-studio-gui",
        description="Game Poster Studio — Windows Collage Maker Desktop GUI"
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="Optional initial game poster image file path to load."
    )
    parser.add_argument(
        "--ratio", "-r",
        type=str,
        default="4:5",
        choices=["4:5", "1:1", "9:16", "16:9", "4:3", "21:9"],
        help="Initial aspect ratio preset (default: 4:5)."
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="dark",
        choices=["dark", "light", "system"],
        help="UI color theme appearance mode."
    )
    parser.add_argument(
        "--fallback-tkinter",
        action="store_true",
        help="Force native Tkinter mode even if CustomTkinter is installed."
    )

    args = parser.parse_args(argv)

    model = PosterStudioModel(initial_ratio=args.ratio)

    if args.input:
        in_path = Path(args.input)
        if in_path.is_file():
            model.load_image(in_path)
        else:
            sys.stderr.write(f"[WARNING] Specified input image not found: {in_path}\n")

    app = MainWindow(
        model=model,
        force_tkinter=args.fallback_tkinter,
        theme=args.theme
    )

    try:
        app.run()
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as err:
        sys.stderr.write(f"[FATAL] GUI Application Error: {err}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(launch_gui(sys.argv[1:]))
