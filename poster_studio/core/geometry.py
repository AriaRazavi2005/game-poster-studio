"""
poster_studio.core.geometry
~~~~~~~~~~~~~~~~~~~~~~~~~~~
Aspect ratio catalogs, canvas dimension resolution, boundary-clamped margin
calculations, and fit-in-box containment scaling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Union

# Standard aspect ratio resolutions (Width, Height)
ASPECT_RATIOS: Dict[str, Tuple[int, int]] = {
    "4:5": (1080, 1350),
    "4:5_hd": (1440, 1800),
    "1:1": (1200, 1200),
    "9:16": (1080, 1920),
    "16:9": (1920, 1080),
    "4:3": (1440, 1080),
    "21:9": (2560, 1080),
}

# High-resolution (HD) aspect ratio resolutions
ASPECT_RATIOS_HD: Dict[str, Tuple[int, int]] = {
    "4:5": (1440, 1800),
    "1:1": (1600, 1600),
    "9:16": (1440, 2560),
    "16:9": (2560, 1440),
    "4:3": (1920, 1440),
    "21:9": (3440, 1440),
}


@dataclass(frozen=True)
class PosterPlacement:
    """Immutable record of the fitted poster's placement on the canvas."""
    x: int
    y: int
    width: int
    height: int
    scale: float
    box_width: int
    box_height: int

    @property
    def box(self) -> Tuple[int, int, int, int]:
        """Returns bounding box (left, top, right, bottom)."""
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    @property
    def position(self) -> Tuple[int, int]:
        """Returns top-left position (x, y)."""
        return (self.x, self.y)

    @property
    def size(self) -> Tuple[int, int]:
        """Returns fitted dimensions (width, height)."""
        return (self.width, self.height)


def resolve_canvas_size(
    ratio: str = "4:5",
    custom_size: Optional[Tuple[int, int]] = None,
    hd: bool = False
) -> Tuple[int, int]:
    """
    Resolves canvas dimensions (width, height) from an aspect ratio preset or custom size.

    Parameters:
        ratio: Aspect ratio preset key (e.g. '4:5', '1:1', '9:16', '16:9', '4:3', '21:9').
               Supports '_hd' suffix (e.g. '4:5_hd'). Case-insensitive.
        custom_size: Explicit (width, height) tuple overriding preset if provided.
        hd: When True, uses higher resolution tier for standard presets.

    Returns:
        (width, height) in pixels.

    Raises:
        ValueError: If custom_size has non-positive dimensions or ratio is unrecognized.
    """
    if custom_size is not None:
        w, h = custom_size
        if w <= 0 or h <= 0:
            raise ValueError(f"Custom canvas size must be positive integers, got ({w}, {h})")
        return (int(w), int(h))

    clean_ratio = ratio.strip().lower()

    # Handle explicit '_hd' suffix
    if clean_ratio.endswith("_hd"):
        clean_ratio = clean_ratio[:-3]
        hd = True

    catalog = ASPECT_RATIOS_HD if hd else ASPECT_RATIOS

    if clean_ratio not in catalog:
        valid_keys = list(ASPECT_RATIOS.keys())
        raise ValueError(
            f"Unsupported aspect ratio '{ratio}'. Supported presets: {valid_keys} "
            f"(with optional hd=True or '_hd' suffix)"
        )

    return catalog[clean_ratio]


def parse_canvas_dimensions(
    ratio_str: str = "4:5",
    hd: bool = False,
    custom_size: Optional[Tuple[int, int]] = None
) -> Tuple[int, int]:
    """Alias for resolve_canvas_size for backward/forward compatibility."""
    return resolve_canvas_size(ratio=ratio_str, custom_size=custom_size, hd=hd)


def resolve_margin(
    canvas_size: Tuple[int, int],
    margin: Union[int, float, Tuple[Union[int, float], Union[int, float]]] = 50
) -> Tuple[int, int]:
    """
    Resolves and clamps horizontal and vertical margin padding.

    Parameters:
        canvas_size: (width, height) of the canvas.
        margin: Padding in pixels (int) or fraction of shortest edge (float in (0, 1)),
                or a 2-tuple (margin_x, margin_y).

    Returns:
        (margin_x, margin_y) clamped within safe canvas bounds.
    """
    w_canvas, h_canvas = canvas_size
    min_dim = min(w_canvas, h_canvas)

    # Maximum safe margin: leaves at least 20px visible box
    max_margin = max(0, (min_dim // 2) - 10)

    def _parse_single(m: Union[int, float]) -> int:
        if isinstance(m, float) and 0.0 < m < 1.0:
            val = round(min_dim * m)
        else:
            val = round(float(m))
        return max(0, min(val, max_margin))

    if isinstance(margin, (tuple, list)):
        if len(margin) != 2:
            raise ValueError(f"Margin tuple must have 2 elements, got {len(margin)}")
        mx = _parse_single(margin[0])
        my = _parse_single(margin[1])
    else:
        mx = my = _parse_single(margin)

    return (mx, my)


def calculate_poster_placement(
    canvas_size: Tuple[int, int],
    raw_size: Tuple[int, int],
    margin: Union[int, float, Tuple[Union[int, float], Union[int, float]]] = 50,
    zoom: float = 1.0,
    pan: Tuple[Union[int, float], Union[int, float]] = (0, 0)
) -> PosterPlacement:
    """
    Calculates containment scaling and centering offsets for a poster on the canvas.
    Guarantees strict aspect ratio preservation without distortion.

    Parameters:
        canvas_size: (canvas_width, canvas_height).
        raw_size: (raw_width, raw_height) of the original poster image.
        margin: Spacing padding (px, percentage, or tuple).
        zoom: Scale multiplier (default 1.0, clamped >= 0.1).
        pan: (pan_x, pan_y) offset in pixels relative to center (default (0, 0)).

    Returns:
        PosterPlacement containing fitted dimensions, coordinates, and scale factor.

    Raises:
        ValueError: If canvas_size or raw_size contain non-positive values.
    """
    cw, ch = canvas_size
    rw, rh = raw_size

    if cw <= 0 or ch <= 0:
        raise ValueError(f"Canvas dimensions must be positive, got ({cw}, {ch})")
    if rw <= 0 or rh <= 0:
        raise ValueError(f"Raw image dimensions must be positive, got ({rw}, {rh})")

    mx, my = resolve_margin(canvas_size, margin)

    box_w = max(1, cw - 2 * mx)
    box_h = max(1, ch - 2 * my)

    # Containment scale factor
    safe_zoom = max(0.1, float(zoom))
    scale = min(box_w / rw, box_h / rh) * safe_zoom

    fitted_w = max(1, round(rw * scale))
    fitted_h = max(1, round(rh * scale))

    # Centering offsets with pan
    pan_x = round(float(pan[0])) if pan else 0
    pan_y = round(float(pan[1])) if pan else 0

    offset_x = round((cw - fitted_w) / 2.0) + pan_x
    offset_y = round((ch - fitted_h) / 2.0) + pan_y

    return PosterPlacement(
        x=offset_x,
        y=offset_y,
        width=fitted_w,
        height=fitted_h,
        scale=scale,
        box_width=box_w,
        box_height=box_h
    )


def calculate_fit_box(
    raw_size: Tuple[int, int],
    canvas_size: Tuple[int, int],
    margin: Union[int, float, Tuple[Union[int, float], Union[int, float]]] = 50,
    zoom: float = 1.0,
    pan: Tuple[Union[int, float], Union[int, float]] = (0, 0)
) -> Tuple[Tuple[int, int], Tuple[int, int]]:
    """
    Interface compatibility helper matching PROJECT.md specification contract.

    Returns:
        ((scaled_w, scaled_h), (offset_x, offset_y))
    """
    placement = calculate_poster_placement(canvas_size, raw_size, margin, zoom, pan)
    return (placement.size, placement.position)
