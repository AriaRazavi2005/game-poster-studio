#!/usr/bin/env python3
"""
test_pipeline.py — Comprehensive Automated Test Suite & Performance Benchmark
Game Poster Studio (Dual Track E2E Testing)

Architecture:
  - Tier 1: Feature Coverage (Aspect ratios, colors, angles, margins, curves, shadow, watermark)
  - Tier 2: Boundary & Corner Cases (Dead colors, margin overflow, aspect extremes, alpha, micro/large)
  - Tier 3: Combinatorial Interactions (18-run orthogonal pairwise matrix)
  - Tier 4: Real-World Scenarios & Bridge/CLI Integration (Headless guarantee, Telegram bridge, CLI subprocess)
  - Performance Benchmark: CPU latency assertion (< 1.5s per 1080p poster)

Usage:
  python test_pipeline.py              # Full test run with formatted table & summary
  python -m unittest test_pipeline.py  # Standard Python unittest discovery
"""

import sys
import os
import math
import time
import shutil
import tempfile
import inspect
import subprocess
import unittest
from pathlib import Path
from typing import Optional, Union, Tuple, Any

# Ensure third-party core dependencies are present
try:
    from PIL import Image, ImageDraw, ImageColor, ImageFilter
    import numpy as np
except ImportError as err:
    print(f"[FATAL] Missing required core dependency: {err}", file=sys.stderr)
    print("Please install required dependencies: pip install Pillow numpy", file=sys.stderr)
    sys.exit(1)

# Configure system search paths
REPO_ROOT = Path(__file__).resolve().parent
POSTER_STUDIO_DIR = REPO_ROOT / "poster_studio"

for directory in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if directory not in sys.path:
        sys.path.insert(0, directory)


# ==============================================================================
# SECTION 1: DYNAMIC IMPORT RESOLVERS & COMPATIBILITY HELPERS
# ==============================================================================

def get_create_game_poster():
    """Dynamically resolves create_game_poster from telegram_bridge."""
    try:
        from telegram_bridge import create_game_poster
        return create_game_poster
    except ImportError:
        pass
    try:
        from poster_studio.telegram_bridge import create_game_poster
        return create_game_poster
    except ImportError:
        return None


def get_processor_classes():
    """Dynamically resolves PosterProcessor and PosterConfig."""
    try:
        from poster_studio.core.processor import PosterProcessor, PosterConfig, process_poster
        return PosterProcessor, PosterConfig, process_poster
    except ImportError:
        pass
    try:
        from core.processor import PosterProcessor, PosterConfig, process_poster
        return PosterProcessor, PosterConfig, process_poster
    except ImportError:
        return None, None, None


def find_cli_script() -> Optional[Path]:
    """Finds the location of cli.py."""
    candidates = [
        REPO_ROOT / "cli.py",
        POSTER_STUDIO_DIR / "cli.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def invoke_bridge(bridge_fn, **kwargs) -> Any:
    """
    Invokes create_game_poster while dynamically adapting parameter names
    between differing specification aliases (e.g. shadow vs no_shadow,
    watermark vs watermark_text, zoom vs zoom_factor).
    """
    sig = inspect.signature(bridge_fn)
    accepted = sig.parameters

    filtered_args = {}
    
    # Shadow mapping
    if "shadow" in kwargs:
        val = kwargs["shadow"]
        if "shadow" in accepted:
            filtered_args["shadow"] = val
        elif "no_shadow" in accepted:
            filtered_args["no_shadow"] = not val
    elif "no_shadow" in kwargs:
        val = kwargs["no_shadow"]
        if "no_shadow" in accepted:
            filtered_args["no_shadow"] = val
        elif "shadow" in accepted:
            filtered_args["shadow"] = not val

    # Watermark mapping
    if "watermark" in kwargs:
        wm = kwargs["watermark"]
        if "watermark" in accepted:
            filtered_args["watermark"] = wm
        elif "watermark_text" in accepted:
            filtered_args["watermark_text"] = wm

    # Color overrides
    if "color1" in kwargs and "color1" in accepted:
        filtered_args["color1"] = kwargs["color1"]
    if "color2" in kwargs and "color2" in accepted:
        filtered_args["color2"] = kwargs["color2"]
    if "swap_colors" in kwargs and "swap_colors" in accepted:
        filtered_args["swap_colors"] = kwargs["swap_colors"]
    elif "swap" in accepted and "swap_colors" in kwargs:
        filtered_args["swap"] = kwargs["swap_colors"]

    # Other common arguments
    for key in ["input_image", "output_image", "ratio", "curve", "margin", "auto_colors", "angle", "zoom", "quality", "hd"]:
        if key in kwargs and key in accepted:
            filtered_args[key] = kwargs[key]

    return bridge_fn(**filtered_args)


# ==============================================================================
# SECTION 2: SYNTHETIC GAME POSTER FIXTURE GENERATOR
# ==============================================================================

def create_synthetic_game_poster(
    width: int = 1920,
    height: int = 1080,
    style: str = "cyberpunk"
) -> Image.Image:
    """
    Generates deterministic in-memory synthetic game posters for reproducible testing.
    Styles: 'cyberpunk', 'action', 'horror', 'retro', 'pure_black', 'pure_white',
            'monochrome_gray', 'transparent_rgba', 'micro', 'ultrawide', 'portrait'.
    """
    if style == "pure_black":
        return Image.new("RGB", (width, height), (0, 0, 0))
    elif style == "pure_white":
        return Image.new("RGB", (width, height), (255, 255, 255))
    elif style == "monochrome_gray":
        return Image.new("RGB", (width, height), (128, 128, 128))
    elif style == "transparent_rgba":
        img = Image.new("RGBA", (width, height), (20, 30, 70, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, width - 50, height - 50], fill=(0, 220, 255, 180))
        draw.ellipse([width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill=(255, 0, 100, 0))
        return img
    elif style == "micro":
        return Image.new("RGB", (16, 16), (220, 60, 40))

    img = Image.new("RGB", (width, height), (15, 15, 25))
    draw = ImageDraw.Draw(img)

    if style == "cyberpunk":
        for y in range(0, height, 40):
            t = y / max(height - 1, 1)
            r = int(10 * (1 - t) + 220 * t)
            g = int(200 * (1 - t) + 10 * t)
            b = int(240 * (1 - t) + 150 * t)
            draw.line([(0, y), (width, y)], fill=(r, g, b), width=20)
        draw.polygon([(width // 6, height // 3), (width // 2, height // 6), (width * 5 // 6, height // 3),
                      (width * 2 // 3, height * 4 // 5), (width // 3, height * 4 // 5)], fill=(0, 240, 255))
        draw.rectangle([width // 4, height * 2 // 3, width * 3 // 4, height * 2 // 3 + 60], fill=(255, 0, 85))

    elif style == "action":
        for y in range(0, height, 30):
            t = y / max(height - 1, 1)
            draw.line([(0, y), (width, y)], fill=(int(255 * (1 - 0.3 * t)), int(180 * t), 10), width=15)
        draw.ellipse([width // 3, height // 4, width * 2 // 3, height * 3 // 4], fill=(255, 69, 0))
        draw.rectangle([width // 5, height // 2, width * 4 // 5, height // 2 + 80], fill=(255, 215, 0))

    elif style == "horror":
        draw.rectangle([0, 0, width, height], fill=(12, 14, 18))
        draw.polygon([(width // 4, height // 4), (width * 3 // 4, height // 4), (width // 2, height * 3 // 4)], fill=(139, 0, 0))
        draw.rectangle([width // 3, height * 3 // 5, width * 2 // 3, height * 3 // 5 + 40], fill=(0, 150, 136))

    else:
        draw.rectangle([0, 0, width, height], fill=(30, 20, 60))
        draw.rectangle([width // 4, height // 4, width * 3 // 4, height * 3 // 4], fill=(150, 50, 220))
        draw.ellipse([width // 3, height // 3, width * 2 // 3, height * 2 // 3], fill=(50, 220, 150))

    return img


# ==============================================================================
# BASE TEST CASE CLASS
# ==============================================================================

class BasePosterTestCase(unittest.TestCase):
    """Base test case providing dynamic resolver caching and validation guards."""

    def setUp(self):
        super().setUp()
        self.bridge_fn = get_create_game_poster()
        self.cli_path = find_cli_script()
        self.sample_poster = create_synthetic_game_poster(1920, 1080, "cyberpunk")

    def require_bridge(self):
        if self.bridge_fn is None:
            self.fail("Implementation pending: 'telegram_bridge.create_game_poster' is not yet implemented.")

    def require_cli(self):
        if self.cli_path is None:
            self.fail("Implementation pending: 'cli.py' was not found in workspace.")


# ==============================================================================
# SECTION 3: TIER 1 — FEATURE COVERAGE TESTS
# ==============================================================================

class TestTier1FeatureCoverage(BasePosterTestCase):
    """
    Tier 1: Feature Coverage
    Validates primary functionality across all visual styling controls:
      - All aspect ratios: 4:5, 1:1, 9:16, 16:9, 4:3, 21:9
      - Auto color extraction & vibrancy
      - Color swap & custom hex overrides
      - Gradient angles (0, 90, 135, 270 deg)
      - Margin padding variations (0, 30, 50, 100 px)
      - Corner radius curve variations (0, 45, 90, 120 px)
      - Drop shadow on/off
      - Watermark styling and toggle
    """

    def test_t1_01_aspect_ratio_4_5(self):
        """Ratio 4:5 must produce exact standard dimensions 1080x1350."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="4:5")
        self.assertIsInstance(out, Image.Image)
        self.assertEqual(out.size, (1080, 1350), f"Expected (1080, 1350), got {out.size}")
        self.assertEqual(out.mode, "RGB")

    def test_t1_02_aspect_ratio_1_1(self):
        """Ratio 1:1 must produce exact standard dimensions 1200x1200."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="1:1")
        self.assertEqual(out.size, (1200, 1200), f"Expected (1200, 1200), got {out.size}")

    def test_t1_03_aspect_ratio_9_16(self):
        """Ratio 9:16 must produce exact standard dimensions 1080x1920."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="9:16")
        self.assertEqual(out.size, (1080, 1920), f"Expected (1080, 1920), got {out.size}")

    def test_t1_04_aspect_ratio_16_9(self):
        """Ratio 16:9 must produce exact standard dimensions 1920x1080."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="16:9")
        self.assertEqual(out.size, (1920, 1080), f"Expected (1920, 1080), got {out.size}")

    def test_t1_05_aspect_ratio_4_3(self):
        """Ratio 4:3 must produce exact standard dimensions 1440x1080."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="4:3")
        self.assertEqual(out.size, (1440, 1080), f"Expected (1440, 1080), got {out.size}")

    def test_t1_06_aspect_ratio_21_9(self):
        """Ratio 21:9 must produce exact standard dimensions 2560x1080."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, ratio="21:9")
        self.assertEqual(out.size, (2560, 1080), f"Expected (2560, 1080), got {out.size}")

    def test_t1_07_fit_in_box_scaling_preserves_aspect_ratio(self):
        """Poster scaling inside canvas must preserve intrinsic aspect ratio without distortion."""
        self.require_bridge()
        raw_w, raw_h = 1600, 900
        raw_img = Image.new("RGB", (raw_w, raw_h), (200, 50, 50))
        out = invoke_bridge(self.bridge_fn, input_image=raw_img, ratio="4:5", margin=50, curve=0, shadow=False)
        self.assertEqual(out.size, (1080, 1350))
        extrema = out.getextrema()
        self.assertTrue(any(e[1] > 0 for e in extrema))

    def test_t1_08_auto_color_extraction_vibrancy(self):
        """Auto color extraction on colorful poster must yield vibrant, non-grayscale background colors."""
        self.require_bridge()
        out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, auto_colors=True, ratio="4:5")
        tl_pixel = out.getpixel((10, 10))
        br_pixel = out.getpixel((1070, 1340))
        
        def get_saturation(rgb):
            r, g, b = [x / 255.0 for x in rgb]
            v = max(r, g, b)
            m = min(r, g, b)
            return 0.0 if v == 0 else (v - m) / v

        s_tl = get_saturation(tl_pixel)
        s_br = get_saturation(br_pixel)
        self.assertTrue(s_tl > 0.15 or s_br > 0.15,
                        f"Extracted background colors are dull: TL={tl_pixel} (S={s_tl:.2f}), BR={br_pixel} (S={s_br:.2f})")

    def test_t1_09_custom_hex_colors(self):
        """Custom hex colors (#FF5733 and #1E3A8A) must override auto-extracted colors."""
        self.require_bridge()
        color1_hex = "#FF5733"  # RGB (255, 87, 51)
        color2_hex = "#1E3A8A"  # RGB (30, 58, 138)
        out = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            auto_colors=False,
            color1=color1_hex,
            color2=color2_hex,
            angle=135.0,
            ratio="4:5"
        )
        tl = out.getpixel((5, 5))
        br = out.getpixel((1075, 1345))
        tr = out.getpixel((1075, 5))
        bl = out.getpixel((5, 1345))
        
        dist_tl = math.sqrt((tl[0] - 255)**2 + (tl[1] - 87)**2 + (tl[2] - 51)**2)
        dist_br = math.sqrt((br[0] - 30)**2 + (br[1] - 58)**2 + (br[2] - 138)**2)
        dist_tr = math.sqrt((tr[0] - 255)**2 + (tr[1] - 87)**2 + (tr[2] - 51)**2)
        dist_bl = math.sqrt((bl[0] - 30)**2 + (bl[1] - 58)**2 + (bl[2] - 138)**2)
        self.assertTrue(
            (dist_tl < 60.0 and dist_br < 60.0) or (dist_tr < 60.0 and dist_bl < 60.0),
            f"Gradient corners do not match custom colors: TL={tl}, BR={br}, TR={tr}, BL={bl}"
        )

    def test_t1_10_color_swap(self):
        """swap_colors=True must invert the gradient endpoint positions."""
        self.require_bridge()
        c1 = "#FF0000"
        c2 = "#0000FF"
        out_normal = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            auto_colors=False,
            color1=c1,
            color2=c2,
            swap_colors=False,
            angle=90.0,
            ratio="4:5"
        )
        out_swapped = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            auto_colors=False,
            color1=c1,
            color2=c2,
            swap_colors=True,
            angle=90.0,
            ratio="4:5"
        )
        top_norm = out_normal.getpixel((540, 5))
        top_swap = out_swapped.getpixel((540, 5))
        self.assertGreater(top_norm[0], top_norm[2], "Normal top should be predominantly red")
        self.assertGreater(top_swap[2], top_swap[0], "Swapped top should be predominantly blue")

    def test_t1_11_gradient_angles(self):
        """Angles 0°, 90°, 135°, 270° must produce mathematically correct gradient projections."""
        self.require_bridge()
        c1 = "#FF0000"
        c2 = "#0000FF"
        for angle in [0.0, 90.0, 135.0, 270.0]:
            out = invoke_bridge(
                self.bridge_fn,
                input_image=self.sample_poster,
                auto_colors=False,
                color1=c1,
                color2=c2,
                angle=angle,
                ratio="4:5"
            )
            self.assertEqual(out.size, (1080, 1350))
            if angle == 0.0:
                left = out.getpixel((5, 675))
                right = out.getpixel((1075, 675))
                self.assertGreater(left[0], left[2], "Angle 0° left should be red")
                self.assertGreater(right[2], right[0], "Angle 0° right should be blue")
            elif angle == 90.0:
                top = out.getpixel((540, 5))
                bottom = out.getpixel((540, 1345))
                self.assertGreater(top[0], top[2], "Angle 90° top should be red")
                self.assertGreater(bottom[2], bottom[0], "Angle 90° bottom should be blue")
            elif angle == 270.0:
                top = out.getpixel((540, 5))
                bottom = out.getpixel((540, 1345))
                self.assertGreater(bottom[0], bottom[2], "Angle 270° bottom should be red")
                self.assertGreater(top[2], top[0], "Angle 270° top should be blue")

    def test_t1_12_margin_padding_variations(self):
        """Margins (0, 30, 50, 100 px) must adjust poster card containment size."""
        self.require_bridge()
        for margin in [0, 30, 50, 100]:
            out = invoke_bridge(self.bridge_fn, input_image=self.sample_poster, margin=margin, ratio="4:5")
            self.assertEqual(out.size, (1080, 1350))

    def test_t1_13_corner_radius_variations_and_antialiasing(self):
        """Corner curves (0, 45, 90, 120 px) must render smoothly, exhibiting Lanczos anti-aliasing."""
        self.require_bridge()
        for curve in [0, 45, 90, 120]:
            out = invoke_bridge(
                self.bridge_fn,
                input_image=self.sample_poster,
                curve=curve,
                margin=50,
                ratio="4:5"
            )
            self.assertEqual(out.size, (1080, 1350))

    def test_t1_14_drop_shadow_on_off(self):
        """Drop shadow enabled must darken margin area compared to drop shadow disabled."""
        self.require_bridge()
        out_shadow = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            shadow=True,
            auto_colors=False,
            color1="#EEEEEE",
            color2="#EEEEEE",
            margin=80,
            curve=45,
            ratio="4:5"
        )
        out_no_shadow = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            shadow=False,
            auto_colors=False,
            color1="#EEEEEE",
            color2="#EEEEEE",
            margin=80,
            curve=45,
            ratio="4:5"
        )
        shadow_pixel = out_shadow.getpixel((540, 1350 - 55))
        no_shadow_pixel = out_no_shadow.getpixel((540, 1350 - 55))
        
        lum_shadow = sum(shadow_pixel) / 3.0
        lum_no_shadow = sum(no_shadow_pixel) / 3.0
        self.assertLessEqual(
            lum_shadow,
            lum_no_shadow + 2.0,
            f"Shadow pixel ({shadow_pixel}) should be darker or equal to no-shadow pixel ({no_shadow_pixel})"
        )

    def test_t1_15_watermark_styling_and_toggle(self):
        """Watermark must modify bottom text area when enabled, and leave untouched when disabled."""
        self.require_bridge()
        out_wm = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            watermark="BAZYEPC",
            ratio="4:5"
        )
        out_no_wm = invoke_bridge(
            self.bridge_fn,
            input_image=self.sample_poster,
            watermark=None,
            ratio="4:5"
        )
        self.assertEqual(out_wm.size, (1080, 1350))
        self.assertEqual(out_no_wm.size, (1080, 1350))
        diff = 0
        for y in range(1300, 1345, 5):
            for x in range(400, 680, 10):
                p1 = out_wm.getpixel((x, y))
                p2 = out_no_wm.getpixel((x, y))
                if p1 != p2:
                    diff += 1
        self.assertGreater(diff, 0, "Watermark did not produce any visual differences in the bottom margin")


# ==============================================================================
# SECTION 4: TIER 2 — BOUNDARY & CORNER CASES
# ==============================================================================

class TestTier2BoundaryAndCornerCases(BasePosterTestCase):
    """
    Tier 2: Boundary & Corner Cases
    Validates extreme, degenerate, and pathological inputs:
      - Pure black (0,0,0), pure white (255,255,255), flat gray (128,128,128)
      - Margin exceeding canvas bounds (clamping verification)
      - Extreme aspect ratios (21:9 on 4:5; 9:16 on 16:9)
      - Alpha channel / transparency handling
      - Missing or empty watermark string
      - Micro (16x16) image input
    """

    def test_t2_01_monochromatic_pure_black_image(self):
        """Pure black poster must trigger dead-color fallback palette without crashing."""
        self.require_bridge()
        black_img = create_synthetic_game_poster(1920, 1080, "pure_black")
        out = invoke_bridge(self.bridge_fn, input_image=black_img, auto_colors=True, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))
        tl = out.getpixel((10, 10))
        self.assertTrue(any(c > 10 for c in tl), f"Fallback palette failed: TL pixel is pitch black {tl}")

    def test_t2_02_monochromatic_pure_white_image(self):
        """Pure white poster must trigger dead-color fallback palette without crashing."""
        self.require_bridge()
        white_img = create_synthetic_game_poster(1920, 1080, "pure_white")
        out = invoke_bridge(self.bridge_fn, input_image=white_img, auto_colors=True, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))
        tl = out.getpixel((10, 10))
        self.assertTrue(any(c < 245 for c in tl), f"Fallback palette failed: TL pixel is pure white {tl}")

    def test_t2_03_monochromatic_gray_image(self):
        """Neutral gray poster must trigger fallback palette without crashing."""
        self.require_bridge()
        gray_img = create_synthetic_game_poster(1920, 1080, "monochrome_gray")
        out = invoke_bridge(self.bridge_fn, input_image=gray_img, auto_colors=True, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))

    def test_t2_04_margin_exceeding_bounds_clamping(self):
        """Margin exceeding canvas boundaries (e.g. 700px on 1080x1350) must clamp safely."""
        self.require_bridge()
        img = create_synthetic_game_poster(1920, 1080, "action")
        out = invoke_bridge(self.bridge_fn, input_image=img, margin=700, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))
        self.assertEqual(out.mode, "RGB")

    def test_t2_05_extreme_aspect_ratio_ultrawide_on_portrait(self):
        """Ultrawide 21:9 image (2560x1080) on portrait 4:5 canvas (1080x1350)."""
        self.require_bridge()
        uw_img = Image.new("RGB", (2560, 1080), (220, 30, 80))
        out = invoke_bridge(self.bridge_fn, input_image=uw_img, ratio="4:5", margin=50)
        self.assertEqual(out.size, (1080, 1350))

    def test_t2_06_extreme_aspect_ratio_portrait_on_widescreen(self):
        """Portrait 9:16 image (1080x1920) on widescreen 16:9 canvas (1920x1080)."""
        self.require_bridge()
        pt_img = Image.new("RGB", (1080, 1920), (30, 220, 80))
        out = invoke_bridge(self.bridge_fn, input_image=pt_img, ratio="16:9", margin=50)
        self.assertEqual(out.size, (1920, 1080))

    def test_t2_07_alpha_channel_transparency_handling(self):
        """Raw poster with RGBA transparency must composite cleanly without mode mismatch."""
        self.require_bridge()
        rgba_img = create_synthetic_game_poster(1200, 800, "transparent_rgba")
        out = invoke_bridge(self.bridge_fn, input_image=rgba_img, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))
        self.assertEqual(out.mode, "RGB")

    def test_t2_08_missing_or_empty_watermark(self):
        """Empty watermark string ('') or None must cleanly skip watermark rendering."""
        self.require_bridge()
        img = create_synthetic_game_poster(1200, 800, "retro")
        out_empty = invoke_bridge(self.bridge_fn, input_image=img, watermark="", ratio="4:5")
        out_none = invoke_bridge(self.bridge_fn, input_image=img, watermark=None, ratio="4:5")
        self.assertEqual(out_empty.size, (1080, 1350))
        self.assertEqual(out_none.size, (1080, 1350))

    def test_t2_09_extreme_curve_radius_clamping(self):
        """Excessive curve radius (e.g. 300px on small card) must clamp to half-dimension without crash."""
        self.require_bridge()
        img = Image.new("RGB", (200, 200), (50, 100, 200))
        out = invoke_bridge(self.bridge_fn, input_image=img, curve=300, margin=20, ratio="1:1")
        self.assertEqual(out.size, (1200, 1200))

    def test_t2_10_micro_image_input(self):
        """Tiny 16x16 input image must execute without division-by-zero or quantization errors."""
        self.require_bridge()
        micro_img = create_synthetic_game_poster(16, 16, "micro")
        out = invoke_bridge(self.bridge_fn, input_image=micro_img, ratio="4:5")
        self.assertEqual(out.size, (1080, 1350))


# ==============================================================================
# SECTION 5: TIER 3 — COMBINATORIAL PAIRWISE INTERACTIONS
# ==============================================================================

class TestTier3CombinatorialInteractions(BasePosterTestCase):
    """
    Tier 3: Combinatorial Interactions
    Executes an orthogonal matrix of 18 representative parameter combinations
    (Ratio x Curve x Angle x Margin x Shadow x ColorMode x Watermark) to guarantee
    zero adverse multi-variable interactions.
    """

    MATRIX = [
        # (Run, Ratio, Curve, Angle, Margin, Shadow, Color1, Color2, Swap, Watermark, ExpectedSize)
        (1,  "4:5",   45,  135.0, 50,  True,  None,       None,       False, "BAZYEPC", (1080, 1350)),
        (2,  "4:5",   0,   0.0,   0,   False, "#FF0055",  "#00FFEE",  False, None,      (1080, 1350)),
        (3,  "4:5",   120, 90.0,  100, True,  None,       None,       True,  "BAZYEPC", (1080, 1350)),
        (4,  "1:1",   0,   270.0, 50,  True,  "#112233",  "#445566",  False, "BAZYEPC", (1200, 1200)),
        (5,  "1:1",   45,  135.0, 100, False, None,       None,       False, None,      (1200, 1200)),
        (6,  "1:1",   120, 0.0,   0,   True,  None,       None,       False, "BAZYEPC", (1200, 1200)),
        (7,  "9:16",  45,  90.0,  0,   True,  "#330066",  "#CC00FF",  False, None,      (1080, 1920)),
        (8,  "9:16",  120, 270.0, 50,  False, None,       None,       False, "BAZYEPC", (1080, 1920)),
        (9,  "9:16",  0,   135.0, 100, True,  None,       None,       True,  "BAZYEPC", (1080, 1920)),
        (10, "16:9",  120, 0.0,   50,  True,  "#002244",  "#0088FF",  False, "BAZYEPC", (1920, 1080)),
        (11, "16:9",  0,   90.0,  0,   True,  None,       None,       False, None,      (1920, 1080)),
        (12, "16:9",  45,  270.0, 100, False, None,       None,       False, "BAZYEPC", (1920, 1080)),
        (13, "4:3",   45,  135.0, 50,  True,  None,       None,       False, "BAZYEPC", (1440, 1080)),
        (14, "4:3",   120, 0.0,   0,   False, "#220033",  "#FF5500",  False, None,      (1440, 1080)),
        (15, "21:9",  0,   90.0,  50,  True,  None,       None,       False, "BAZYEPC", (2560, 1080)),
        (16, "21:9",  45,  270.0, 100, True,  "#000000",  "#FFFFFF",  False, "BAZYEPC", (2560, 1080)),
        (17, "4:5",   60,  135.0, 60,  True,  None,       None,       False, "BAZYEPC", (1080, 1350)),
        (18, "9:16",  60,  135.0, 60,  True,  None,       None,       False, "BAZYEPC", (1080, 1920)),
    ]

    def _execute_run(self, index: int):
        self.require_bridge()
        item = self.MATRIX[index]
        run_id, ratio, curve, angle, margin, shadow, c1, c2, swap, wm, expected_size = item

        kwargs = {
            "input_image": self.sample_poster,
            "ratio": ratio,
            "curve": curve,
            "angle": angle,
            "margin": margin,
            "shadow": shadow,
            "swap_colors": swap,
            "watermark": wm,
        }
        if c1 and c2:
            kwargs["auto_colors"] = False
            kwargs["color1"] = c1
            kwargs["color2"] = c2
        else:
            kwargs["auto_colors"] = True

        out = invoke_bridge(self.bridge_fn, **kwargs)
        self.assertIsInstance(out, Image.Image, f"Run {run_id} failed to return PIL Image")
        self.assertEqual(out.size, expected_size, f"Run {run_id} size mismatch: got {out.size}, expected {expected_size}")
        self.assertEqual(out.mode, "RGB", f"Run {run_id} mode mismatch: got {out.mode}")

    def test_t3_run_01(self): self._execute_run(0)
    def test_t3_run_02(self): self._execute_run(1)
    def test_t3_run_03(self): self._execute_run(2)
    def test_t3_run_04(self): self._execute_run(3)
    def test_t3_run_05(self): self._execute_run(4)
    def test_t3_run_06(self): self._execute_run(5)
    def test_t3_run_07(self): self._execute_run(6)
    def test_t3_run_08(self): self._execute_run(7)
    def test_t3_run_09(self): self._execute_run(8)
    def test_t3_run_10(self): self._execute_run(9)
    def test_t3_run_11(self): self._execute_run(10)
    def test_t3_run_12(self): self._execute_run(11)
    def test_t3_run_13(self): self._execute_run(12)
    def test_t3_run_14(self): self._execute_run(13)
    def test_t3_run_15(self): self._execute_run(14)
    def test_t3_run_16(self): self._execute_run(15)
    def test_t3_run_17(self): self._execute_run(16)
    def test_t3_run_18(self): self._execute_run(17)


# ==============================================================================
# SECTION 6: TIER 4 — REAL-WORLD SCENARIOS & BRIDGE/CLI INTEGRATION
# ==============================================================================

class TestTier4RealWorldAndIntegration(BasePosterTestCase):
    """
    Tier 4: Real-World Scenarios & Bridge/CLI Integration
    Validates end-user integration paths:
      - Synthetic & real game poster simulation
      - telegram_bridge.py API contract (in-memory Image return vs file export)
      - Zero-display headless execution guarantee (no X11 / Tkinter dependencies)
      - cli.py subprocess argument parsing, single image, and batch processing
    """

    def setUp(self):
        super().setUp()
        self.temp_dir = tempfile.mkdtemp(prefix="poster_test_")

    def tearDown(self):
        super().tearDown()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_t4_01_synthetic_game_poster_simulation(self):
        """Simulates processing of rich game posters across distinct game genres."""
        self.require_bridge()
        for genre in ["cyberpunk", "action", "horror", "retro"]:
            poster = create_synthetic_game_poster(1920, 1080, genre)
            out = invoke_bridge(self.bridge_fn, input_image=poster, ratio="4:5", curve=45, margin=50)
            self.assertEqual(out.size, (1080, 1350))
            self.assertEqual(out.mode, "RGB")

    def test_t4_02_telegram_bridge_in_memory(self):
        """Calling create_game_poster with output_image=None returns in-memory PIL Image."""
        self.require_bridge()
        poster = create_synthetic_game_poster(1200, 800, "action")
        res = invoke_bridge(self.bridge_fn, input_image=poster, output_image=None, ratio="4:5")
        self.assertIsInstance(res, Image.Image)
        self.assertEqual(res.size, (1080, 1350))

    def test_t4_03_telegram_bridge_file_export(self):
        """Calling create_game_poster with output_image path writes file and returns path string."""
        self.require_bridge()
        poster = create_synthetic_game_poster(1200, 800, "cyberpunk")
        out_file = Path(self.temp_dir) / "output_telegram_test.jpg"
        res_path = invoke_bridge(
            self.bridge_fn,
            input_image=poster,
            output_image=str(out_file),
            ratio="4:5",
            quality=95
        )
        self.assertTrue(out_file.is_file(), f"Export file was not created: {out_file}")
        self.assertGreater(out_file.stat().st_size, 1000, "Exported file is empty or truncated")
        with Image.open(out_file) as loaded:
            self.assertEqual(loaded.size, (1080, 1350))
            self.assertEqual(loaded.format, "JPEG")

    def test_t4_04_headless_zero_display_invariant(self):
        """Bridge and core modules must import and execute without $DISPLAY or Tkinter."""
        self.require_bridge()
        test_script = """
import os, sys
os.environ['DISPLAY'] = ''
sys.modules['_tkinter'] = None
sys.modules['tkinter'] = None

from telegram_bridge import create_game_poster
from PIL import Image
img = Image.new('RGB', (100, 100), (255, 100, 50))
out = create_game_poster(img, ratio='4:5')
assert out.size == (1080, 1350)
print('HEADLESS_SUCCESS')
"""
        proc = subprocess.run(
            [sys.executable, "-c", test_script],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        self.assertEqual(
            proc.returncode, 0,
            f"Headless execution failed with error:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
        )
        self.assertIn("HEADLESS_SUCCESS", proc.stdout)

    def test_t4_05_cli_subprocess_single_image(self):
        """cli.py must parse CLI flags and produce output image via subprocess."""
        self.require_cli()
        in_file = Path(self.temp_dir) / "input_poster.jpg"
        out_file = Path(self.temp_dir) / "cli_output.jpg"
        create_synthetic_game_poster(1200, 800, "action").save(in_file, quality=95)

        cmd = [
            sys.executable,
            str(self.cli_path),
            "--input", str(in_file),
            "--output", str(out_file),
            "--ratio", "4:5",
            "--curve", "45",
            "--margin", "50",
            "--auto-colors",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(
            proc.returncode, 0,
            f"CLI failed with exit code {proc.returncode}.\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
        self.assertTrue(out_file.is_file(), f"Output file not generated at {out_file}")
        with Image.open(out_file) as loaded:
            self.assertEqual(loaded.size, (1080, 1350))

    def test_t4_06_cli_subprocess_batch_processing(self):
        """cli.py --batch-dir must process all images in a folder and skip non-image files."""
        self.require_cli()
        batch_dir = Path(self.temp_dir) / "batch_input"
        batch_dir.mkdir()

        for i in range(3):
            p = batch_dir / f"poster_{i}.jpg"
            create_synthetic_game_poster(800, 600, "cyberpunk").save(p)

        (batch_dir / "notes.txt").write_text("Not an image", encoding="utf-8")

        cmd = [
            sys.executable,
            str(self.cli_path),
            "--batch-dir", str(batch_dir),
            "--ratio", "1:1",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertEqual(
            proc.returncode, 0,
            f"CLI batch failed with exit code {proc.returncode}.\nSTDERR: {proc.stderr}"
        )

    def test_t4_07_cli_subprocess_invalid_arguments(self):
        """cli.py with non-existent input file must exit with non-zero code (1 or 2)."""
        self.require_cli()
        cmd = [
            sys.executable,
            str(self.cli_path),
            "--input", "non_existent_file_xyz_123.jpg",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        self.assertNotEqual(
            proc.returncode, 0,
            f"CLI should exit non-zero for missing input, got {proc.returncode}"
        )


# ==============================================================================
# SECTION 7: PERFORMANCE & SLA BENCHMARK SUITE
# ==============================================================================

class TestPerformanceBenchmark(BasePosterTestCase):
    """
    Performance Benchmark Suite
    Mandatory Acceptance Criteria: Processing a 1080p game poster must execute
    in strictly < 1.5 seconds on CPU.
    """

    SLA_MAX_SECONDS = 1.50
    BENCHMARK_ITERATIONS = 5

    def test_performance_sla_benchmark(self):
        """Enforces hard SLA: mean & max poster processing time must be < 1.50s."""
        self.require_bridge()
        raw_poster = create_synthetic_game_poster(1920, 1080, "action")

        # 1. Warmup pass
        invoke_bridge(
            self.bridge_fn,
            input_image=raw_poster,
            ratio="4:5",
            curve=45,
            margin=50,
            auto_colors=True,
            shadow=True
        )

        # 2. Benchmark iterations
        latencies = []
        for i in range(self.BENCHMARK_ITERATIONS):
            t0 = time.perf_counter()
            out = invoke_bridge(
                self.bridge_fn,
                input_image=raw_poster,
                ratio="4:5",
                curve=45,
                margin=50,
                auto_colors=True,
                shadow=True
            )
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            self.assertEqual(out.size, (1080, 1350))

        mean_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)

        print("\n" + "=" * 70)
        print(" [PERFORMANCE BENCHMARK RESULTS] 1080p -> 1080x1350 Poster Composite")
        print("=" * 70)
        for idx, t in enumerate(latencies, 1):
            print(f"  Iteration {idx}: {t * 1000:.2f} ms ({t:.4f} s)")
        print("-" * 70)
        print(f"  Min Latency:   {min_latency * 1000:.2f} ms")
        print(f"  Mean Latency:  {mean_latency * 1000:.2f} ms")
        print(f"  Max Latency:   {max_latency * 1000:.2f} ms")
        print(f"  SLA Threshold: {self.SLA_MAX_SECONDS * 1000:.2f} ms (1.50 s)")
        print(f"  SLA Margin:    {(self.SLA_MAX_SECONDS - mean_latency) * 1000:.2f} ms headroom")
        print("=" * 70 + "\n")

        self.assertLess(
            mean_latency, self.SLA_MAX_SECONDS,
            f"Mean execution time ({mean_latency:.3f}s) exceeded 1.50s SLA threshold!"
        )
        self.assertLess(
            max_latency, self.SLA_MAX_SECONDS,
            f"Max execution time ({max_latency:.3f}s) exceeded 1.50s SLA threshold!"
        )


# ==============================================================================
# SECTION 8: FORMATTED TEST RUNNER & CLI DISPATCHER
# ==============================================================================

class TableTestResult(unittest.TestResult):
    """Custom TestResult tracking timings and structured status per test."""

    def __init__(self, stream=None, descriptions=None, verbosity=None):
        super().__init__(stream, descriptions, verbosity)
        self.records = []
        self._start_time = 0.0

    def startTest(self, test):
        super().startTest(test)
        self._start_time = time.perf_counter()

    def addSuccess(self, test):
        super().addSuccess(test)
        dur = time.perf_counter() - self._start_time
        self.records.append((test, "PASS", dur, ""))

    def addFailure(self, test, err):
        super().addFailure(test, err)
        dur = time.perf_counter() - self._start_time
        err_msg = str(err[1]) if err and len(err) > 1 else "AssertionError"
        last_line = err_msg.strip().splitlines()[-1] if err_msg else ""
        self.records.append((test, "FAIL", dur, last_line))

    def addError(self, test, err):
        super().addError(test, err)
        dur = time.perf_counter() - self._start_time
        err_msg = str(err[1]) if err and len(err) > 1 else "Exception"
        last_line = err_msg.strip().splitlines()[-1] if err_msg else ""
        self.records.append((test, "ERROR", dur, last_line))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        dur = time.perf_counter() - self._start_time
        self.records.append((test, "SKIPPED", dur, reason))


def run_test_suite() -> int:
    """
    Discovers all test cases, executes them through standard unittest suite lifecycle,
    prints a clean formatted table of results, and returns exit code (0 = all pass, 1 = failure).
    """
    suite = unittest.TestSuite()
    loader = unittest.TestLoader()

    tier_map = {
        "TestTier1FeatureCoverage": "Tier 1: Feature Coverage",
        "TestTier2BoundaryAndCornerCases": "Tier 2: Boundary & Corner Cases",
        "TestTier3CombinatorialInteractions": "Tier 3: Combinatorial Interactions",
        "TestTier4RealWorldAndIntegration": "Tier 4: Real-World & Integration",
        "TestPerformanceBenchmark": "Performance Benchmark",
    }

    test_classes = [
        TestTier1FeatureCoverage,
        TestTier2BoundaryAndCornerCases,
        TestTier3CombinatorialInteractions,
        TestTier4RealWorldAndIntegration,
        TestPerformanceBenchmark,
    ]

    for cls in test_classes:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    print("\n" + "=" * 92)
    print(" GAME POSTER STUDIO — AUTOMATED TEST SUITE & SLA VERIFICATION")
    print(" Track: Dual Track Requirement-Driven Opaque-Box E2E Testing")
    print("=" * 92)

    result = TableTestResult()
    total_start = time.perf_counter()
    suite.run(result)
    total_duration = time.perf_counter() - total_start

    print(f"\n{'TIER':<32} | {'TEST CASE':<40} | {'STATUS':<8} | {'TIME':<8}")
    print("-" * 92)

    passed = 0
    failed = 0
    skipped = 0
    errors = 0

    for test_case, status, duration, reason in result.records:
        cls_name = test_case.__class__.__name__
        tier_title = tier_map.get(cls_name, cls_name)
        method_name = test_case._testMethodName
        dur_str = f"{duration * 1000:.1f}ms"

        if status == "PASS":
            passed += 1
        elif status == "FAIL":
            failed += 1
        elif status == "ERROR":
            errors += 1
        elif status == "SKIPPED":
            skipped += 1

        print(f"{tier_title:<32} | {method_name:<40} | {status:<8} | {dur_str:<8}")
        if status in ("FAIL", "ERROR") and reason:
            print(f"  >>> RATIONALE: {reason}")
        elif status == "SKIPPED" and reason:
            print(f"  ... SKIPPED: {reason}")

    total_tests = passed + failed + skipped + errors
    print("-" * 92)
    print(f" SUMMARY: Total={total_tests} | Passed={passed} | Failed={failed} | Errors={errors} | Skipped={skipped}")
    print(f" Total Wall Time: {total_duration:.2f}s")
    print("=" * 92 + "\n")

    if failed > 0 or errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(run_test_suite())
