"""
poster_studio.core.effects
~~~~~~~~~~~~~~~~~~~~~~~~~~
Backdrop generators (blur, radial, mesh), card glow, borders, reflections,
vignette, film grain, geometric patterns, auto-trim, and platform/logo overlays.
Pure Pillow + NumPy with zero external heavy dependencies.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from poster_studio.core.gradient import generate_linear_gradient, _get_bayer_dither
from poster_studio.core.palette import parse_hex_color
from poster_studio.core.shadow import create_drop_shadow, apply_drop_shadow
from poster_studio.core. watermark import resolve_watermark_font

ColorType = Union[Tuple[int, int, int], str]


def _to_rgb(c: Optional[ColorType], fallback: Tuple[int, int, int] = (255, 255, 255)) -> Tuple[int, int, int]:
    if c is None:
        return fallback
    if isinstance(c, str):
        return parse_hex_color(c)
    return (int(c[0]), int(c[1]), int(c[2]))


def auto_trim_borders(image: Image.Image, tolerance: int = 12) -> Image.Image:
    """Automatically strips solid/near-solid black or white letterbox borders from raw covers."""
    w, h = image.size
    if w < 32 or h < 32:
        return image
    rgb = image.convert("RGB")
    for bg_col in [(0, 0, 0), (255, 255, 255), rgb.getpixel((0, 0))]:
        bg = Image.new("RGB", (w, h), bg_col)
        diff = ImageChops.difference(rgb, bg).convert("L")
        mask = diff.point(lambda p: 255 if p > tolerance else 0)
        bbox = mask.getbbox()
        if bbox and (bbox[2] - bbox[0]) >= w * 0.5 and (bbox[3] - bbox[1]) >= h * 0.5:
            if bbox != (0, 0, w, h):
                return image.crop(bbox)
    return image


def generate_backdrop(
    size: Tuple[int, int],
    raw_image: Image.Image,
    c1: Tuple[int, int, int],
    c2: Tuple[int, int, int],
    color3: Optional[ColorType] = None,
    angle: float = 135.0,
    bg_mode: str = "gradient",
    dither: bool = True,
) -> Image.Image:
    """Generates canvas background according to bg_mode ('gradient', 'blur', 'radial', 'mesh')."""
    w, h = size
    mode = (bg_mode or "gradient").strip().lower()

    if mode == "blur":
        iw, ih = raw_image.size
        scale = max(w / max(1, iw), h / max(1, ih))
        nw, nh = max(1, round(iw * scale)), max(1, round(ih * scale))
        cover = raw_image.convert("RGB").resize((nw, nh), Image.Resampling.BILINEAR)
        x0, y0 = (nw - w) // 2, (nh - h) // 2
        cropped = cover.crop((x0, y0, x0 + w, y0 + h))
        # Fast downscale-blur-upscale for speed (< 15ms)
        small = cropped.resize((max(16, w // 8), max(16, h // 8)), Image.Resampling.BILINEAR)
        blurred = small.filter(ImageFilter.GaussianBlur(radius=6)).resize((w, h), Image.Resampling.BILINEAR)
        return ImageEnhance.Brightness(blurred).enhance(0.55)

    if mode == "radial":
        y_grid = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        x_grid = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        dist = np.sqrt(x_grid * x_grid + y_grid * y_grid) / math.sqrt(2.0)
        np.clip(dist, 0.0, 1.0, out=dist)
        if dither:
            dist = np.clip(dist * 255.0 + _get_bayer_dither(h, w), 0.0, 255.0).astype(np.uint8)
        else:
            dist = (dist * 255.0).astype(np.uint8)
        lut = np.empty((256, 3), dtype=np.uint8)
        for ch in range(3):
            lut[:, ch] = np.round(np.linspace(c1[ch], c2[ch], 256)).astype(np.uint8)
        return Image.fromarray(lut[dist], mode="RGB")

    if mode == "mesh":
        c3 = _to_rgb(color3, ((c1[0] + c2[0]) // 2, c1[1], c2[2]))
        c4 = (c2[0], (c1[1] + c2[1]) // 2, c1[2])
        u = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :, None]
        v = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        p00 = np.array(c1, dtype=np.float32)
        p10 = np.array(c3, dtype=np.float32)
        p01 = np.array(c4, dtype=np.float32)
        p11 = np.array(c2, dtype=np.float32)
        mesh = (1 - u) * (1 - v) * p00 + u * (1 - v) * p10 + (1 - u) * v * p01 + u * v * p11
        if dither:
            mesh += _get_bayer_dither(h, w)[:, :, None]
        return Image.fromarray(np.clip(mesh, 0, 255).astype(np.uint8), mode="RGB")

    # Default 'gradient' (with optional 3-stop if color3 is set)
    if color3 is not None:
        c3 = _to_rgb(color3)
        g1 = np.asarray(generate_linear_gradient(w, h, c1, c3, angle=angle, dither=dither), dtype=np.float32)
        g2 = np.asarray(generate_linear_gradient(w, h, c3, c2, angle=angle, dither=dither), dtype=np.float32)
        t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
        return Image.fromarray(np.clip(g1 * (1 - t) + g2 * t, 0, 255).astype(np.uint8), mode="RGB")

    return generate_linear_gradient(width=w, height=h, color1=c1, color2=c2, angle=angle, dither=dither)


def apply_pattern(canvas: Image.Image, pattern: Optional[str], opacity: float = 0.08) -> Image.Image:
    """Applies subtle geometric overlay ('dots', 'scanlines', 'diagonal', 'hex') onto backdrop."""
    if not pattern or pattern.lower() == "none":
        return canvas
    pat = pattern.strip().lower()
    w, h = canvas.size
    alpha_val = max(1, min(255, round(opacity * 255)))
    overlay = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(overlay)

    if pat == "scanlines":
        for y in range(0, h, 6):
            draw.line([(0, y), (w, y)], fill=alpha_val, width=2)
    elif pat == "dots":
        step = 24
        for y in range(12, h, step):
            for x in range(12, w, step):
                draw.ellipse((x - 2, y - 2, x + 2, y + 2), fill=alpha_val)
    elif pat == "diagonal":
        step = 28
        for offset in range(-h, w + h, step):
            draw.line([(offset, 0), (offset - h, h)], fill=alpha_val, width=2)
    elif pat == "hex":
        r = 22
        dx = int(r * 1.5)
        dy = int(r * math.sqrt(3))
        for col, x in enumerate(range(0, w + r, max(1, dx))):
            y_offset = (dy // 2) if (col % 2) else 0
            for y in range(y_offset, h + r, max(1, dy)):
                pts = [
                    (x + r * math.cos(math.radians(60 * k)), y + r * math.sin(math.radians(60 * k)))
                    for k in range(6)
                ]
                draw.polygon(pts, outline=alpha_val)

    white = Image.new("RGB", (w, h), (255, 255, 255))
    canvas.paste(white, (0, 0), mask=overlay)
    return canvas


def apply_glow(
    canvas: Image.Image,
    card_mask: Image.Image,
    card_position: Tuple[int, int],
    glow_color: Tuple[int, int, int],
    blur_radius: int = 32,
    opacity: float = 0.55,
) -> Image.Image:
    """Renders a colored neon/ambient glow behind the poster card."""
    _, glow_mask = create_drop_shadow(
        mask=card_mask,
        canvas_size=canvas.size,
        offset=(0, 0),
        blur_radius=blur_radius,
        opacity=opacity,
        card_position=card_position,
    )
    apply_drop_shadow(canvas, glow_mask, shadow_color=glow_color)
    return canvas


def apply_reflection(
    canvas: Image.Image,
    resized_poster: Image.Image,
    card_mask: Image.Image,
    card_position: Tuple[int, int],
    opacity: float = 0.28,
) -> Image.Image:
    """Renders a subtle faded mirror reflection directly beneath the poster card."""
    cw, ch = canvas.size
    cx, cy = card_position
    pw, ph = resized_poster.size
    refl_y = cy + ph + 6
    if refl_y >= ch or pw <= 0 or ph <= 0:
        return canvas

    refl_h = min(ph // 3, ch - refl_y)
    if refl_h <= 4:
        return canvas

    flipped_img = resized_poster.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, 0, pw, refl_h))
    flipped_mask = card_mask.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, 0, pw, refl_h))

    fade = np.linspace(opacity, 0.0, refl_h, dtype=np.float32)[:, None]
    mask_arr = (np.asarray(flipped_mask, dtype=np.float32) * fade).astype(np.uint8)
    faded_mask = Image.fromarray(mask_arr, mode="L")

    canvas.paste(flipped_img, (cx, refl_y), mask=faded_mask)
    return canvas


def apply_card_border(
    canvas: Image.Image,
    card_position: Tuple[int, int],
    card_size: Tuple[int, int],
    radius: int,
    border_width: int,
    border_color: Tuple[int, int, int],
) -> Image.Image:
    """Draws an anti-aliased rounded border around the poster card."""
    if border_width <= 0:
        return canvas
    cx, cy = card_position
    pw, ph = card_size
    draw = ImageDraw.Draw(canvas)
    clamped_r = max(0, min(radius, min(pw, ph) // 2))
    draw.rounded_rectangle(
        (cx, cy, cx + pw - 1, cy + ph - 1),
        radius=clamped_r,
        outline=border_color,
        width=border_width,
    )
    return canvas


def apply_vignette_and_grain(
    canvas: Image.Image,
    vignette: float = 0.0,
    grain: float = 0.0,
) -> Image.Image:
    """Applies cinematic edge darkening (vignette) and deterministic film grain."""
    if vignette <= 0.0 and grain <= 0.0:
        return canvas
    w, h = canvas.size
    arr = np.asarray(canvas, dtype=np.float32)

    if vignette > 0.0:
        strength = min(1.0, float(vignette))
        y = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
        x = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
        r2 = x * x + y * y
        factor = 1.0 - strength * np.clip(r2 * 0.65, 0.0, 1.0)
        arr *= factor[:, :, None]

    if grain > 0.0:
        g_amp = min(0.5, float(grain)) * 128.0
        # Deterministic spatial grain from Bayer matrix + coordinate hash
        bayer = _get_bayer_dither(h, w)
        arr += bayer[:, :, None] * g_amp

    np.clip(arr, 0.0, 255.0, out=arr)
    out = Image.fromarray(arr.astype(np.uint8), mode="RGB")
    canvas.paste(out)
    return canvas


def apply_logo_and_platforms(
    canvas: Image.Image,
    logo_path: Optional[Union[str, Path]] = None,
    logo_pos: str = "top_right",
    platforms: Optional[List[str]] = None,
) -> Image.Image:
    """Overlays a transparent PNG channel logo and/or gaming platform badges (PC, STEAM, PS5, XBOX, EPIC)."""
    cw, ch = canvas.size

    if logo_path:
        lp = Path(logo_path)
        if lp.is_file():
            try:
                logo = Image.open(lp).convert("RGBA")
                max_w = max(48, cw // 7)
                if logo.width > max_w:
                    ratio = max_w / logo.width
                    logo = logo.resize((max_w, max(1, round(logo.height * ratio))), Image.Resampling.LANCZOS)
                pad = 28
                pos = logo_pos.strip().lower()
                lx = cw - logo.width - pad if "right" in pos else (pad if "left" in pos else (cw - logo.width) // 2)
                ly = ch - logo.height - pad if "bottom" in pos else pad
                canvas.paste(logo.convert("RGB"), (lx, ly), mask=logo.split()[3])
            except Exception:
                pass

    if platforms:
        draw = ImageDraw.Draw(canvas)
        font = resolve_watermark_font("Bebas Neue", 20)
        pad_x = 28
        cur_y = 28
        palette_map = {
            "steam": (23, 26, 33),
            "epic": (32, 32, 32),
            "pc": (15, 23, 42),
            "ps": (0, 55, 145),
            "ps5": (0, 55, 145),
            "xbox": (16, 124, 16),
            "gog": (108, 34, 166),
            "switch": (230, 0, 18),
        }
        cur_x = pad_x
        for p_raw in platforms:
            label = p_raw.strip().upper()
            if not label:
                continue
            bg_c = palette_map.get(label.lower(), (15, 23, 42))
            bbox = font.getbbox(label)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            bw, bh = tw + 20, th + 12
            draw.rounded_rectangle(
                (cur_x, cur_y, cur_x + bw, cur_y + bh),
                radius=8,
                fill=bg_c,
                outline=(255, 255, 255),
                width=1,
            )
            draw.text((cur_x + 10, cur_y + 4), label, font=font, fill=(255, 255, 255))
            cur_x += bw + 8

    return canvas
