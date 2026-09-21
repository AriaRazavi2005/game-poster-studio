import gc
import os
import statistics
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import psutil
import tracemalloc

from poster_studio.core.processor import process_poster
from poster_studio.core.watermark import apply_watermark, resolve_watermark_font


def make_test_poster(width=1920, height=1080):
    img = Image.new("RGB", (width, height), (20, 25, 45))
    draw = ImageDraw.Draw(img)
    for y in range(0, height, 40):
        t = y / max(height - 1, 1)
        r = int(15 * (1 - t) + 210 * t)
        g = int(180 * (1 - t) + 30 * t)
        b = int(240 * (1 - t) + 120 * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b), width=20)
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
    draw.ellipse([width // 3, height // 3, width * 2 // 3, height * 2 // 3], fill=(0, 230, 210))
    return img


def run_all():
    raw_img = make_test_poster(1920, 1080)

    print("=" * 80)
    print("1. THROUGHPUT BENCHMARKS (15 runs each, 1 warmup discarded)")
    print("=" * 80)
    resolutions = [
        ("Standard 4:5", False, "4:5", (1080, 1350)),
        ("HD 4:5", True, "4:5", (1440, 1800)),
        ("Square 1:1", False, "1:1", (1200, 1200)),
        ("Story 9:16", False, "9:16", (1080, 1920)),
        ("Ultrawide 21:9", False, "21:9", (2560, 1080)),
    ]

    for name, hd, ratio_key, exp_size in resolutions:
        # warmup
        process_poster(
            raw_img,
            ratio=ratio_key,
            hd=hd,
            curve=45,
            margin=50,
            angle=135.0,
            auto_colors=True,
            drop_shadow=True,
            watermark="BAZYEPC",
        )
        lats = []
        for _ in range(15):
            t0 = time.perf_counter()
            out = process_poster(
                raw_img,
                ratio=ratio_key,
                hd=hd,
                curve=45,
                margin=50,
                angle=135.0,
                auto_colors=True,
                drop_shadow=True,
                watermark="BAZYEPC",
            )
            t1 = time.perf_counter()
            assert out.size == exp_size
            lats.append((t1 - t0) * 1000.0)

        min_val = min(lats)
        mean_val = statistics.mean(lats)
        median_val = statistics.median(lats)
        max_val = max(lats)
        p95_val = sorted(lats)[int(0.95 * len(lats))]
        stdev_val = statistics.stdev(lats)

        print(f"\n{name} ({exp_size[0]}x{exp_size[1]}):")
        print(f"  Min:    {min_val:6.2f} ms")
        print(f"  Mean:   {mean_val:6.2f} ms")
        print(f"  Median: {median_val:6.2f} ms")
        print(f"  Max:    {max_val:6.2f} ms")
        print(f"  P95:    {p95_val:6.2f} ms")
        print(f"  Stdev:  {stdev_val:6.2f} ms")
        print(f"  SLA (1500ms) Headroom: {1500.0 - mean_val:6.2f} ms")
        print(f"  Target (250ms) Margin: {250.0 - mean_val:6.2f} ms")

    print("\n" + "=" * 80)
    print("2. MEMORY & CPU STABILITY (20 consecutive runs)")
    print("=" * 80)
    proc = psutil.Process()
    gc.collect()
    tracemalloc.start()
    init_rss = proc.memory_info().rss / (1024 * 1024)

    mem_rss = []
    mem_trace = []
    latencies = []

    print(f"Initial RSS: {init_rss:.2f} MB")
    print(f"{'Iter':<5} | {'Ratio':<6} | {'Latency':<9} | {'RSS (MB)':<9} | {'Delta RSS':<10} | {'Heap (MB)':<10}")
    print("-" * 65)

    prev_rss = init_rss
    for i in range(1, 21):
        ratio = ["4:5", "1:1", "9:16", "16:9", "21:9"][(i - 1) % 5]
        t0 = time.perf_counter()
        out = process_poster(
            raw_img,
            ratio=ratio,
            curve=45,
            margin=50,
            auto_colors=True,
            drop_shadow=True,
            watermark="BAZYEPC",
        )
        t_el = (time.perf_counter() - t0) * 1000.0
        latencies.append(t_el)

        cur_rss = proc.memory_info().rss / (1024 * 1024)
        mem_rss.append(cur_rss)
        cur_heap, peak_heap = tracemalloc.get_traced_memory()
        heap_mb = cur_heap / (1024 * 1024)
        mem_trace.append(heap_mb)
        delta_rss = cur_rss - prev_rss
        prev_rss = cur_rss
        print(f"{i:<5} | {ratio:<6} | {t_el:6.1f} ms | {cur_rss:7.2f} MB | {delta_rss:+7.2f} MB | {heap_mb:7.2f} MB")

    gc.collect()
    post_gc_rss = proc.memory_info().rss / (1024 * 1024)
    final_heap, peak_heap = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    stable_rss = mem_rss[2:]
    x = np.arange(len(stable_rss))
    slope, _ = np.polyfit(x, np.array(stable_rss), 1)

    print("-" * 65)
    print(f"Final RSS (post-GC): {post_gc_rss:.2f} MB")
    print(f"Post-warmup Net RSS Drift (Iter 3->20): {stable_rss[-1] - stable_rss[0]:+.2f} MB")
    print(f"Linear Regression RSS Slope: {slope:+.4f} MB/iteration")
    print(f"Tracemalloc Peak Heap: {peak_heap / (1024 * 1024):.2f} MB")

    print("\n" + "=" * 80)
    print("3. FONT RESOLUTION FALLBACK TIERS")
    print("=" * 80)
    # Tier 1: Custom font
    t1_font = resolve_watermark_font("poster_studio/assets/fonts/Anton-Regular.ttf", 28)
    print(f"Tier 1 (Custom path): {type(t1_font).__name__} | Bbox: {t1_font.getbbox('BAZYEPC')}")

    # Tier 2: Bundled font
    t2_font = resolve_watermark_font(None, 28)
    print(f"Tier 2 (Bundled auto): {type(t2_font).__name__} | Bbox: {t2_font.getbbox('BAZYEPC')}")

    # Tier 3: System font (mock bundled missing)
    with patch.object(Path, "is_dir", return_value=False):
        t3_font = resolve_watermark_font(None, 28)
        print(f"Tier 3 (System font fallback): {type(t3_font).__name__} | Bbox: {t3_font.getbbox('BAZYEPC')}")

    # Tier 4: Default font (mock bundled and system missing)
    orig_tt = ImageFont.truetype

    def mock_missing(f, *a, **k):
        if isinstance(f, (str, Path)):
            raise OSError(f"Not found: {f}")
        return orig_tt(f, *a, **k)

    with patch("PIL.ImageFont.truetype", side_effect=mock_missing):
        t4_font = resolve_watermark_font(None, 28)
        print(f"Tier 4 (PIL default font fallback): {type(t4_font).__name__} | Bbox: {t4_font.getbbox('BAZYEPC')}")


if __name__ == "__main__":
    run_all()
