"""
poster_studio.tests.test_gui_model
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Headless test suite for PosterStudioModel, PreviewEngine, and ExportEngine.
Validates state synchronization, parameter mutations, palette caching,
fast preview rendering performance, and high-resolution disk export.
Zero display server or X11/Win32 desktop session required.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import time
import pytest
from PIL import Image

from poster_studio.core.geometry import ASPECT_RATIOS, resolve_canvas_size
from poster_studio.gui.main_window import PosterStudioModel
from poster_studio.gui.preview_engine import calculate_preview_dimensions


def _create_synthetic_test_image(width: int = 1200, height: int = 1600) -> Image.Image:
    """Generates a synthetic dual-tone image for testing."""
    img = Image.new("RGB", (width, height), (30, 60, 180))
    # Add contrasting rectangle
    rect = Image.new("RGB", (width // 2, height // 2), (220, 80, 40))
    img.paste(rect, (width // 4, height // 4))
    return img


class TestPosterStudioModel:
    """Test suite covering PosterStudioModel headless behavior."""

    def test_model_default_state(self) -> None:
        """Verifies default model configuration matches Collage Maker layout."""
        model = PosterStudioModel()

        assert model.config.ratio == "4:5"
        assert model.config.curve == 45
        assert model.config.margin == 50
        assert model.config.angle == 135.0
        assert model.config.auto_colors is True
        assert model.config.drop_shadow is True
        assert model.config.watermark == "BAZYEPC"
        assert model.config.zoom == 1.0
        assert model.raw_image is None
        assert model.source_path is None

    def test_model_image_loading_and_palette_extraction(self) -> None:
        """Verifies image loading, thumbnail generation, and dominant color extraction."""
        model = PosterStudioModel()
        synth = _create_synthetic_test_image(1200, 1600)

        model.load_image(synth)

        assert model.raw_image is not None
        assert model.raw_image.size == (1200, 1600)

        # Working preview image should be scaled down to max dim <= 800
        assert model.preview_engine.preview_raw_image is not None
        assert max(model.preview_engine.preview_raw_image.size) <= 800

        # Dominant palette should be auto-extracted
        assert model.active_palette is not None
        assert len(model.active_palette) == 2
        assert model.config.color1 == model.active_palette[0]
        assert model.config.color2 == model.active_palette[1]

    def test_model_invalid_image_handling(self, tmp_path: Path) -> None:
        """Verifies robust error handling on missing, empty, or corrupted files."""
        model = PosterStudioModel()

        # Non-existent file
        with pytest.raises(FileNotFoundError):
            model.load_image(tmp_path / "non_existent.jpg")

        # Empty file (0 bytes)
        empty_file = tmp_path / "empty.jpg"
        empty_file.write_bytes(b"")
        with pytest.raises(ValueError):
            model.load_image(empty_file)

        # Corrupted file
        corrupt_file = tmp_path / "corrupt.jpg"
        corrupt_file.write_bytes(b"NOT_A_VALID_IMAGE_FILE_DATA_CORRUPTION")
        with pytest.raises(ValueError):
            model.load_image(corrupt_file)

    def test_model_parameter_mutations_and_observer(self) -> None:
        """Verifies state mutations and observer callback dispatch."""
        model = PosterStudioModel()
        notifications: list[int] = []

        def _on_changed() -> None:
            notifications.append(len(notifications) + 1)

        model.subscribe(_on_changed)

        model.set_spacing(75)
        assert model.config.margin == 75
        assert len(notifications) == 1

        model.set_curve(60)
        assert model.config.curve == 60
        assert len(notifications) == 2

        model.set_zoom(1.35)
        assert model.config.zoom == 1.35
        assert len(notifications) == 3

        model.set_angle(270.0)
        assert model.config.angle == 270.0
        assert len(notifications) == 4

        model.set_drop_shadow(False)
        assert model.config.drop_shadow is False
        assert len(notifications) == 5

        model.set_watermark("CUSTOM_BRAND", size=36)
        assert model.config.watermark == "CUSTOM_BRAND"
        assert model.config.watermark_size == 36
        assert len(notifications) == 6

        model.unsubscribe(_on_changed)
        model.set_spacing(40)
        assert len(notifications) == 6  # Unsubscribed, no extra notification

    def test_model_color_swap_and_overrides(self) -> None:
        """Verifies custom color assignment and swap operation."""
        model = PosterStudioModel()
        model.set_color1("#FF0000")
        model.set_color2("#0000FF")

        assert model.config.color1 == (255, 0, 0)
        assert model.config.color2 == (0, 0, 255)
        assert model.config.auto_colors is False

        model.swap_colors()
        assert model.config.color1 == (0, 0, 255)
        assert model.config.color2 == (255, 0, 0)

    def test_model_aspect_ratio_selection(self) -> None:
        """Verifies all supported aspect ratios update configuration and dimensions."""
        model = PosterStudioModel()

        for ratio in ["4:5", "1:1", "9:16", "16:9", "4:3", "21:9"]:
            model.set_ratio(ratio)
            assert model.config.ratio == ratio
            expected_w, expected_h = resolve_canvas_size(ratio)
            assert (expected_w, expected_h) == ASPECT_RATIOS[ratio]

        # HD Mode
        model.set_hd(True)
        assert model.config.hd is True
        hd_w, hd_h = resolve_canvas_size("4:5", hd=True)
        assert (hd_w, hd_h) == (1440, 1800)

    def test_model_preview_generation_performance(self) -> None:
        """
        Verifies preview generation executes in < 50ms on CPU,
        delivering fast 60fps slider responsiveness.
        """
        model = PosterStudioModel()
        synth = _create_synthetic_test_image(800, 1000)
        model.load_image(synth)

        # Warmup
        _ = model.generate_preview_image((600, 750))

        # Benchmark 5 iterations
        times: list[float] = []
        for _ in range(5):
            t0 = time.perf_counter()
            preview = model.generate_preview_image((600, 750))
            times.append(time.perf_counter() - t0)

        mean_ms = (sum(times) / len(times)) * 1000.0

        assert isinstance(preview, Image.Image)
        assert preview.mode == "RGB"
        assert preview.width <= 640
        assert preview.height <= 750
        assert mean_ms < 50.0, f"Preview generation took {mean_ms:.2f}ms (expected < 50ms)"

    def test_model_high_res_export(self, tmp_path: Path) -> None:
        """Verifies full-resolution poster export to JPEG and PNG."""
        model = PosterStudioModel()
        synth = _create_synthetic_test_image(800, 1000)
        model.load_image(synth)

        # 1. Export JPEG (quality=95)
        jpg_out = tmp_path / "test_export.jpg"
        saved_path, file_size = model.export_poster(jpg_out, format="JPEG", quality=95)

        assert saved_path == jpg_out
        assert jpg_out.is_file()
        assert file_size > 20000

        with Image.open(jpg_out) as exported_jpg:
            assert exported_jpg.format == "JPEG"
            assert exported_jpg.size == (1080, 1350)

        # 2. Export PNG
        png_out = tmp_path / "test_export.png"
        saved_png, png_size = model.export_poster(png_out, format="PNG")

        assert saved_png == png_out
        assert png_out.is_file()
        assert png_size > 20000

        with Image.open(png_out) as exported_png:
            assert exported_png.format == "PNG"
            assert exported_png.size == (1080, 1350)

    def test_model_reset(self) -> None:
        """Verifies reset_config restores default parameters."""
        model = PosterStudioModel()
        model.set_spacing(120)
        model.set_curve(90)
        model.set_zoom(1.8)
        model.set_ratio("9:16")
        model.set_angle(45.0)

        model.reset_config()

        assert model.config.margin == 50
        assert model.config.curve == 45
        assert model.config.zoom == 1.0
        assert model.config.ratio == "4:5"
        assert model.config.angle == 135.0

    def test_preview_scaling_math(self) -> None:
        """Verifies calculate_preview_dimensions preserves aspect ratio."""
        for ratio, (full_w, full_h) in ASPECT_RATIOS.items():
            prev_w, prev_h, S = calculate_preview_dimensions(
                full_canvas_size=(full_w, full_h),
                viewport_max_size=(640, 750)
            )

            assert prev_w <= 640
            assert prev_h <= 750
            full_aspect = full_w / full_h
            prev_aspect = prev_w / prev_h
            assert abs(full_aspect - prev_aspect) < 0.05
            assert S > 0.0
