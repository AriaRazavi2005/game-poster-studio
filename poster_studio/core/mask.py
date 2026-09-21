"""
poster_studio.core.mask
~~~~~~~~~~~~~~~~~~~~~~~
Supersampled anti-aliased rounded corner mask generation using Lanczos downsampling.
Outputs single-channel 'L' grayscale masks.
"""

from __future__ import annotations

from typing import Tuple
from PIL import Image, ImageDraw


def create_rounded_mask(
    size: Tuple[int, int],
    radius: int,
    supersample: int = 2,
    *,
    supersample_factor: int | None = None
) -> Image.Image:
    """
    Generates an 8-bit single-channel ('L') anti-aliased rounded rectangle mask.

    Parameters:
        size: Target (width, height) of the poster card in pixels.
        radius: Corner curvature radius in pixels (0 to 120+).
        supersample: Supersampling scale factor (default 2; 2x is optimal for speed/quality).
        supersample_factor: Optional keyword alias for supersample.

    Returns:
        PIL.Image.Image in mode 'L' (0 = transparent/outside, 255 = opaque/inside).

    Raises:
        ValueError: If width or height are non-positive, or supersample < 1.
    """
    if supersample_factor is not None:
        supersample = supersample_factor

    w, h = size
    if w <= 0 or h <= 0:
        raise ValueError(f"Mask size must be positive integers, got ({w}, {h})")
    if supersample < 1:
        raise ValueError(f"Supersample factor must be >= 1, got {supersample}")

    # Clamp radius to valid geometric range [0, min(w, h) // 2]
    max_radius = min(w, h) // 2
    r_eff = max(0, min(int(radius), max_radius))

    # Fast short-circuit path: Sharp rectangle with zero radius
    if r_eff == 0:
        return Image.new("L", (w, h), 255)

    # 1x path if supersample == 1
    if supersample == 1:
        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle([0, 0, w - 1, h - 1], radius=r_eff, fill=255)
        return mask

    # High-resolution supersampled canvas
    k = int(supersample)
    w_hi, h_hi = w * k, h * k
    r_hi = r_eff * k

    hi_mask = Image.new("L", (w_hi, h_hi), 0)
    draw = ImageDraw.Draw(hi_mask)
    draw.rounded_rectangle([0, 0, w_hi - 1, h_hi - 1], radius=r_hi, fill=255)

    # Downsample back to target resolution with Lanczos interpolation
    return hi_mask.resize((w, h), resample=Image.Resampling.LANCZOS)


# Alias matching survey_arch & processor conventions
generate_rounded_mask = create_rounded_mask
