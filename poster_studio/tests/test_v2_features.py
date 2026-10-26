"""
poster_studio.tests.test_v2_features
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Unit and integration tests for Game Poster Studio v2 features (Phases 1-7):
- Phase 1: Persian RTL shaping & typography layers (title, subtitle, badge)
- Phase 2: Genre presets, auto-preset, WCAG contrast, safe-zone, auto-trim
- Phase 3: 22 collage templates, smart/contain/cover fit modes, custom JSON template
- Phase 4: Backdrop modes (blur, radial, mesh, 3-color), patterns, glow, border, reflection, vignette, grain, platforms
- Phase 5: CLI --json, --list-presets, --list-templates, --ratios, stdin/stdout, bot caption parser
- Phase 6: GUI PosterStudioModel undo/redo, presets, project save/load, multi-ratio export
- Phase 7: Pro AI plugin hooks (upscale_image, apply_pop_out, generate_caption_ai)
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw

from poster_studio.core.watermark import (
    has_rtl,
    shape_rtl_text,
    resolve_wcag_colors,
    select_safe_zone_position,
)
from poster_studio.core.presets import PRESETS, get_preset, list_presets, auto_select_preset
from poster_studio.core.collage import COLLAGE_TEMPLATES, list_templates
from poster_studio.core.effects import (
    auto_trim_borders,
    generate_backdrop,
)
from poster_studio.telegram_bridge import create_game_poster, create_game_collage
from poster_studio.bot import parse_caption_parts
from poster_studio.gui.main_window import PosterStudioModel
import poster_studio_pro


def _make_sample_image(width: int = 300, height: int = 400, color=(40, 120, 220)) -> Image.Image:
    img = Image.new("RGB", (width, height), color)
    draw = ImageDraw.Draw(img)
    pad_x = max(10, width // 6)
    pad_y = max(10, height // 6)
    draw.rectangle((pad_x, pad_y, width - pad_x, height - pad_y), fill=(220, 80, 50))
    draw.ellipse((pad_x * 2, pad_y * 2, width - pad_x * 2, height - pad_y * 2), fill=(250, 220, 60))
    return img


# ==============================================================================
# Phase 1: Persian RTL & Multi-Layer Typography
# ==============================================================================

def test_rtl_detection_and_shaping():
    assert has_rtl("بازی پی سی") is True
    assert has_rtl("BAZYEPC 2026") is False
    shaped = shape_rtl_text("بازی")
    assert isinstance(shaped, str)
    assert len(shaped) > 0
    assert shaped != "بازی"


def test_persian_poster_and_typography_layers():
    img = _make_sample_image()
    out = create_game_poster(
        img,
        watermark_text="بازی پی سی",
        title="گوست آو سوشیما",
        subtitle="نسخه کارگردان",
        badge="زیرنویس فارسی",
        ratio="4:5",
    )
    assert isinstance(out, Image.Image)
    assert out.size == (1080, 1350)


# ==============================================================================
# Phase 2: Presets, WCAG Contrast, Safe-Zone, Auto-Trim
# ==============================================================================

def test_all_10_presets_and_auto_select():
    all_presets = list_presets()
    assert len(all_presets) >= 10
    img = _make_sample_image()
    for name in PRESETS:
        p = get_preset(name)
        assert "curve" in p
        out = create_game_poster(img, preset=name, ratio="1:1")
        assert isinstance(out, Image.Image)
        assert out.size == (1200, 1200)

    selected = auto_select_preset(img)
    assert selected in PRESETS


def test_wcag_contrast_and_safe_zone():
    bright_bg = Image.new("RGB", (400, 400), (245, 245, 245))
    fill_b, stroke_b = resolve_wcag_colors(bright_bg, (100, 320), (120, 30), "auto", "#0f172a")
    assert fill_b == (15, 23, 42)  # dark text on bright background

    dark_bg = Image.new("RGB", (400, 400), (15, 15, 20))
    fill_d, stroke_d = resolve_wcag_colors(dark_bg, (100, 320), (120, 30), "auto", "#0f172a")
    assert fill_d == (255, 255, 255)  # white text on dark background

    pos = select_safe_zone_position(dark_bg, (100, 30), margin_bottom=30)
    assert len(pos) == 2


def test_auto_trim_letterbox_borders():
    img = Image.new("RGB", (400, 400), (0, 0, 0))
    inner = _make_sample_image(300, 260)
    img.paste(inner, (50, 70))
    trimmed = auto_trim_borders(img)
    assert trimmed.width <= 310 and trimmed.height <= 270


# ==============================================================================
# Phase 3: 22 Collage Templates & Fit Modes
# ==============================================================================

def test_collage_templates_and_3_image_fix():
    templates = list_templates()
    assert len(templates) >= 22
    imgs = [_make_sample_image(200, 260, (50 * i, 100, 180)) for i in range(1, 5)]

    # 3 images with auto template should select hero_left (3 slots, no empty 4th cell)
    out3 = create_game_collage(imgs[:3], template="auto", ratio="4:5")
    assert isinstance(out3, Image.Image)
    assert out3.size == (1080, 1350)

    # Test representative templates across fit modes
    for tpl in ["versus", "trilogy", "hero_plus_3", "polaroid_scatter", "film_strip", "hexagon_hive", "box_shelf"]:
        out = create_game_collage(imgs, template=tpl, fit="smart", ratio="1:1")
        assert isinstance(out, Image.Image)
        assert out.size == (1200, 1200)


# ==============================================================================
# Phase 4: Effects, Backdrops, Patterns, Borders, Reflection, Platforms
# ==============================================================================

def test_phase4_effects_pipeline():
    img = _make_sample_image()
    for mode in ["gradient", "blur", "radial", "mesh"]:
        bg = generate_backdrop((400, 500), img, (20, 30, 80), (180, 40, 90), color3=(40, 200, 180), bg_mode=mode)
        assert bg.size == (400, 500)

    out = create_game_poster(
        img,
        ratio="4:5",
        bg_mode="mesh",
        color3="#22d3ee",
        pattern="hex",
        glow=True,
        glow_color="#ec4899",
        border=3,
        border_color="#22d3ee",
        reflection=True,
        vignette=0.25,
        grain=0.04,
        platforms=["PC", "PS5", "STEAM"],
        auto_trim=True,
    )
    assert isinstance(out, Image.Image)
    assert out.size == (1080, 1350)


# ==============================================================================
# Phase 5: CLI JSON / Multi-Ratio / Bot Caption Parser
# ==============================================================================

def test_bot_caption_parser():
    title, subtitle, badge = parse_caption_parts("Ghost of Tsushima | Director's Cut | PC, PS5")
    assert title == "Ghost of Tsushima"
    assert subtitle == "Director's Cut"
    assert badge == "PC, PS5"


def test_cli_list_presets_and_json_multi_ratio(tmp_path: Path):
    in_path = tmp_path / "in.jpg"
    out_path = tmp_path / "out.jpg"
    _make_sample_image().save(in_path)

    res_list = subprocess.run(
        [sys.executable, "-m", "poster_studio.cli", "--list-presets", "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    presets_data = json.loads(res_list.stdout)
    assert "cyberpunk" in presets_data

    res_run = subprocess.run(
        [
            sys.executable, "-m", "poster_studio.cli",
            "-i", str(in_path),
            "-o", str(out_path),
            "--preset", "cyberpunk",
            "--ratios", "4:5,1:1",
            "--caption",
            "--json",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    payload = json.loads(res_run.stdout)
    assert payload["status"] == "ok"
    assert len(payload["outputs"]) == 2
    assert "caption" in payload


# ==============================================================================
# Phase 6: GUI Model Undo/Redo, Presets, Save/Load Project
# ==============================================================================

def test_gui_model_undo_redo_and_project_io(tmp_path: Path):
    img = _make_sample_image()
    model = PosterStudioModel(initial_image=img)
    assert model.config.margin == 50

    model.set_spacing(90)
    assert model.config.margin == 90
    assert model.undo() is True
    assert model.config.margin == 50
    assert model.redo() is True
    assert model.config.margin == 90

    model.set_preset("cyberpunk")
    assert model.config.preset == "cyberpunk"

    proj_file = tmp_path / "test.gps.json"
    model.save_project(proj_file)
    assert proj_file.is_file()

    model2 = PosterStudioModel(initial_image=img)
    model2.load_project(proj_file)
    assert model2.config.preset == "cyberpunk"

    exported = model2.export_multi_ratios(tmp_path / "multi", ratios=["4:5", "1:1"])
    assert len(exported) == 2


# ==============================================================================
# Phase 7: Pro AI Plugin Hooks (4GB RAM Safe)
# ==============================================================================

def test_pro_plugin_functions():
    img = _make_sample_image(120, 160)
    up = poster_studio_pro.upscale_image(img, scale=2)
    assert up.size == (240, 320)

    canvas = Image.new("RGB", (200, 240), (20, 20, 30))
    popped = poster_studio_pro.apply_pop_out(canvas, img, (40, 40))
    assert popped.size == (200, 240)

    cap = poster_studio_pro.generate_caption_ai(img, title="Elden Ring", preset="fantasy_rpg")
    assert "Elden Ring" in cap["title"] and "@BazyePc" in cap["caption_fa"]
