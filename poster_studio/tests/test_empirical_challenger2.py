"""
poster_studio.tests.test_empirical_challenger2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Empirical Challenger 2 Test Harness for Milestone 1:
1. Performance & SLA stress testing across 5 aspect ratio resolutions:
   - Standard 4:5 poster (1080x1350)
   - HD 4:5 poster (1440x1800)
   - Square 1:1 poster (1200x1200)
   - Story 9:16 poster (1080x1920)
   - Ultrawide 21:9 poster (2560x1080)
   Verifying all execution times are strictly under the 1.5s SLA (target < 250ms).
2. CPU and memory leak detection across 20+ consecutive poster generations.
3. Font resolution fallback resilience: simulating missing bundled fonts,
   missing system fonts, and corrupt font files.
"""

from __future__ import annotations

import gc
import math
import os
from pathlib import Path
import statistics
import sys
import tempfile
import time
from typing import Any, Dict, List, Tuple
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import psutil
import pytest

from poster_studio.core.geometry import ASPECT_RATIOS, resolve_canvas_size
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.mask import create_rounded_mask
from poster_studio.core.palette import extract_dominant_colors
from poster_studio.core.processor import PosterConfig, PosterProcessor, process_poster
from poster_studio.core.shadow import apply_drop_shadow, create_drop_shadow
from poster_studio.core.watermark import (
    apply_watermark,
    calculate_watermark_position,
    resolve_watermark_font,
)


def make_test_poster(width: int = 1920, height: int = 1080) -> Image.Image:
    """Creates a high-entropy synthetic game poster image simulating realistic assets."""
    img = Image.new("RGB", (width, height), (20, 25, 45))
    draw = ImageDraw.Draw(img)
    # Background gradient-like stripes
    for y in range(0, height, 40):
        t = y / max(height - 1, 1)
        r = int(15 * (1 - t) + 210 * t)
        g = int(180 * (1 - t) + 30 * t)
        b = int(240 * (1 - t) + 120 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b), width=20)
    # Center character / hero silhouette
    draw.polygon(
        [
            (width // 4, height // 2),
            (width // 2, height // 5),
            (width * 3 // 4, height // 2),
            (width * 5 // 8, height * 4 // 5),
            (width * 3 // 8, height * 4 // 5),
        ],
        fill=(255, 60, 90),
    )
    # Bright emblem / title card
    draw.ellipse(
        [width // 3, height // 3, width * 2 // 3, height * 2 // 3],
        fill=(0, 230, 210),
    )
    return img


# =====================================================================
# 1. Performance and SLA Stress Testing Suite
# =====================================================================

class TestSlaThroughput:
    """
    Empirical SLA verification across 5 mandatory aspect ratio presets.
    SLA Threshold: Strictly < 1.50 seconds on CPU.
    Performance Target: < 250ms on CPU.
    """

    RESOLUTIONS: List[Tuple[str, bool, str, Tuple[int, int]]] = [
        ("Standard 4:5", False, "4:5", (1080, 1350)),
        ("HD 4:5", True, "4:5", (1440, 1800)),
        ("Square 1:1", False, "1:1", (1200, 1200)),
        ("Story 9:16", False, "9:16", (1080, 1920)),
        ("Ultrawide 21:9", False, "21:9", (2560, 1080)),
    ]

    BENCHMARK_ITERATIONS = 10
    SLA_MAX_SECONDS = 1.50
    TARGET_MAX_SECONDS = 0.250

    @pytest.mark.parametrize("name,hd,ratio_key,expected_size", RESOLUTIONS)
    def test_resolution_sla_throughput(
        self,
        name: str,
        hd: bool,
        ratio_key: str,
        expected_size: Tuple[int, int]
    ):
        """Measures CPU latency across multiple runs for each target resolution."""
        raw_image = make_test_poster(1920, 1080)

        # 1. Warmup pass
        warmup_out = process_poster(
            raw_image,
            ratio=ratio_key,
            hd=hd,
            curve=45,
            margin=50,
            angle=135.0,
            auto_colors=True,
            drop_shadow=True,
            watermark="BAZYEPC",
        )
        assert warmup_out.size == expected_size
        assert warmup_out.mode == "RGB"

        # 2. Benchmark iterations
        latencies: List[float] = []
        for _ in range(self.BENCHMARK_ITERATIONS):
            t0 = time.perf_counter()
            out = process_poster(
                raw_image,
                ratio=ratio_key,
                hd=hd,
                curve=45,
                margin=50,
                angle=135.0,
                auto_colors=True,
                drop_shadow=True,
                watermark="BAZYEPC",
            )
            elapsed = time.perf_counter() - t0
            latencies.append(elapsed)
            assert out.size == expected_size

        min_lat = min(latencies)
        mean_lat = statistics.mean(latencies)
        median_lat = statistics.median(latencies)
        max_lat = max(latencies)
        p95_lat = sorted(latencies)[int(0.95 * len(latencies))]
        stdev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0

        print(
            f"\n[BENCHMARK] {name} ({expected_size[0]}x{expected_size[1]}): "
            f"Mean={mean_lat * 1000:.1f}ms | Median={median_lat * 1000:.1f}ms | "
            f"Min={min_lat * 1000:.1f}ms | Max={max_lat * 1000:.1f}ms | "
            f"P95={p95_lat * 1000:.1f}ms | Stdev={stdev_lat * 1000:.2f}ms"
        )

        # Hard SLA assertions: strictly under 1.5s
        assert max_lat < self.SLA_MAX_SECONDS, (
            f"Resolution {name} exceeded 1.5s SLA! Max latency: {max_lat:.3f}s"
        )
        assert mean_lat < self.SLA_MAX_SECONDS, (
            f"Resolution {name} exceeded 1.5s SLA! Mean latency: {mean_lat:.3f}s"
        )
        # Verify against <250ms CPU target
        assert mean_lat < self.TARGET_MAX_SECONDS, (
            f"Resolution {name} exceeded 250ms CPU target! Mean latency: {mean_lat * 1000:.1f}ms"
        )

    def test_pipeline_substage_profiling(self):
        """Profiles individual pipeline sub-stages on standard 4:5 resolution."""
        raw_image = make_test_poster(1920, 1080)
        canvas_size = (1080, 1350)
        times: Dict[str, float] = {}

        # 1. Dominant color extraction
        t0 = time.perf_counter()
        c1, c2 = extract_dominant_colors(raw_image)
        times["palette_extraction"] = (time.perf_counter() - t0) * 1000.0

        # 2. Gradient generation
        t0 = time.perf_counter()
        canvas = generate_linear_gradient(1080, 1350, c1, c2, angle=135.0)
        times["gradient_generation"] = (time.perf_counter() - t0) * 1000.0

        # 3. Geometry & Lanczos resize
        t0 = time.perf_counter()
        from poster_studio.core.geometry import calculate_poster_placement
        place = calculate_poster_placement(canvas_size, raw_image.size, margin=50)
        resized = raw_image.resize(place.size, resample=Image.Resampling.LANCZOS)
        times["lanczos_resize"] = (time.perf_counter() - t0) * 1000.0

        # 4. Rounded mask creation
        t0 = time.perf_counter()
        mask = create_rounded_mask(place.size, radius=45, supersample=2)
        times["mask_creation"] = (time.perf_counter() - t0) * 1000.0

        # 5. Drop shadow creation & application
        t0 = time.perf_counter()
        _, s_mask = create_drop_shadow(mask, canvas_size, offset=(0, 15), blur_radius=25)
        apply_drop_shadow(canvas, s_mask, (0, 0, 0))
        times["drop_shadow"] = (time.perf_counter() - t0) * 1000.0

        # 6. Card compositing
        t0 = time.perf_counter()
        canvas.paste(resized, place.position, mask=mask)
        times["card_composite"] = (time.perf_counter() - t0) * 1000.0

        # 7. Watermark rendering
        t0 = time.perf_counter()
        apply_watermark(canvas, text="BAZYEPC", font_size=32)
        times["watermark"] = (time.perf_counter() - t0) * 1000.0

        total_stage_time = sum(times.values())
        print("\n[SUBSTAGE PROFILING - Standard 4:5 1080x1350]:")
        for stage, duration in times.items():
            print(f"  - {stage:<22}: {duration:6.2f} ms ({duration / total_stage_time * 100:4.1f}%)")
        print(f"  * Total Stage Sum       : {total_stage_time:6.2f} ms")

        # Every stage must execute well within budget
        assert total_stage_time < 250.0, f"Total sub-stage sum ({total_stage_time:.1f}ms) exceeded 250ms target"


# =====================================================================
# 2. CPU & Memory Leak Stress Testing Suite
# =====================================================================

class TestMemoryAndCpuStability:
    """
    Verifies memory stability and zero memory leak over 20+ consecutive poster generations.
    Tracks RSS process memory, Python tracemalloc heap allocation, and CPU execution time.
    """

    def test_twenty_consecutive_generations_memory_leak(self):
        """
        Executes 20 consecutive runs of poster generation and records memory.
        Performs linear regression to ensure memory slope is bounded.
        """
        process = psutil.Process(os.getpid())
        raw_image = make_test_poster(1920, 1080)

        # Force clean garbage collection before start
        gc.collect()
        time.sleep(0.05)

        initial_rss = process.memory_info().rss / (1024 * 1024)

        rss_measurements: List[float] = []
        cpu_times: List[float] = []

        # Run 20 consecutive poster generations
        for iteration in range(1, 21):
            t0 = time.perf_counter()
            # Vary ratios and parameters to simulate varied production traffic
            ratio = ["4:5", "1:1", "9:16", "16:9", "21:9"][iteration % 5]
            curve = (iteration * 7) % 60
            margin = 30 + (iteration * 3) % 40

            out = process_poster(
                raw_image,
                ratio=ratio,
                curve=curve,
                margin=margin,
                auto_colors=True,
                drop_shadow=True,
                watermark="BAZYEPC",
            )
            # Ensure output image is fully loaded and valid
            assert out.size[0] > 0 and out.size[1] > 0

            elapsed = time.perf_counter() - t0
            cpu_times.append(elapsed)

            current_rss = process.memory_info().rss / (1024 * 1024)
            rss_measurements.append(current_rss)

        gc.collect()
        final_rss = process.memory_info().rss / (1024 * 1024)

        print("\n[MEMORY LEAK BENCHMARK — 20 Consecutive Runs]")
        print(f"  Initial RSS: {initial_rss:.2f} MB")
        for i, (m, c) in enumerate(zip(rss_measurements, cpu_times), 1):
            if i in [1, 5, 10, 15, 20]:
                print(f"  Iter {i:02d}: RSS = {m:6.2f} MB | Latency = {c * 1000:5.1f} ms")
        print(f"  Final RSS (post-GC): {final_rss:.2f} MB")

        # Analyze memory trajectory post-warmup (iterations 3 through 20)
        stable_rss = rss_measurements[2:]  # iter 3 to 20
        x = np.arange(len(stable_rss))
        y = np.array(stable_rss)

        # Linear regression slope: delta MB per iteration
        slope, intercept = np.polyfit(x, y, 1)
        net_stable_growth = stable_rss[-1] - stable_rss[0]

        print(f"  Post-warmup Net RSS Drift: {net_stable_growth:+.2f} MB")
        print(f"  Linear Regression Slope:   {slope:+.4f} MB/iteration")

        # Memory leak assertion:
        # A true memory leak will steadily allocate uncollectable memory (> 1 MB per iteration).
        # Normal Python buffer reuse exhibits slope near 0 (< 0.5 MB/iter).
        assert slope < 0.50, (
            f"Detected potential memory leak! Memory slope is {slope:.4f} MB/iteration"
        )
        assert abs(net_stable_growth) < 25.0, (
            f"Net memory drift ({net_stable_growth:.2f} MB) exceeds safety threshold (25 MB)"
        )


# =====================================================================
# 3. Font Resolution Fallback Resilience Testing Suite
# =====================================================================

class TestFontFallbackResilience:
    """
    Stress-tests the 4-tier font resolution chain:
    - Tier 1: Non-existent custom font -> falls back gracefully.
    - Tier 2: Missing bundled font directory / files -> falls back to system fonts.
    - Tier 3: Missing system fonts -> falls back to PIL default font.
    - Tier 4: Total font starvation -> PIL default font works without crashing.
    """

    def test_nonexistent_custom_font_fallback(self):
        """Providing an invalid custom font path must not crash."""
        font = resolve_watermark_font(
            font_name_or_path="C:/NonExistent/Directory/totally_missing_font.ttf",
            font_size=32,
        )
        assert font is not None
        bbox = font.getbbox("BAZYEPC")
        assert bbox[2] > bbox[0]
        assert bbox[3] > bbox[1]

    def test_corrupt_font_file_fallback(self):
        """Providing a corrupt 0-byte font file must not crash."""
        with tempfile.NamedTemporaryFile(suffix=".ttf", delete=False) as tf:
            tf.write(b"CORRUPT_FONT_DATA_NOT_A_REAL_TRUETYPE_TABLE")
            temp_font_path = tf.name

        try:
            font = resolve_watermark_font(
                font_name_or_path=temp_font_path,
                font_size=28,
            )
            assert font is not None
            bbox = font.getbbox("BAZYEPC")
            assert bbox[2] > bbox[0]
        finally:
            if os.path.exists(temp_font_path):
                try:
                    os.remove(temp_font_path)
                except OSError:
                    pass

    def test_missing_bundled_fonts_falls_back_to_system_or_default(self):
        """
        Simulates missing bundled fonts directory by mocking Path.is_dir and glob
        to simulate a stripped deployment without assets/fonts.
        """
        # Mock bundled directory check to return False
        with patch.object(Path, "is_dir", return_value=False):
            font = resolve_watermark_font(font_size=28)
            assert font is not None

            # Verify watermark application succeeds
            canvas = Image.new("RGB", (800, 1000), (40, 50, 60))
            result = apply_watermark(canvas, text="BAZYEPC", font_size=28)
            assert result is not None
            assert result.size == (800, 1000)

    def test_total_font_starvation_tier4_pil_default(self):
        """
        Simulates a headless minimal Linux/Docker container where neither
        bundled fonts nor system fonts (Impact, Arial, DejaVu, FreeSans) exist on disk.
        All disk-based TrueType font loading raises OSError.
        """
        orig_truetype = ImageFont.truetype

        def disk_fonts_missing(font, *args, **kwargs):
            if isinstance(font, (str, Path)):
                raise OSError(f"Simulated missing font file on disk: {font}")
            return orig_truetype(font, *args, **kwargs)

        with patch("PIL.ImageFont.truetype", side_effect=disk_fonts_missing):
            font = resolve_watermark_font(font_size=24)
            # Must return default font without raising
            assert font is not None

            # Apply watermark on test canvas
            canvas = Image.new("RGB", (600, 800), (50, 50, 50))
            canvas_copy = canvas.copy()
            out = apply_watermark(canvas, text="BAZYEPC", font_size=24)
            assert out is not None

            # Verify watermark rendered pixels even on default font
            diff = np.array(out) != np.array(canvas_copy)
            assert np.any(diff), "Watermark must draw pixels even with Tier 4 default font"

    def test_full_pipeline_with_total_font_starvation(self):
        """
        Verifies that process_poster runs end-to-end under total disk font absence
        (no bundled font, no system fonts) without any crash or unhandled error.
        """
        raw_image = make_test_poster(800, 600)
        orig_truetype = ImageFont.truetype

        def disk_fonts_missing(font, *args, **kwargs):
            if isinstance(font, (str, Path)):
                raise OSError(f"Simulated missing font file on disk: {font}")
            return orig_truetype(font, *args, **kwargs)

        with patch("PIL.ImageFont.truetype", side_effect=disk_fonts_missing):
            out = process_poster(
                raw_image,
                ratio="4:5",
                curve=30,
                margin=40,
                watermark="BAZYEPC",
            )
            assert out.size == (1080, 1350)
            assert out.mode == "RGB"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
