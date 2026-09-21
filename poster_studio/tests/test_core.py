"""
poster_studio.tests.test_core
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Comprehensive unit test suite for Game Poster Studio Milestone 1:
- palette.py (color extraction, dead-color filtering, hex parsing)
- gradient.py (vectorized 1D linear gradient generation)
- geometry.py (aspect ratios, containment scaling, margin clamping)
- mask.py (supersampled anti-aliased rounded masks)
- shadow.py (single-channel Gaussian drop shadows)
- watermark.py (typography, stroke outline, 4-tier font fallback)
- processor.py (PosterConfig and master pipeline orchestration)
- Performance SLA timing assertions (<250ms per poster)
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import time
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest

from poster_studio.core.palette import (
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
    color_distance_rgb,
    extract_dominant_colors,
    generate_harmonic_fallback,
    is_dead_color,
    parse_hex_color,
    rgb_to_hex,
    rgb_to_relative_luminance,
)
from poster_studio.core.gradient import (
    generate_linear_gradient,
)
from poster_studio.core.geometry import (
    ASPECT_RATIOS,
    ASPECT_RATIOS_HD,
    PosterPlacement,
    calculate_fit_box,
    calculate_poster_placement,
    parse_canvas_dimensions,
    resolve_canvas_size,
    resolve_margin,
)
from poster_studio.core.mask import (
    create_rounded_mask,
    generate_rounded_mask,
)
from poster_studio.core.shadow import (
    apply_drop_shadow,
    apply_shadow_to_canvas,
    create_drop_shadow,
    create_drop_shadow_from_placement,
    create_drop_shadow_mask,
)
from poster_studio.core.watermark import (
    apply_watermark,
    calculate_watermark_position,
    resolve_watermark_font,
)
from poster_studio.core.processor import (
    PosterConfig,
    PosterProcessingError,
    PosterProcessor,
    process_poster,
)
from poster_studio.assets.fonts import get_bundled_font_path


# =====================================================================
# 1. Palette Module Tests
# =====================================================================

class TestPaletteModule:
    def test_parse_hex_color_valid(self):
        # 6-digit hex
        assert parse_hex_color("#1e1b4b") == (30, 27, 75)
        assert parse_hex_color("1E1B4B") == (30, 27, 75)
        assert parse_hex_color("#0284c7") == (2, 132, 199)
        assert parse_hex_color("#ffffff") == (255, 255, 255)
        assert parse_hex_color("#000000") == (0, 0, 0)
        # 3-digit shorthand
        assert parse_hex_color("#fff") == (255, 255, 255)
        assert parse_hex_color("1ab") == (17, 170, 187)

    def test_parse_hex_color_invalid(self):
        with pytest.raises(TypeError):
            parse_hex_color(12345)  # type: ignore
        with pytest.raises(ValueError):
            parse_hex_color("#12345")  # 5 digits
        with pytest.raises(ValueError):
            parse_hex_color("#gggggg")  # Non-hex characters
        with pytest.raises(ValueError):
            parse_hex_color("")

    def test_rgb_to_hex(self):
        assert rgb_to_hex((30, 27, 75)) == "#1E1B4B"
        assert rgb_to_hex((2, 132, 199)) == "#0284C7"
        with pytest.raises(ValueError):
            rgb_to_hex((300, 0, 0))

    def test_dead_color_rejection(self):
        # Near black (V < 0.15)
        assert is_dead_color(0, 0, 0) is True
        assert is_dead_color(10, 10, 12) is True
        # Near white (V > 0.90 and S < 0.12)
        assert is_dead_color(255, 255, 255) is True
        assert is_dead_color(245, 245, 248) is True
        # Dull neutral gray (S < 0.18)
        assert is_dead_color(128, 128, 128) is True
        assert is_dead_color(100, 105, 102) is True
        # Vibrant colors (should NOT be dead)
        assert is_dead_color(220, 20, 60) is False  # Crimson
        assert is_dead_color(0, 200, 255) is False   # Cyan
        assert is_dead_color(255, 215, 0) is False   # Gold

    def test_color_distance_rgb(self):
        assert color_distance_rgb((0, 0, 0), (255, 255, 255)) == pytest.approx(441.67, 0.1)
        assert color_distance_rgb((100, 100, 100), (100, 100, 100)) == 0.0

    def test_extract_dominant_colors_pure_black_fallback(self):
        black_img = Image.new("RGB", (200, 200), (0, 0, 0))
        c1, c2 = extract_dominant_colors(black_img)
        assert c1 == DEFAULT_FALLBACK_C1
        assert c2 == DEFAULT_FALLBACK_C2

    def test_extract_dominant_colors_pure_white_fallback(self):
        white_img = Image.new("RGB", (200, 200), (255, 255, 255))
        c1, c2 = extract_dominant_colors(white_img)
        assert c1 == DEFAULT_FALLBACK_C1
        assert c2 == DEFAULT_FALLBACK_C2

    def test_extract_dominant_colors_pure_gray_fallback(self):
        gray_img = Image.new("RGB", (200, 200), (128, 128, 128))
        c1, c2 = extract_dominant_colors(gray_img)
        assert c1 == DEFAULT_FALLBACK_C1
        assert c2 == DEFAULT_FALLBACK_C2

    def test_extract_dominant_colors_vibrant_dual_tones(self):
        # Create an image half crimson (220, 20, 60) and half bright sky blue (0, 180, 240)
        img = Image.new("RGB", (200, 200), (220, 20, 60))
        draw = ImageDraw.Draw(img)
        draw.rectangle([100, 0, 199, 199], fill=(0, 180, 240))

        c1, c2 = extract_dominant_colors(img)
        # Both colors should be vibrant and separated by >= 50.0 distance
        assert color_distance_rgb(c1, c2) >= 50.0
        assert not is_dead_color(*c1)
        assert not is_dead_color(*c2)

    def test_extract_dominant_colors_monochromatic_harmonic_shift(self):
        # Monochromatic red image with black border
        img = Image.new("RGB", (200, 200), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.rectangle([20, 20, 180, 180], fill=(230, 30, 30))

        c1, c2 = extract_dominant_colors(img)
        assert not is_dead_color(*c1)
        # Color 2 should be harmonic fallback satisfying delta E >= 50
        assert color_distance_rgb(c1, c2) >= 50.0

    def test_extract_dominant_colors_rgba_transparency(self):
        rgba_img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(rgba_img)
        draw.rectangle([10, 10, 90, 90], fill=(0, 220, 100, 255))
        c1, c2 = extract_dominant_colors(rgba_img)
        assert not is_dead_color(*c1)


# =====================================================================
# 2. Gradient Module Tests
# =====================================================================

class TestGradientModule:
    def test_linear_gradient_dimensions_and_mode(self):
        grad = generate_linear_gradient(400, 500, (255, 0, 0), (0, 0, 255), angle=135.0)
        assert grad.size == (400, 500)
        assert grad.mode == "RGB"

    def test_linear_gradient_css_135_degrees(self):
        # At 135 degrees (CSS convention: clockwise from top/North):
        # Direction points towards bottom-right.
        # Top-left (0, 0) is C1, Bottom-right (w-1, h-1) is C2.
        c1 = (255, 0, 0)
        c2 = (0, 0, 255)
        grad = generate_linear_gradient(200, 200, c1, c2, angle=135.0, convention="css")

        px_tl = grad.getpixel((0, 0))
        px_br = grad.getpixel((199, 199))

        # Top-left should be strongly red
        assert px_tl[0] >= 240 and px_tl[2] <= 15
        # Bottom-right should be strongly blue
        assert px_br[2] >= 240 and px_br[0] <= 15

    def test_linear_gradient_various_angles(self):
        c1 = (255, 0, 0)
        c2 = (0, 255, 0)
        for ang in [0, 45, 90, 135, 180, 270, 360, -45]:
            grad = generate_linear_gradient(100, 100, c1, c2, angle=ang)
            assert grad.size == (100, 100)
            assert grad.mode == "RGB"

    def test_linear_gradient_hex_colors(self):
        grad = generate_linear_gradient(50, 50, "#FF0000", "#00FF00")
        assert grad.size == (50, 50)
        assert grad.mode == "RGB"

    def test_linear_gradient_overloads(self):
        # Tuple size
        grad1 = generate_linear_gradient((80, 60), (255, 0, 0), (0, 0, 255))
        assert grad1.size == (80, 60)
        # Keyword arguments
        grad2 = generate_linear_gradient(size=(80, 60), color1=(255, 0, 0), color2=(0, 0, 255))
        assert grad2.size == (80, 60)

    def test_linear_gradient_degenerate_and_errors(self):
        # 1x1 image
        grad_1x1 = generate_linear_gradient(1, 1, (100, 150, 200), (0, 0, 0))
        assert grad_1x1.size == (1, 1)
        assert grad_1x1.getpixel((0, 0)) == (100, 150, 200)

        with pytest.raises(ValueError):
            generate_linear_gradient(0, 100, (255, 0, 0), (0, 0, 255))

        with pytest.raises(ValueError):
            generate_linear_gradient(100, -10, (255, 0, 0), (0, 0, 255))

    def test_linear_gradient_performance(self):
        # 1080x1350 linear gradient benchmark
        t0 = time.perf_counter()
        grad = generate_linear_gradient(1080, 1350, (30, 27, 75), (2, 132, 199), angle=135.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        assert grad.size == (1080, 1350)
        # Target is < 50ms
        assert elapsed_ms < 60.0, f"Gradient generation took {elapsed_ms:.1f}ms, expected < 60ms"


# =====================================================================
# 3. Geometry Module Tests
# =====================================================================

class TestGeometryModule:
    def test_aspect_ratios_presets(self):
        assert resolve_canvas_size("4:5") == (1080, 1350)
        assert resolve_canvas_size("1:1") == (1200, 1200)
        assert resolve_canvas_size("9:16") == (1080, 1920)
        assert resolve_canvas_size("16:9") == (1920, 1080)
        assert resolve_canvas_size("4:3") == (1440, 1080)
        assert resolve_canvas_size("21:9") == (2560, 1080)
        # HD presets
        assert resolve_canvas_size("4:5", hd=True) == (1440, 1800)
        assert resolve_canvas_size("4:5_hd") == (1440, 1800)
        assert resolve_canvas_size("1:1_hd") == (1600, 1600)

    def test_custom_canvas_size(self):
        assert resolve_canvas_size("4:5", custom_size=(800, 600)) == (800, 600)
        with pytest.raises(ValueError):
            resolve_canvas_size("4:5", custom_size=(0, 500))

    def test_resolve_margin_pixel_and_percentage(self):
        # Absolute pixel margin
        assert resolve_margin((1000, 1000), 50) == (50, 50)
        # Percentage margin (5% of 1000 = 50)
        assert resolve_margin((1000, 1000), 0.05) == (50, 50)
        # Clamping excessive margin (max is (min_dim // 2) - 10 = 490)
        assert resolve_margin((1000, 1000), 600) == (490, 490)

    def test_calculate_poster_placement_no_distortion(self):
        # Landscape 16:9 raw image placed in 4:5 canvas
        raw_size = (1920, 1080)  # AR = 16/9 = 1.7778
        canvas_size = (1080, 1350)
        placement = calculate_poster_placement(canvas_size, raw_size, margin=50)

        # Fitted width must be <= box_width (1080 - 100 = 980)
        # Fitted height must be <= box_height (1350 - 100 = 1250)
        assert placement.width <= 980
        assert placement.height <= 1250

        # Raw aspect ratio must be preserved
        fitted_ar = placement.width / placement.height
        raw_ar = raw_size[0] / raw_size[1]
        assert abs(fitted_ar - raw_ar) < 0.01

        # Centering offsets check
        expected_x = round((1080 - placement.width) / 2)
        expected_y = round((1350 - placement.height) / 2)
        assert placement.x == expected_x
        assert placement.y == expected_y

    def test_calculate_fit_box_compatibility(self):
        size, pos = calculate_fit_box((1920, 1080), (1080, 1350), margin=50)
        assert isinstance(size, tuple) and len(size) == 2
        assert isinstance(pos, tuple) and len(pos) == 2


# =====================================================================
# 4. Mask Module Tests
# =====================================================================

class TestMaskModule:
    def test_create_rounded_mask_dimensions_and_mode(self):
        mask = create_rounded_mask((300, 400), radius=30)
        assert mask.size == (300, 400)
        assert mask.mode == "L"

    def test_create_rounded_mask_zero_radius_fast_path(self):
        mask = create_rounded_mask((100, 100), radius=0)
        # All pixels must be 255 (completely opaque rectangle)
        arr = np.array(mask)
        assert np.all(arr == 255)

    def test_create_rounded_mask_antialiased_corners(self):
        mask = create_rounded_mask((200, 200), radius=40, supersample=2)
        arr = np.array(mask)
        # Center should be completely opaque
        assert arr[100, 100] == 255
        # Extreme top-left pixel should be 0 (transparent outside curve)
        assert arr[0, 0] == 0
        # Check for antialiased sub-pixel values along the corner curve
        corner_crop = arr[0:40, 0:40]
        intermediate = np.logical_and(corner_crop > 0, corner_crop < 255)
        assert np.any(intermediate), "Expected antialiased transition pixels along corner curve"

    def test_create_rounded_mask_oversized_radius_clamped(self):
        # 100x80 card with radius 200 -> clamped to 40 (min(w,h)//2)
        mask = create_rounded_mask((100, 80), radius=200)
        assert mask.size == (100, 80)
        arr = np.array(mask)
        assert arr[40, 50] == 255  # Center pixel is opaque


# =====================================================================
# 5. Shadow Module Tests
# =====================================================================

class TestShadowModule:
    def test_create_drop_shadow_dimensions_and_mode(self):
        card_mask = create_rounded_mask((300, 400), radius=30)
        shadow_color, shadow_mask = create_drop_shadow(
            mask=card_mask,
            canvas_size=(600, 800),
            offset=(0, 15),
            blur_radius=25,
            opacity=0.48,
            card_position=(150, 200)
        )
        assert shadow_mask.size == (600, 800)
        assert shadow_mask.mode == "L"
        assert shadow_color == (0, 0, 0)

    def test_create_drop_shadow_offset_and_blur(self):
        card_mask = Image.new("L", (100, 100), 255)
        _, shadow_mask = create_drop_shadow(
            mask=card_mask,
            canvas_size=(300, 300),
            offset=(0, 20),
            blur_radius=10,
            opacity=0.5,
            card_position=(100, 100)
        )
        arr = np.array(shadow_mask)
        # Due to +20 Y offset, area below card (around Y=210) should have shadow presence
        assert arr[210, 150] > 0
        # Area far above card (Y=20) should have zero shadow
        assert arr[20, 150] == 0

    def test_apply_drop_shadow(self):
        canvas = Image.new("RGB", (200, 200), (200, 200, 200))
        shadow_mask = Image.new("L", (200, 200), 0)
        draw = ImageDraw.Draw(shadow_mask)
        draw.rectangle([50, 50, 150, 150], fill=128)

        apply_drop_shadow(canvas, shadow_mask, (0, 0, 0))
        # Pixels inside shadow area should be darkened
        px = canvas.getpixel((100, 100))
        assert px[0] < 200 and px[1] < 200 and px[2] < 200
        # Pixels outside shadow area remain 200
        px_out = canvas.getpixel((10, 10))
        assert px_out == (200, 200, 200)


# =====================================================================
# 6. Watermark Module Tests
# =====================================================================

class TestWatermarkModule:
    def test_bundled_font_present_and_resolves(self):
        font_path = get_bundled_font_path()
        assert font_path is not None
        assert font_path.is_file()
        font = resolve_watermark_font(font_size=32)
        assert font is not None

    def test_watermark_positioning(self):
        pos_bc = calculate_watermark_position(
            canvas_size=(1000, 1200),
            text_size=(100, 30),
            position="bottom_center",
            margin_bottom=40
        )
        assert pos_bc[0] == 450  # (1000 - 100) / 2
        assert pos_bc[1] == 1200 - 30 - 40

        pos_bl = calculate_watermark_position(
            canvas_size=(1000, 1200),
            text_size=(100, 30),
            position="bottom_left",
            margin_side=50,
            margin_bottom=40
        )
        assert pos_bl[0] == 50
        assert pos_bl[1] == 1200 - 30 - 40

    def test_apply_watermark_modifies_canvas(self):
        canvas = Image.new("RGB", (400, 400), (100, 100, 100))
        canvas_copy = canvas.copy()
        apply_watermark(canvas, text="BAZYEPC", font_size=24)

        # Verify pixels were modified by text and stroke
        diff = np.array(canvas) != np.array(canvas_copy)
        assert np.any(diff), "Watermark must draw pixels on canvas"

    def test_apply_watermark_empty_text_skips(self):
        canvas = Image.new("RGB", (200, 200), (100, 100, 100))
        canvas_copy = canvas.copy()
        apply_watermark(canvas, text="")
        apply_watermark(canvas, text=None)
        assert np.array_equal(np.array(canvas), np.array(canvas_copy))


# =====================================================================
# 7. Processor Master Pipeline Tests & Performance SLA
# =====================================================================

class TestProcessorModule:
    def test_poster_config_defaults_and_normalization(self):
        config = PosterConfig()
        assert config.ratio == "4:5"
        assert config.curve == 45
        assert config.margin == 50
        assert config.angle == 135.0
        assert config.drop_shadow is True
        assert config.watermark == "BAZYEPC"

    def test_poster_config_from_dict_aliases(self):
        cfg = PosterConfig.from_dict({
            "spacing": 60,
            "radius": 35,
            "no_shadow": True,
            "watermark_text": "GAMING",
        })
        assert cfg.margin == 60
        assert cfg.curve == 35
        assert cfg.drop_shadow is False
        assert cfg.watermark == "GAMING"

    def test_full_pipeline_standard_4_5(self):
        # Create a synthetic 1920x1080 input poster image
        raw_img = Image.new("RGB", (1920, 1080), (200, 50, 50))
        draw = ImageDraw.Draw(raw_img)
        draw.rectangle([400, 200, 1500, 800], fill=(50, 150, 230))

        result = process_poster(
            raw_img,
            ratio="4:5",
            curve=45,
            margin=50,
            angle=135.0,
            drop_shadow=True,
            watermark="BAZYEPC"
        )

        assert result.size == (1080, 1350)
        assert result.mode == "RGB"

    def test_full_pipeline_all_ratios(self):
        raw_img = Image.new("RGB", (800, 600), (100, 150, 200))
        for r_key, (exp_w, exp_h) in ASPECT_RATIOS.items():
            if r_key.endswith("_hd"):
                continue
            out = process_poster(raw_img, ratio=r_key, margin=30, curve=20)
            assert out.size == (exp_w, exp_h), f"Ratio {r_key} produced size {out.size}, expected {(exp_w, exp_h)}"

    def test_full_pipeline_color_overrides_and_swap(self):
        raw_img = Image.new("RGB", (400, 300), (128, 128, 128))
        # Custom colors: Red and Blue
        c1 = "#FF0000"
        c2 = "#0000FF"

        # Normal order
        out_normal = process_poster(raw_img, auto_colors=False, color1=c1, color2=c2, swap_colors=False, margin=60)
        c_normal = out_normal.getpixel((out_normal.width - 5, 5))
        assert c_normal[0] > 200 or out_normal.getpixel((5, 5))[0] > 200  # Corner has high red

        # Swapped order
        out_swapped = process_poster(raw_img, auto_colors=False, color1=c1, color2=c2, swap_colors=True, margin=60)
        c_swapped = out_swapped.getpixel((out_swapped.width - 5, 5))
        assert c_swapped[2] > 200 or out_swapped.getpixel((5, 5))[2] > 200  # Corner has high blue

    def test_full_pipeline_drop_shadow_delta(self):
        raw_img = Image.new("RGB", (400, 300), (255, 255, 255))
        out_shadow = process_poster(raw_img, ratio="1:1", margin=80, drop_shadow=True, watermark=None)
        out_no_shadow = process_poster(raw_img, ratio="1:1", margin=80, drop_shadow=False, watermark=None)

        # Region below the card should be darker with drop shadow enabled
        # Center of canvas is (600, 600). Card bottom is at ~ 600 + card_h//2.
        arr_shadow = np.array(out_shadow, dtype=np.float32)
        arr_no_shadow = np.array(out_no_shadow, dtype=np.float32)

        # Bottom margin pixels (e.g. Y in [1050, 1150])
        diff = arr_no_shadow - arr_shadow
        assert np.sum(diff > 5) > 100, "Drop shadow should darken pixels beneath the poster card"

    def test_full_pipeline_pathological_inputs(self):
        # 1. Pure black input
        black = Image.new("RGB", (200, 200), (0, 0, 0))
        out_black = process_poster(black, ratio="4:5")
        assert out_black.size == (1080, 1350)

        # 2. Pure white input
        white = Image.new("RGB", (200, 200), (255, 255, 255))
        out_white = process_poster(white, ratio="4:5")
        assert out_white.size == (1080, 1350)

        # 3. Micro input (16x16)
        micro = Image.new("RGB", (16, 16), (220, 50, 80))
        out_micro = process_poster(micro, ratio="4:5")
        assert out_micro.size == (1080, 1350)

        # 4. RGBA input with transparent portions
        rgba = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
        draw = ImageDraw.Draw(rgba)
        draw.ellipse([50, 50, 250, 250], fill=(240, 100, 20, 255))
        out_rgba = process_poster(rgba, ratio="4:5")
        assert out_rgba.size == (1080, 1350)
        assert out_rgba.mode == "RGB"

    def test_full_pipeline_save_to_disk(self, tmp_path):
        raw_img = Image.new("RGB", (400, 400), (150, 50, 100))
        out_jpg = tmp_path / "test_poster.jpg"
        out_png = tmp_path / "test_poster.png"

        process_poster(raw_img, output_path=out_jpg, quality=95)
        assert out_jpg.is_file() and out_jpg.stat().st_size > 1000

        process_poster(raw_img, output_path=out_png)
        assert out_png.is_file() and out_png.stat().st_size > 1000

    def test_performance_sla_under_250ms(self):
        """
        SLA Assertion: Full end-to-end processing of a 1080p game poster must
        execute in under 250ms on CPU.
        """
        # Create a realistic 1920x1080 synthetic game poster
        raw_img = Image.new("RGB", (1920, 1080), (35, 45, 90))
        draw = ImageDraw.Draw(raw_img)
        draw.rectangle([300, 150, 1600, 950], fill=(220, 70, 30))
        draw.ellipse([600, 300, 1300, 800], fill=(10, 180, 230))

        # Warmup iteration
        process_poster(raw_img, ratio="4:5", curve=45, margin=50)

        # Benchmark 5 runs
        durations = []
        for _ in range(5):
            t0 = time.perf_counter()
            out = process_poster(raw_img, ratio="4:5", curve=45, margin=50)
            t_elapsed = time.perf_counter() - t0
            durations.append(t_elapsed)

        mean_duration = sum(durations) / len(durations)
        min_duration = min(durations)

        print(f"\n[PERFORMANCE BENCHMARK] 1080p Poster Pipeline: mean={mean_duration*1000:.1f}ms, min={min_duration*1000:.1f}ms")

        # Hard assertion: mean execution time < 250ms
        assert mean_duration < 0.250, (
            f"Pipeline mean latency ({mean_duration*1000:.1f}ms) exceeded 250ms SLA!"
        )
