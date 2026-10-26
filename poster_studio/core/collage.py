"""
poster_studio.core.collage
~~~~~~~~~~~~~~~~~~~~~~~~~~
Data-driven Multi-Image Gaming Collage Engine (Collage 2.0).
Includes 22 built-in templates (2 to 9 images), custom JSON template loading,
'cover' / 'contain' / 'smart' fit modes, hexagonal & circular masks, rotated cards,
and decorative overlays (VS badge, Trilogy numerals, Film strip, Polaroid frames).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from poster_studio.core.geometry import resolve_canvas_size
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.mask import create_rounded_mask
from poster_studio.core.palette import extract_dominant_colors, parse_hex_color
from poster_studio.core.shadow import create_drop_shadow
from poster_studio.core.watermark import apply_watermark, apply_typography_layers, resolve_watermark_font

# ==============================================================================
# 22 BUILT-IN COLLAGE TEMPLATES (Normalized 0..1 coordinates inside margin box)
# ==============================================================================

COLLAGE_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "duo_split": {
        "name": "Duo Split (Side by Side)",
        "slots": 2,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.485, "h": 1.0},
            {"x": 0.515, "y": 0.0, "w": 0.485, "h": 1.0},
        ],
    },
    "duo_stack": {
        "name": "Duo Stack (Top & Bottom)",
        "slots": 2,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.485},
            {"x": 0.0, "y": 0.515, "w": 1.0, "h": 0.485},
        ],
    },
    "versus": {
        "name": "Versus Head-to-Head (VS Badge)",
        "slots": 2,
        "decoration": "vs_badge",
        "cells": [
            {"x": 0.0, "y": 0.02, "w": 0.48, "h": 0.96},
            {"x": 0.52, "y": 0.02, "w": 0.48, "h": 0.96},
        ],
    },
    "diagonal_split": {
        "name": "Diagonal Split Showcase",
        "slots": 2,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.58, "h": 0.58},
            {"x": 0.42, "y": 0.42, "w": 0.58, "h": 0.58},
        ],
    },
    "trilogy": {
        "name": "Trilogy Columns (I / II / III)",
        "slots": 3,
        "decoration": "roman_numerals",
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.315, "h": 1.0},
            {"x": 0.3425, "y": 0.0, "w": 0.315, "h": 1.0},
            {"x": 0.685, "y": 0.0, "w": 0.315, "h": 1.0},
        ],
    },
    "hero_left": {
        "name": "Hero Left (1 Large + 2 Right)",
        "slots": 3,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.60, "h": 1.0},
            {"x": 0.625, "y": 0.0, "w": 0.375, "h": 0.485},
            {"x": 0.625, "y": 0.515, "w": 0.375, "h": 0.485},
        ],
    },
    "hero_top": {
        "name": "Hero Top (1 Large Top + 2 Bottom)",
        "slots": 3,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.58},
            {"x": 0.0, "y": 0.605, "w": 0.485, "h": 0.395},
            {"x": 0.515, "y": 0.605, "w": 0.485, "h": 0.395},
        ],
    },
    "grid_2x2": {
        "name": "Classic 2x2 Floating Grid",
        "slots": 4,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.485, "h": 0.485},
            {"x": 0.515, "y": 0.0, "w": 0.485, "h": 0.485},
            {"x": 0.0, "y": 0.515, "w": 0.485, "h": 0.485},
            {"x": 0.515, "y": 0.515, "w": 0.485, "h": 0.485},
        ],
    },
    "hero_plus_3": {
        "name": "Hero Top + 3 Bottom Strip",
        "slots": 4,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 1.0, "h": 0.62},
            {"x": 0.0, "y": 0.645, "w": 0.315, "h": 0.355},
            {"x": 0.3425, "y": 0.645, "w": 0.315, "h": 0.355},
            {"x": 0.685, "y": 0.645, "w": 0.315, "h": 0.355},
        ],
    },
    "quad_strip": {
        "name": "Quad Vertical Strip (Quadrilogy)",
        "slots": 4,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.232, "h": 1.0},
            {"x": 0.256, "y": 0.0, "w": 0.232, "h": 1.0},
            {"x": 0.512, "y": 0.0, "w": 0.232, "h": 1.0},
            {"x": 0.768, "y": 0.0, "w": 0.232, "h": 1.0},
        ],
    },
    "timeline": {
        "name": "Franchise Evolution Timeline",
        "slots": 4,
        "decoration": "timeline_bar",
        "cells": [
            {"x": 0.0, "y": 0.05, "w": 0.232, "h": 0.90},
            {"x": 0.256, "y": 0.05, "w": 0.232, "h": 0.90},
            {"x": 0.512, "y": 0.05, "w": 0.232, "h": 0.90},
            {"x": 0.768, "y": 0.05, "w": 0.232, "h": 0.90},
        ],
    },
    "spotlight": {
        "name": "Center Spotlight (4 Corners + 1 Center Hero)",
        "slots": 5,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.485, "h": 0.485},
            {"x": 0.515, "y": 0.0, "w": 0.485, "h": 0.485},
            {"x": 0.0, "y": 0.515, "w": 0.485, "h": 0.485},
            {"x": 0.515, "y": 0.515, "w": 0.485, "h": 0.485},
            {"x": 0.22, "y": 0.22, "w": 0.56, "h": 0.56},
        ],
    },
    "mosaic_5": {
        "name": "Asymmetric 5-Game Mosaic",
        "slots": 5,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.58, "h": 0.54},
            {"x": 0.605, "y": 0.0, "w": 0.395, "h": 0.54},
            {"x": 0.0, "y": 0.565, "w": 0.315, "h": 0.435},
            {"x": 0.3425, "y": 0.565, "w": 0.315, "h": 0.435},
            {"x": 0.685, "y": 0.565, "w": 0.315, "h": 0.435},
        ],
    },
    "grid_3x2": {
        "name": "6-Pack Grid (2 Columns x 3 Rows)",
        "slots": 6,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.485, "h": 0.315},
            {"x": 0.515, "y": 0.0, "w": 0.485, "h": 0.315},
            {"x": 0.0, "y": 0.3425, "w": 0.485, "h": 0.315},
            {"x": 0.515, "y": 0.3425, "w": 0.485, "h": 0.315},
            {"x": 0.0, "y": 0.685, "w": 0.485, "h": 0.315},
            {"x": 0.515, "y": 0.685, "w": 0.485, "h": 0.315},
        ],
    },
    "magazine": {
        "name": "Editorial Magazine Spread",
        "slots": 4,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.64, "h": 0.68},
            {"x": 0.665, "y": 0.0, "w": 0.335, "h": 0.33},
            {"x": 0.665, "y": 0.35, "w": 0.335, "h": 0.33},
            {"x": 0.0, "y": 0.705, "w": 1.0, "h": 0.295},
        ],
    },
    "grid_3x3": {
        "name": "9-Game Monthly Showcase (3x3)",
        "slots": 9,
        "cells": [
            {"x": c * 0.3425, "y": r * 0.3425, "w": 0.315, "h": 0.315}
            for r in range(3)
            for c in range(3)
        ],
    },
    "fan_stack": {
        "name": "Fanned Overlapping Bundle Cards",
        "slots": 3,
        "cells": [
            {"x": 0.04, "y": 0.14, "w": 0.52, "h": 0.72, "rotation": 10},
            {"x": 0.44, "y": 0.14, "w": 0.52, "h": 0.72, "rotation": -10},
            {"x": 0.22, "y": 0.08, "w": 0.56, "h": 0.78, "rotation": 0},
        ],
    },
    "polaroid_scatter": {
        "name": "Polaroid Instant Frame Scatter",
        "slots": 4,
        "decoration": "polaroid",
        "cells": [
            {"x": 0.02, "y": 0.02, "w": 0.46, "h": 0.46, "rotation": 4},
            {"x": 0.52, "y": 0.03, "w": 0.46, "h": 0.46, "rotation": -4},
            {"x": 0.03, "y": 0.51, "w": 0.46, "h": 0.46, "rotation": -3},
            {"x": 0.51, "y": 0.51, "w": 0.46, "h": 0.46, "rotation": 5},
        ],
    },
    "film_strip": {
        "name": "Cinema Film Strip Reel",
        "slots": 3,
        "decoration": "film_sprockets",
        "cells": [
            {"x": 0.08, "y": 0.01, "w": 0.84, "h": 0.31},
            {"x": 0.08, "y": 0.345, "w": 0.84, "h": 0.31},
            {"x": 0.08, "y": 0.68, "w": 0.84, "h": 0.31},
        ],
    },
    "staircase": {
        "name": "Staircase Podium Ranking",
        "slots": 3,
        "cells": [
            {"x": 0.0, "y": 0.0, "w": 0.315, "h": 0.82},
            {"x": 0.3425, "y": 0.09, "w": 0.315, "h": 0.82},
            {"x": 0.685, "y": 0.18, "w": 0.315, "h": 0.82},
        ],
    },
    "hexagon_hive": {
        "name": "Hexagonal eSports Hive",
        "slots": 4,
        "cells": [
            {"x": 0.02, "y": 0.02, "w": 0.46, "h": 0.46, "clip": "hexagon"},
            {"x": 0.52, "y": 0.02, "w": 0.46, "h": 0.46, "clip": "hexagon"},
            {"x": 0.02, "y": 0.52, "w": 0.46, "h": 0.46, "clip": "hexagon"},
            {"x": 0.52, "y": 0.52, "w": 0.46, "h": 0.46, "clip": "hexagon"},
        ],
    },
    "box_shelf": {
        "name": "Collector Shelf Display",
        "slots": 4,
        "decoration": "shelf_bars",
        "cells": [
            {"x": 0.04, "y": 0.02, "w": 0.43, "h": 0.45},
            {"x": 0.53, "y": 0.02, "w": 0.43, "h": 0.45},
            {"x": 0.04, "y": 0.52, "w": 0.43, "h": 0.45},
            {"x": 0.53, "y": 0.52, "w": 0.43, "h": 0.45},
        ],
    },
}


def list_collage_templates() -> Dict[str, Dict[str, Any]]:
    """Returns catalog of all 22 built-in collage templates."""
    return dict(COLLAGE_TEMPLATES)


list_templates = list_collage_templates


def resolve_collage_template(template: Optional[str], num_images: int) -> Dict[str, Any]:
    """Resolves a template by ID, JSON path, or 'auto' based on image count."""
    if not template or template.strip().lower() == "auto":
        auto_map = {
            1: "duo_split",
            2: "duo_split",
            3: "hero_left",
            4: "grid_2x2",
            5: "spotlight",
            6: "grid_3x2",
        }
        chosen = auto_map.get(num_images, "grid_3x3" if num_images >= 7 else "grid_2x2")
        return COLLAGE_TEMPLATES[chosen]

    key = template.strip().lower()
    if key in COLLAGE_TEMPLATES:
        return COLLAGE_TEMPLATES[key]

    p = Path(template)
    if p.is_file():
        return json.loads(p.read_text(encoding="utf-8"))

    valid = ", ".join(sorted(COLLAGE_TEMPLATES.keys()))
    raise ValueError(f"Unknown collage template '{template}'. Available: {valid}, auto")


def fit_and_center_crop(
    image: Image.Image,
    target_w: int,
    target_h: int,
    zoom: float = 1.0,
    pan_y_px: int = 0,
    pan_x_px: int = 0,
    fit: str = "cover",
) -> Image.Image:
    """
    Fits an image into (target_w, target_h) using:
      - 'cover': center crop with zoom & pan
      - 'contain': full uncropped cover over blurred backdrop of the same image
      - 'smart': crops around the highest gradient-energy focal point
    """
    iw, ih = image.size
    mode = (fit or "cover").strip().lower()

    if mode == "contain":
        # Blurred background fill
        bg_scale = max(target_w / max(1, iw), target_h / max(1, ih))
        bw, bh = max(1, round(iw * bg_scale)), max(1, round(ih * bg_scale))
        bg = image.convert("RGB").resize((bw, bh), Image.Resampling.BILINEAR)
        bx, by = (bw - target_w) // 2, (bh - target_h) // 2
        bg_crop = bg.crop((bx, by, bx + target_w, by + target_h))
        small = bg_crop.resize((max(8, target_w // 6), max(8, target_h // 6)), Image.Resampling.BILINEAR)
        blurred = ImageEnhance.Brightness(
            small.filter(ImageFilter.GaussianBlur(radius=4)).resize((target_w, target_h), Image.Resampling.BILINEAR)
        ).enhance(0.5)

        fg_scale = min(target_w / max(1, iw), target_h / max(1, ih)) * zoom
        fw, fh = max(1, round(iw * fg_scale)), max(1, round(ih * fg_scale))
        fg = image.convert("RGB").resize((fw, fh), Image.Resampling.LANCZOS)
        blurred.paste(fg, ((target_w - fw) // 2 + pan_x_px, (target_h - fh) // 2 + pan_y_px))
        return blurred

    scale = max(target_w / max(1, iw), target_h / max(1, ih)) * zoom
    nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
    resized = image.convert("RGB").resize((nw, nh), Image.Resampling.LANCZOS)

    if mode == "smart" and pan_x_px == 0 and pan_y_px == 0:
        gray = np.asarray(resized.convert("L"), dtype=np.float32)
        if nw > target_w:
            col_energy = np.abs(np.diff(gray, axis=0)).sum(axis=0)
            best_x = int(np.argmax(np.convolve(col_energy, np.ones(target_w), mode="valid")))
        else:
            best_x = 0
        if nh > target_h:
            row_energy = np.abs(np.diff(gray, axis=1)).sum(axis=1)
            best_y = int(np.argmax(np.convolve(row_energy, np.ones(target_h), mode="valid")))
        else:
            best_y = 0
        x0 = max(0, min(nw - target_w, best_x))
        y0 = max(0, min(nh - target_h, best_y))
        return resized.crop((x0, y0, x0 + target_w, y0 + target_h))

    base_x = (nw - target_w) // 2
    x0 = max(0, min(nw - target_w, base_x + pan_x_px))
    base_y = (nh - target_h) // 2
    y0 = max(0, min(nh - target_h, base_y + pan_y_px))
    return resized.crop((x0, y0, x0 + target_w, y0 + target_h))


def _create_cell_mask(w: int, h: int, radius: int, clip_shape: str = "rect") -> Image.Image:
    shape = (clip_shape or "rect").lower()
    if shape == "circle":
        mask = Image.new("L", (w * 2, h * 2), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, w * 2 - 1, h * 2 - 1), fill=255)
        return mask.resize((w, h), Image.Resampling.LANCZOS)
    if shape == "hexagon":
        mask = Image.new("L", (w * 2, h * 2), 0)
        cx, cy = w, h
        rx, ry = w - 2, h - 2
        pts = [
            (cx + rx * math.cos(math.radians(60 * k - 30)), cy + ry * math.sin(math.radians(60 * k - 30)))
            for k in range(6)
        ]
        ImageDraw.Draw(mask).polygon(pts, fill=255)
        return mask.resize((w, h), Image.Resampling.LANCZOS)
    return create_rounded_mask((w, h), radius=radius)


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
    pans_y: Optional[List[int]] = None,
    pans_x: Optional[List[int]] = None,
    zooms: Optional[List[float]] = None,
    template: Optional[str] = None,
    fit: str = "cover",
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    badge: Optional[str] = None,
) -> Image.Image:
    """
    Creates a floating-card multi-image collage using any of the 22 built-in templates
    or a custom JSON template definition.
    """
    if not images:
        raise ValueError("At least one image is required for collage creation.")

    cw, ch = resolve_canvas_size(ratio, hd=False)

    if not auto_colors and color1 and color2:
        c1 = parse_hex_color(color1)
        c2 = parse_hex_color(color2)
    else:
        num_imgs = len(images)
        thumb_strip = Image.new("RGB", (160 * num_imgs, 160))
        for i, im in enumerate(images):
            thumb_strip.paste(im.convert("RGB").resize((160, 160)), (i * 160, 0))
        c1, c2 = extract_dominant_colors(thumb_strip)
        if color1:
            c1 = parse_hex_color(color1)
        if color2:
            c2 = parse_hex_color(color2)

    canvas = generate_linear_gradient((cw, ch), c1, c2, angle=angle)

    # Resolve template
    tpl = resolve_collage_template(template, len(images))
    cells = tpl["cells"]
    decoration = tpl.get("decoration")

    bottom_reserved = 85 if (watermark or title) else 42
    avail_w = max(40, cw - 2 * margin_x)
    avail_h = max(40, ch - margin_top - bottom_reserved)

    if decoration == "film_sprockets":
        draw_bg = ImageDraw.Draw(canvas)
        strip_l = margin_x
        strip_r = cw - margin_x
        draw_bg.rounded_rectangle((strip_l, margin_top - 10, strip_r, margin_top + avail_h + 10), radius=16, fill=(12, 12, 16))
        for sy in range(margin_top + 8, margin_top + avail_h - 12, 34):
            draw_bg.rounded_rectangle((strip_l + 10, sy, strip_l + 24, sy + 18), radius=3, fill=(220, 220, 220))
            draw_bg.rounded_rectangle((strip_r - 24, sy, strip_r - 10, sy + 18), radius=3, fill=(220, 220, 220))

    cell_boxes: List[Tuple[int, int, int, int]] = []

    for idx, cell in enumerate(cells):
        img = images[idx % len(images)].convert("RGB")
        cx = margin_x + round(float(cell["x"]) * avail_w)
        cy = margin_top + round(float(cell["y"]) * avail_h)
        card_w = max(16, round(float(cell["w"]) * avail_w))
        card_h = max(16, round(float(cell["h"]) * avail_h))
        rot = float(cell.get("rotation", 0.0))
        clip_shape = str(cell.get("clip", "rect"))
        cell_curve = int(cell.get("curve", curve))
        cell_fit = str(cell.get("fit", fit))

        py = pans_y[idx] if (pans_y and idx < len(pans_y)) else 0
        px = pans_x[idx] if (pans_x and idx < len(pans_x)) else 0
        zm = zooms[idx] if (zooms and idx < len(zooms)) else 1.0

        cropped = fit_and_center_crop(img, card_w, card_h, zoom=zm, pan_y_px=py, pan_x_px=px, fit=cell_fit)

        if decoration == "polaroid":
            pad = 12
            bot_pad = 36
            pol = Image.new("RGB", (card_w, card_h), (248, 250, 252))
            inner = fit_and_center_crop(img, max(8, card_w - 2 * pad), max(8, card_h - pad - bot_pad), fit=cell_fit)
            pol.paste(inner, (pad, pad))
            cropped = pol
            cell_curve = 8

        card_mask = _create_cell_mask(card_w, card_h, radius=cell_curve, clip_shape=clip_shape)

        if abs(rot) > 0.1:
            rgba = cropped.convert("RGBA")
            rgba.putalpha(card_mask)
            rotated = rgba.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)
            rx = cx - (rotated.width - card_w) // 2
            ry = cy - (rotated.height - card_h) // 2
            canvas.paste(rotated.convert("RGB"), (rx, ry), mask=rotated.split()[3])
        else:
            shadow_pad = 24
            _, card_shadow = create_drop_shadow(
                card_mask,
                (card_w + 2 * shadow_pad, card_h + 2 * shadow_pad),
                offset=(0, 12),
                blur_radius=18,
                opacity=0.58,
                card_position=(shadow_pad, shadow_pad),
            )
            canvas.paste((0, 0, 0), (cx - shadow_pad, cy - shadow_pad), card_shadow)
            canvas.paste(cropped, (cx, cy), card_mask)

        cell_boxes.append((cx, cy, card_w, card_h))

    # Decorative overlays
    draw = ImageDraw.Draw(canvas)
    if decoration == "vs_badge" and len(cell_boxes) >= 2:
        mx, my = cw // 2, margin_top + avail_h // 2
        r = 38
        draw.ellipse((mx - r, my - r, mx + r, my + r), fill=(220, 38, 38), outline=(255, 255, 255), width=4)
        vs_font = resolve_watermark_font("Bebas Neue", 36)
        bbox = vs_font.getbbox("VS")
        draw.text((mx - (bbox[2] - bbox[0]) // 2, my - (bbox[3] - bbox[1]) // 2 - bbox[1]), "VS", font=vs_font, fill=(255, 255, 255))

    elif decoration == "roman_numerals":
        numerals = ["I", "II", "III", "IV", "V"]
        n_font = resolve_watermark_font("Bebas Neue", 28)
        for idx, (bx, by, bw, bh) in enumerate(cell_boxes[:5]):
            num = numerals[idx]
            nb = n_font.getbbox(num)
            nw_t, nh_t = nb[2] - nb[0], nb[3] - nb[1]
            cx_n = bx + bw // 2
            cy_n = by + bh - 34
            draw.rounded_rectangle((cx_n - 22, cy_n - 16, cx_n + 22, cy_n + 16), radius=8, fill=(15, 23, 42), outline=(245, 186, 66), width=2)
            draw.text((cx_n - nw_t // 2, cy_n - nh_t // 2 - nb[1]), num, font=n_font, fill=(245, 186, 66))

    elif decoration == "shelf_bars":
        for sy in [margin_top + int(avail_h * 0.48), margin_top + int(avail_h * 0.98)]:
            draw.rounded_rectangle((margin_x - 10, sy, cw - margin_x + 10, sy + 14), radius=4, fill=(30, 41, 59), outline=(71, 85, 105), width=1)

    elif decoration == "timeline_bar":
        ty = margin_top + avail_h + 8
        draw.line([(margin_x + 30, ty), (cw - margin_x - 30, ty)], fill=(245, 186, 66), width=4)
        for bx, _, bw, _ in cell_boxes:
            dot_x = bx + bw // 2
            draw.ellipse((dot_x - 7, ty - 7, dot_x + 7, ty + 7), fill=(245, 186, 66), outline=(15, 23, 42), width=2)

    if title or subtitle or badge:
        apply_typography_layers(
            canvas,
            title=title,
            subtitle=subtitle,
            badge=badge,
            font_name=watermark_font,
            text_color=watermark_color,
            stroke_color=watermark_stroke_color,
        )

    if watermark:
        canvas = apply_watermark(
            canvas,
            text=watermark,
            font_name=watermark_font,
            font_size=44,
            text_color=watermark_color,
            stroke_color=watermark_stroke_color,
            stroke_width=watermark_stroke_width,
            margin_bottom=30,
        )

    return canvas
