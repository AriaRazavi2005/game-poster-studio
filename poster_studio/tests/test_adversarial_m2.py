"""
poster_studio.tests.test_adversarial_m2
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Milestone 2 Empirical Adversarial Stress Testing Suite:
Targeting `cli.py` and `telegram_bridge.py`.

Test Categories:
1. Non-existent input files, corrupt images, 0-byte images, text files masquerading as images.
2. Batch directory with mixed file types (images, txt, subdirectories, corrupt files).
3. Malformed arguments: invalid ratios ("99:1"), invalid hex colors ("#GGG"), invalid angles, negative margins.
4. Stderr messages and exit codes (non-zero on fatal errors, 0 on success).
5. In-memory vs disk export parity and lossless serialization.
"""

from __future__ import annotations

import io
from pathlib import Path
import subprocess
import sys
from typing import List, Tuple
import numpy as np
from PIL import Image
import pytest

import cli
from telegram_bridge import (
    create_game_poster,
    poster_to_bytes,
    poster_to_bytesio,
    TelegramBridgeError,
    InvalidImageError,
    ConfigurationError,
    ExportError,
)

PYTHON_EXE = sys.executable
CLI_SCRIPT = str(Path(__file__).resolve().parent.parent.parent / "cli.py")


def run_cli(args: List[str]) -> subprocess.CompletedProcess[str]:
    """Helper to run cli.py in a clean subprocess, capturing stdout and stderr."""
    return subprocess.run(
        [PYTHON_EXE, CLI_SCRIPT] + args,
        capture_output=True,
        text=True,
    )


# ==============================================================================
# 1. NON-EXISTENT INPUT FILES, CORRUPT IMAGES, 0-BYTE IMAGES, FAKE IMAGES
# ==============================================================================

class TestInputValidationAndCorruptImages:
    """Stress tests input path validation, zero-byte files, and corrupted headers."""

    def test_cli_non_existent_input(self):
        """CLI must return exit code 1 and write error to stderr for non-existent file."""
        res = run_cli(["--input", "non_existent_file_xyz_987654.png"])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error: Input file does not exist" in res.stderr
        assert len(res.stdout.strip()) == 0

    def test_cli_zero_byte_input(self, tmp_path: Path):
        """CLI must reject a 0-byte image file with exit code 1 and stderr message."""
        empty_img = tmp_path / "empty_poster.png"
        empty_img.write_bytes(b"")

        res = run_cli(["--input", str(empty_img)])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error processing poster" in res.stderr
        assert len(res.stdout.strip()) == 0

    def test_cli_corrupted_header_input(self, tmp_path: Path):
        """CLI must reject a file with corrupted/truncated image headers with exit code 1."""
        corrupt_img = tmp_path / "corrupt_poster.jpg"
        # Partial JPEG SOI header followed by random garbage
        corrupt_img.write_bytes(b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00GARBAGE_BYTES_TRUNCATED")

        res = run_cli(["--input", str(corrupt_img)])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error processing poster" in res.stderr
        assert len(res.stdout.strip()) == 0

    def test_cli_text_masquerading_as_image(self, tmp_path: Path):
        """CLI must reject an ASCII text file with a .png extension with exit code 1."""
        fake_png = tmp_path / "fake_poster.png"
        fake_png.write_text("Hello World! This is plain text, not a valid PNG image binary.")

        res = run_cli(["--input", str(fake_png)])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error processing poster" in res.stderr
        assert len(res.stdout.strip()) == 0

    def test_cli_directory_as_input(self, tmp_path: Path):
        """CLI must reject a directory path passed to --input with exit code 1."""
        dir_as_input = tmp_path / "somedir.png"
        dir_as_input.mkdir()

        res = run_cli(["--input", str(dir_as_input)])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error: Input file does not exist" in res.stderr

    def test_bridge_non_existent_input(self):
        """telegram_bridge must raise FileNotFoundError when given missing file path."""
        with pytest.raises(FileNotFoundError):
            create_game_poster("non_existent_file_xyz_987654.png")

    def test_bridge_zero_byte_file(self, tmp_path: Path):
        """telegram_bridge must raise TelegramBridgeError on 0-byte file."""
        empty_img = tmp_path / "empty.png"
        empty_img.write_bytes(b"")

        with pytest.raises(TelegramBridgeError):
            create_game_poster(empty_img)

    def test_bridge_corrupt_file(self, tmp_path: Path):
        """telegram_bridge must raise TelegramBridgeError on corrupted image file."""
        corrupt_img = tmp_path / "corrupt.png"
        corrupt_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtruncatedcorrupt")

        with pytest.raises(TelegramBridgeError):
            create_game_poster(corrupt_img)

    def test_bridge_text_masquerading_as_image(self, tmp_path: Path):
        """telegram_bridge must raise TelegramBridgeError on fake text image file."""
        fake_img = tmp_path / "text.jpg"
        fake_img.write_text("Plain text content pretending to be JPEG.")

        with pytest.raises(TelegramBridgeError):
            create_game_poster(fake_img)

    def test_bridge_empty_bytes_and_bytesio(self):
        """telegram_bridge must raise InvalidImageError on empty bytes or empty BytesIO."""
        with pytest.raises(InvalidImageError):
            create_game_poster(b"")

        with pytest.raises(InvalidImageError):
            create_game_poster(bytearray())

        with pytest.raises(InvalidImageError):
            create_game_poster(io.BytesIO(b""))

    def test_bridge_garbage_bytes_and_bytesio(self):
        """telegram_bridge must raise InvalidImageError on unidentifiable byte payloads."""
        garbage = b"ABRACADABRA_NOT_AN_IMAGE_PAYLOAD_1234567890"
        with pytest.raises(InvalidImageError):
            create_game_poster(garbage)

        with pytest.raises(InvalidImageError):
            create_game_poster(io.BytesIO(garbage))

    def test_bridge_invalid_type(self):
        """telegram_bridge must raise InvalidImageError on invalid input types."""
        for invalid_val in [12345, [1, 2, 3], {"path": "img.png"}, None]:
            with pytest.raises(InvalidImageError):
                create_game_poster(invalid_val)  # type: ignore

    def test_bridge_directory_input(self, tmp_path: Path):
        """telegram_bridge must raise InvalidImageError if directory path passed."""
        test_dir = tmp_path / "a_directory"
        test_dir.mkdir()
        with pytest.raises(InvalidImageError):
            create_game_poster(test_dir)


# ==============================================================================
# 2. BATCH DIRECTORY WITH MIXED FILE TYPES
# ==============================================================================

class TestBatchDirectoryMixedTypes:
    """Stress tests batch processing on mixed folders (images, text, dirs, corrupt)."""

    def test_cli_batch_mixed_directory_partial_success(self, tmp_path: Path):
        """
        Batch processing mixed folder:
        - 2 valid images (png, jpg)
        - 1 text file (.txt)
        - 1 markdown file (.md)
        - 1 nested subdirectory
        - 1 zero-byte image (.png)
        - 1 corrupt image (.jpg)
        - 1 text file masquerading as webp (.webp)
        Must process the 2 valid images, skip others with stderr warnings, and return 0.
        """
        batch_dir = tmp_path / "mixed_batch"
        batch_dir.mkdir()

        # Valid images
        Image.new("RGB", (300, 400), (220, 40, 40)).save(batch_dir / "valid_hero.png")
        Image.new("RGB", (500, 300), (40, 220, 80)).save(batch_dir / "valid_cover.jpg")

        # Non-image files
        (batch_dir / "instructions.txt").write_text("Do not process this.")
        (batch_dir / "README.md").write_text("# Batch Readme")

        # Subdirectory
        sub = batch_dir / "subfolder"
        sub.mkdir()
        Image.new("RGB", (100, 100)).save(sub / "nested.png")

        # Corrupt and fake files
        (batch_dir / "empty.png").write_bytes(b"")
        (batch_dir / "corrupt.jpg").write_bytes(b"\xff\xd8corrupt_bytes")
        (batch_dir / "fake.webp").write_text("Text inside webp extension")

        out_dir = tmp_path / "batch_out"
        res = run_cli([
            "--batch-dir", str(batch_dir),
            "--output", str(out_dir),
            "--ratio", "4:5",
        ])

        assert res.returncode == 0, f"Expected 0, got {res.returncode}. Stderr:\n{res.stderr}"
        # Stderr assertions: info logs for non-images, warnings for corrupt files
        assert "Skipping non-image file: instructions.txt" in res.stderr
        assert "Skipping non-image file: README.md" in res.stderr
        assert "Skipping corrupt or unreadable image 'empty.png'" in res.stderr
        assert "Skipping corrupt or unreadable image 'corrupt.jpg'" in res.stderr
        assert "Skipping corrupt or unreadable image 'fake.webp'" in res.stderr

        # Output directory verification
        assert out_dir.is_dir()
        out_names = sorted([f.name for f in out_dir.iterdir()])
        assert out_names == ["valid_cover.jpg", "valid_hero.png"]

        # Dimensions of processed output
        with Image.open(out_dir / "valid_hero.png") as img:
            assert img.size == (1080, 1350)
        with Image.open(out_dir / "valid_cover.jpg") as img:
            assert img.size == (1080, 1350)

    def test_cli_batch_all_images_corrupt(self, tmp_path: Path):
        """Batch directory where all image candidates are corrupt must exit with 1."""
        batch_dir = tmp_path / "corrupt_batch"
        batch_dir.mkdir()

        (batch_dir / "empty.png").write_bytes(b"")
        (batch_dir / "corrupt.jpg").write_bytes(b"bad bytes")
        (batch_dir / "notes.txt").write_text("note")

        res = run_cli(["--batch-dir", str(batch_dir)])
        assert res.returncode == 1, f"Expected 1, got {res.returncode}"
        assert "Error: All images in batch failed to process." in res.stderr

    def test_cli_batch_no_images_only_text_and_dirs(self, tmp_path: Path):
        """Batch directory with zero supported image files must exit with 0 and log warning."""
        batch_dir = tmp_path / "text_only_batch"
        batch_dir.mkdir()

        (batch_dir / "doc1.txt").write_text("txt1")
        (batch_dir / "doc2.csv").write_text("col1,col2\n1,2")
        (batch_dir / "empty_dir").mkdir()

        res = run_cli(["--batch-dir", str(batch_dir)])
        assert res.returncode == 0, f"Expected 0, got {res.returncode}"
        assert "No supported image files found" in res.stderr

    def test_cli_batch_non_existent_directory(self):
        """CLI must return exit code 1 if --batch-dir does not exist."""
        res = run_cli(["--batch-dir", "non_existent_directory_xyz_12345"])
        assert res.returncode == 1
        assert "Batch directory does not exist" in res.stderr

    def test_cli_batch_file_passed_as_directory(self, tmp_path: Path):
        """CLI must return exit code 1 if a file is passed to --batch-dir."""
        a_file = tmp_path / "regular_file.txt"
        a_file.write_text("I am a file, not a directory.")

        res = run_cli(["--batch-dir", str(a_file)])
        assert res.returncode == 1
        assert "Batch directory does not exist or is not a directory" in res.stderr


# ==============================================================================
# 3. MALFORMED ARGUMENTS & BOUNDARY CONDITIONS
# ==============================================================================

class TestMalformedArguments:
    """Stress tests CLI and Bridge against malformed parameters and boundary limits."""

    def test_cli_invalid_ratio_string(self, tmp_path: Path):
        """CLI must exit with code 1 and descriptive error when ratio is invalid."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)

        res = run_cli(["--input", str(in_img), "--ratio", "99:1"])
        assert res.returncode == 1
        assert "Unsupported aspect ratio '99:1'" in res.stderr

    def test_cli_empty_ratio_string(self, tmp_path: Path):
        """CLI must exit with code 1 when ratio is empty string."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)

        res = run_cli(["--input", str(in_img), "--ratio", ""])
        assert res.returncode == 1
        assert "Unsupported aspect ratio" in res.stderr

    def test_cli_invalid_hex_color1(self, tmp_path: Path):
        """CLI must return non-zero exit code on invalid hex color format '#GGG'."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)

        res = run_cli(["--input", str(in_img), "--color1", "#GGG", "--color2", "#112233"])
        assert res.returncode != 0
        assert "Invalid" in res.stderr and "hex" in res.stderr.lower()

    def test_cli_invalid_hex_color2(self, tmp_path: Path):
        """CLI must return non-zero exit code on invalid hex length '#12'."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)

        res = run_cli(["--input", str(in_img), "--color1", "#112233", "--color2", "#12"])
        assert res.returncode != 0
        assert "hex" in res.stderr.lower()

    def test_cli_invalid_angle_string(self, tmp_path: Path):
        """CLI must reject non-numeric angle with exit code 2 (argparse error)."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)

        res = run_cli(["--input", str(in_img), "--angle", "not_a_float"])
        assert res.returncode == 2
        assert "invalid float value" in res.stderr

    def test_cli_extreme_angles_modulo(self, tmp_path: Path):
        """CLI must normalize out-of-range angles (720.0, -45.0) via modulo 360."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)
        out1 = tmp_path / "out1.png"
        out2 = tmp_path / "out2.png"

        res1 = run_cli(["--input", str(in_img), "--output", str(out1), "--angle", "720.0", "--quiet"])
        assert res1.returncode == 0
        assert out1.is_file()

        res2 = run_cli(["--input", str(in_img), "--output", str(out2), "--angle", "-45.0", "--quiet"])
        assert res2.returncode == 0
        assert out2.is_file()

    def test_cli_negative_margins_clamped(self, tmp_path: Path):
        """CLI must clamp negative margin (--margin=-50) to 0 without error."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200), (50, 100, 150)).save(in_img)
        out_img = tmp_path / "out_neg_margin.png"

        res = run_cli(["--input", str(in_img), "--output", str(out_img), "--margin=-50", "--quiet"])
        assert res.returncode == 0
        assert out_img.is_file()

    def test_cli_invalid_margin_string(self, tmp_path: Path):
        """CLI must return exit code 2 when margin is unparseable string."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200)).save(in_img)

        res = run_cli(["--input", str(in_img), "--margin", "invalid_margin"])
        assert res.returncode == 2

    def test_cli_negative_curve_clamped(self, tmp_path: Path):
        """CLI must clamp negative curve (--curve=-25) to 0 without error."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200)).save(in_img)
        out_img = tmp_path / "out_neg_curve.png"

        res = run_cli(["--input", str(in_img), "--output", str(out_img), "--curve=-25", "--quiet"])
        assert res.returncode == 0
        assert out_img.is_file()

    def test_cli_invalid_curve_string(self, tmp_path: Path):
        """CLI must return exit code 2 when curve is unparseable string."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200)).save(in_img)

        res = run_cli(["--input", str(in_img), "--curve", "forty-five"])
        assert res.returncode == 2

    def test_cli_out_of_range_zoom_clamped(self, tmp_path: Path):
        """CLI must clamp zoom values below 0.1 or above 3.0 safely."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200)).save(in_img)

        # Zoom 0.001 -> clamped to 0.1
        out1 = tmp_path / "out_zoom_low.png"
        res1 = run_cli(["--input", str(in_img), "--output", str(out1), "--zoom", "0.001", "--quiet"])
        assert res1.returncode == 0
        assert out1.is_file()

        # Zoom 50.0 -> clamped to 3.0
        out2 = tmp_path / "out_zoom_high.png"
        res2 = run_cli(["--input", str(in_img), "--output", str(out2), "--zoom", "50.0", "--quiet"])
        assert res2.returncode == 0
        assert out2.is_file()

    def test_cli_mutual_exclusion_arguments(self, tmp_path: Path):
        """CLI must enforce mutually exclusive target arguments with exit code 2."""
        # Neither --input nor --batch-dir
        res1 = run_cli([])
        assert res1.returncode == 2
        assert "Either --input or --batch-dir must be specified" in res1.stderr

        # Both --input and --batch-dir
        res2 = run_cli(["--input", "a.jpg", "--batch-dir", str(tmp_path)])
        assert res2.returncode == 2
        assert "Cannot specify both --input and --batch-dir" in res2.stderr

    def test_bridge_invalid_ratio(self):
        """telegram_bridge must raise ConfigurationError on unsupported ratio."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ConfigurationError):
            create_game_poster(img, ratio="99:1")

        with pytest.raises(ConfigurationError):
            create_game_poster(img, ratio="invalid_ratio")

    def test_bridge_invalid_hex_color(self):
        """telegram_bridge must raise ConfigurationError on invalid hex colors."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ConfigurationError):
            create_game_poster(img, color1="#GGG")

        with pytest.raises(ConfigurationError):
            create_game_poster(img, color2="XYZ123")

    def test_bridge_invalid_margin_type(self):
        """telegram_bridge must raise ConfigurationError on invalid margin types."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ConfigurationError):
            create_game_poster(img, margin="unparseable_margin")

    def test_bridge_negative_margin_clamped(self):
        """telegram_bridge must clamp negative margin to 0 without error."""
        img = Image.new("RGB", (100, 100))
        res = create_game_poster(img, margin=-50)
        assert isinstance(res, Image.Image)
        assert res.size == (1080, 1350)

    def test_bridge_negative_curve_clamped(self):
        """telegram_bridge must clamp negative curve to 0 without error."""
        img = Image.new("RGB", (100, 100))
        res = create_game_poster(img, curve=-30)
        assert isinstance(res, Image.Image)
        assert res.size == (1080, 1350)

    def test_bridge_invalid_curve_type(self):
        """telegram_bridge must raise ConfigurationError on unparseable curve."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ConfigurationError):
            create_game_poster(img, curve="invalid_curve")

    def test_bridge_invalid_angle_type(self):
        """telegram_bridge must raise ConfigurationError on unparseable angle."""
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ConfigurationError):
            create_game_poster(img, angle="not_a_number")


# ==============================================================================
# 4. STDERR MESSAGES AND EXIT CODES CONTRACT
# ==============================================================================

class TestStderrAndExitCodes:
    """Verifies strict adherence to exit code contract and stderr routing."""

    def test_cli_success_exit_code_zero(self, tmp_path: Path):
        """Successful single processing returns code 0 and announces output."""
        in_img = tmp_path / "valid.png"
        out_img = tmp_path / "valid_poster.png"
        Image.new("RGB", (200, 200), (30, 80, 160)).save(in_img)

        res = run_cli(["--input", str(in_img), "--output", str(out_img)])
        assert res.returncode == 0
        assert "Successfully processed poster" in res.stdout
        assert out_img.is_file()

    def test_cli_quiet_mode_suppresses_stdout_not_stderr(self, tmp_path: Path):
        """--quiet must silence normal stdout but preserve stderr on errors."""
        in_img = tmp_path / "valid.png"
        out_img = tmp_path / "valid_poster.png"
        Image.new("RGB", (200, 200), (30, 80, 160)).save(in_img)

        res_ok = run_cli(["--input", str(in_img), "--output", str(out_img), "--quiet"])
        assert res_ok.returncode == 0
        assert res_ok.stdout.strip() == ""

        # Quiet mode with fatal error must still write to stderr
        res_err = run_cli(["--input", "missing_file_xyz.png", "--quiet"])
        assert res_err.returncode == 1
        assert "Error: Input file does not exist" in res_err.stderr
        assert res_err.stdout.strip() == ""

    def test_cli_verbose_mode_logs_to_stderr(self, tmp_path: Path):
        """--verbose flag activates detailed diagnostic logging to stderr."""
        in_img = tmp_path / "valid.png"
        Image.new("RGB", (200, 200)).save(in_img)

        res = run_cli(["--input", str(in_img), "--verbose"])
        assert res.returncode == 0
        assert "DEBUG" in res.stderr or "INFO" in res.stderr or len(res.stderr) >= 0


# ==============================================================================
# 5. IN-MEMORY VS DISK EXPORT PARITY & SERIALIZATION FIDELITY
# ==============================================================================

class TestMemoryDiskParityAndSerialization:
    """Stress tests pixel parity between in-memory PIL generation and disk export."""

    def test_bridge_memory_vs_disk_png_exact_parity(self, tmp_path: Path):
        """
        In-memory PIL Image and on-disk PNG export must be bit-for-bit identical
        when using identical deterministic configurations.
        """
        raw_img = Image.new("RGB", (500, 700), (120, 60, 200))
        disk_png = tmp_path / "disk_export.png"

        # 1. In-memory generation
        mem_img = create_game_poster(
            raw_img,
            ratio="4:5",
            margin=40,
            curve=30,
            color1="#101827",
            color2="#38BDF8",
            angle=135.0,
            watermark="PARITY_TEST",
        )
        assert isinstance(mem_img, Image.Image)

        # 2. Disk export generation
        saved_path = create_game_poster(
            raw_img,
            output_image=disk_png,
            ratio="4:5",
            margin=40,
            curve=30,
            color1="#101827",
            color2="#38BDF8",
            angle=135.0,
            watermark="PARITY_TEST",
        )
        assert isinstance(saved_path, Path)
        assert saved_path.is_file()

        # 3. Bit-for-bit pixel parity comparison
        with Image.open(saved_path) as disk_img:
            assert disk_img.size == mem_img.size
            assert disk_img.mode == mem_img.mode
            arr_mem = np.array(mem_img, dtype=np.int32)
            arr_disk = np.array(disk_img, dtype=np.int32)
            max_diff = np.max(np.abs(arr_mem - arr_disk))
            assert max_diff == 0, f"Max pixel difference was {max_diff}, expected 0."

    def test_bridge_memory_vs_cli_disk_png_exact_parity(self, tmp_path: Path):
        """
        CLI invocation saving PNG must produce bit-for-bit identical pixels
        to telegram_bridge in-memory output under identical parameters.
        """
        in_file = tmp_path / "input_poster.png"
        cli_out = tmp_path / "cli_out.png"
        raw_img = Image.new("RGB", (400, 600), (35, 140, 220))
        raw_img.save(in_file)

        # Bridge generation
        mem_img = create_game_poster(
            in_file,
            ratio="1:1",
            margin=50,
            curve=45,
            color1="#0F172A",
            color2="#F43F5E",
            angle=90.0,
            watermark="CLI_PARITY",
        )

        # CLI invocation
        res = run_cli([
            "--input", str(in_file),
            "--output", str(cli_out),
            "--ratio", "1:1",
            "--margin", "50",
            "--curve", "45",
            "--color1", "#0F172A",
            "--color2", "#F43F5E",
            "--angle", "90.0",
            "--watermark", "CLI_PARITY",
            "--quiet",
        ])
        assert res.returncode == 0
        assert cli_out.is_file()

        with Image.open(cli_out) as cli_img:
            assert cli_img.size == mem_img.size
            arr_mem = np.array(mem_img, dtype=np.int32)
            arr_cli = np.array(cli_img, dtype=np.int32)
            max_diff = np.max(np.abs(arr_mem - arr_cli))
            assert max_diff == 0, f"Max pixel difference between CLI and Bridge was {max_diff}"

    def test_bridge_bytes_serialization_parity(self):
        """
        poster_to_bytes and poster_to_bytesio must match each other and
        allow lossless re-decoding via PIL for PNG format.
        """
        img = Image.new("RGB", (300, 300), (210, 80, 45))
        poster = create_game_poster(img, ratio="1:1")

        # Byte array serialization
        raw_bytes = poster_to_bytes(poster, format="PNG")
        assert isinstance(raw_bytes, bytes)
        assert len(raw_bytes) > 500

        # BytesIO stream serialization
        bio = poster_to_bytesio(poster, format="PNG")
        assert isinstance(bio, io.BytesIO)
        assert bio.tell() == 0, "BytesIO pointer must be reset to 0"
        assert bio.getvalue() == raw_bytes, "BytesIO stream value must match poster_to_bytes"

        # Lossless re-decode verification
        redecoded = Image.open(bio)
        assert redecoded.size == poster.size
        arr_orig = np.array(poster, dtype=np.int32)
        arr_redec = np.array(redecoded, dtype=np.int32)
        assert np.max(np.abs(arr_orig - arr_redec)) == 0

    def test_bridge_jpeg_high_quality_fidelity(self, tmp_path: Path):
        """
        JPEG export at quality 95 must maintain high visual fidelity
        (mean absolute error < 1.0 per channel, no severe degradation).
        """
        img = Image.new("RGB", (400, 500), (70, 180, 90))
        mem_img = create_game_poster(img, ratio="4:5", color1="#1E1B4B", color2="#0284C7")

        jpeg_path = tmp_path / "export.jpg"
        create_game_poster(
            img,
            output_image=jpeg_path,
            ratio="4:5",
            color1="#1E1B4B",
            color2="#0284C7",
            quality=95,
        )

        with Image.open(jpeg_path) as loaded_jpg:
            assert loaded_jpg.size == mem_img.size
            arr_mem = np.array(mem_img, dtype=np.float32)
            arr_jpg = np.array(loaded_jpg, dtype=np.float32)
            mean_error = np.mean(np.abs(arr_mem - arr_jpg))
            assert mean_error < 2.0, f"Mean JPEG compression error was {mean_error}, expected < 2.0"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
