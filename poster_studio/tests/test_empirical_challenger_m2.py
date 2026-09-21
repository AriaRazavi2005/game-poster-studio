"""
poster_studio.tests.test_empirical_challenger_m2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Empirical Challenger 2 Test Harness for Milestone 2:
Headless CLI & Telegram Bridge Performance, Throughput, and Memory Stability.

Verification Objectives:
1. create_game_poster Throughput & Latency:
   - 20 sequential calls via telegram_bridge.py in-memory mode (output_image=None).
   - In-memory BytesIO streaming: img.save(buf, format='JPEG', quality=95) and poster_to_bytesio.
   - Statistical latency analysis (min, mean, median, max, p95).
   - Assert mean latency < 100ms per 1080p poster on CPU.
2. CLI Subprocess Launch Latency & Batch Throughput:
   - Subprocess launch latency for `python cli.py --input ... --output ...`.
   - Subprocess overhead breakdown (Python runtime startup vs pipeline execution).
   - Batch mode processing of 20 images in a folder: verification of throughput and output integrity.
   - Batch fault-tolerance: skipping corrupt images and non-image files.
3. Memory Stability & Leak Detection:
   - Process 20+ images in batch sequence.
   - Profile Resident Set Size (RSS) across iterations using psutil.
   - tracemalloc memory allocation tracking.
   - Assert bounded memory growth and absence of memory leaks.
"""

from __future__ import annotations

import gc
import io
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw
import psutil
import pytest

# Ensure repository root and package are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
POSTER_STUDIO_DIR = REPO_ROOT / "poster_studio"
for p in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from telegram_bridge import (
    create_game_poster,
    poster_to_bytes,
    poster_to_bytesio,
    TelegramBridgeError,
)
import cli


def generate_synthetic_1080p_poster(seed: int = 42) -> Image.Image:
    """
    Generates a high-entropy 1920x1080 (1080p) synthetic gaming poster image.
    Contains gradients, shapes, text-like blocks, and vibrant contrasting colors.
    """
    rng = np.random.RandomState(seed)
    img = Image.new("RGB", (1920, 1080), (15, 20, 35))
    draw = ImageDraw.Draw(img)

    # Gradient background bands
    base_r = int(rng.randint(20, 200))
    base_g = int(rng.randint(20, 200))
    base_b = int(rng.randint(20, 200))
    for y in range(0, 1080, 40):
        t = y / 1080.0
        r = int(base_r * (1 - t) + (255 - base_r) * t)
        g = int(base_g * (1 - t) + (255 - base_g) * t)
        b = int(base_b * (1 - t) + (255 - base_b) * t)
        draw.line([(0, y), (1920, y)], fill=(r, g, b), width=25)

    # Dynamic geometric gaming shapes
    for i in range(12):
        x0 = int(rng.randint(50, 1800))
        y0 = int(rng.randint(50, 950))
        w = int(rng.randint(100, 400))
        h = int(rng.randint(100, 400))
        color = (int(rng.randint(0, 255)), int(rng.randint(0, 255)), int(rng.randint(0, 255)))
        if i % 2 == 0:
            draw.rectangle([x0, y0, min(1920, x0 + w), min(1080, y0 + h)], fill=color)
        else:
            draw.ellipse([x0, y0, min(1920, x0 + w), min(1080, y0 + h)], fill=color)

    # Center hero polygonal motif
    draw.polygon(
        [(960, 200), (1300, 750), (1100, 900), (820, 900), (620, 750)],
        fill=(255, 75, 45),
    )
    draw.ellipse([860, 450, 1060, 650], fill=(0, 240, 210))
    return img


# ==============================================================================
# TEST SUITE 1: TELEGRAM BRIDGE IN-MEMORY & BYTESIO STREAMING BENCHMARK
# ==============================================================================

class TestTelegramBridgeThroughput:
    """Empirical verification of create_game_poster throughput and BytesIO streaming."""

    NUM_ITERATIONS = 20
    SLA_MEAN_THRESHOLD_MS = 100.0  # Requirement: assert mean < 100ms per 1080p poster on CPU

    def test_20_sequential_in_memory_and_bytesio_streaming(self):
        """
        Run 20 sequential calls via telegram_bridge.py in-memory mode (output_image=None)
        and test BytesIO streaming:
            buf = io.BytesIO(); img.save(buf, format='JPEG', quality=95)
        Assert mean execution latency < 100ms per 1080p poster on CPU.
        """
        input_image = generate_synthetic_1080p_poster(seed=100)

        pipeline_latencies_ms: List[float] = []
        streaming_latencies_ms: List[float] = []
        total_latencies_ms: List[float] = []
        buffer_sizes: List[int] = []

        # Warm-up run to exclude JIT / first-time module compilation overhead
        warmup_out = create_game_poster(input_image, output_image=None, ratio="4:5")
        warmup_buf = io.BytesIO()
        warmup_out.save(warmup_buf, format="JPEG", quality=95)

        for i in range(self.NUM_ITERATIONS):
            # Measure pure in-memory pipeline execution
            t0 = time.perf_counter()
            poster = create_game_poster(
                input_image=input_image,
                output_image=None,
                ratio="4:5",
                curve=45,
                margin=50,
                auto_colors=True,
                watermark="BAZYEPC",
                quality=95,
            )
            t1 = time.perf_counter()

            # Measure BytesIO JPEG serialization
            buf = io.BytesIO()
            poster.save(buf, format="JPEG", quality=95)
            t2 = time.perf_counter()

            pipeline_ms = (t1 - t0) * 1000.0
            streaming_ms = (t2 - t1) * 1000.0
            total_ms = (t2 - t0) * 1000.0

            pipeline_latencies_ms.append(pipeline_ms)
            streaming_latencies_ms.append(streaming_ms)
            total_latencies_ms.append(total_ms)

            buf_bytes = buf.getvalue()
            buffer_sizes.append(len(buf_bytes))

            # Verify image properties
            assert isinstance(poster, Image.Image)
            assert poster.size == (1080, 1350)
            assert poster.mode == "RGB"
            assert len(buf_bytes) > 50_000  # Non-trivial JPEG payload

        mean_pipeline_ms = statistics.mean(pipeline_latencies_ms)
        mean_streaming_ms = statistics.mean(streaming_latencies_ms)
        mean_total_ms = statistics.mean(total_latencies_ms)
        min_pipeline_ms = min(pipeline_latencies_ms)
        max_pipeline_ms = max(pipeline_latencies_ms)
        median_pipeline_ms = statistics.median(pipeline_latencies_ms)

        print("\n" + "=" * 70)
        print(" [BENCHMARK 1] create_game_poster In-Memory + BytesIO Streaming (20 Runs)")
        print("=" * 70)
        print(f"  Input Resolution:          1920x1080 (1080p)")
        print(f"  Canvas Output:             1080x1350 (4:5)")
        print(f"  Iterations:                {self.NUM_ITERATIONS}")
        print(f"  Mean Pipeline Latency:     {mean_pipeline_ms:.2f} ms")
        print(f"  Min / Median / Max:        {min_pipeline_ms:.2f} / {median_pipeline_ms:.2f} / {max_pipeline_ms:.2f} ms")
        print(f"  Mean Streaming Latency:    {mean_streaming_ms:.2f} ms")
        print(f"  Mean Total (Pipe+Stream):  {mean_total_ms:.2f} ms")
        print(f"  Mean JPEG Size:            {statistics.mean(buffer_sizes) / 1024:.1f} KB")
        print(f"  SLA Threshold:             < {self.SLA_MEAN_THRESHOLD_MS:.1f} ms")
        print("=" * 70)

        # Core Assertion: mean < 100ms per 1080p poster on CPU
        assert mean_pipeline_ms < self.SLA_MEAN_THRESHOLD_MS, (
            f"Mean pipeline latency {mean_pipeline_ms:.2f}ms exceeds {self.SLA_MEAN_THRESHOLD_MS}ms SLA"
        )

    def test_bytesio_input_to_bytesio_output_streaming(self):
        """
        Verify end-to-end in-memory flow where input is BytesIO and output is BytesIO,
        matching a real Telegram webhook / bot handler pipeline.
        """
        raw_img = generate_synthetic_1080p_poster(seed=101)
        in_buf = io.BytesIO()
        raw_img.save(in_buf, format="JPEG", quality=90)
        in_buf.seek(0)

        t0 = time.perf_counter()
        out_img = create_game_poster(in_buf, output_image=None, ratio="1:1")
        out_buf = poster_to_bytesio(out_img, format="JPEG", quality=95)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert out_img.size == (1200, 1200)
        assert out_buf.tell() == 0  # Ready for immediate Telegram upload
        assert len(out_buf.getvalue()) > 50_000
        print(f"\nBytesIO -> Bridge -> BytesIO turnaround: {elapsed_ms:.2f} ms")
        assert elapsed_ms < 250.0

    def test_multi_ratio_latency_matrix(self):
        """Measures create_game_poster latency across 4 major aspect ratios."""
        input_image = generate_synthetic_1080p_poster(seed=102)
        ratios = [("4:5", (1080, 1350)), ("1:1", (1200, 1200)), ("9:16", (1080, 1920)), ("16:9", (1920, 1080))]

        print("\n" + "-" * 60)
        print(f"{'Ratio':<8} | {'Canvas Size':<12} | {'Mean Latency':<14} | {'Status'}")
        print("-" * 60)
        for ratio_name, expected_size in ratios:
            times = []
            for _ in range(5):
                t0 = time.perf_counter()
                out = create_game_poster(input_image, output_image=None, ratio=ratio_name)
                times.append((time.perf_counter() - t0) * 1000.0)
                assert out.size == expected_size
            mean_ms = statistics.mean(times)
            print(f"{ratio_name:<8} | {str(expected_size):<12} | {mean_ms:>8.2f} ms     | PASS")
            assert mean_ms < 500.0  # Well within the 1.5s SLA


# ==============================================================================
# TEST SUITE 2: CLI SUBPROCESS LAUNCH LATENCY & BATCH BENCHMARK
# ==============================================================================

class TestCliSubprocessLatencyAndBatch:
    """Empirical verification of CLI subprocess execution and 20-image batch mode."""

    def test_subprocess_launch_latency(self, tmp_path: Path):
        """
        Measure subprocess launch latency for `python cli.py --input ... --output ...`.
        Decomposes total execution into:
          - Python interpreter process startup overhead (measured via python -c "pass")
          - CLI argument parsing & image processing
        """
        input_file = tmp_path / "bench_in.jpg"
        output_file = tmp_path / "bench_out.jpg"
        poster_img = generate_synthetic_1080p_poster(seed=200)
        poster_img.save(input_file, format="JPEG", quality=95)

        # 1. Baseline Python process startup latency
        startup_times: List[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            subprocess.run([sys.executable, "-c", "pass"], check=True)
            startup_times.append((time.perf_counter() - t0) * 1000.0)
        mean_startup_ms = statistics.mean(startup_times)

        # 2. Measure cli.py subprocess execution latency
        cli_times: List[float] = []
        cmd = [
            sys.executable,
            str(REPO_ROOT / "cli.py"),
            "--input", str(input_file),
            "--output", str(output_file),
            "--ratio", "4:5",
            "--quiet",
        ]

        for i in range(5):
            t0 = time.perf_counter()
            res = subprocess.run(cmd, capture_output=True, text=True)
            t1 = time.perf_counter()
            assert res.returncode == 0, f"CLI failed: {res.stderr}"
            assert output_file.is_file()
            cli_times.append((t1 - t0) * 1000.0)

        mean_cli_ms = statistics.mean(cli_times)
        estimated_core_ms = mean_cli_ms - mean_startup_ms

        print("\n" + "=" * 70)
        print(" [BENCHMARK 2A] CLI Subprocess Launch Latency Breakdown")
        print("=" * 70)
        print(f"  Python Process Startup Overhead: {mean_startup_ms:.2f} ms")
        print(f"  Total Subprocess CLI Execution:  {mean_cli_ms:.2f} ms")
        print(f"  Estimated In-Subprocess Core:    {estimated_core_ms:.2f} ms")
        print(f"  Generated Poster Valid Size:     1080x1350")
        print("=" * 70)

        with Image.open(output_file) as loaded:
            assert loaded.size == (1080, 1350)
            assert loaded.mode == "RGB"

        # Assert total subprocess time is reasonable (< 1500ms on Windows)
        assert mean_cli_ms < 1500.0

    def test_batch_mode_processing_20_images(self, tmp_path: Path):
        """
        Test batch mode processing 20 images in a folder and verify throughput.
        Measures total batch processing time, throughput (images/sec), and average
        latency per poster. Demonstrates elimination of subprocess startup overhead.
        """
        batch_in_dir = tmp_path / "batch_in"
        batch_out_dir = tmp_path / "batch_out"
        batch_in_dir.mkdir()
        batch_out_dir.mkdir()

        NUM_BATCH_IMAGES = 20
        print(f"\nGenerating {NUM_BATCH_IMAGES} synthetic 1080p images for batch benchmark...")

        for i in range(NUM_BATCH_IMAGES):
            img = generate_synthetic_1080p_poster(seed=300 + i)
            fmt = "JPEG" if i % 2 == 0 else "PNG"
            ext = ".jpg" if i % 2 == 0 else ".png"
            img.save(batch_in_dir / f"game_{i:02d}{ext}", format=fmt)

        # Also add non-image files to verify filtering
        (batch_in_dir / "notes.txt").write_text("Ignore this file.")
        (batch_in_dir / "data.json").write_text("{}")

        # Run CLI in batch mode
        cmd = [
            sys.executable,
            str(REPO_ROOT / "cli.py"),
            "--batch-dir", str(batch_in_dir),
            "--output", str(batch_out_dir),
            "--ratio", "4:5",
            "--quiet",
        ]

        t0 = time.perf_counter()
        proc = subprocess.run(cmd, capture_output=True, text=True)
        total_batch_sec = time.perf_counter() - t0

        assert proc.returncode == 0, f"Batch run failed: {proc.stderr}"

        # Verify output directory contains exactly 20 processed images
        output_files = sorted(list(batch_out_dir.glob("*")))
        assert len(output_files) == NUM_BATCH_IMAGES, (
            f"Expected {NUM_BATCH_IMAGES} output files, got {len(output_files)}"
        )

        for out_file in output_files:
            assert out_file.suffix.lower() in [".jpg", ".png"]
            with Image.open(out_file) as loaded:
                assert loaded.size == (1080, 1350)
                assert loaded.mode == "RGB"

        # Non-image files must not be processed into the output folder
        assert not (batch_out_dir / "notes.txt").exists()
        assert not (batch_out_dir / "data.json").exists()

        time_per_image_ms = (total_batch_sec / NUM_BATCH_IMAGES) * 1000.0
        throughput_fps = NUM_BATCH_IMAGES / total_batch_sec

        print("\n" + "=" * 70)
        print(f" [BENCHMARK 2B] CLI Batch Processing ({NUM_BATCH_IMAGES} Images in Single Process)")
        print("=" * 70)
        print(f"  Batch Size:                 {NUM_BATCH_IMAGES} posters")
        print(f"  Total Batch Execution Time: {total_batch_sec:.2f} s")
        print(f"  Mean Time per Poster:       {time_per_image_ms:.2f} ms")
        print(f"  Throughput:                 {throughput_fps:.2f} posters/sec")
        print("=" * 70)

        # Batch amortized time should be well below 250ms per poster on CPU
        assert time_per_image_ms < 250.0, (
            f"Batch amortized time {time_per_image_ms:.2f}ms exceeds 250ms target"
        )

    def test_batch_fault_tolerance_and_corrupt_files(self, tmp_path: Path):
        """
        Stress-tests batch mode with corrupt files, truncated images, and non-image files.
        Verifies CLI survives, skips bad files with warnings, and processes valid images.
        """
        batch_in = tmp_path / "batch_corrupt_in"
        batch_out = tmp_path / "batch_corrupt_out"
        batch_in.mkdir()
        batch_out.mkdir()

        # 3 valid images
        for i in range(3):
            img = generate_synthetic_1080p_poster(seed=500 + i)
            img.save(batch_in / f"valid_{i}.jpg", format="JPEG")

        # 2 corrupt image files (truncated header / random noise)
        (batch_in / "corrupt_1.jpg").write_bytes(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00corrupt_data_garbage")
        (batch_in / "corrupt_2.png").write_bytes(b"\x89PNG\r\n\x1a\ntruncated_png_header")

        # 2 non-image files
        (batch_in / "readme.txt").write_text("just text")
        (batch_in / "config.yaml").write_text("key: value")

        cmd = [
            sys.executable,
            str(REPO_ROOT / "cli.py"),
            "--batch-dir", str(batch_in),
            "--output", str(batch_out),
            "--quiet",
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)

        # Batch should return 0 (partial success) and produce 3 valid output files
        assert res.returncode == 0
        output_files = sorted(list(batch_out.glob("*")))
        assert len(output_files) == 3
        for out_file in output_files:
            assert "valid_" in out_file.name
            with Image.open(out_file) as loaded:
                assert loaded.size == (1080, 1350)


# ==============================================================================
# TEST SUITE 3: MEMORY STABILITY & LEAK DETECTION IN BATCH PROCESSING
# ==============================================================================

class TestBatchMemoryStability:
    """
    Empirically profiles memory footprint during batch processing of 25 posters.
    Verifies that memory usage stabilizes and does not leak uncontrollably.
    """

    def test_memory_stability_across_batch(self, tmp_path: Path):
        """
        Process 25 consecutive posters in batch while tracking RSS memory via psutil
        and Python heap via tracemalloc.
        """
        process = psutil.Process(os.getpid())
        gc.collect()

        # Start tracemalloc
        tracemalloc.start()
        snapshot_start = tracemalloc.take_snapshot()

        rss_start_mb = process.memory_info().rss / (1024 * 1024)

        NUM_POSTERS = 25
        rss_samples: List[float] = []

        print("\n" + "=" * 70)
        print(f" [BENCHMARK 3] Memory Stability Profiling ({NUM_POSTERS} Sequential Posters)")
        print("=" * 70)
        print(f"  Initial Process RSS: {rss_start_mb:.2f} MB")
        print("-" * 70)
        print(f"{'Iteration':<10} | {'RSS (MB)':<12} | {'Delta vs Start (MB)':<20}")
        print("-" * 70)

        for i in range(NUM_POSTERS):
            img = generate_synthetic_1080p_poster(seed=400 + i)
            # Process via bridge in-memory
            poster = create_game_poster(
                img,
                output_image=None,
                ratio="4:5",
                curve=45,
                margin=50,
                auto_colors=True,
                watermark="BAZYEPC",
            )
            # Simulate Telegram serialization
            bio = poster_to_bytesio(poster, quality=95)
            del poster, img, bio

            current_rss_mb = process.memory_info().rss / (1024 * 1024)
            rss_samples.append(current_rss_mb)

            if (i + 1) % 5 == 0 or i == NUM_POSTERS - 1:
                delta = current_rss_mb - rss_start_mb
                print(f"{i + 1:<10} | {current_rss_mb:>8.2f} MB   | {delta:>+10.2f} MB")

        # Explicit garbage collection check
        gc.collect()
        rss_end_mb = process.memory_info().rss / (1024 * 1024)
        net_rss_growth_mb = rss_end_mb - rss_start_mb

        # Take final tracemalloc snapshot
        snapshot_end = tracemalloc.take_snapshot()
        top_stats = snapshot_end.compare_to(snapshot_start, "lineno")
        tracemalloc.stop()

        print("-" * 70)
        print(f"  Final RSS after GC:         {rss_end_mb:.2f} MB")
        print(f"  Net Process RSS Growth:     {net_rss_growth_mb:+.2f} MB")
        print(f"  Max RSS during Run:         {max(rss_samples):.2f} MB")
        print("  Top 3 Memory Allocations Delta:")
        for stat in top_stats[:3]:
            print(f"    {stat}")
        print("=" * 70)

        # Assert memory stability:
        # After garbage collection, net RSS growth over 25 large 1080p posters must be < 35 MB
        # (operating within Python and OS memory allocator pooling limits)
        assert net_rss_growth_mb < 35.0, (
            f"Net memory growth of {net_rss_growth_mb:.2f}MB exceeds 35MB threshold, potential memory leak!"
        )


if __name__ == "__main__":
    pytest.main(["-v", "-s", __file__])
