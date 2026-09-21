"""
poster_studio.core.palette
~~~~~~~~~~~~~~~~~~~~~~~~~~
Dominant color extraction, HSV & ITU-R BT.709 relative luminance dead-color
filtering, vibrancy scoring, color distance separation, harmonic hue-shift
fallbacks, and hex code parsing for Game Poster Studio.
"""

from __future__ import annotations

import colorsys
import math
import re
from typing import List, Optional, Tuple, Union
from PIL import Image

# Aesthetic Fallback Palette (Deep Midnight Violet & Electric Sky Blue)
DEFAULT_FALLBACK_C1: Tuple[int, int, int] = (30, 27, 75)   # #1e1b4b
DEFAULT_FALLBACK_C2: Tuple[int, int, int] = (2, 132, 199)  # #0284c7

HEX_COLOR_PATTERN_6 = re.compile(r"^[0-9a-fA-F]{6}$")
HEX_COLOR_PATTERN_3 = re.compile(r"^[0-9a-fA-F]{3}$")


def parse_hex_color(hex_str: str) -> Tuple[int, int, int]:
    """
    Parses and validates a hexadecimal color string into an (R, G, B) integer tuple.

    Supports:
        - '#RRGGBB' or 'RRGGBB'
        - '#RGB' or 'RGB' shorthand

    Raises:
        TypeError: If hex_str is not a string.
        ValueError: If hex_str has invalid characters or incorrect length.
    """
    if not isinstance(hex_str, str):
        raise TypeError(f"Hex color must be a string, got {type(hex_str).__name__}")

    s = hex_str.strip()
    if s.startswith("#"):
        s = s[1:]

    if len(s) == 3:
        if not HEX_COLOR_PATTERN_3.fullmatch(s):
            raise ValueError(f"Invalid 3-digit hex color format: {hex_str!r}")
        s = "".join(ch * 2 for ch in s)
    elif len(s) == 6:
        if not HEX_COLOR_PATTERN_6.fullmatch(s):
            raise ValueError(f"Invalid 6-digit hex color format: {hex_str!r}")
    else:
        raise ValueError(
            f"Invalid hex color length for {hex_str!r}: expected 3 or 6 hex digits."
        )

    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    return (r, g, b)


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """Converts an (R, G, B) integer tuple to a standardized '#RRGGBB' string."""
    if len(rgb) != 3 or not all(isinstance(c, int) and 0 <= c <= 255 for c in rgb):
        raise ValueError(f"Invalid RGB tuple: {rgb!r} (expected 3 integers 0..255)")
    return f"#{rgb[0]:02X}{rgb[1]:02X}{rgb[2]:02X}"


def rgb_to_relative_luminance(r: int, g: int, b: int) -> float:
    """Calculates ITU-R BT.709 relative luminance L in range [0.0, 1.0]."""
    return 0.2126 * (r / 255.0) + 0.7152 * (g / 255.0) + 0.0722 * (b / 255.0)


def color_distance_rgb(c1: Tuple[int, int, int], c2: Tuple[int, int, int]) -> float:
    """Calculates Euclidean distance between two RGB colors in 3D color space."""
    return math.sqrt(
        (c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2 + (c1[2] - c2[2]) ** 2
    )


def is_dead_color(r: int, g: int, b: int) -> bool:
    """
    Evaluates whether an RGB color should be rejected as a 'dead color'.

    Rejection gates:
        1. Near-Black: Value V < 0.15 OR Relative Luminance L < 0.12
        2. Near-White: (Value V > 0.90 AND Saturation S < 0.12) OR Relative Luminance L > 0.88
        3. Dull Neutral Gray: Saturation S < 0.18
    """
    _, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    lum = rgb_to_relative_luminance(r, g, b)

    # Near-black gate (shadows, black borders, dark noise)
    if v < 0.15 or lum < 0.12:
        return True

    # Near-white gate (blown-out highlights, white title text)
    if (v > 0.90 and s < 0.12) or lum > 0.88:
        return True

    # Dull neutral gray gate (desaturated muddy tones)
    if s < 0.18:
        return True

    return False


def generate_harmonic_fallback(
    color: Tuple[int, int, int],
    min_distance: float = 50.0
) -> Tuple[int, int, int]:
    """
    Generates a harmonic, high-contrast second color by shifting hue by +/-30 or +/-60 deg,
    boosting saturation and adjusting value to enforce minimum Euclidean distance.
    """
    h, s, v = colorsys.rgb_to_hsv(
        color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
    )

    shifts = [30.0, -30.0, 60.0, -60.0]
    best_candidate: Optional[Tuple[int, int, int]] = None
    max_d = 0.0

    for deg in shifts:
        h2 = (h + deg / 360.0) % 1.0
        s2 = min(1.0, max(0.40, s))
        v2 = min(1.0, max(0.35, v * 0.80 if v > 0.60 else v * 1.30))
        r2, g2, b2 = [round(c * 255.0) for c in colorsys.hsv_to_rgb(h2, s2, v2)]
        c2 = (r2, g2, b2)
        d = color_distance_rgb(color, c2)
        if d >= min_distance:
            return c2
        if d > max_d:
            max_d = d
            best_candidate = c2

    return best_candidate or DEFAULT_FALLBACK_C2


def extract_dominant_colors(
    image: Image.Image,
    filter_dead_colors: bool = True,
    fallback_colors: Tuple[Tuple[int, int, int], Tuple[int, int, int]] = (
        DEFAULT_FALLBACK_C1,
        DEFAULT_FALLBACK_C2,
    ),
    thumbnail_size: Tuple[int, int] = (160, 160),
    num_quantize_colors: int = 24,
    min_distance: float = 50.0,
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Extracts 2 vibrant, harmonic, dominant RGB colors from a game poster.

    Parameters:
        image: PIL Image in any format/mode.
        filter_dead_colors: If True, filters out near-black, near-white, and dull grays.
        fallback_colors: (C1, C2) tuple to return if zero valid colors survive filtering.
        thumbnail_size: Fast downsampling thumbnail size (default 160x160).
        num_quantize_colors: Number of quantization bins (default 24).
        min_distance: Minimum Euclidean color distance required between C1 and C2 (default 50.0).

    Returns:
        ((R1, G1, B1), (R2, G2, B2)) representing vibrant gradient endpoints.
    """
    # 1. Normalize image mode to RGB
    if image.mode != "RGB":
        if image.mode in ("RGBA", "LA") or (
            "transparency" in image.info and image.mode == "P"
        ):
            rgba = image.convert("RGBA")
            bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
            norm_image = Image.alpha_composite(bg, rgba).convert("RGB")
        else:
            norm_image = image.convert("RGB")
    else:
        norm_image = image

    # 2. Fast thumbnail downscale (< 3 ms)
    thumb = norm_image.resize(thumbnail_size, Image.Resampling.BILINEAR)

    # 3. Median-cut color quantization (< 5 ms)
    q = thumb.quantize(colors=num_quantize_colors, method=Image.Quantize.MEDIANCUT)
    palette = q.getpalette()
    if not palette:
        return fallback_colors

    total_pixels = thumb.width * thumb.height
    color_counts = q.getcolors(maxcolors=total_pixels)
    if not color_counts:
        return fallback_colors

    # 4. Filter dead colors and calculate vibrancy scores
    candidates: List[Tuple[Tuple[int, int, int], float]] = []
    for count, idx in color_counts:
        r, g, b = palette[idx * 3 : idx * 3 + 3]
        if filter_dead_colors and is_dead_color(r, g, b):
            continue

        _, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        # Power-law score prioritizing vibrant, saturated highlights
        score = (count ** 0.4) * s * v
        candidates.append(((r, g, b), score))

    if not candidates:
        return fallback_colors

    # 5. Select C1 as top-scoring vibrant color
    candidates.sort(key=lambda item: item[1], reverse=True)
    c1 = candidates[0][0]

    # 6. Select C2 satisfying minimum Euclidean distance
    c2: Optional[Tuple[int, int, int]] = None
    for cand_rgb, _ in candidates[1:]:
        if color_distance_rgb(c1, cand_rgb) >= min_distance:
            c2 = cand_rgb
            break

    # 7. Fallback to harmonic hue shift if no candidate met distance threshold
    if c2 is None:
        c2 = generate_harmonic_fallback(c1, min_distance=min_distance)

    return (c1, c2)
