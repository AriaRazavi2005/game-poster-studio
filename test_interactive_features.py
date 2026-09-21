"""
Unit & Integration tests for new interactive features in Game Poster Studio:
- Mouse Pan & Zoom
- Multiple Gaming Fonts (Bebas Neue, Russo One, Orbitron, Anton)
- Watermark Text & Stroke Colors & Stroke Width
- Custom Watermark Positioning & Presets
- CLI & Telegram Bridge parameter propagation
"""

import os
from pathlib import Path
from PIL import Image
import pytest

from poster_studio.core.processor import PosterConfig, PosterProcessor, process_poster
from poster_studio.core.watermark import AVAILABLE_FONTS, get_available_fonts, resolve_watermark_font
from poster_studio.gui.main_window import PosterStudioModel
import telegram_bridge
import cli


@pytest.fixture
def sample_img():
    # 800x1000 sample test poster
    img = Image.new("RGB", (800, 1000), color=(180, 50, 40))
    # Add contrasting pattern
    for x in range(200, 600):
        for y in range(200, 600):
            img.putpixel((x, y), (20, 150, 220))
    return img


def test_available_fonts_catalog():
    fonts = get_available_fonts()
    assert "Anton (Default Gaming)" in fonts
    assert "Bebas Neue (Bold Tall)" in fonts
    assert "Russo One (Action Block)" in fonts
    assert "Orbitron (Cyberpunk)" in fonts

    # Test font loading for each bundled font
    for font_key in ["Anton", "Bebas Neue", "Russo One", "Orbitron"]:
        f = resolve_watermark_font(font_key, font_size=32)
        assert f is not None


def test_poster_studio_model_state_mutations(sample_img):
    model = PosterStudioModel()
    model.load_image(sample_img)

    # Test pan
    model.set_pan(25.5, -40.0)
    assert model.config.pan_x == 25.5
    assert model.config.pan_y == -40.0

    model.reset_pan()
    assert model.config.pan_x == 0.0
    assert model.config.pan_y == 0.0

    # Test watermark position
    model.set_watermark_position(0.5, 0.2)
    assert model.config.watermark_x == 0.5
    assert model.config.watermark_y == 0.2

    model.reset_watermark_position()
    assert model.config.watermark_x is None
    assert model.config.watermark_y is None

    # Test font mutation
    model.set_watermark_font("Orbitron")
    assert model.config.watermark_font == "Orbitron"

    # Test color mutations (normalized to RGB tuples)
    model.set_watermark_colors(text_color="#facc15", stroke_color="#ef4444", stroke_width=6)
    assert model.config.watermark_color == (250, 204, 21)
    assert model.config.watermark_stroke_color == (239, 68, 68)
    assert model.config.watermark_stroke_width == 6


def test_processor_with_pan_and_custom_styling(sample_img, tmp_path):
    config = PosterConfig(
        ratio="4:5",
        margin=40,
        curve=30,
        pan_x=35.0,
        pan_y=-20.0,
        watermark="TESTGAMING",
        watermark_font="Bebas Neue",
        watermark_color="#facc15",
        watermark_stroke_color="#000000",
        watermark_stroke_width=5,
        watermark_x=0.5,
        watermark_y=0.1,  # Top position
        quality=90
    )

    out_file = tmp_path / "test_styled.jpg"
    result = process_poster(sample_img, config, output_path=out_file)
    assert out_file.is_file()
    assert result.size == (1080, 1350)


def test_telegram_bridge_new_parameters(sample_img, tmp_path):
    out_file = tmp_path / "bridge_test.jpg"
    res = telegram_bridge.create_game_poster(
        input_image=sample_img,
        output_image=out_file,
        ratio="1:1",
        watermark="CYBERPUNK",
        watermark_font="Orbitron",
        watermark_color="#06b6d4",
        watermark_stroke_color="#0f172a",
        watermark_stroke_width=4,
        pan_x=15.0,
        pan_y=10.0,
        watermark_x=0.5,
        watermark_y=0.9
    )
    assert isinstance(res, Path)
    assert res.is_file()
    with Image.open(res) as im:
        assert im.size == (1200, 1200)


def test_cli_argument_parsing():
    parser = cli.build_arg_parser()
    args = parser.parse_args([
        "--input", "dummy.jpg",
        "--pan-x", "30",
        "--pan-y", "-15",
        "--font", "Russo One",
        "--watermark-color", "#facc15",
        "--stroke-color", "#7f1d1d",
        "--stroke-width", "5",
        "--watermark-x", "0.5",
        "--watermark-y", "0.85"
    ])

    config = cli.create_poster_config(args)
    assert config.pan_x == 30.0
    assert config.pan_y == -15.0
    assert config.watermark_font == "Russo One"
    assert config.watermark_color == (250, 204, 21)
    assert config.watermark_stroke_color == (127, 29, 29)
    assert config.watermark_stroke_width == 5
    assert config.watermark_x == 0.5
    assert config.watermark_y == 0.85
