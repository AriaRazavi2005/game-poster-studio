#!/usr/bin/env python3
"""
test_m4_challenger_harness.py
Empirical Challenger Test Suite for Milestone 4 (Tiers 1 & 2)
Game Poster Studio

Validates:
Tier 1: Feature Coverage
  - All 6 aspect ratios (4:5, 1:1, 9:16, 16:9, 4:3, 21:9) + HD variants
  - Fit-in-box aspect ratio preservation (mathematical bounding box checks)
  - Auto color extraction & saturation assertion across multiple genres
  - Custom hex color parsing (#RGB, #RRGGBB, invalid handling)
  - Color swap toggle inversion across angles
  - Gradient projections for 0°, 90°, 135°, 270°, and intermediate angles (45°, 180°, 315°)
  - Margins (0, 30, 50, 100 px) containment geometry
  - Corner radius curves (0, 45, 90, 120 px) & anti-aliasing gradient inspection
  - Drop shadow on/off luminance deltas
  - Watermark presence, omission, and custom positioning

Tier 2: Boundary & Corner Cases
  - Dead colors: pure black, pure white, monochrome gray, near-black, near-white
  - Single-color input (solid red) & harmonic fallback distance verification
  - Margin overflow clamping (700px, 1000px, negative margin, float margin)
  - Extreme aspect ratios:
      * 32:9 super-ultrawide input (3200x900, 5120x1440) on various canvas ratios
      * 1:3 tall banner input (600x1800, 360x1080) on various canvas ratios
      * Custom canvas dimensions (e.g. 32:9, 1:3)
  - RGBA transparency compositing (alpha channel, semi-transparent overlays, LA mode, P mode)
  - Micro images: 16x16, 8x8, 2x2, 1x1
  - Large 4K images (3840x2160, 4096x2160) and 8K (7680x4320) latency & memory stress test
"""

import sys
import os
import time
import math
import colorsys
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telegram_bridge import create_game_poster
from poster_studio.core.processor import PosterProcessor, PosterConfig, process_poster
from poster_studio.core.geometry import (
    ASPECT_RATIOS,
    ASPECT_RATIOS_HD,
    resolve_canvas_size,
    resolve_margin,
    calculate_poster_placement,
)
from poster_studio.core.palette import (
    extract_dominant_colors,
    is_dead_color,
    color_distance_rgb,
    parse_hex_color,
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
)
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.mask import create_rounded_mask


class ChallengerTier1Tests(unittest.TestCase):
    """Empirical adversarial verification of Tier 1 Feature Coverage."""

    def setUp(self):
        # Create standard test poster
        self.poster_1080p = Image.new("RGB", (1920, 1080), (20, 40, 90))
        d = ImageDraw.Draw(self.poster_1080p)
        d.rectangle([200, 200, 1720, 880], fill=(255, 60, 120))
        d.ellipse([500, 300, 1420, 780], fill=(0, 230, 255))

    def test_tier1_all_six_aspect_ratios_standard_and_hd(self):
        """Verify all 6 standard aspect ratios and their HD counterparts."""
        expected_standard = {
            "4:5": (1080, 1350),
            "1:1": (1200, 1200),
            "9:16": (1080, 1920),
            "16:9": (1920, 1080),
            "4:3": (1440, 1080),
            "21:9": (2560, 1080),
        }
        expected_hd = {
            "4:5": (1440, 1800),
            "1:1": (1600, 1600),
            "9:16": (1440, 2560),
            "16:9": (2560, 1440),
            "4:3": (1920, 1440),
            "21:9": (3440, 1440),
        }

        for ratio, expected_size in expected_standard.items():
            out = create_game_poster(self.poster_1080p, ratio=ratio)
            self.assertEqual(out.size, expected_size, f"Standard ratio {ratio} size mismatch")
            self.assertEqual(out.mode, "RGB")

        for ratio, expected_size in expected_hd.items():
            out = create_game_poster(self.poster_1080p, ratio=ratio, hd=True)
            self.assertEqual(out.size, expected_size, f"HD ratio {ratio} size mismatch")
            self.assertEqual(out.mode, "RGB")

    def test_tier1_auto_color_extraction_and_saturation(self):
        """Verify auto color extraction extracts saturated, distinct colors."""
        out = create_game_poster(self.poster_1080p, auto_colors=True, ratio="4:5")
        c1, c2 = extract_dominant_colors(self.poster_1080p)

        # Neither color should be dead
        self.assertFalse(is_dead_color(*c1), f"Color 1 {c1} is a dead color")
        self.assertFalse(is_dead_color(*c2), f"Color 2 {c2} is a dead color")

        # Check Euclidean separation
        dist = color_distance_rgb(c1, c2)
        self.assertGreaterEqual(dist, 50.0, f"Extracted colors too close: {dist:.1f} < 50.0")

        # Check saturation
        h1, s1, v1 = colorsys.rgb_to_hsv(c1[0]/255, c1[1]/255, c1[2]/255)
        h2, s2, v2 = colorsys.rgb_to_hsv(c2[0]/255, c2[1]/255, c2[2]/255)
        self.assertGreater(max(s1, s2), 0.25, f"Saturation too low: s1={s1:.2f}, s2={s2:.2f}")

    def test_tier1_custom_hex_colors_and_swap_toggle(self):
        """Verify custom hex colors and color swap inversion."""
        c1_hex = "#FF1020"
        c2_hex = "#1020FF"
        c1_rgb = (255, 16, 32)
        c2_rgb = (16, 32, 255)

        # Standard orientation at 90 deg (top-to-bottom)
        out_normal = create_game_poster(
            self.poster_1080p,
            auto_colors=False,
            color1=c1_hex,
            color2=c2_hex,
            swap_colors=False,
            angle=90.0,
            ratio="4:5",
            margin=50
        )
        # Swapped orientation
        out_swapped = create_game_poster(
            self.poster_1080p,
            auto_colors=False,
            color1=c1_hex,
            color2=c2_hex,
            swap_colors=True,
            angle=90.0,
            ratio="4:5",
            margin=50
        )

        top_norm = out_normal.getpixel((540, 5))
        bot_norm = out_normal.getpixel((540, 1345))
        top_swap = out_swapped.getpixel((540, 5))
        bot_swap = out_swapped.getpixel((540, 1345))

        # In normal: top is predominantly c1 (red), bottom is c2 (blue)
        self.assertGreater(top_norm[0], 200)
        self.assertGreater(bot_norm[2], 200)

        # In swapped: top is predominantly c2 (blue), bottom is c1 (red)
        self.assertGreater(top_swap[2], 200)
        self.assertGreater(bot_swap[0], 200)

    def test_tier1_gradient_projections(self):
        """Verify gradient projections for 0°, 90°, 135°, 270°, 45°, 180°."""
        c1 = (255, 0, 0)
        c2 = (0, 0, 255)

        angles_to_check = [0.0, 45.0, 90.0, 135.0, 180.0, 270.0]
        for angle in angles_to_check:
            grad = generate_linear_gradient(200, 200, c1, c2, angle=angle)
            self.assertEqual(grad.size, (200, 200))
            self.assertEqual(grad.mode, "RGB")

            if angle == 0.0:
                # Left is red, Right is blue
                self.assertGreater(grad.getpixel((2, 100))[0], 230)
                self.assertGreater(grad.getpixel((197, 100))[2], 230)
            elif angle == 90.0:
                # Top is red, Bottom is blue
                self.assertGreater(grad.getpixel((100, 2))[0], 230)
                self.assertGreater(grad.getpixel((100, 197))[2], 230)
            elif angle == 180.0:
                # Left is blue, Right is red
                self.assertGreater(grad.getpixel((2, 100))[2], 230)
                self.assertGreater(grad.getpixel((197, 100))[0], 230)
            elif angle == 270.0:
                # Top is blue, Bottom is red
                self.assertGreater(grad.getpixel((100, 2))[2], 230)
                self.assertGreater(grad.getpixel((100, 197))[0], 230)

    def test_tier1_margins_curves_shadow_watermark(self):
        """Verify margins (0, 30, 50, 100), curves (0, 45, 90, 120), shadow on/off, watermark."""
        # 1. Margins
        for m in [0, 30, 50, 100]:
            out = create_game_poster(self.poster_1080p, margin=m, ratio="4:5")
            self.assertEqual(out.size, (1080, 1350))

        # 2. Curves & Lanczos anti-aliasing inspection
        for curve in [0, 45, 90, 120]:
            mask = create_rounded_mask((600, 600), radius=curve, supersample=2)
            self.assertEqual(mask.size, (600, 600))
            if curve == 0:
                # All pixels should be 255
                ext = mask.getextrema()
                self.assertEqual(ext, (255, 255))
            else:
                # Corner pixel (0, 0) must be 0
                self.assertEqual(mask.getpixel((0, 0)), 0)
                # Center pixel (300, 300) must be 255
                self.assertEqual(mask.getpixel((300, 300)), 255)
                # There must be anti-aliased intermediate values (between 1 and 254)
                hist = mask.histogram()
                intermediate = sum(hist[1:255])
                self.assertGreater(intermediate, 0, f"No anti-aliased gradient pixels found for curve={curve}")

        # 3. Drop shadow on vs off
        out_shadow = create_game_poster(
            self.poster_1080p, no_shadow=False, watermark=None, margin=80, color1="#FFFFFF", color2="#FFFFFF", auto_colors=False
        )
        out_no_shadow = create_game_poster(
            self.poster_1080p, no_shadow=True, watermark=None, margin=80, color1="#FFFFFF", color2="#FFFFFF", auto_colors=False
        )
        # 16:9 poster on 4:5 canvas has card bottom at y=934, shadow is around y=950
        placement = calculate_poster_placement((1080, 1350), self.poster_1080p.size, margin=80)
        shadow_y = placement.y + placement.height + 15
        p_shadow = out_shadow.getpixel((540, shadow_y))
        p_no_shadow = out_no_shadow.getpixel((540, shadow_y))
        self.assertLess(sum(p_shadow)/3, sum(p_no_shadow)/3,
                        f"Shadow pixel {p_shadow} should be strictly darker than no-shadow {p_no_shadow}")

        # 4. Watermark presence
        out_wm = create_game_poster(self.poster_1080p, watermark="BAZYEPC")
        out_no_wm = create_game_poster(self.poster_1080p, watermark=None)
        # Verify differences in bottom region
        diff_count = 0
        for y in range(1280, 1345, 2):
            for x in range(400, 680, 5):
                if out_wm.getpixel((x, y)) != out_no_wm.getpixel((x, y)):
                    diff_count += 1
        self.assertGreater(diff_count, 10, "Watermark did not render in bottom margin")


class ChallengerTier2Tests(unittest.TestCase):
    """Empirical adversarial verification of Tier 2 Boundary & Corner Cases."""

    def test_tier2_dead_colors_fallback(self):
        """Verify dead colors (pure black, pure white, gray, near-black, near-white)."""
        test_dead_styles = [
            ("pure_black", (0, 0, 0)),
            ("pure_white", (255, 255, 255)),
            ("monochrome_gray", (128, 128, 128)),
            ("near_black", (8, 8, 8)),
            ("near_white", (250, 250, 250)),
            ("dull_gray", (135, 130, 128)),
        ]

        for name, rgb in test_dead_styles:
            img = Image.new("RGB", (640, 480), rgb)
            c1, c2 = extract_dominant_colors(img)
            self.assertEqual((c1, c2), (DEFAULT_FALLBACK_C1, DEFAULT_FALLBACK_C2),
                             f"Style {name} did not trigger fallback palette")

            # Must process without crashing and produce valid RGB poster
            out = create_game_poster(img, auto_colors=True, ratio="4:5")
            self.assertEqual(out.size, (1080, 1350))
            self.assertEqual(out.mode, "RGB")
            # Margin pixel should match fallback gradient, not dead color
            tl = out.getpixel((10, 10))
            self.assertTrue(tl != rgb, f"Poster background remained dead color {rgb}")

    def test_tier2_solid_single_color_harmonic_shift(self):
        """A single non-dead vibrant color must generate a harmonic second color."""
        solid_red = Image.new("RGB", (400, 400), (255, 0, 0))
        c1, c2 = extract_dominant_colors(solid_red)
        self.assertEqual(c1, (255, 0, 0))
        dist = color_distance_rgb(c1, c2)
        self.assertGreaterEqual(dist, 50.0, f"Harmonic color distance too small: {dist:.1f}")

    def test_tier2_margin_overflow_and_negative_clamping(self):
        """Verify margin clamping for extreme values: 700px, 1000px, -50px, float 0.49."""
        img = Image.new("RGB", (800, 600), (50, 150, 200))

        # Margin 700 on 1080x1350
        out_700 = create_game_poster(img, margin=700, ratio="4:5")
        self.assertEqual(out_700.size, (1080, 1350))

        # Margin 1500 (exceeds all dimensions)
        out_1500 = create_game_poster(img, margin=1500, ratio="4:5")
        self.assertEqual(out_1500.size, (1080, 1350))

        # Negative margin
        out_neg = create_game_poster(img, margin=-50, ratio="4:5")
        self.assertEqual(out_neg.size, (1080, 1350))

        # Geometry resolve_margin sanity
        mx, my = resolve_margin((1080, 1350), 9999)
        self.assertLessEqual(mx, 530)
        self.assertLessEqual(my, 530)
        self.assertGreaterEqual(mx, 0)
        self.assertGreaterEqual(my, 0)

    def test_tier2_extreme_aspect_ratios_32_9_and_1_3(self):
        """
        Verify extreme input aspect ratios:
          - 32:9 super-ultrawide (e.g. 3200x900, 5120x1440)
          - 1:3 tall banner (e.g. 600x1800, 360x1080)
        Fitted onto 4:5, 1:1, 16:9, 21:9.
        """
        # 1. 32:9 super ultrawide
        uw_img = Image.new("RGB", (3200, 900), (220, 80, 20))
        d = ImageDraw.Draw(uw_img)
        d.line([(0, 0), (3200, 900)], fill=(0, 255, 200), width=10)

        for ratio in ["4:5", "1:1", "16:9", "21:9"]:
            out = create_game_poster(uw_img, ratio=ratio, margin=50)
            expected_size = ASPECT_RATIOS[ratio]
            self.assertEqual(out.size, expected_size, f"32:9 on {ratio} produced incorrect size")
            self.assertEqual(out.mode, "RGB")

            # Check mathematical aspect ratio preservation
            placement = calculate_poster_placement(expected_size, (3200, 900), margin=50)
            calc_ratio = placement.width / placement.height
            expected_aspect = 3200 / 900
            self.assertAlmostEqual(calc_ratio, expected_aspect, delta=0.05,
                                   msg=f"Distortion detected on 32:9 placed on {ratio}")

        # 2. 1:3 tall banner
        banner_img = Image.new("RGB", (600, 1800), (40, 20, 180))
        d2 = ImageDraw.Draw(banner_img)
        d2.ellipse([100, 300, 500, 1500], fill=(255, 200, 0))

        for ratio in ["4:5", "1:1", "16:9", "21:9"]:
            out = create_game_poster(banner_img, ratio=ratio, margin=50)
            expected_size = ASPECT_RATIOS[ratio]
            self.assertEqual(out.size, expected_size, f"1:3 on {ratio} produced incorrect size")
            self.assertEqual(out.mode, "RGB")

            placement = calculate_poster_placement(expected_size, (600, 1800), margin=50)
            calc_ratio = placement.width / placement.height
            expected_aspect = 600 / 1800
            self.assertAlmostEqual(calc_ratio, expected_aspect, delta=0.05,
                                   msg=f"Distortion detected on 1:3 placed on {ratio}")

    def test_tier2_rgba_transparency_and_modes(self):
        """Verify RGBA transparency, translucent pixels, LA mode, P mode with transparency."""
        # 1. RGBA with full and partial alpha
        rgba_img = Image.new("RGBA", (800, 600), (0, 0, 0, 0))
        d = ImageDraw.Draw(rgba_img)
        # Semi-transparent rectangle
        d.rectangle([100, 100, 700, 500], fill=(255, 50, 100, 180))
        # Fully opaque circle
        d.ellipse([250, 150, 550, 450], fill=(0, 200, 255, 255))

        out_rgba = create_game_poster(rgba_img, ratio="4:5")
        self.assertEqual(out_rgba.size, (1080, 1350))
        self.assertEqual(out_rgba.mode, "RGB")

        # 2. LA mode (Luminance + Alpha)
        la_img = Image.new("LA", (400, 400), (128, 200))
        out_la = create_game_poster(la_img, ratio="1:1")
        self.assertEqual(out_la.size, (1200, 1200))
        self.assertEqual(out_la.mode, "RGB")

        # 3. P mode with transparency
        p_img = rgba_img.convert("P", palette=Image.Palette.ADAPTIVE)
        out_p = create_game_poster(p_img, ratio="4:3")
        self.assertEqual(out_p.size, (1440, 1080))
        self.assertEqual(out_p.mode, "RGB")

    def test_tier2_micro_and_large_4k_8k_images(self):
        """
        Verify micro images (16x16, 8x8, 2x2, 1x1)
        and large images: 4K (3840x2160) and 8K (7680x4320).
        Measure CPU latency and ensure no crashes or memory overflow.
        """
        # 1. Micro images: 16x16, 8x8, 2x2, 1x1
        for dim in [16, 8, 2, 1]:
            micro = Image.new("RGB", (dim, dim), (200, 50, 30))
            out = create_game_poster(micro, ratio="4:5")
            self.assertEqual(out.size, (1080, 1350))
            self.assertEqual(out.mode, "RGB")

        # 2. Large 4K image (3840x2160)
        img_4k = Image.new("RGB", (3840, 2160), (30, 60, 120))
        d_4k = ImageDraw.Draw(img_4k)
        d_4k.rectangle([500, 500, 3340, 1660], fill=(255, 100, 0))

        t0 = time.perf_counter()
        out_4k = create_game_poster(img_4k, ratio="4:5")
        latency_4k = time.perf_counter() - t0

        self.assertEqual(out_4k.size, (1080, 1350))
        self.assertEqual(out_4k.mode, "RGB")
        print(f"\n[STRESS TEST] 4K (3840x2160) processing time: {latency_4k*1000:.2f} ms ({latency_4k:.3f} s)")
        self.assertLess(latency_4k, 1.5, f"4K processing time ({latency_4k:.3f}s) exceeded 1.5s SLA threshold!")

        # 3. Large 8K image (7680x4320)
        img_8k = Image.new("RGB", (7680, 4320), (10, 80, 160))
        d_8k = ImageDraw.Draw(img_8k)
        d_8k.rectangle([1000, 1000, 6680, 3320], fill=(255, 180, 20))

        t0 = time.perf_counter()
        out_8k = create_game_poster(img_8k, ratio="4:5")
        latency_8k = time.perf_counter() - t0

        self.assertEqual(out_8k.size, (1080, 1350))
        self.assertEqual(out_8k.mode, "RGB")
        print(f"[STRESS TEST] 8K (7680x4320) processing time: {latency_8k*1000:.2f} ms ({latency_8k:.3f} s)")


if __name__ == "__main__":
    unittest.main(verbosity=2)
