#!/usr/bin/env python3
"""
Empirical Adversarial Verification Suite for Milestone 3 Remediation.
Author: challenger_m3_3

Focus areas:
1. Gradient Smoothness & Vector Sign Flips (360° sweep at 1.0° and 0.1° around 135°).
2. EXIF Metadata Preservation & Injection via ExportEngine.
3. Edge case stress testing (extreme angles, dynamic range, canvas sizes).
"""

import math
import sys
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image, ExifTags

REPO_ROOT = Path(__file__).resolve().parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.gui.export_engine import ExportEngine
from poster_studio.core.processor import PosterConfig, process_poster


def benchmark_gradient_continuous_360():
    print("======================================================================")
    print("STEP 1A: 360° Rotation Sweep at 1.0° Step (Cartesian & CSS)")
    print("======================================================================")

    # Standard Challenger 2 benchmark colors: (255, 0, 0) to (0, 0, 255)
    c1 = (255, 0, 0)
    c2 = (0, 0, 255)
    w, h = 300, 375

    angles = np.arange(0.0, 360.0, 1.0)
    conventions = ["cartesian", "css"]

    results = {}
    for conv in conventions:
        print(f"\n[Testing Convention: {conv.upper()}] (Canvas: {w}x{h}, Benchmark Colors: {c1}->{c2})")
        max_rmse = 0.0
        max_pair = (None, None)
        all_rmses = []
        visual_jumps = []
        vector_flips = []

        prev_img = None
        prev_angle = None
        prev_u = None

        for angle in angles:
            img = generate_linear_gradient(w, h, c1, c2, angle=angle, convention=conv)
            arr = np.array(img, dtype=np.float32)

            rad = math.radians(angle % 360.0)
            if conv == "cartesian":
                ux, uy = math.cos(rad), math.sin(rad)
            else:
                ux, uy = math.sin(rad), -math.cos(rad)
            curr_u = (ux, uy)

            if prev_img is not None:
                mse = np.mean((arr - prev_img) ** 2)
                rmse = math.sqrt(mse)
                all_rmses.append(rmse)

                if rmse > max_rmse:
                    max_rmse = rmse
                    max_pair = (prev_angle, angle)

                if rmse > 2.0:
                    visual_jumps.append((prev_angle, angle, rmse))

                # Check vector continuity: dot product must be > 0 (strictly positive, ~cos(1 deg) = 0.9998)
                dot = prev_u[0] * curr_u[0] + prev_u[1] * curr_u[1]
                if dot < 0.95:  # sudden deviation or sign flip
                    vector_flips.append((prev_angle, angle, dot))

            prev_img = arr
            prev_angle = angle
            prev_u = curr_u

        # Wrap-around check: 359° -> 0°
        img_0 = generate_linear_gradient(w, h, c1, c2, angle=0.0, convention=conv)
        arr_0 = np.array(img_0, dtype=np.float32)
        mse_wrap = np.mean((arr_0 - prev_img) ** 2)
        rmse_wrap = math.sqrt(mse_wrap)
        if rmse_wrap > max_rmse:
            max_rmse = rmse_wrap
            max_pair = (359.0, 0.0)

        mean_rmse = np.mean(all_rmses)
        print(f"  Max Step RMSE: {max_rmse:.4f} between angles {max_pair}")
        print(f"  Mean Step RMSE: {mean_rmse:.4f}")
        print(f"  Step RMSE <= 2.0 Everywhere: {'PASS' if max_rmse <= 2.0 else 'FAIL'}")
        print(f"  Visual Jumps (RMSE > 2.0): {len(visual_jumps)}")
        print(f"  Vector Sign Flips: {len(vector_flips)}")

        assert max_rmse <= 2.0, f"Max RMSE {max_rmse:.4f} exceeded threshold 2.0 for {conv}"
        assert len(visual_jumps) == 0, f"Visual jumps detected in {conv}: {visual_jumps}"
        assert len(vector_flips) == 0, f"Vector sign flips detected in {conv}: {vector_flips}"

        results[conv] = {
            "max_rmse": max_rmse,
            "max_pair": max_pair,
            "mean_rmse": mean_rmse,
            "visual_jumps": len(visual_jumps),
            "vector_flips": len(vector_flips),
        }

    return results


def benchmark_gradient_fine_sweep_135():
    print("\n======================================================================")
    print("STEP 1B: Fine-grained Rotation Sweep at 0.1° and 0.01° Around 135°")
    print("======================================================================")

    c1 = (255, 0, 0)
    c2 = (0, 0, 255)
    w, h = 300, 375

    # Sweep from 130.0° to 140.0° at 0.1° intervals
    fine_angles = [round(float(x), 2) for x in np.arange(130.0, 140.01, 0.1)]
    print(f"Testing {len(fine_angles)} angles in [130.0°, 140.0°] with 0.1° step...")

    for conv in ["cartesian", "css"]:
        prev_img = None
        prev_angle = None
        max_rmse = 0.0
        max_pair = (None, None)
        jumps = []
        sign_flips = []

        for angle in fine_angles:
            img = generate_linear_gradient(w, h, c1, c2, angle=angle, convention=conv)
            arr = np.array(img, dtype=np.float32)

            rad = math.radians(angle % 360.0)
            if conv == "cartesian":
                ux, uy = math.cos(rad), math.sin(rad)
            else:
                ux, uy = math.sin(rad), -math.cos(rad)

            if prev_img is not None:
                rmse = math.sqrt(np.mean((arr - prev_img) ** 2))
                if rmse > max_rmse:
                    max_rmse = rmse
                    max_pair = (prev_angle, angle)
                if rmse > 2.0:
                    jumps.append((prev_angle, angle, rmse))

                # Check vector continuity
                prev_rad = math.radians(prev_angle % 360.0)
                if conv == "cartesian":
                    pux, puy = math.cos(prev_rad), math.sin(prev_rad)
                else:
                    pux, puy = math.sin(prev_rad), -math.cos(prev_rad)
                dot = pux * ux + puy * uy
                if dot < 0.999:
                    sign_flips.append((prev_angle, angle, dot))

            prev_img = arr
            prev_angle = angle

        print(f"Convention '{conv}' (0.1° step around 135°):")
        print(f"  Max Step RMSE: {max_rmse:.4f} between {max_pair}")
        print(f"  RMSE <= 2.0 Everywhere: {'PASS' if max_rmse <= 2.0 else 'FAIL'}")
        print(f"  Visual Jumps (> 2.0): {len(jumps)}")
        print(f"  Vector Sign Flips: {len(sign_flips)}")
        assert max_rmse <= 2.0, f"Fine sweep RMSE {max_rmse} > 2.0"
        assert len(jumps) == 0
        assert len(sign_flips) == 0

    # Ultra-fine test around 134.90 -> 135.10 at 0.01° steps
    print("\nTesting ultra-fine 0.01° steps across 134.90° -> 135.10°...")
    uf_angles = np.linspace(134.90, 135.10, 21)
    for conv in ["cartesian", "css"]:
        prev_img = None
        max_uf_rmse = 0.0
        for angle in uf_angles:
            img = generate_linear_gradient(w, h, c1, c2, angle=angle, convention=conv)
            arr = np.array(img, dtype=np.float32)
            if prev_img is not None:
                rmse = math.sqrt(np.mean((arr - prev_img) ** 2))
                if rmse > max_uf_rmse:
                    max_uf_rmse = rmse
            prev_img = arr
        print(f"Convention '{conv}' (0.01° step): Max RMSE = {max_uf_rmse:.5f} (PASS)")
        assert max_uf_rmse < 0.1, f"Expected < 0.1 for 0.01° step, got {max_uf_rmse}"


def verify_exif_preservation_and_injection():
    print("\n======================================================================")
    print("STEP 2: EXIF Metadata Preservation & Injection Verification")
    print("======================================================================")

    tmpdir = Path(tempfile.mkdtemp(prefix="challenger_exif_test_"))
    engine = ExportEngine()

    # ---------------------------------------------------------
    # Scenario A: Input image with rich EXIF tags
    # ---------------------------------------------------------
    print("\n--- Scenario A: Input image with comprehensive EXIF tags ---")
    in_img_a = Image.new("RGB", (720, 900), color=(50, 120, 200))
    exif_a = in_img_a.getexif()

    # Populate standard tags
    exif_a[0x010E] = "Challenger 3 Adversarial Test Image"  # ImageDescription
    exif_a[0x013B] = "BazyePc Master Artist"                # Artist
    exif_a[0x8298] = "Copyright 2026 BazyePc Studio"       # Copyright
    exif_a[0x0132] = "2026:09:21 12:00:00"                 # DateTime
    exif_a[0x010F] = "Nikon Corporation"                   # Make
    exif_a[0x0110] = "NIKON Z 9"                           # Model

    in_path_a = tmpdir / "input_with_rich_exif.jpg"
    in_img_a.save(in_path_a, "JPEG", exif=exif_a)

    # Export via ExportEngine.export_sync
    out_path_a = tmpdir / "exported_a.jpg"
    cfg_a = PosterConfig(ratio="4:5", hd=False)

    with Image.open(in_path_a) as loaded_in:
        saved_path_a, fsize_a = engine.export_sync(loaded_in, cfg_a, out_path_a, format="JPEG")

    with Image.open(saved_path_a) as check_a:
        exif_out_a = dict(check_a.getexif())
        w_a, h_a = check_a.size

    print(f"Exported Image Size: {w_a}x{h_a}")
    print(f"Exported EXIF Tag Count: {len(exif_out_a)}")

    # Verify injected studio metadata
    software = exif_out_a.get(0x0131)
    img_w = exif_out_a.get(0x0100)
    img_h = exif_out_a.get(0x0101)
    exif_w = exif_out_a.get(0xA002)
    exif_h = exif_out_a.get(0xA003)

    print(f"  Software (0x0131): {software!r} -> {'PASS' if software == 'Game Poster Studio' else 'FAIL'}")
    print(f"  ImageWidth (0x0100): {img_w} (Expected {w_a}) -> {'PASS' if img_w == w_a else 'FAIL'}")
    print(f"  ImageLength (0x0101): {img_h} (Expected {h_a}) -> {'PASS' if img_h == h_a else 'FAIL'}")
    print(f"  ExifImageWidth (0xA002): {exif_w} (Expected {w_a}) -> {'PASS' if exif_w == w_a else 'FAIL'}")
    print(f"  ExifImageHeight (0xA003): {exif_h} (Expected {h_a}) -> {'PASS' if exif_h == h_a else 'FAIL'}")

    assert software == "Game Poster Studio", f"Software tag mismatch: {software}"
    assert img_w == w_a == 1080
    assert img_h == h_a == 1350
    assert exif_w == w_a == 1080
    assert exif_h == h_a == 1350

    # Verify preserved source tags
    desc = exif_out_a.get(0x010E)
    artist = exif_out_a.get(0x013B)
    copyright_tag = exif_out_a.get(0x8298)
    dt = exif_out_a.get(0x0132)
    make = exif_out_a.get(0x010F)
    model = exif_out_a.get(0x0110)

    print(f"  Preserved Artist (0x013B): {artist!r} -> {'PASS' if artist == 'BazyePc Master Artist' else 'FAIL'}")
    print(f"  Preserved Description (0x010E): {desc!r} -> {'PASS' if desc == 'Challenger 3 Adversarial Test Image' else 'FAIL'}")
    print(f"  Preserved Copyright (0x8298): {copyright_tag!r} -> {'PASS' if copyright_tag == 'Copyright 2026 BazyePc Studio' else 'FAIL'}")
    print(f"  Preserved DateTime (0x0132): {dt!r} -> {'PASS' if dt == '2026:09:21 12:00:00' else 'FAIL'}")
    print(f"  Preserved Make/Model: {make} / {model}")

    assert artist == "BazyePc Master Artist"
    assert desc == "Challenger 3 Adversarial Test Image"
    assert copyright_tag == "Copyright 2026 BazyePc Studio"
    assert dt == "2026:09:21 12:00:00"
    assert make == "Nikon Corporation"
    assert model == "NIKON Z 9"

    # ---------------------------------------------------------
    # Scenario B: Input image with ZERO EXIF tags
    # ---------------------------------------------------------
    print("\n--- Scenario B: Input image with NO EXIF metadata ---")
    in_img_b = Image.new("RGB", (500, 500), color=(10, 80, 150))
    in_path_b = tmpdir / "input_no_exif.png"
    in_img_b.save(in_path_b, "PNG")

    out_path_b = tmpdir / "exported_b.jpg"
    cfg_b = PosterConfig(ratio="1:1", hd=True)  # 1600x1600

    with Image.open(in_path_b) as loaded_b:
        saved_path_b, fsize_b = engine.export_sync(loaded_b, cfg_b, out_path_b, format="JPEG")

    with Image.open(saved_path_b) as check_b:
        exif_out_b = dict(check_b.getexif())
        w_b, h_b = check_b.size

    print(f"Exported Image Size: {w_b}x{h_b}")
    print(f"Exported EXIF Tag Count: {len(exif_out_b)}")
    print(f"Exported EXIF Tags: {exif_out_b}")
    assert check_b.size == (1600, 1600)
    assert exif_out_b.get(0x0131) == "Game Poster Studio"
    assert exif_out_b.get(0x0100) == 1600
    assert exif_out_b.get(0x0101) == 1600
    assert exif_out_b.get(0xA002) == 1600
    assert exif_out_b.get(0xA003) == 1600
    print("  PASS: Injected standard EXIF metadata even when source image had zero EXIF tags!")

    # ---------------------------------------------------------
    # Scenario C: Custom Canvas Size preservation with EXIF
    # ---------------------------------------------------------
    print("\n--- Scenario C: Custom Canvas Size & EXIF Consistency ---")
    custom_w, custom_h = 1000, 1200
    cfg_c = PosterConfig(custom_canvas_size=(custom_w, custom_h))
    out_path_c = tmpdir / "exported_custom.jpg"

    with Image.open(in_path_a) as loaded_c:
        saved_path_c, fsize_c = engine.export_sync(loaded_c, cfg_c, out_path_c, format="JPEG")

    with Image.open(saved_path_c) as check_c:
        exif_out_c = dict(check_c.getexif())
        w_c, h_c = check_c.size

    print(f"Custom Export Size: {w_c}x{h_c} (Expected {custom_w}x{custom_h})")
    assert (w_c, h_c) == (custom_w, custom_h)
    assert exif_out_c.get(0x0100) == custom_w
    assert exif_out_c.get(0x0101) == custom_h
    assert exif_out_c.get(0xA002) == custom_w
    assert exif_out_c.get(0xA003) == custom_h
    print("  PASS: Custom canvas size correctly reflected in both raster dimensions and EXIF tags!")


def test_stress_edge_cases():
    print("\n======================================================================")
    print("STEP 3: Adversarial Edge Case Stress Testing")
    print("======================================================================")

    # 1. Extreme angles: negative angles, large angles, boundary angles
    test_angles = [-720.0, -360.0, -135.0, -45.0, 0.0, 0.0001, 89.9999, 90.0, 134.9999, 135.0, 135.0001, 270.0, 359.9999, 360.0, 495.0, 1080.0]
    print(f"Testing extreme angles: {test_angles}...")
    for ang in test_angles:
        im_cart = generate_linear_gradient(64, 64, (255, 0, 0), (0, 255, 0), angle=ang, convention="cartesian")
        im_css = generate_linear_gradient(64, 64, (255, 0, 0), (0, 255, 0), angle=ang, convention="css")
        assert im_cart.size == (64, 64)
        assert im_css.size == (64, 64)
    print("  PASS: Extreme angles handled gracefully without numerical errors or crashes.")

    # 2. Canvas dimension extremes: 1x1 micro-canvas, 1x1000, 1000x1
    print("Testing micro-canvas dimensions...")
    im_1x1 = generate_linear_gradient(1, 1, (10, 20, 30), (40, 50, 60), angle=135.0)
    assert im_1x1.size == (1, 1)
    assert im_1x1.getpixel((0, 0)) == (10, 20, 30)

    im_1x100 = generate_linear_gradient(1, 100, (0, 0, 0), (255, 255, 255), angle=90.0)
    assert im_1x100.size == (1, 100)

    im_100x1 = generate_linear_gradient(100, 1, (0, 0, 0), (255, 255, 255), angle=0.0)
    assert im_100x1.size == (100, 1)
    print("  PASS: Micro-canvas and extreme aspect ratios handled correctly.")

    # 3. Identical colors
    print("Testing identical colors gradient...")
    im_same = generate_linear_gradient(50, 50, (128, 128, 128), (128, 128, 128), angle=135.0)
    arr_same = np.array(im_same)
    assert np.all(arr_same == 128)
    print("  PASS: Identical colors produce uniform field.")

    # 4. Multi-color palette comparisons
    print("Testing multiple color palettes for rotation smoothness...")
    palettes = [
        ("Default fallback palette", ((30, 27, 75), (2, 132, 199))),
        ("Warm complementary", ((255, 100, 0), (0, 150, 255))),
        ("Forest sunset", ((20, 80, 40), (240, 120, 20))),
    ]
    for pal_name, (col1, col2) in palettes:
        max_pal_rmse = 0.0
        for ang in range(0, 360, 5):
            i1 = np.array(generate_linear_gradient(100, 100, col1, col2, angle=float(ang)), dtype=np.float32)
            i2 = np.array(generate_linear_gradient(100, 100, col1, col2, angle=float(ang+1)), dtype=np.float32)
            rmse = math.sqrt(np.mean((i1 - i2) ** 2))
            if rmse > max_pal_rmse:
                max_pal_rmse = rmse
        print(f"  Palette '{pal_name}': Max 1.0° step RMSE = {max_pal_rmse:.4f} (<= 2.0: PASS)")
        assert max_pal_rmse <= 2.0


if __name__ == "__main__":
    print("**********************************************************************")
    print("CHALLENGER 3 EMPIRICAL TEST SUITE STARTING")
    print("**********************************************************************")
    benchmark_gradient_continuous_360()
    benchmark_gradient_fine_sweep_135()
    verify_exif_preservation_and_injection()
    test_stress_edge_cases()
    print("\n**********************************************************************")
    print("ALL EMPIRICAL TESTS PASSED SUCCESSFULLY!")
    print("**********************************************************************")
