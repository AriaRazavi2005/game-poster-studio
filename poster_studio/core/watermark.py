"""
poster_studio.core.watermark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Watermark and branding typography layer rendering "BAZYEPC" with stroke
outlines and text drop shadows for legibility across any gradient.
Features a 4-tier font resolution fallback chain for bulletproof cross-platform operation.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, Optional, Tuple, Union
from PIL import Image, ImageDraw, ImageFont

# Curated gaming & display font catalog (human-friendly names mapped to font files)
AVAILABLE_FONTS: Dict[str, str] = {
    # Core Gaming & Action Fonts
    "Anton (Default Gaming)": "Anton-Regular.ttf",
    "Bebas Neue (Bold Tall)": "BebasNeue-Regular.ttf",
    "Russo One (Action Block)": "RussoOne-Regular.ttf",
    "Orbitron (Cyberpunk)": "Orbitron-Bold.ttf",
    "Audiowide (Speed / Sci-Fi)": "Audiowide-Regular.ttf",
    "Bungee (Heavy Brutalist)": "Bungee-Regular.ttf",
    "Black Ops One (Military Stencil)": "BlackOpsOne-Regular.ttf",
    "Press Start 2P (Retro 8-Bit Arcade)": "PressStart2P-Regular.ttf",
    # Display & Creative Styles (matching Collage Maker)
    "Luckiest Guy (Bubble / Cartoon)": "LuckiestGuy-Regular.ttf",
    "Pacifico (Cursive Script)": "Pacifico-Regular.ttf",
    "Creepster (Horror / Dripping)": "Creepster-Regular.ttf",
    "Special Elite (Grunge Typewriter)": "SpecialElite-Regular.ttf",
    "Unifraktur (Gothic / Blackletter)": "UnifrakturMaguntia-Book.ttf",
    # System Fonts
    "Impact (Blockbuster)": "impact.ttf",
    "Arial Black (Ultra Heavy)": "ariblk.ttf",
    "Bahnschrift (Modern Geometric)": "bahnschrift.ttf",
    "Segoe UI Bold (Clean Modern)": "segoeuib.ttf",
    "Trebuchet Bold (Dynamic Punch)": "trebucbd.ttf",
    "Consolas Bold (Tech Hacker)": "consolab.ttf",
}

# Preferred system font candidates for gaming typography
WINDOWS_SYSTEM_FONTS = [
    "impact.ttf",
    "ariblk.ttf",
    "bahnschrift.ttf",
    "segoeuib.ttf",
    "trebucbd.ttf",
    "tahomabd.ttf",
    "arialbd.ttf",
    "consolab.ttf",
]

LINUX_SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def get_available_fonts() -> Dict[str, str]:
    """Returns dictionary of available gaming and system fonts."""
    return dict(AVAILABLE_FONTS)


def resolve_watermark_font(
    font_name_or_path: Optional[str] = None,
    font_size: int = 28
) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """
    Resolves an appropriate font using a robust 5-tier fallback chain.

    Tier 1: Named catalog font from AVAILABLE_FONTS.
    Tier 2: Caller-specified custom font path or name.
    Tier 3: Bundled gaming fonts in poster_studio/assets/fonts/.
    Tier 4: Operating system fonts (Windows / Linux standard paths).
    Tier 5: PIL built-in default font (ImageFont.load_default()).
    """
    size = max(8, int(font_size))

    # Tier 1: Check if font is a key, value, or normalized match in AVAILABLE_FONTS
    resolved_target = font_name_or_path
    if font_name_or_path:
        if font_name_or_path in AVAILABLE_FONTS:
            resolved_target = AVAILABLE_FONTS[font_name_or_path]
        elif font_name_or_path in AVAILABLE_FONTS.values():
            resolved_target = font_name_or_path
        else:
            norm_query = re.sub(r"[^a-z0-9]", "", str(font_name_or_path).lower())
            for key, val in AVAILABLE_FONTS.items():
                norm_key = re.sub(r"[^a-z0-9]", "", key.lower())
                norm_val = re.sub(r"[^a-z0-9]", "", val.lower())
                if (norm_query and (norm_query in norm_key or norm_query in norm_val
                                    or norm_key.startswith(norm_query) or norm_val.startswith(norm_query))):
                    resolved_target = val
                    break

    # Tier 2: Direct file path or system font name
    if resolved_target:
        if os.path.isfile(resolved_target):
            try:
                return ImageFont.truetype(resolved_target, size)
            except (OSError, IOError):
                pass
        # Check assets/fonts directory
        bundled_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
        candidate_path = bundled_dir / resolved_target
        if candidate_path.is_file():
            try:
                return ImageFont.truetype(str(candidate_path), size)
            except (OSError, IOError):
                pass
        # Check Windows Fonts directory directly
        if os.name == "nt":
            win_font_path = Path("C:/Windows/Fonts") / resolved_target
            if win_font_path.is_file():
                try:
                    return ImageFont.truetype(str(win_font_path), size)
                except (OSError, IOError):
                    pass
        try:
            return ImageFont.truetype(resolved_target, size)
        except (OSError, IOError):
            pass
    # Tier 3: Bundled project asset fonts
    bundled_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"
    if bundled_dir.is_dir():
        candidates = sorted(
            list(bundled_dir.glob("*.ttf")) + list(bundled_dir.glob("*.otf")),
            key=lambda p: (0 if "anton" in p.name.lower() else 1, p.name)
        )
        for font_file in candidates:
            try:
                return ImageFont.truetype(str(font_file), size)
            except (OSError, IOError):
                continue

    # Tier 4: Operating System fonts
    os_candidates = WINDOWS_SYSTEM_FONTS if os.name == "nt" else LINUX_SYSTEM_FONTS
    all_candidates = os_candidates + (LINUX_SYSTEM_FONTS if os.name == "nt" else WINDOWS_SYSTEM_FONTS)

    for candidate in all_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue

    # Tier 5: PIL default font (guaranteed success)
    return ImageFont.load_default()


def calculate_watermark_position(
    canvas_size: Tuple[int, int],
    text_size: Tuple[int, int],
    position: str = "bottom_center",
    margin_bottom: int = 35,
    margin_side: int = 40,
    card_placement: Optional[Tuple[int, int, int, int]] = None,
    custom_pos: Optional[Tuple[float, float]] = None
) -> Tuple[int, int]:
    """
    Calculates (x, y) coordinates for the watermark.

    Parameters:
        canvas_size: (canvas_width, canvas_height).
        text_size: (text_width, text_height).
        position: 'bottom_center', 'bottom_right', 'bottom_left', 'top_center',
                  'top_left', 'top_right', 'center', 'card_bottom_left'.
        margin_bottom: Distance in px from bottom canvas edge.
        margin_side: Distance in px from side canvas edge.
        card_placement: Optional (card_x, card_y, card_w, card_h) bounding box.
        custom_pos: Optional (x, y) coordinate, either normalized [0.0, 1.0] or absolute pixels.

    Returns:
        (x, y) pixel coordinates.
    """
    cw, ch = canvas_size
    tw, th = text_size

    # Direct custom position (e.g. from mouse drag)
    if custom_pos is not None:
        cx_val, cy_val = custom_pos
        if 0.0 <= cx_val <= 1.0 and 0.0 <= cy_val <= 1.0:
            x = round(cw * cx_val - tw / 2.0)
            y = round(ch * cy_val - th / 2.0)
        else:
            x = round(cx_val - tw / 2.0)
            y = round(cy_val - th / 2.0)
        return (max(0, min(cw - tw, x)), max(0, min(ch - th, y)))

    # Normalize card_placement if provided
    has_card = card_placement is not None
    card_l, card_t, card_r, card_b = 0, 0, cw, ch
    if has_card:
        p0, p1, p2, p3 = card_placement  # type: ignore[misc]
        if p2 > p0 and p3 > p1 and p3 <= ch + 20:
            # Format is (left, top, right, bottom)
            card_l, card_t, card_r, card_b = p0, p1, p2, p3
        else:
            # Format is (x, y, width, height)
            card_l, card_t, card_r, card_b = p0, p1, p0 + p2, p1 + p3

    pos_clean = position.strip().lower()

    if pos_clean == "card_bottom_left" and has_card:
        return (card_l + 25, card_b - th - 25)

    if pos_clean == "card_inside_bottom" and has_card:
        x = round((card_l + card_r - tw) / 2.0)
        y = round(card_b - th - 32)
        return (max(0, x), max(0, y))

    if pos_clean == "card_outside_bottom" and has_card:
        x = round((cw - tw) / 2.0)
        available_bottom = max(0, ch - card_b)
        y = round(card_b + (available_bottom - th) / 2.0)
        return (max(0, x), max(0, y))

    if pos_clean == "top_center":
        x = round((cw - tw) / 2.0)
        y = margin_bottom
    elif pos_clean == "top_left":
        x = margin_side
        y = margin_bottom
    elif pos_clean == "top_right":
        x = cw - tw - margin_side
        y = margin_bottom
    elif pos_clean == "center":
        x = round((cw - tw) / 2.0)
        y = round((ch - th) / 2.0)
    elif pos_clean == "bottom_right":
        x = cw - tw - margin_side
        y = ch - th - margin_bottom
    elif pos_clean == "bottom_left":
        x = margin_side
        y = ch - th - margin_bottom
    else:  # 'bottom_center' default (smart layout)
        x = round((cw - tw) / 2.0)
        ideal_y = ch - th - margin_bottom
        # If the card extends into the ideal bottom margin area, placing it there
        # would collide with the bottom rounded border and shadow.
        # Intelligently nest it inside the card with safe padding:
        if has_card and card_b > (ideal_y - 10):
            y = round(card_b - th - 32)
        else:
            y = ideal_y

    return (max(0, x), max(0, y))


def apply_watermark(
    canvas: Optional[Image.Image] = None,
    text: Optional[str] = "BAZYEPC",
    font_size: int = 28,
    font_name: Optional[str] = None,
    stroke_width: int = 3,
    text_color: Union[Tuple[int, int, int], str] = (255, 255, 255),
    stroke_color: Union[Tuple[int, int, int], str] = (15, 23, 42),
    shadow_offset: Tuple[int, int] = (2, 2),
    shadow_color: Tuple[int, int, int] = (0, 0, 0),
    position: str = "bottom_center",
    margin_bottom: int = 35,
    margin_side: int = 40,
    card_placement: Optional[Tuple[int, int, int, int]] = None,
    custom_position: Optional[Tuple[float, float]] = None,
    *,
    image: Optional[Image.Image] = None,
    placement: Any = None,
) -> Image.Image:
    """
    Renders high-visibility styled watermark with stroke outline and text shadow onto canvas.

    Parameters:
        canvas: RGB PIL Image to draw upon (or pass as keyword 'image').
        text: Watermark text string. If None or empty, watermark is skipped.
        font_size: Font size in pixels (default 28).
        font_name: Optional custom font file path, name, or catalog key.
        stroke_width: Outline stroke width in pixels (default 3).
        text_color: Foreground RGB text color or hex string (default (255, 255, 255)).
        stroke_color: Outline RGB stroke color or hex string (default (15, 23, 42) Slate).
        shadow_offset: (dx, dy) shadow offset in pixels (default (2, 2)).
        shadow_color: RGB shadow color (default (0, 0, 0)).
        position: 'bottom_center', 'bottom_right', 'bottom_left', 'top_center', 'center', etc.
        margin_bottom: Distance in pixels from bottom edge (default 35).
        margin_side: Distance in pixels from side edges (default 40).
        card_placement: Optional (x, y, width, height) of the poster card.
        custom_position: Optional (x, y) custom location (normalized or absolute).
        image: Keyword alias for canvas.
        placement: Optional PosterPlacement instance to extract bounding box.

    Returns:
        The composited PIL Image.
    """
    target_img = canvas if canvas is not None else image
    if target_img is None:
        raise ValueError("apply_watermark requires a target canvas or image.")

    if not text or not str(text).strip():
        return target_img

    clean_text = str(text).strip()

    # Parse hex colors if provided
    from poster_studio.core.palette import parse_hex_color
    resolved_text_color = parse_hex_color(text_color) if isinstance(text_color, str) else tuple(text_color)
    resolved_stroke_color = parse_hex_color(stroke_color) if isinstance(stroke_color, str) else tuple(stroke_color)

    # Extract placement box if PosterPlacement provided
    box = card_placement
    if box is None and placement is not None:
        if hasattr(placement, "box"):
            box = placement.box
        elif hasattr(placement, "x") and hasattr(placement, "y") and hasattr(placement, "width") and hasattr(placement, "height"):
            box = (placement.x, placement.y, placement.width, placement.height)

    draw = ImageDraw.Draw(target_img)
    font = resolve_watermark_font(font_name, font_size)

    # Measure text bounding box
    bbox = font.getbbox(clean_text)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    # Calculate position
    x, y = calculate_watermark_position(
        canvas_size=target_img.size,
        text_size=(text_w, text_h),
        position=position,
        margin_bottom=margin_bottom,
        margin_side=margin_side,
        card_placement=box,
        custom_pos=custom_position
    )

    # Pass 1: Drop Shadow
    if shadow_offset != (0, 0):
        sx = x + shadow_offset[0]
        sy = y + shadow_offset[1]
        draw.text(
            (sx, sy),
            clean_text,
            font=font,
            fill=shadow_color,
            stroke_width=stroke_width,
            stroke_fill=shadow_color,
            anchor="lt"
        )

    # Pass 2: Main Text with Stroke Outline
    draw.text(
        (x, y),
        clean_text,
        font=font,
        fill=resolved_text_color,
        stroke_width=stroke_width,
        stroke_fill=resolved_stroke_color,
        anchor="lt"
    )

    return target_img
