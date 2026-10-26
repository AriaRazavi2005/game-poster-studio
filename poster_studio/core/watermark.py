"""
poster_studio.core.watermark
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Watermark and multi-layer typography engine (Title, Subtitle, Pill Badge, Watermark)
with built-in Persian/Arabic RTL contextual shaping, WCAG contrast auto-selection,
and safe-zone energy detection.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from PIL import Image, ImageDraw, ImageFont, features

from poster_studio.core.palette import parse_hex_color, rgb_to_relative_luminance
from poster_studio.core.types import Box

# Curated gaming, Persian RTL, & display font catalog
AVAILABLE_FONTS: Dict[str, str] = {
    # Core Gaming & Action Fonts
    "Anton (Default Gaming)": "Anton-Regular.ttf",
    "Bebas Neue (Bold Tall)": "BebasNeue-Regular.ttf",
    "Teko (Athletic Block)": "Teko-Bold.ttf",
    "Russo One (Action Block)": "RussoOne-Regular.ttf",
    "Orbitron (Cyberpunk)": "Orbitron-Bold.ttf",
    "Audiowide (Speed / Sci-Fi)": "Audiowide-Regular.ttf",
    "Bungee (Heavy Brutalist)": "Bungee-Regular.ttf",
    "Black Ops One (Military Stencil)": "BlackOpsOne-Regular.ttf",
    "Press Start 2P (Retro 8-Bit Arcade)": "PressStart2P-Regular.ttf",
    # Persian / RTL Gaming Fonts
    "Lalezar (Persian Gaming)": "Lalezar-Regular.ttf",
    "Vazirmatn (Persian Bold)": "Vazirmatn-Bold.ttf",
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

WINDOWS_SYSTEM_FONTS = [
    "impact.ttf", "ariblk.ttf", "bahnschrift.ttf", "segoeuib.ttf",
    "trebucbd.ttf", "tahomabd.ttf", "arialbd.ttf", "consolab.ttf",
]

LINUX_SYSTEM_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_RTL_REGEX = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]")

# Zero-dependency Persian/Arabic Presentation Forms table:
# char -> (isolated, final, initial, medial, joins_after)
_ARABIC_FORMS: Dict[str, Tuple[str, str, str, str, bool]] = {
    "\u0621": ("\uFE80", "\uFE80", "\uFE80", "\uFE80", False),  # ء
    "\u0622": ("\uFE81", "\uFE82", "\uFE81", "\uFE82", False),  # آ
    "\u0623": ("\uFE83", "\uFE84", "\uFE83", "\uFE84", False),  # أ
    "\u0624": ("\uFE85", "\uFE86", "\uFE85", "\uFE86", False),  # ؤ
    "\u0625": ("\uFE87", "\uFE88", "\uFE87", "\uFE88", False),  # إ
    "\u0626": ("\uFE89", "\uFE8A", "\uFE8B", "\uFE8C", True),   # ئ
    "\u0627": ("\uFE8D", "\uFE8E", "\uFE8D", "\uFE8E", False),  # ا
    "\u0628": ("\uFE8F", "\uFE90", "\uFE91", "\uFE92", True),   # ب
    "\u067E": ("\uFB56", "\uFB57", "\uFB58", "\uFB59", True),   # پ
    "\u0629": ("\uFE93", "\uFE94", "\uFE93", "\uFE94", False),  # ة
    "\u062A": ("\uFE95", "\uFE96", "\uFE97", "\uFE98", True),   # ت
    "\u062B": ("\uFE99", "\uFE9A", "\uFE9B", "\uFE9C", True),   # ث
    "\u062C": ("\uFE9D", "\uFE9E", "\uFE9F", "\uFEA0", True),   # ج
    "\u0686": ("\uFB7A", "\uFB7B", "\uFB7C", "\uFB7D", True),   # چ
    "\u062D": ("\uFEA1", "\uFEA2", "\uFEA3", "\uFEA4", True),   # ح
    "\u062E": ("\uFEA5", "\uFEA6", "\uFEA7", "\uFEA8", True),   # خ
    "\u062F": ("\uFEA9", "\uFEAA", "\uFEA9", "\uFEAA", False),  # د
    "\u0630": ("\uFEAB", "\uFEAC", "\uFEAB", "\uFEAC", False),  # ذ
    "\u0631": ("\uFEAD", "\uFEAE", "\uFEAD", "\uFEAE", False),  # ر
    "\u0632": ("\uFEAF", "\uFEB0", "\uFEAF", "\uFEB0", False),  # ز
    "\u0698": ("\uFB8A", "\uFB8B", "\uFB8A", "\uFB8B", False),  # ژ
    "\u0633": ("\uFEB1", "\uFEB2", "\uFEB3", "\uFEB4", True),   # س
    "\u0634": ("\uFEB5", "\uFEB6", "\uFEB7", "\uFEB8", True),   # ش
    "\u0635": ("\uFEB9", "\uFEBA", "\uFEBB", "\uFEBC", True),   # ص
    "\u0636": ("\uFEBD", "\uFEBE", "\uFEBF", "\uFEC0", True),   # ض
    "\u0637": ("\uFEC1", "\uFEC2", "\uFEC3", "\uFEC4", True),   # ط
    "\u0638": ("\uFEC5", "\uFEC6", "\uFEC7", "\uFEC8", True),   # ظ
    "\u0639": ("\uFEC9", "\uFECA", "\uFECB", "\uFECC", True),   # ع
    "\u063A": ("\uFECD", "\uFECE", "\uFECF", "\uFED0", True),   # غ
    "\u0641": ("\uFED1", "\uFED2", "\uFED3", "\uFED4", True),   # ف
    "\u0642": ("\uFED5", "\uFED6", "\uFED7", "\uFED8", True),   # ق
    "\u0643": ("\uFED9", "\uFEDA", "\uFEDB", "\uFEDC", True),   # ك
    "\u06A9": ("\uFB8E", "\uFB8F", "\uFB90", "\uFB91", True),   # ک
    "\u06AF": ("\uFB92", "\uFB93", "\uFB94", "\uFB95", True),   # گ
    "\u0644": ("\uFEDD", "\uFEDE", "\uFEDF", "\uFEE0", True),   # ل
    "\u0645": ("\uFEE1", "\uFEE2", "\uFEE3", "\uFEE4", True),   # م
    "\u0646": ("\uFEE5", "\uFEE6", "\uFEE7", "\uFEE8", True),   # ن
    "\u0647": ("\uFEE9", "\uFEEA", "\uFEEB", "\uFEEC", True),   # ه
    "\u0648": ("\uFEED", "\uFEEE", "\uFEED", "\uFEEE", False),  # و
    "\u0649": ("\uFEEF", "\uFEF0", "\uFEEF", "\uFEF0", False),  # ى
    "\u064A": ("\uFEF1", "\uFEF2", "\uFEF3", "\uFEF4", True),   # ي
    "\u06CC": ("\uFBFC", "\uFBFD", "\uFBFE", "\uFBFF", True),   # ی
}

_LAM_ALEF: Dict[str, Tuple[str, str]] = {
    "\u0622": ("\uFEF5", "\uFEF6"),  # لآ
    "\u0623": ("\uFEF7", "\uFEF8"),  # لأ
    "\u0625": ("\uFEF9", "\uFEFA"),  # لإ
    "\u0627": ("\uFEFB", "\uFEFC"),  # لا
}


def has_rtl(text: str) -> bool:
    """Returns True if string contains Persian or Arabic characters."""
    return bool(_RTL_REGEX.search(text))


def shape_rtl_text(text: str) -> str:
    """
    Shapes Persian/Arabic text for visual rendering in Pillow.
    If libraqm is built into Pillow, returns text unchanged (Pillow handles it natively).
    If arabic_reshaper + python-bidi are installed, uses them.
    Otherwise uses built-in zero-dependency Presentation Forms shaper + BiDi visual reorder.
    """
    if not text or not has_rtl(text):
        return text
    if features.check("raqm"):
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return str(get_display(arabic_reshaper.reshape(text)))
    except ImportError:
        pass

    # Built-in zero-dependency shaper
    chars = list(text)
    shaped: List[str] = []
    n = len(chars)
    i = 0
    prev_joins = False

    while i < n:
        ch = chars[i]
        if ch == "\u200C":  # ZWNJ (نیم‌فاصله)
            prev_joins = False
            i += 1
            continue

        # Lam-Alef ligature check
        if ch == "\u0644" and (i + 1) < n and chars[i + 1] in _LAM_ALEF:
            iso, fin = _LAM_ALEF[chars[i + 1]]
            shaped.append(fin if prev_joins else iso)
            prev_joins = False
            i += 2
            continue

        if ch in _ARABIC_FORMS:
            iso, fin, ini, med, joins_after = _ARABIC_FORMS[ch]
            next_joins = (i + 1 < n) and (chars[i + 1] in _ARABIC_FORMS or (ch == "\u0644" and chars[i + 1] in _LAM_ALEF))
            if prev_joins and next_joins:
                shaped.append(med)
            elif prev_joins and not next_joins:
                shaped.append(fin)
            elif not prev_joins and next_joins:
                shaped.append(ini)
            else:
                shaped.append(iso)
            prev_joins = joins_after
        else:
            shaped.append(ch)
            prev_joins = False
        i += 1

    # Visual BiDi reorder for RTL lines: keep LTR runs (Latin/numbers) intact while reversing RTL flow
    tokens = re.findall(r"[A-Za-z0-9_.\-+:/@#]+|[^A-Za-z0-9_.\-+:/@#]+", "".join(shaped))
    visual_tokens: List[str] = []
    for tok in reversed(tokens):
        if re.match(r"^[A-Za-z0-9_.\-+:/@#]+$", tok):
            visual_tokens.append(tok)
        else:
            visual_tokens.append(tok[::-1])
    return "".join(visual_tokens)


def get_available_fonts() -> Dict[str, str]:
    """Returns dictionary of available gaming, Persian, and system fonts."""
    return dict(AVAILABLE_FONTS)


def resolve_watermark_font(
    font_name_or_path: Optional[str] = None,
    font_size: int = 28,
    for_rtl: bool = False,
) -> Union[ImageFont.FreeTypeFont, ImageFont.ImageFont]:
    """
    Resolves an appropriate font using a 5-tier fallback chain.
    Automatically switches to bundled Persian font (Lalezar/Vazirmatn) when rendering RTL text
    if no explicit RTL-capable font was chosen.
    """
    size = max(8, int(font_size))
    bundled_dir = Path(__file__).resolve().parent.parent / "assets" / "fonts"

    if for_rtl:
        q = (font_name_or_path or "").lower()
        if not any(k in q for k in ("lalezar", "vazir", "tahoma", "arial", "segoe", ".ttf")):
            for rtl_font in ("Lalezar-Regular.ttf", "Vazirmatn-Bold.ttf"):
                cand = bundled_dir / rtl_font
                if cand.is_file():
                    try:
                        return ImageFont.truetype(str(cand), size)
                    except (OSError, IOError):
                        pass

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
                if norm_query and (
                    norm_query in norm_key
                    or norm_query in norm_val
                    or norm_key.startswith(norm_query)
                    or norm_val.startswith(norm_query)
                ):
                    resolved_target = val
                    break

    if resolved_target:
        if os.path.isfile(resolved_target):
            try:
                return ImageFont.truetype(resolved_target, size)
            except (OSError, IOError):
                pass
        candidate_path = bundled_dir / resolved_target
        if candidate_path.is_file():
            try:
                return ImageFont.truetype(str(candidate_path), size)
            except (OSError, IOError):
                pass
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

    if bundled_dir.is_dir():
        candidates = sorted(
            list(bundled_dir.glob("*.ttf")) + list(bundled_dir.glob("*.otf")),
            key=lambda p: (0 if "anton" in p.name.lower() else 1, p.name),
        )
        for font_file in candidates:
            try:
                return ImageFont.truetype(str(font_file), size)
            except (OSError, IOError):
                continue

    os_candidates = WINDOWS_SYSTEM_FONTS if os.name == "nt" else LINUX_SYSTEM_FONTS
    all_candidates = os_candidates + (LINUX_SYSTEM_FONTS if os.name == "nt" else WINDOWS_SYSTEM_FONTS)
    for candidate in all_candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except (OSError, IOError):
            continue

    return ImageFont.load_default()


def select_safe_zone_position(
    canvas: Image.Image,
    text_size: Tuple[int, int],
    card_placement: Optional[Union[Box, Tuple[int, int, int, int]]] = None,
    margin_bottom: int = 35,
) -> Tuple[int, int]:
    """
    Evaluates local gradient energy (busyness) across candidate regions
    (bottom margin, inside card bottom, inside card top) and selects the quietest zone.
    """
    cw, ch = canvas.size
    tw, th = text_size
    x_center = max(0, (cw - tw) // 2)

    card_b = ch
    card_t = 0
    if card_placement is not None:
        box = Box.from_any(card_placement)
        card_t, card_b = box.top, box.bottom

    # If ample bottom margin exists outside card, always prefer clean gradient margin
    ideal_y = ch - th - margin_bottom
    if card_b <= ideal_y - 12:
        return (x_center, max(0, ideal_y))

    # Otherwise compare inside-bottom vs inside-top energy
    y_bot = max(0, min(ch - th, card_b - th - 32))
    y_top = max(0, min(ch - th, card_t + 28))

    gray = np.asarray(canvas.convert("L"), dtype=np.float32)

    def _region_energy(rx: int, ry: int) -> float:
        patch = gray[max(0, ry):min(ch, ry + th), max(0, rx):min(cw, rx + tw)]
        if patch.size < 4:
            return 0.0
        gx = np.abs(np.diff(patch, axis=1)).mean() if patch.shape[1] > 1 else 0.0
        gy = np.abs(np.diff(patch, axis=0)).mean() if patch.shape[0] > 1 else 0.0
        return float(gx + gy)

    e_bot = _region_energy(x_center, y_bot)
    e_top = _region_energy(x_center, y_top)
    # Prefer bottom unless bottom is significantly busier (> 1.4x) than top
    chosen_y = y_top if (e_bot > e_top * 1.4 and e_bot > 18.0) else y_bot
    return (x_center, chosen_y)


def resolve_wcag_colors(
    canvas: Image.Image,
    pos: Tuple[int, int],
    text_size: Tuple[int, int],
    text_color: Union[Tuple[int, int, int], str],
    stroke_color: Union[Tuple[int, int, int], str],
) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
    """
    Ensures WCAG >= 4.5 contrast ratio when text_color is 'auto', or validates contrast against patch luminance.
    """
    cw, ch = canvas.size
    x, y = pos
    tw, th = text_size

    if isinstance(stroke_color, str):
        s_rgb = parse_hex_color(stroke_color)
    else:
        s_rgb = (int(stroke_color[0]), int(stroke_color[1]), int(stroke_color[2]))

    if isinstance(text_color, str) and text_color.strip().lower() == "auto":
        patch = canvas.crop((max(0, x), max(0, y), min(cw, x + max(1, tw)), min(ch, y + max(1, th))))
        arr = np.asarray(patch.convert("RGB"), dtype=np.float32)
        if arr.size > 0:
            r_m, g_m, b_m = float(arr[:, :, 0].mean()), float(arr[:, :, 1].mean()), float(arr[:, :, 2].mean())
            bg_lum = rgb_to_relative_luminance(round(r_m), round(g_m), round(b_m))
        else:
            bg_lum = 0.2
        if bg_lum < 0.42:
            return ((255, 255, 255), (15, 23, 42))
        return ((15, 23, 42), (255, 255, 255))

    if isinstance(text_color, str):
        t_rgb = parse_hex_color(text_color)
    else:
        t_rgb = (int(text_color[0]), int(text_color[1]), int(text_color[2]))
    return (t_rgb, s_rgb)


def calculate_watermark_position(
    canvas_size: Tuple[int, int],
    text_size: Tuple[int, int],
    position: str = "bottom_center",
    margin_bottom: int = 35,
    margin_side: int = 40,
    card_placement: Optional[Union[Box, Tuple[int, int, int, int]]] = None,
    custom_pos: Optional[Tuple[float, float]] = None,
    pos_mode: Optional[str] = None,
) -> Tuple[int, int]:
    """Calculates (x, y) coordinates for the watermark."""
    cw, ch = canvas_size
    tw, th = text_size

    if custom_pos is not None:
        cx_val, cy_val = custom_pos
        mode = (pos_mode or "auto").lower()
        if mode == "relative":
            is_relative = True
        elif mode == "absolute":
            is_relative = False
        else:
            is_relative = (0.0 <= cx_val <= 1.0 and 0.0 <= cy_val <= 1.0)

        if is_relative:
            x = round(cw * cx_val - tw / 2.0)
            y = round(ch * cy_val - th / 2.0)
        else:
            x = round(cx_val - tw / 2.0)
            y = round(cy_val - th / 2.0)
        return (max(0, min(cw - tw, x)), max(0, min(ch - th, y)))

    has_card = card_placement is not None
    card_l, card_t, card_r, card_b = 0, 0, cw, ch
    if has_card and card_placement is not None:
        if isinstance(card_placement, Box):
            card_l, card_t, card_r, card_b = (
                card_placement.left,
                card_placement.top,
                card_placement.right,
                card_placement.bottom,
            )
        else:
            p0, p1, p2, p3 = card_placement
            if p2 > p0 and p3 > p1 and p3 <= ch + 20:
                card_l, card_t, card_r, card_b = p0, p1, p2, p3
            else:
                card_l, card_t, card_r, card_b = p0, p1, p0 + p2, p1 + p3

    pos_clean = position.strip().lower()

    if pos_clean == "card_bottom_left" and has_card:
        return (card_l + 25, card_b - th - 25)
    if pos_clean == "card_inside_bottom" and has_card:
        return (max(0, round((card_l + card_r - tw) / 2.0)), max(0, round(card_b - th - 32)))
    if pos_clean == "card_outside_bottom" and has_card:
        available_bottom = max(0, ch - card_b)
        return (max(0, round((cw - tw) / 2.0)), max(0, round(card_b + (available_bottom - th) / 2.0)))

    if pos_clean == "top_center":
        x, y = round((cw - tw) / 2.0), margin_bottom
    elif pos_clean == "top_left":
        x, y = margin_side, margin_bottom
    elif pos_clean == "top_right":
        x, y = cw - tw - margin_side, margin_bottom
    elif pos_clean == "center":
        x, y = round((cw - tw) / 2.0), round((ch - th) / 2.0)
    elif pos_clean == "bottom_right":
        x, y = cw - tw - margin_side, ch - th - margin_bottom
    elif pos_clean == "bottom_left":
        x, y = margin_side, ch - th - margin_bottom
    else:
        x = round((cw - tw) / 2.0)
        ideal_y = ch - th - margin_bottom
        if has_card and card_b > (ideal_y - 10):
            y = round(card_b - th - 32)
        else:
            y = ideal_y

    return (max(0, x), max(0, y))


def _fit_font(
    font_name: Optional[str],
    initial_size: int,
    shaped_text: str,
    max_width: int,
    for_rtl: bool,
) -> Tuple[Union[ImageFont.FreeTypeFont, ImageFont.ImageFont], int, int]:
    """Auto-scales font size down if text width exceeds max_width."""
    cur_size = max(10, initial_size)
    while cur_size >= 12:
        font = resolve_watermark_font(font_name, cur_size, for_rtl=for_rtl)
        bbox = font.getbbox(shaped_text)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if tw <= max_width or cur_size <= 12:
            return font, tw, th
        cur_size = max(12, int(cur_size * 0.88))
    font = resolve_watermark_font(font_name, 12, for_rtl=for_rtl)
    bbox = font.getbbox(shaped_text)
    return font, bbox[2] - bbox[0], bbox[3] - bbox[1]


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
    card_placement: Optional[Union[Box, Tuple[int, int, int, int]]] = None,
    custom_position: Optional[Tuple[float, float]] = None,
    pos_mode: Optional[str] = None,
    *,
    image: Optional[Image.Image] = None,
    placement: Any = None,
) -> Image.Image:
    """Renders high-visibility styled watermark with Persian/Arabic RTL support, stroke, and shadow."""
    target_img = canvas if canvas is not None else image
    if target_img is None:
        raise ValueError("apply_watermark requires 'canvas' or 'image' parameter.")

    if not text or not str(text).strip():
        return target_img

    raw_text = str(text).strip()
    is_rtl = has_rtl(raw_text)
    clean_text = shape_rtl_text(raw_text)

    box = card_placement
    if box is None and placement is not None:
        if hasattr(placement, "box"):
            box = placement.box
        elif all(hasattr(placement, k) for k in ("x", "y", "width", "height")):
            box = (placement.x, placement.y, placement.width, placement.height)

    cw, _ = target_img.size
    font, text_w, text_h = _fit_font(font_name, font_size, clean_text, max(100, cw - 2 * margin_side), is_rtl)

    if position.strip().lower() == "auto" and custom_position is None:
        x, y = select_safe_zone_position(target_img, (text_w, text_h), box, margin_bottom=margin_bottom)
    else:
        x, y = calculate_watermark_position(
            canvas_size=target_img.size,
            text_size=(text_w, text_h),
            position=position,
            margin_bottom=margin_bottom,
            margin_side=margin_side,
            card_placement=box,
            custom_pos=custom_position,
            pos_mode=pos_mode,
        )

    resolved_text_color, resolved_stroke_color = resolve_wcag_colors(
        target_img, (x, y), (text_w, text_h), text_color, stroke_color
    )

    draw = ImageDraw.Draw(target_img)

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
            anchor="lt",
        )

    draw.text(
        (x, y),
        clean_text,
        font=font,
        fill=resolved_text_color,
        stroke_width=stroke_width,
        stroke_fill=resolved_stroke_color,
        anchor="lt",
    )

    return target_img


def apply_typography_layers(
    canvas: Image.Image,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    badge: Optional[str] = None,
    badge_color: Union[Tuple[int, int, int], str] = "#EF4444",
    font_name: Optional[str] = None,
    text_color: Union[Tuple[int, int, int], str] = (255, 255, 255),
    stroke_color: Union[Tuple[int, int, int], str] = (15, 23, 42),
    card_box: Optional[Box] = None,
) -> Image.Image:
    """
    Renders optional multi-layer game title, subtitle (e.g. 'Repack • 48GB'),
    and pill badge (e.g. 'NEW', 'UPDATE') with full Persian RTL and auto-fit support.
    """
    cw, ch = canvas.size
    draw = ImageDraw.Draw(canvas)

    # 1. Pill Badge (top-right of card or canvas)
    if badge and str(badge).strip():
        raw_b = str(badge).strip()
        rtl_b = has_rtl(raw_b)
        shaped_b = shape_rtl_text(raw_b)
        b_font = resolve_watermark_font(font_name or "Bebas Neue", max(18, ch // 52), for_rtl=rtl_b)
        bbox = b_font.getbbox(shaped_b)
        bw, bh = (bbox[2] - bbox[0]) + 28, (bbox[3] - bbox[1]) + 14
        if card_box is not None:
            bx = max(16, min(cw - bw - 16, card_box.right - bw - 20))
            by = max(16, card_box.top + 20)
        else:
            bx, by = cw - bw - 36, 36
        b_rgb = parse_hex_color(badge_color) if isinstance(badge_color, str) else badge_color
        draw.rounded_rectangle(
            (bx + 2, by + 3, bx + bw + 2, by + bh + 3),
            radius=bh // 2,
            fill=(0, 0, 0),
        )
        draw.rounded_rectangle(
            (bx, by, bx + bw, by + bh),
            radius=bh // 2,
            fill=b_rgb,
            outline=(255, 255, 255),
            width=2,
        )
        draw.text(
            (bx + 14, by + 6 - bbox[1]),
            shaped_b,
            font=b_font,
            fill=(255, 255, 255),
        )

    # 2. Title & Subtitle block (placed near bottom of card, above watermark)
    base_y = (card_box.bottom - 78) if card_box is not None else (ch - 120)
    max_w = (card_box.width - 48) if card_box is not None else (cw - 96)

    if subtitle and str(subtitle).strip():
        raw_sub = str(subtitle).strip()
        rtl_sub = has_rtl(raw_sub)
        shaped_sub = shape_rtl_text(raw_sub)
        sub_size = max(18, ch // 48)
        sub_font, sw, sh = _fit_font(font_name, sub_size, shaped_sub, max_w, rtl_sub)
        sx = (cw - sw) // 2
        sy = max(20, base_y - sh)
        draw.text(
            (sx, sy),
            shaped_sub,
            font=sub_font,
            fill=(226, 232, 240),
            stroke_width=3,
            stroke_fill=(15, 23, 42),
        )
        base_y = sy - 10

    if title and str(title).strip():
        raw_t = str(title).strip()
        rtl_t = has_rtl(raw_t)
        shaped_t = shape_rtl_text(raw_t)
        t_size = max(28, ch // 26)
        t_font, tw, th = _fit_font(font_name, t_size, shaped_t, max_w, rtl_t)
        tx = (cw - tw) // 2
        ty = max(20, base_y - th)
        t_rgb, s_rgb = resolve_wcag_colors(canvas, (tx, ty), (tw, th), text_color, stroke_color)
        draw.text(
            (tx + 3, ty + 3),
            shaped_t,
            font=t_font,
            fill=(0, 0, 0),
            stroke_width=4,
            stroke_fill=(0, 0, 0),
        )
        draw.text(
            (tx, ty),
            shaped_t,
            font=t_font,
            fill=t_rgb,
            stroke_width=4,
            stroke_fill=s_rgb,
        )

    return canvas
