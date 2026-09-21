"""
poster_studio.core.shadow
~~~~~~~~~~~~~~~~~~~~~~~~~
Realistic 3D Gaussian drop shadow for floating poster cards.
Operates exclusively on single-channel 'L' grayscale masks to eliminate
4-channel RGBA memory and convolution overhead.
"""

from __future__ import annotations

from typing import Any, Tuple, Union
from PIL import Image, ImageFilter


def create_drop_shadow(
    mask: Image.Image,
    canvas_size: Tuple[int, int],
    offset: Tuple[int, int] = (0, 15),
    blur_radius: int = 25,
    opacity: float = 0.48,
    card_position: Tuple[int, int] = (0, 0),
    shadow_color: Tuple[int, int, int] = (0, 0, 0)
) -> Tuple[Tuple[int, int, int], Image.Image]:
    """
    Generates a single-channel 'L' drop shadow mask positioned for the canvas.

    Parameters:
        mask: Single-channel 'L' poster mask (size matches poster or canvas).
        canvas_size: (width, height) of the target canvas.
        offset: (offset_x, offset_y) directional shadow offset (default (0, 15)).
        blur_radius: Gaussian blur radius in pixels (default 25).
        opacity: Shadow intensity multiplier [0.0, 1.0] (default 0.48).
        card_position: (x, y) top-left placement of poster card on canvas.
        shadow_color: RGB shadow color tuple (default (0, 0, 0)).

    Returns:
        (shadow_color, shadow_mask_L) ready for direct canvas.paste().

    Raises:
        ValueError: If canvas_size has non-positive dimensions.
    """
    cw, ch = canvas_size
    if cw <= 0 or ch <= 0:
        raise ValueError(f"Canvas dimensions must be positive, got ({cw}, {ch})")

    op = max(0.0, min(float(opacity), 1.0))
    if op <= 0.0 or blur_radius < 0:
        return (shadow_color, Image.new("L", (cw, ch), 0))

    # Pre-scale poster mask alpha by opacity
    if op < 1.0:
        lut = [int(round(i * op)) for i in range(256)]
        scaled_mask = mask.point(lut)
    else:
        scaled_mask = mask

    # Allocate single-channel canvas mask
    shadow_canvas = Image.new("L", (cw, ch), 0)

    # Determine paste location
    if mask.size == canvas_size:
        paste_x = offset[0]
        paste_y = offset[1]
    else:
        paste_x = card_position[0] + offset[0]
        paste_y = card_position[1] + offset[1]

    shadow_canvas.paste(scaled_mask, (paste_x, paste_y))

    # Apply Gaussian blur on single channel
    if blur_radius > 0:
        blurred_shadow = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur_radius))
    else:
        blurred_shadow = shadow_canvas

    return (shadow_color, blurred_shadow)


def apply_drop_shadow(
    canvas: Image.Image,
    shadow_mask: Image.Image,
    shadow_color: Tuple[int, int, int] = (0, 0, 0)
) -> Image.Image:
    """
    Applies the drop shadow mask directly onto the RGB canvas in-place.

    Parameters:
        canvas: Target RGB PIL Image.
        shadow_mask: Single-channel 'L' shadow mask matching canvas size.
        shadow_color: RGB color to blend (default (0, 0, 0)).

    Returns:
        The modified canvas Image.
    """
    canvas.paste(shadow_color, (0, 0), mask=shadow_mask)
    return canvas


def create_drop_shadow_mask(
    canvas_size: Tuple[int, int],
    placement: Any,
    poster_mask: Image.Image,
    offset_y: int = 15,
    blur_radius: int = 25,
    opacity: float = 0.48,
    offset_x: int = 0
) -> Image.Image:
    """
    Convenience wrapper for processor pipeline accepting a PosterPlacement object.

    Returns:
        shadow_mask ('L' Image).
    """
    card_pos = (placement.x, placement.y) if hasattr(placement, "x") else placement
    _, shadow_mask = create_drop_shadow(
        mask=poster_mask,
        canvas_size=canvas_size,
        offset=(offset_x, offset_y),
        blur_radius=blur_radius,
        opacity=opacity,
        card_position=card_pos
    )
    return shadow_mask


def apply_shadow_to_canvas(
    canvas: Image.Image,
    shadow_mask: Image.Image,
    shadow_color: Tuple[int, int, int] = (0, 0, 0)
) -> Image.Image:
    """Alias for apply_drop_shadow."""
    return apply_drop_shadow(canvas, shadow_mask, shadow_color)


def create_drop_shadow_from_placement(
    canvas_size: Tuple[int, int],
    placement_x: int,
    placement_y: int,
    card_mask: Image.Image,
    offset_y: int = 15,
    blur_radius: int = 25,
    opacity: float = 0.48,
    shadow_color: Tuple[int, int, int] = (0, 0, 0)
) -> Tuple[Tuple[int, int, int], Image.Image]:
    """Convenience wrapper using explicit placement coordinates."""
    return create_drop_shadow(
        mask=card_mask,
        canvas_size=canvas_size,
        offset=(0, offset_y),
        blur_radius=blur_radius,
        opacity=opacity,
        card_position=(placement_x, placement_y),
        shadow_color=shadow_color
    )
