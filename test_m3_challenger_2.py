#!/usr/bin/env python3
"""
Empirical test suite for Milestone 3 Launcher and Export Engine verification.
Conducted by challenger_m3_2.
"""

import os
import sys
import math
import tempfile
from pathlib import Path
from PIL import Image
import numpy as np

# Ensure poster_studio is importable
REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poster_studio.core.processor import PosterConfig, process_poster
from poster_studio.gui.export_engine import ExportEngine
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.geometry import resolve_canvas_size


def test_export_dimensions_and_formats():
    print("=== TEST 1: Export Dimensions & Formats ===")
    sample_img_path = REPO_ROOT / "sample_outputs_m1" / "action_poster_4_5.jpg"
    if sample_img_path.exists():
        raw_image = Image.open(sample_img_path)
    else:
        # Fallback synthetic image
        raw_image = Image.new("RGB", (800, 1000), color=(120, 60, 200))

    engine = ExportEngine()
    tmpdir = Path(tempfile.mkdtemp(prefix="export_test_"))
    results = {}

    configs_to_test = [
        ("1080x1350_jpeg", PosterConfig(ratio="4:5", hd=False), "poster_1080x1350.jpg", "JPEG"),
        ("1080x1350_png", PosterConfig(ratio="4:5", hd=False), "poster_1080x1350.png", "PNG"),
        ("1440x1800_jpeg", PosterConfig(ratio="4:5", hd=True), "poster_1440x1800.jpg", "JPEG"),
        ("1440x1800_png", PosterConfig(ratio="4:5", hd=True), "poster_1440x1800.png", "PNG"),
    ]

    for name, cfg, fname, fmt in configs_to_test:
        out_path = tmpdir / fname
        saved_path, fsize = engine.export_sync(
            raw_image=raw_image,
            config=cfg,
            output_path=out_path,
            format=fmt,
            quality=95
        )

        with Image.open(saved_path) as im:
            actual_size = im.size
            actual_format = im.format
            exif_obj = im.getexif()
            exif_dict = dict(exif_obj) if exif_obj else {}
            has_exif = len(exif_dict) > 0
            info_keys = list(im.info.keys())
            quantization = getattr(im, "quantization", None)

        expected_size = (1440, 1800) if cfg.hd else (1080, 1350)
        size_match = (actual_size == expected_size)
        format_match = (actual_format.upper() == fmt.upper() or (fmt == "JPEG" and actual_format in ("JPEG", "JPG")))

        results[name] = {
            "saved_path": str(saved_path),
            "file_size": fsize,
            "actual_size": actual_size,
            "expected_size": expected_size,
            "size_match": size_match,
            "actual_format": actual_format,
            "format_match": format_match,
            "has_exif": has_exif,
            "exif_dict": exif_dict,
            "info_keys": info_keys,
            "quantization": bool(quantization),
        }
        print(f"[{name}] Size: {actual_size} (Expected {expected_size}) -> {'PASS' if size_match else 'FAIL'}")
        print(f"[{name}] Format: {actual_format} -> {'PASS' if format_match else 'FAIL'}")
        print(f"[{name}] File Size: {fsize:,} bytes")
        print(f"[{name}] EXIF: has_exif={has_exif}, keys={info_keys}")

    return results


def test_jpeg_quality_and_quantization():
    print("\n=== TEST 2: JPEG 95% Quality & Quantization Tables ===")
    sample_img_path = REPO_ROOT / "sample_outputs_m1" / "action_poster_4_5.jpg"
    raw_image = Image.open(sample_img_path)
    engine = ExportEngine()
    tmpdir = Path(tempfile.mkdtemp(prefix="jpeg_q_test_"))

    # Test qualities: 50, 75, 95
    for q in [50, 75, 95]:
        out_p = tmpdir / f"test_q{q}.jpg"
        cfg = PosterConfig(ratio="4:5", hd=False, quality=q)
        engine.export_sync(raw_image, cfg, out_p, format="JPEG", quality=q)

        with Image.open(out_p) as im:
            q_tables = im.quantization
            print(f"Quality {q}: File size = {out_p.stat().st_size} bytes")
            if q_tables:
                lum_table = q_tables.get(0)
                # Sample few values from luminance table
                sample_vals = lum_table[:8] if isinstance(lum_table, (list, tuple)) else lum_table
                print(f"  Luminance Q-table (first 8 values): {sample_vals[:8]}")

    # IJG Standard quality estimation from luminance quantization table
    out_95 = tmpdir / "test_q95.jpg"
    with Image.open(out_95) as im:
        lum = im.quantization[0]
        # Standard IJG base table element 0 is 16.
        # At Q=95, scale = (100 - 95)/50 = 0.10. 16 * 0.10 = 1.6 -> rounded to 2.
        # Element 1 is 11. 11 * 0.10 = 1.1 -> rounded to 1.
        # Element 2 is 10. 10 * 0.10 = 1.0 -> rounded to 1.
        print(f"  Verified Q=95 Luminance table elements: {lum[:8]}")
        # Check if subsampling is 4:4:4 (0 in Pillow subsampling)
        subsampling = im.info.get("subsampling", "unknown")
        print(f"  Chroma subsampling in info: {subsampling}")


def test_png_lossless():
    print("\n=== TEST 3: PNG Lossless Fidelity ===")
    sample_img_path = REPO_ROOT / "sample_outputs_m1" / "action_poster_4_5.jpg"
    raw_image = Image.open(sample_img_path)

    # For both 1080x1350 and 1440x1800
    for hd, label in [(False, "1080x1350"), (True, "1440x1800")]:
        cfg = PosterConfig(ratio="4:5", hd=hd)
        rendered = process_poster(raw_image, config=cfg)
        
        tmpdir = Path(tempfile.mkdtemp(prefix="png_lossless_"))
        out_png = tmpdir / f"test_{label}.png"
        engine = ExportEngine()
        engine.export_sync(raw_image, cfg, out_png, format="PNG")

        reloaded = Image.open(out_png)
        arr_orig = np.array(rendered)
        arr_reloaded = np.array(reloaded)

        diff = np.abs(arr_orig.astype(int) - arr_reloaded.astype(int))
        max_diff = np.max(diff)
        total_diff_pixels = np.count_nonzero(diff)
        print(f"[{label}] Dimensions: Rendered={rendered.size}, Reloaded={reloaded.size}")
        print(f"[{label}] Lossless check: Max diff = {max_diff}, Nonzero diff pixels = {total_diff_pixels}")
        assert max_diff == 0, f"PNG export is not lossless! Max diff = {max_diff}"
        assert rendered.size == reloaded.size == ((1440, 1800) if hd else (1080, 1350))
        print(f"[{label}] PASS: PNG is 100% bit-exact lossless!")


def test_gradient_rotation_smoothness():
    print("\n=== TEST 4: Gradient Angle Rotation Smoothness ===")
    c1 = (255, 0, 0)
    c2 = (0, 0, 255)
    w, h = 300, 375  # Moderate size for fast multi-angle analysis

    # Test rotation across full 360 degrees in 1-degree steps
    angles = np.arange(0.0, 360.0, 1.0)
    conventions = ["cartesian", "css"]

    for conv in conventions:
        print(f"\n--- Testing convention: {conv} ---")
        prev_img = None
        prev_angle = None
        max_jump = 0.0
        max_jump_angle = None
        jump_events = []

        for angle in angles:
            img = generate_linear_gradient(width=w, height=h, color1=c1, color2=c2, angle=angle, convention=conv)
            arr = np.array(img, dtype=np.float32)

            if prev_img is not None:
                # Calculate Root Mean Squared Error (RMSE) between angle-1 and angle
                mse = np.mean((arr - prev_img) ** 2)
                rmse = math.sqrt(mse)
                if rmse > 15.0:  # A jump threshold
                    jump_events.append((prev_angle, angle, rmse))
                if rmse > max_jump:
                    max_jump = rmse
                    max_jump_angle = (prev_angle, angle)

            prev_img = arr
            prev_angle = angle

        print(f"Convention '{conv}': Max RMSE jump = {max_jump:.2f} at angles {max_jump_angle}")
        if jump_events:
            print(f"Detected {len(jump_events)} visual jump events (RMSE > 15.0):")
            for a1, a2, err in jump_events:
                print(f"  Jump between {a1:.1f}° and {a2:.1f}°: RMSE = {err:.2f}")
        else:
            print("  Smooth continuous rotation! No jumps detected.")

def test_async_export():
    print("\n=== TEST 5: Asynchronous Export & Concurrency Lock ===")
    sample_img_path = REPO_ROOT / "sample_outputs_m1" / "action_poster_4_5.jpg"
    raw_image = Image.open(sample_img_path)
    engine = ExportEngine()
    tmpdir = Path(tempfile.mkdtemp(prefix="async_export_"))
    out_path = tmpdir / "async_poster.jpg"
    cfg = PosterConfig(ratio="4:5", hd=False)

    import threading
    done_event = threading.Event()
    progress_calls = []
    success_calls = []
    error_calls = []

    def on_progress(msg):
        progress_calls.append(msg)

    def on_success(path, fsize):
        success_calls.append((path, fsize))
        done_event.set()

    def on_error(err):
        error_calls.append(err)
        done_event.set()

    engine.export_async(
        raw_image=raw_image,
        config=cfg,
        output_path=out_path,
        format="JPEG",
        on_progress=on_progress,
        on_success=on_success,
        on_error=on_error
    )

    # Immediately try to launch another export to test concurrency lock
    concurrency_error = []
    def on_err2(err):
        concurrency_error.append(err)

    engine.export_async(
        raw_image=raw_image,
        config=cfg,
        output_path=tmpdir / "async_second.jpg",
        on_error=on_err2
    )

    # Wait for completion
    completed = done_event.wait(timeout=10.0)
    print(f"Async export completed within timeout: {completed}")
    print(f"Progress messages logged: {progress_calls}")
    print(f"Success callback called: {len(success_calls) == 1} (File: {out_path.exists()}, Size: {out_path.stat().st_size if out_path.exists() else 0})")
    print(f"Concurrency lock rejected duplicate export: {len(concurrency_error) == 1} (Error: {concurrency_error[0] if concurrency_error else None})")
    assert completed, "Async export timed out"
    assert len(success_calls) == 1, "Success callback was not called exactly once"
    assert len(concurrency_error) == 1, "Concurrency lock failed to reject duplicate async task"


def test_exif_propagation():
    print("\n=== TEST 6: EXIF Metadata Propagation ===")
    from PIL import ExifTags
    # Create an image with known EXIF tags
    img = Image.new("RGB", (600, 800), color=(100, 150, 200))
    exif = img.getexif()
    # 0x010E is ImageDescription, 0x0131 is Software, 0x013B is Artist
    exif[0x010E] = "Test Game Poster Input"
    exif[0x0131] = "Milestone3 Test Harness"
    exif[0x013B] = "Challenger2"

    tmpdir = Path(tempfile.mkdtemp(prefix="exif_test_"))
    in_with_exif = tmpdir / "input_with_exif.jpg"
    img.save(in_with_exif, "JPEG", exif=exif)

    # Verify input has EXIF
    with Image.open(in_with_exif) as check_in:
        in_exif = dict(check_in.getexif())
        print(f"Input image EXIF tags count: {len(in_exif)}")
        print(f"  Artist tag (0x013B): {in_exif.get(0x013B)}")

    # Process and export via ExportEngine
    engine = ExportEngine()
    out_jpeg = tmpdir / "exported_from_exif_input.jpg"
    cfg = PosterConfig(ratio="4:5", hd=False)
    with Image.open(in_with_exif) as raw_in:
        engine.export_sync(raw_in, cfg, out_jpeg, format="JPEG")

    with Image.open(out_jpeg) as check_out:
        out_exif = dict(check_out.getexif())
        print(f"Exported JPEG EXIF tags count: {len(out_exif)}")
        print(f"Exported JPEG EXIF dict: {out_exif}")
        if len(out_exif) == 0:
            print("  OBSERVATION: Exported JPEG contains NO EXIF metadata (EXIF tags are stripped/omitted).")
        else:
            print("  OBSERVATION: Exported JPEG contains EXIF metadata.")


def test_launcher_execution():
    print("\n=== TEST 7: Launcher Execution (run_gui.bat) ===")
    import subprocess
    launcher_path = REPO_ROOT / "run_gui.bat"
    assert launcher_path.is_file(), f"run_gui.bat not found at {launcher_path}"

    # 1. Test --help
    print("Testing 'run_gui.bat --help'...")
    res_help = subprocess.run(
        ["cmd.exe", "/c", str(launcher_path), "--help"],
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=15
    )
    print(f"  Exit code: {res_help.returncode}")
    print(f"  Stdout length: {len(res_help.stdout)} chars")
    has_usage = "usage:" in res_help.stdout.lower()
    has_help_flag = "--help" in res_help.stdout
    print(f"  Contains usage: {has_usage}")
    print(f"  Contains --help: {has_help_flag}")
    assert res_help.returncode == 0, f"run_gui.bat --help returned non-zero exit code: {res_help.returncode}"
    assert has_usage, "run_gui.bat --help did not output usage instructions"

    # 2. Test invalid flag error handling (with piped <nul to avoid pause hang)
    print("\nTesting 'run_gui.bat --invalid-arg-for-testing'...")
    # Note: Using <nul or empty input
    cmd_err = f'cmd.exe /c "<nul \"{launcher_path}\" --invalid-arg-for-testing"'
    res_err = subprocess.run(
        cmd_err,
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
        timeout=15
    )
    print(f"  Exit code: {res_err.returncode}")
    print(f"  Stdout captured: {res_err.stdout.strip()[-300:] if len(res_err.stdout) > 300 else res_err.stdout}")
    has_err_banner = "[ERROR]" in res_err.stdout
    print(f"  Error banner detected: {has_err_banner}")
    assert res_err.returncode != 0, "run_gui.bat should return non-zero on unrecognized arguments"


def test_all_aspect_ratios_export():
    print("\n=== TEST 8: All Supported Aspect Ratios Export ===")
    sample_img_path = REPO_ROOT / "sample_outputs_m1" / "action_poster_4_5.jpg"
    raw_image = Image.open(sample_img_path)
    engine = ExportEngine()
    tmpdir = Path(tempfile.mkdtemp(prefix="aspect_test_"))

    ratios = [
        ("4:5", False, (1080, 1350)),
        ("4:5", True, (1440, 1800)),
        ("1:1", False, (1200, 1200)),
        ("1:1", True, (1600, 1600)),
        ("9:16", False, (1080, 1920)),
        ("9:16", True, (1440, 2560)),
        ("16:9", False, (1920, 1080)),
        ("16:9", True, (2560, 1440)),
        ("4:3", False, (1440, 1080)),
        ("4:3", True, (1920, 1440)),
        ("21:9", False, (2560, 1080)),
        ("21:9", True, (3440, 1440)),
    ]

    for ratio, hd, expected_size in ratios:
        cfg = PosterConfig(ratio=ratio, hd=hd)
        out_jpg = tmpdir / f"test_{ratio.replace(':', '_')}_{'hd' if hd else 'std'}.jpg"
        saved_p, fsize = engine.export_sync(raw_image, cfg, out_jpg, format="JPEG")
        with Image.open(saved_p) as im:
            actual_size = im.size
        assert actual_size == expected_size, f"Ratio {ratio} (HD={hd}): expected {expected_size}, got {actual_size}"
        print(f"  Ratio {ratio:5s} (HD={str(hd):5s}) -> {actual_size} (matches {expected_size}) - {fsize:,} bytes")


if __name__ == "__main__":
    test_export_dimensions_and_formats()
    test_jpeg_quality_and_quantization()
    test_png_lossless()
    test_gradient_rotation_smoothness()
    test_async_export()
    test_exif_propagation()
    test_launcher_execution()
    test_all_aspect_ratios_export()

