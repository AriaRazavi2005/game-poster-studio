"""
Unit and Integration tests for telegram_bridge and cli modules.
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest
from PIL import Image

from telegram_bridge import (
    create_game_poster,
    poster_to_bytes,
    poster_to_bytesio,
    TelegramBridgeError,
    InvalidImageError,
    ConfigurationError,
)
import cli


def test_telegram_bridge_in_memory():
    img = Image.new("RGB", (800, 600), (255, 120, 40))
    res = create_game_poster(img, ratio="4:5", margin=40, curve=30)
    assert isinstance(res, Image.Image)
    assert res.size == (1080, 1350)
    assert res.mode == "RGB"


def test_telegram_bridge_bytes_and_bytesio():
    img = Image.new("RGB", (400, 300), (10, 80, 200))
    bio = io.BytesIO()
    img.save(bio, format="PNG")
    raw_bytes = bio.getvalue()

    # Bytes input
    res1 = create_game_poster(raw_bytes, ratio="1:1")
    assert isinstance(res1, Image.Image)
    assert res1.size == (1200, 1200)

    # BytesIO input
    res2 = create_game_poster(io.BytesIO(raw_bytes), ratio="1:1")
    assert isinstance(res2, Image.Image)
    assert res2.size == (1200, 1200)


def test_telegram_bridge_file_export(tmp_path: Path):
    img = Image.new("RGB", (600, 600), (50, 200, 50))
    out_file = tmp_path / "bridge_out.jpg"

    res_path = create_game_poster(img, output_image=out_file, ratio="16:9")
    assert isinstance(res_path, Path)
    assert res_path.is_file()
    assert res_path.stat().st_size > 500

    with Image.open(res_path) as loaded:
        assert loaded.size == (1920, 1080)


def test_telegram_bridge_aliases():
    img = Image.new("RGB", (400, 400), (200, 30, 80))
    out = create_game_poster(
        img,
        ratio="4:5",
        shadow=False,
        watermark_text="TEST_WATERMARK",
        swap=True,
        spacing=60,
        radius=40,
    )
    assert out.size == (1080, 1350)


def test_telegram_bridge_invalid_inputs(tmp_path: Path):
    # Missing file
    with pytest.raises(FileNotFoundError):
        create_game_poster("non_existent_image_12345.jpg")

    # Invalid bytes
    with pytest.raises(InvalidImageError):
        create_game_poster(b"not an image binary content")

    # Unsupported type
    with pytest.raises(InvalidImageError):
        create_game_poster(12345)  # type: ignore

    # Directory instead of file
    with pytest.raises(InvalidImageError):
        create_game_poster(tmp_path)


def test_telegram_bridge_helper_serialization():
    img = Image.new("RGB", (200, 200), (100, 150, 200))
    raw_bytes = poster_to_bytes(img, format="JPEG", quality=90)
    assert isinstance(raw_bytes, bytes)
    assert len(raw_bytes) > 100

    bio = poster_to_bytesio(img, format="PNG")
    assert isinstance(bio, io.BytesIO)
    assert bio.tell() == 0
    assert len(bio.getvalue()) > 100


def test_cli_custom_type_parsers():
    # parse_bool
    assert cli.parse_bool("true") is True
    assert cli.parse_bool("1") is True
    assert cli.parse_bool("yes") is True
    assert cli.parse_bool("false") is False
    assert cli.parse_bool("0") is False
    assert cli.parse_bool("no") is False
    with pytest.raises(Exception):
        cli.parse_bool("invalid_bool")

    # parse_margin
    assert cli.parse_margin("50") == 50
    assert cli.parse_margin("50px") == 50
    assert cli.parse_margin("10%") == 0.10
    assert cli.parse_margin("0.05") == 0.05

    # parse_curve
    assert cli.parse_curve("45") == 45
    assert cli.parse_curve("45px") == 45


def test_cli_single_image_execution(tmp_path: Path):
    in_file = tmp_path / "in.jpg"
    out_file = tmp_path / "out.jpg"
    Image.new("RGB", (500, 500), (80, 160, 240)).save(in_file)

    exit_code = cli.main([
        "--input", str(in_file),
        "--output", str(out_file),
        "--ratio", "1:1",
        "--margin", "40",
        "--curve", "30",
        "--auto-colors",
        "--quiet",
    ])
    assert exit_code == 0
    assert out_file.is_file()
    with Image.open(out_file) as loaded:
        assert loaded.size == (1200, 1200)


def test_cli_batch_execution(tmp_path: Path):
    batch_dir = tmp_path / "batch"
    batch_dir.mkdir()
    for i in range(2):
        Image.new("RGB", (300, 300), (50 * i, 100, 150)).save(batch_dir / f"img_{i}.png")
    (batch_dir / "ignore.txt").write_text("text")

    exit_code = cli.main([
        "--batch-dir", str(batch_dir),
        "--ratio", "4:5",
        "--quiet",
    ])
    assert exit_code == 0
    out_dir = batch_dir / "output"
    assert out_dir.is_dir()
    assert (out_dir / "img_0.png").is_file()
    assert (out_dir / "img_1.png").is_file()
    assert not (out_dir / "ignore.txt").exists()


def test_cli_argument_errors(tmp_path: Path):
    # Neither input nor batch-dir
    assert cli.main([]) == 2

    # Both input and batch-dir
    assert cli.main(["--input", "a.jpg", "--batch-dir", str(tmp_path)]) == 2

    # Non-existent input
    assert cli.main(["--input", "missing_file_xyz.jpg"]) == 1
