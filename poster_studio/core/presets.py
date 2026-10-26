"""
poster_studio.core.presets
~~~~~~~~~~~~~~~~~~~~~~~~~~
Genre-specific styling presets and automatic image-to-preset heuristic selector.
Supports user custom JSON presets in ~/.poster_studio/presets/.
"""

from __future__ import annotations

import colorsys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np
from PIL import Image

PRESETS: Dict[str, Dict[str, Any]] = {
    "bazyepc_default": {
        "description": "Default @BazyePc balanced framing with vibrant auto palette",
        "watermark_font": "Bebas Neue",
        "watermark_color": "#FFFFFF",
        "watermark_stroke_color": "#0F172A",
        "curve": 45,
        "margin": 50,
        "angle": 135.0,
        "drop_shadow": True,
        "bg_mode": "gradient",
    },
    "sports": {
        "description": "High-energy athletic styling with card glow (EA FC, NBA, WWE)",
        "watermark_font": "Teko",
        "watermark_color": "#FACC15",
        "watermark_stroke_color": "#090D16",
        "curve": 36,
        "margin": 44,
        "angle": 120.0,
        "glow": True,
        "border": 3,
        "border_color": "#FACC15",
    },
    "horror": {
        "description": "Dark atmospheric horror with vignette, film grain, and blood-red accents",
        "watermark_font": "Creepster",
        "watermark_color": "#EF4444",
        "watermark_stroke_color": "#050505",
        "color1": "#450A0A",
        "color2": "#09090B",
        "auto_colors": False,
        "curve": 28,
        "margin": 52,
        "vignette": 0.45,
        "grain": 0.06,
    },
    "fantasy_rpg": {
        "description": "Epic medieval/fantasy styling with warm gold typography and deep shadows",
        "watermark_font": "Unifraktur",
        "watermark_color": "#F59E0B",
        "watermark_stroke_color": "#1C1917",
        "curve": 40,
        "margin": 48,
        "angle": 135.0,
        "glow": True,
        "vignette": 0.25,
    },
    "cyberpunk": {
        "description": "Neon sci-fi aesthetic with cyan/magenta glow and scanline overlay",
        "watermark_font": "Orbitron",
        "watermark_color": "#22D3EE",
        "watermark_stroke_color": "#0F172A",
        "color1": "#D946EF",
        "color2": "#06B6D4",
        "auto_colors": False,
        "curve": 24,
        "margin": 46,
        "glow": True,
        "pattern": "scanlines",
        "border": 2,
        "border_color": "#22D3EE",
    },
    "military_shooter": {
        "description": "Tactical stencil look with gritty grain and olive/slate tones",
        "watermark_font": "Black Ops One",
        "watermark_color": "#E2E8F0",
        "watermark_stroke_color": "#0F172A",
        "curve": 20,
        "margin": 45,
        "grain": 0.05,
        "border": 2,
        "border_color": "#475569",
    },
    "retro_pixel": {
        "description": "8-bit arcade styling with pixel font and dot matrix pattern",
        "watermark_font": "Press Start 2P",
        "watermark_color": "#4ADE80",
        "watermark_stroke_color": "#052E16",
        "curve": 12,
        "margin": 54,
        "pattern": "dots",
    },
    "cozy_indie": {
        "description": "Soft rounded corners and cursive script for narrative & indie games",
        "watermark_font": "Pacifico",
        "watermark_color": "#FFFBEB",
        "watermark_stroke_color": "#292524",
        "curve": 64,
        "margin": 56,
        "bg_mode": "blur",
    },
    "racing": {
        "description": "Aggressive diagonal speed styling with reflection (Forza, NFS, F1)",
        "watermark_font": "Audiowide",
        "watermark_color": "#F97316",
        "watermark_stroke_color": "#0C0A09",
        "curve": 32,
        "margin": 44,
        "angle": 45.0,
        "reflection": True,
        "pattern": "diagonal",
    },
    "persian_bold": {
        "description": "Persian RTL gaming showcase with Lalezar display typography",
        "watermark_font": "Lalezar",
        "watermark_color": "#FDE047",
        "watermark_stroke_color": "#0F172A",
        "curve": 42,
        "margin": 48,
        "glow": True,
    },
}


def get_user_presets_dir() -> Path:
    return Path.home() / ".poster_studio" / "presets"


def list_presets() -> Dict[str, Dict[str, Any]]:
    """Returns merged dictionary of built-in and user custom JSON presets."""
    merged = dict(PRESETS)
    user_dir = get_user_presets_dir()
    if user_dir.is_dir():
        for p in sorted(user_dir.glob("*.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    merged[p.stem.lower()] = data
            except Exception:
                pass
    return merged


def get_preset(name: str, image: Optional[Image.Image] = None) -> Dict[str, Any]:
    """Resolves a preset by name (or 'auto' to infer from image characteristics)."""
    key = name.strip().lower()
    if key == "auto":
        key = auto_select_preset(image) if image is not None else "bazyepc_default"
    catalog = list_presets()
    if key not in catalog:
        valid = ", ".join(sorted(catalog.keys()))
        raise ValueError(f"Unknown preset '{name}'. Available presets: {valid}, auto")
    return {k: v for k, v in catalog[key].items() if k != "description"}


def auto_select_preset(image: Image.Image) -> str:
    """Heuristically selects a genre preset from image luminance, saturation, and contrast."""
    thumb = image.convert("RGB").resize((64, 64), Image.Resampling.BILINEAR)
    arr = np.asarray(thumb, dtype=np.float32) / 255.0
    lum = 0.2126 * arr[:, :, 0] + 0.7152 * arr[:, :, 1] + 0.0722 * arr[:, :, 2]
    mean_lum = float(lum.mean())
    max_c = arr.max(axis=2)
    min_c = arr.min(axis=2)
    sat = np.where(max_c > 1e-4, (max_c - min_c) / np.maximum(max_c, 1e-4), 0.0)
    mean_sat = float(sat.mean())

    if mean_lum < 0.22:
        return "horror"
    if mean_sat > 0.62 and mean_lum > 0.35:
        return "cyberpunk"
    if mean_sat < 0.28:
        return "military_shooter"
    if mean_lum > 0.58:
        return "cozy_indie"
    return "bazyepc_default"
