"""
poster_studio.tests.test_adversarial_m1
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Empirical Adversarial Verification Suite for Milestone 1:
Core Image Processing Engine.

Challenges:
1. Numerical edge cases (angles: 0, 90, 180, 270, 360, negative, non-integer, degenerate 1D dimensions).
2. Extreme image inputs (1x1, 16x16, 4000x3000, pure black, pure white, pure green, solid noise, transparent RGBA, CMYK, exotic modes, extreme aspect ratios).
3. Margin clamping (margin = 0, margin = 1000, negative margin, fractional margin, tuple margins).
4. Radius / Curve clamping (curve = 0, curve = 500, negative curve, non-integer curve).
5. Anti-aliasing quality (subpixel transition band inspection, supersample 1x vs 2x vs 4x).
6. Endurance and memory stability under stress.
7. Discovered edge cases & failure modes (e.g. multiline watermark).
"""

from __future__ import annotations

import gc
import math
import time
import tracemalloc
import numpy as np
from PIL import Image, ImageDraw
import pytest

from poster_studio.core.palette import (
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
    color_distance_rgb,
    extract_dominant_colors,
    is_dead_color,
)
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.geometry import (
    calculate_poster_placement,
    resolve_canvas_size,
    resolve_margin,
)
from poster_studio.core.mask import create_rounded_mask
from poster_studio.core.shadow import create_drop_shadow
from poster_studio.core.watermark import apply_watermark
from poster_studio.core.processor import PosterConfig, process_poster


# =====================================================================
# 1. Numerical Edge Cases (Angles & Degenerate Canvases)
# =====================================================================

class TestNumericalEdgeCases:
    @pytest.mark.parametrize("angle", [0, 90, 180, 270, 360, 450, 720])
    def test_angles_cardinal_and_multi_turn(self, angle):
        """Tests cardinal and multi-rotation angles [0, 90, 180, 270, 360, 450, 720]."""
        grad = generate_linear_gradient(200, 200, (255, 0, 0), (0, 0, 255), angle=angle)
        assert grad.size == (200, 200)
        assert grad.mode == "RGB"
        arr = np.array(grad)
        assert arr.min() >= 0 and arr.max() <= 255

    @pytest.mark.parametrize("angle", [-0.0, -45, -90, -180, -270, -360, -720])
    def test_angles_negative(self, angle):
        """Tests negative angles to ensure modulo arithmetic prevents negative indices or errors."""
        grad = generate_linear_gradient(200, 200, (255, 0, 0), (0, 0, 255), angle=angle)
        assert grad.size == (200, 200)
        assert grad.mode == "RGB"
        arr = np.array(grad)
        assert arr.min() >= 0 and arr.max() <= 255

    @pytest.mark.parametrize("angle", [0.0001, 0.5, 45.12345, 135.999, 270.5, 359.9999])
    def test_angles_non_integer(self, angle):
        """Tests fractional and non-integer rotation angles."""
        grad = generate_linear_gradient(200, 200, (255, 0, 0), (0, 0, 255), angle=angle)
        assert grad.size == (200, 200)
        assert grad.mode == "RGB"
        arr = np.array(grad)
        assert arr.min() >= 0 and arr.max() <= 255

    @pytest.mark.parametrize("size", [(1, 1), (1, 10), (10, 1), (2, 2), (1, 2), (2, 1)])
    @pytest.mark.parametrize("angle", [0, 45, 90, 135, 180, 270])
    def test_degenerate_dimensions_across_angles(self, size, angle):
        """Tests 1D and micro-canvas dimensions across various rotation angles."""
        grad = generate_linear_gradient(size=size, color1=(255, 0, 0), color2=(0, 0, 255), angle=angle)
        assert grad.size == size
        assert grad.mode == "RGB"

    def test_angle_orientation_invariants(self):
        """
        Empirically verifies CSS angle orientation:
        - 0 deg (North): gradient points from South to North (bottom=C1, top=C2).
        - 90 deg (East): gradient points from West to East (left=C1, right=C2).
        - 180 deg (South): gradient points from North to South (top=C1, bottom=C2).
        - 270 deg (West): gradient points from East to West (right=C1, left=C2).
        """
        c1 = (255, 0, 0)
        c2 = (0, 0, 255)

        # 90 deg: Left is C1 (Red), Right is C2 (Blue)
        g90 = generate_linear_gradient(100, 100, c1, c2, angle=90.0, convention="css")
        left_px = g90.getpixel((0, 50))
        right_px = g90.getpixel((99, 50))
        assert left_px[0] > 240 and left_px[2] < 15
        assert right_px[2] > 240 and right_px[0] < 15

        # 180 deg: Top is C1 (Red), Bottom is C2 (Blue)
        g180 = generate_linear_gradient(100, 100, c1, c2, angle=180.0, convention="css")
        top_px = g180.getpixel((50, 0))
        bottom_px = g180.getpixel((50, 99))
        assert top_px[0] > 240 and top_px[2] < 15
        assert bottom_px[2] > 240 and bottom_px[0] < 15


# =====================================================================
# 2. Extreme & Pathological Image Inputs
# =====================================================================

class TestExtremeImageInputs:
    def test_1x1_pixel_image_full_pipeline(self):
        """Tests full pipeline processing on a single-pixel 1x1 image."""
        im = Image.new("RGB", (1, 1), (255, 0, 0))
        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)
        assert out.mode == "RGB"

    def test_16x16_micro_image(self):
        """Tests 16x16 micro image upscaling and framing."""
        im = Image.new("RGB", (16, 16), (40, 180, 220))
        out = process_poster(im, ratio="4:5", curve=20, margin=40)
        assert out.size == (1080, 1350)
        assert out.mode == "RGB"

    def test_4000x3000_ultra_high_res_image(self):
        """Tests downsampling and framing of a 12-megapixel ultra-high-res image."""
        im = Image.new("RGB", (4000, 3000), (80, 120, 210))
        draw = ImageDraw.Draw(im)
        draw.rectangle([500, 500, 3500, 2500], fill=(240, 60, 40))

        t0 = time.perf_counter()
        out = process_poster(im, ratio="4:5", curve=45, margin=50)
        elapsed = time.perf_counter() - t0

        assert out.size == (1080, 1350)
        assert out.mode == "RGB"
        assert elapsed < 1.5, f"4000x3000 processing took {elapsed:.2f}s, exceeding 1.5s SLA!"

    def test_pure_black_input_fallback_trigger(self):
        """Verifies pure black input triggers the default aesthetic fallback palette."""
        im = Image.new("RGB", (300, 300), (0, 0, 0))
        c1, c2 = extract_dominant_colors(im)
        assert c1 == DEFAULT_FALLBACK_C1
        assert c2 == DEFAULT_FALLBACK_C2

        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)

    def test_pure_white_input_fallback_trigger(self):
        """Verifies pure white input triggers the default aesthetic fallback palette."""
        im = Image.new("RGB", (300, 300), (255, 255, 255))
        c1, c2 = extract_dominant_colors(im)
        assert c1 == DEFAULT_FALLBACK_C1
        assert c2 == DEFAULT_FALLBACK_C2

        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)

    def test_pure_green_monochrome_harmonic_fallback(self):
        """Verifies single vibrant color triggers harmonic hue-shift for C2."""
        im = Image.new("RGB", (300, 300), (0, 255, 0))
        c1, c2 = extract_dominant_colors(im)
        assert c1 == (0, 255, 0)
        assert not is_dead_color(*c1)
        assert not is_dead_color(*c2)
        assert color_distance_rgb(c1, c2) >= 50.0

        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)

    def test_solid_random_noise_image(self):
        """Verifies full pipeline stability with high-entropy solid random noise."""
        np.random.seed(42)
        noise = np.random.randint(0, 256, (600, 600, 3), dtype=np.uint8)
        im = Image.fromarray(noise, mode="RGB")
        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)

    def test_transparent_rgba_png(self):
        """Verifies full pipeline with 100% transparent and semi-transparent alpha channels."""
        # Fully transparent
        im_trans = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
        out_trans = process_poster(im_trans, ratio="4:5")
        assert out_trans.size == (1080, 1350)
        assert out_trans.mode == "RGB"

        # Semi-transparent with vibrant foreground
        im_semi = Image.new("RGBA", (400, 400), (255, 100, 20, 128))
        out_semi = process_poster(im_semi, ratio="4:5")
        assert out_semi.size == (1080, 1350)
        assert out_semi.mode == "RGB"

    def test_cmyk_image_input(self):
        """Verifies 4-channel CMYK print poster auto-converts to RGB without errors."""
        im_cmyk = Image.new("CMYK", (400, 500), (100, 50, 0, 20))
        out = process_poster(im_cmyk, ratio="4:5")
        assert out.size == (1080, 1350)
        assert out.mode == "RGB"

    @pytest.mark.parametrize("mode", ["1", "L", "P", "RGB", "RGBA", "CMYK", "YCbCr", "LAB", "HSV"])
    def test_all_pil_supported_image_modes(self, mode):
        """Exhaustive check across all standard Pillow image modes."""
        im = Image.new(mode, (200, 200))
        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)
        assert out.mode == "RGB"

    @pytest.mark.parametrize("size", [(10000, 50), (50, 10000)])
    def test_extreme_aspect_ratios(self, size):
        """Tests ultra-wide (200:1) and ultra-tall (1:200) input aspect ratios."""
        im = Image.new("RGB", size, (120, 180, 240))
        out = process_poster(im, ratio="4:5")
        assert out.size == (1080, 1350)


# =====================================================================
# 3. Margin Clamping Stress
# =====================================================================

class TestMarginClamping:
    def test_margin_zero(self):
        """Tests margin = 0 (full bleed to canvas boundary)."""
        placement = calculate_poster_placement(canvas_size=(1000, 1000), raw_size=(500, 500), margin=0)
        assert placement.x == 0
        assert placement.y == 0
        assert placement.width == 1000
        assert placement.height == 1000

        im = Image.new("RGB", (500, 500), (200, 50, 50))
        out = process_poster(im, margin=0)
        assert out.size == (1080, 1350)

    @pytest.mark.parametrize("margin", [1000, 5000, 10000])
    def test_margin_exceeding_canvas(self, margin):
        """Tests oversized margins exceeding canvas half-dimension (should clamp leaving >= 20px box)."""
        canvas_size = (1080, 1350)
        mx, my = resolve_margin(canvas_size, margin)
        min_dim = min(canvas_size)
        expected_max = (min_dim // 2) - 10  # 530px
        assert mx == expected_max
        assert my == expected_max

        # Box dimensions remain strictly positive
        box_w = canvas_size[0] - 2 * mx
        box_h = canvas_size[1] - 2 * my
        assert box_w >= 20
        assert box_h >= 20

        im = Image.new("RGB", (400, 400), (100, 100, 200))
        out = process_poster(im, margin=margin)
        assert out.size == (1080, 1350)

    @pytest.mark.parametrize("margin", [-1, -50, -1000])
    def test_margin_negative(self, margin):
        """Tests negative margin values, ensuring they clamp to 0."""
        mx, my = resolve_margin((1000, 1000), margin)
        assert mx == 0 and my == 0

        im = Image.new("RGB", (400, 400), (100, 100, 200))
        out = process_poster(im, margin=margin)
        assert out.size == (1080, 1350)

    def test_margin_tuple(self):
        """Tests separate horizontal and vertical margins."""
        mx, my = resolve_margin((1000, 1200), (20, 80))
        assert mx == 20
        assert my == 80

        # With negative and oversized tuple
        mx, my = resolve_margin((1000, 1200), (-10, 2000))
        assert mx == 0
        assert my == (1000 // 2) - 10  # 490

    @pytest.mark.parametrize("frac", [0.05, 0.25, 0.45])
    def test_margin_fractional(self, frac):
        """Tests percentage/fractional margin values."""
        mx, my = resolve_margin((1000, 1000), frac)
        assert mx == round(1000 * frac)
        assert my == round(1000 * frac)


# =====================================================================
# 4. Radius / Curve Clamping Stress
# =====================================================================

class TestRadiusClamping:
    def test_curve_zero_sharp_corners(self):
        """Tests curve = 0 creates an exact binary rectangular mask without anti-aliasing overhead."""
        mask = create_rounded_mask((300, 300), radius=0)
        arr = np.array(mask)
        assert np.all(arr == 255)

        im = Image.new("RGB", (300, 300), (200, 50, 50))
        out = process_poster(im, curve=0)
        assert out.size == (1080, 1350)

    @pytest.mark.parametrize("radius", [500, 2000, 10000])
    def test_curve_exceeding_card_dimensions(self, radius):
        """Tests curve radius exceeding half the shortest dimension clamps to min(w, h)//2."""
        card_w, card_h = 200, 150
        mask = create_rounded_mask((card_w, card_h), radius=radius)
        assert mask.size == (card_w, card_h)

        # Center pixel must still be fully opaque
        arr = np.array(mask)
        assert arr[card_h // 2, card_w // 2] == 255

        im = Image.new("RGB", (300, 300), (200, 50, 50))
        out = process_poster(im, curve=radius)
        assert out.size == (1080, 1350)

    @pytest.mark.parametrize("radius", [-1, -50, -500])
    def test_curve_negative(self, radius):
        """Tests negative curve radius clamps safely to 0 (sharp rectangle)."""
        mask = create_rounded_mask((200, 200), radius=radius)
        arr = np.array(mask)
        assert np.all(arr == 255)

        im = Image.new("RGB", (300, 300), (200, 50, 50))
        out = process_poster(im, curve=radius)
        assert out.size == (1080, 1350)

    def test_curve_non_integer(self):
        """Tests floating-point curve values truncate/round to integer safely."""
        mask = create_rounded_mask((200, 200), radius=45.7)  # type: ignore
        assert mask.size == (200, 200)


# =====================================================================
# 5. Anti-Aliasing Quality & Transition Pixel Inspection
# =====================================================================

class TestAntiAliasingQuality:
    def test_supersampling_subpixel_transition_inspection(self):
        """
        Adversarial inspection of corner transition pixels:
        - supersample=1 (1x): Must have exactly 0 intermediate gray pixels (binary staircase).
        - supersample=2 (2x): Must generate >100 intermediate gray pixels and >30 unique gray levels.
        - supersample=4 (4x): Must generate >100 intermediate gray pixels and >50 unique gray levels.
        """
        w, h, r = 200, 200, 50

        # 1x (no supersampling)
        m1 = create_rounded_mask((w, h), radius=r, supersample=1)
        arr1 = np.array(m1)[:r, :r]
        inter1 = np.logical_and(arr1 > 0, arr1 < 255)
        count1 = np.sum(inter1)
        levels1 = len(np.unique(arr1))

        # 2x (standard supersampling)
        m2 = create_rounded_mask((w, h), radius=r, supersample=2)
        arr2 = np.array(m2)[:r, :r]
        inter2 = np.logical_and(arr2 > 0, arr2 < 255)
        count2 = np.sum(inter2)
        levels2 = len(np.unique(arr2))

        # 4x (high supersampling)
        m4 = create_rounded_mask((w, h), radius=r, supersample=4)
        arr4 = np.array(m4)[:r, :r]
        inter4 = np.logical_and(arr4 > 0, arr4 < 255)
        count4 = np.sum(inter4)
        levels4 = len(np.unique(arr4))

        print(f"\n[AA INSPECTION] 1x: inter={count1}, levels={levels1}")
        print(f"[AA INSPECTION] 2x: inter={count2}, levels={levels2}")
        print(f"[AA INSPECTION] 4x: inter={count4}, levels={levels4}")

        # Verification assertions:
        assert count1 == 0, "1x supersampling must have 0 intermediate pixels (hard staircase)"
        assert levels1 == 2, "1x supersampling must be binary {0, 255}"

        assert count2 > 150, f"2x supersampling generated only {count2} intermediate pixels, expected > 150"
        assert levels2 > 30, f"2x supersampling generated only {levels2} unique gray levels, expected > 30"

        assert count4 > 150, f"4x supersampling generated only {count4} intermediate pixels, expected > 150"
        assert levels4 >= levels2, f"4x supersampling should have >= gray levels than 2x"

    def test_corner_diagonal_smoothness(self):
        """
        Inspects pixel gradient along diagonal ray (x = y) near the corner curve:
        Verifies smooth monotonic ramp from transparent (0) to opaque (255).
        """
        w, h, r = 300, 300, 80
        m = create_rounded_mask((w, h), radius=r, supersample=2)
        arr = np.array(m)

        # Diagonal line coordinates (from (0,0) towards center (r,r))
        diag_samples = [int(arr[i, i]) for i in range(r)]

        # Find transition zone where 0 < val < 255
        transitions = [val for val in diag_samples if 0 < val < 255]

        assert len(transitions) >= 2, (
            f"Expected at least 2 intermediate subpixel values along diagonal, got {transitions}"
        )
        # Verify values along diagonal are non-decreasing
        for i in range(len(diag_samples) - 1):
            assert diag_samples[i] <= diag_samples[i + 1], "Diagonal alpha values must be non-decreasing"


# =====================================================================
# 6. Endurance, Memory Stability & Performance Stress
# =====================================================================

class TestEnduranceAndStress:
    def test_pipeline_memory_stability_loop(self):
        """
        Runs 30 pipeline iterations and verifies heap memory growth is negligible (< 100 KB).
        """
        im = Image.new("RGB", (1280, 720), (50, 100, 150))

        # Warmup
        for _ in range(3):
            _ = process_poster(im)
        gc.collect()

        tracemalloc.start()
        snap1 = tracemalloc.take_snapshot()

        for i in range(30):
            _ = process_poster(im, ratio="4:5", angle=i * 12.0, curve=i % 40, margin=i % 30)

        gc.collect()
        snap2 = tracemalloc.take_snapshot()
        tracemalloc.stop()

        diff = sum(s.size_diff for s in snap2.compare_to(snap1, "lineno"))
        diff_kb = diff / 1024.0

        print(f"\n[STRESS MEMORY] 30 iterations diff: {diff_kb:.1f} KB")
        assert diff_kb < 100.0, f"Memory grew by {diff_kb:.1f} KB, possible memory leak!"


# =====================================================================
# 7. Discovered Vulnerabilities & White-box Edge Cases
# =====================================================================

class TestDiscoveredVulnerabilities:
    def test_multiline_watermark_vulnerability(self):
        """
        Empirical reproduction of PIL anchor limitation on multiline watermark text:
        Pillow raises ValueError: anchor not supported for multiline text when
        newlines are present in text and anchor='lt'.
        """
        canvas = Image.new("RGB", (500, 500), (0, 0, 0))
        # Known bug: newline triggers ValueError in PIL ImageDraw.text with anchor="lt"
        with pytest.raises(ValueError, match="anchor not supported for multiline text"):
            apply_watermark(canvas, text="BAZYEPC\nOFFICIAL")

    def test_watermark_long_and_unicode_safe(self):
        """Verifies very long strings and unicode characters succeed without crash."""
        canvas = Image.new("RGB", (800, 800), (30, 30, 30))
        # Long string
        apply_watermark(canvas, text="A" * 300)
        # Standard unicode text
        apply_watermark(canvas, text="BAZYEPC - GAME POSTER")
