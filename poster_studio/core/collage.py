"""
poster_studio.core.collage
~~~~~~~~~~~~~~~~~~~~~~~~~~
Multi-image gaming collage engine for Game Poster Studio.
Supports 2x2 grid, 1x2, 1x3, 1x4, and floating card collages on dynamic 2-color
gradient backdrops with individual anti-aliased rounded corners and 3D drop shadows.
"""

from __future__ import annotations

from typing import List, Optional, Tuple, Union
from PIL import Image

from poster_studio.core.geometry import resolve_canvas_size
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.mask import create_rounded_mask
from poster_studio.core.palette import extract_dominant_colors, parse_hex_color
from poster_studio.core.shadow import create_drop_shadow
from poster_studio.core.watermark import apply_watermark


def fit_and_center_crop(
    image: Image.Image,
    target_w: int,
    target_h: int,
    zoom: float = 1.0,
    pan_y_px: int = 0,
    pan_x_px: int = 0
) -> Image.Image:
    """Resizes and center-crops an image to exact target dimensions with zoom & pan."""
    iw, ih = image.size
    scale = max(target_w / iw, target_h / ih) * zoom
    nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
    resized = image.resize((nw, nh), Image.Resampling.LANCZOS)
    
    base_x = (nw - target_w) // 2
    x0 = max(0, min(nw - target_w, base_x + pan_x_px))
    
    base_y = (nh - target_h) // 2
    y0 = max(0, min(nh - target_h, base_y + pan_y_px))
    
    return resized.crop((x0, y0, x0 + target_w, y0 + target_h))


def create_game_collage(
    images: List[Image.Image],
    ratio: str = "4:5",
    margin_x: int = 42,
    margin_top: int = 44,
    gap: int = 18,
    curve: int = 28,
    auto_colors: bool = True,
    color1: Optional[str] = None,
    color2: Optional[str] = None,
    angle: float = 135.0,
    watermark: Optional[str] = "BAZYEPC",
    watermark_font: str = "bebas_neue",
    watermark_color: str = "#F5BA42",
    watermark_stroke_color: str = "#0B131F",
    watermark_stroke_width: int = 4,
    pans_y: Optional[List[int]] = None
) -> Image.Image:
    """
    Creates a floating-card multi-image collage on a dynamic 2-color gradient backdrop.

    Parameters:
        images: List of 2, 3, or 4 PIL Images.
        ratio: Aspect ratio preset ('4:5', '1:1', '9:16', '16:9').
        margin_x: Horizontal outer canvas margin.
        margin_top: Top outer canvas margin.
        gap: Spacing in pixels between cards.
        curve: Corner curvature radius for cards.
        auto_colors: Extract unified dominant color pair from all images.
        color1, color2: Optional explicit hex color overrides.
        angle: Gradient rotation angle in degrees.
        watermark: Watermark branding text.
        pans_y: Optional list of vertical pan offsets (px) per image.

    Returns:
        Composited PIL Image.
    """
    if not images:
        raise ValueError("At least one image is required for collage creation.")

    # 1. Resolve canvas dimensions
    cw, ch = resolve_canvas_size(ratio, hd=False)

    # 2. Extract or resolve colors
    if not auto_colors and color1 and color2:
        c1 = parse_hex_color(color1)
        c2 = parse_hex_color(color2)
    else:
        # Create thumbnail strip across all images for unified palette extraction
        num_imgs = len(images)
        thumb_strip = Image.new("RGB", (160 * num_imgs, 160))
        for i, im in enumerate(images):
            thumb_strip.paste(im.convert("RGB").resize((160, 160)), (i * 160, 0))
        c1, c2 = extract_dominant_colors(thumb_strip)
        if color1:
            c1 = parse_hex_color(color1)
        if color2:
            c2 = parse_hex_color(color2)

    # 3. Generate background gradient
    canvas = generate_linear_gradient((cw, ch), c1, c2, angle=angle)

    # 4. Determine grid layout (2x2 for 4 images, 1x2 for 2 images)
    num = len(images)
    if num >= 4 or num == 3:
        # 2x2 grid
        rows, cols = 2, 2
        active_imgs = images[:4]
    else:
        # 1x2 side by side
        rows, cols = 1, 2
        active_imgs = images[:2]

    # Calculate card dimensions
    bottom_reserved = 80 if watermark else 40
    avail_w = cw - (2 * margin_x) - ((cols - 1) * gap)
    card_w = max(10, avail_w // cols)

    avail_h = ch - margin_top - bottom_reserved - ((rows - 1) * gap)
    card_h = max(10, avail_h // rows)

    # 5. Pre-render card rounded mask & 3D drop shadow
    card_mask = create_rounded_mask((card_w, card_h), radius=curve)
    shadow_pad = 25
    _, card_shadow = create_drop_shadow(
        card_mask,
        (card_w + 2 * shadow_pad, card_h + 2 * shadow_pad),
        offset=(0, 12),
        blur_radius=18,
        opacity=0.60,
        card_position=(shadow_pad, shadow_pad)
    )

    # Calculate positions
    positions: List[Tuple[int, int]] = []
    for r in range(rows):
        for c in range(cols):
            x = margin_x + c * (card_w + gap)
            y = margin_top + r * (card_h + gap)
            positions.append((x, y))

    # Paste shadows first
    for i in range(len(active_imgs)):
        x, y = positions[i]
        canvas.paste((0, 0, 0), (x - shadow_pad, y - shadow_pad), card_shadow)

    # Paste cropped cards
    for i, img in enumerate(active_imgs):
        x, y = positions[i]
        py = pans_y[i] if (pans_y and i < len(pans_y)) else 0
        cropped = fit_and_center_crop(img.convert("RGB"), card_w, card_h, pan_y_px=py)
        canvas.paste(cropped, (x, y), card_mask)

    # 6. Apply watermark
    if watermark:
        canvas = apply_watermark(
            canvas,
            text=watermark,
            font_name=watermark_font,
            font_size=44,
            text_color=watermark_color,
            stroke_color=watermark_stroke_color,
            stroke_width=watermark_stroke_width,
            margin_bottom=30
        )

    return canvas
