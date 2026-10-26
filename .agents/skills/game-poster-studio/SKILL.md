---
name: game-poster-studio
description: Automated framing, 22-template collage engine, Persian RTL typography, 10 genre presets, 4 backdrop modes, and Telegram publishing pipelines (@BazyePc) with Lite (<15MB) and Pro (4GB RAM AI) editions.
---

# 🎮 Game Poster Studio v2.0 — Agent Skill Guide

**Game Poster Studio v2.0** is a dual-edition Python framework for automated game poster framing, multi-image collages, Persian/English typography, and Telegram channel publishing (`@BazyePc`).

- **Lite Edition (`game-poster-studio`)**: Pure `Pillow` + `numpy`, <15MB, 100% headless (zero X11 dependency).
- **Pro Edition (`game-poster-studio-pro`)**: Optional AI plugin in `poster_studio_pro/` engineered for 4GB RAM CPU-only Linux VPS (<1.5GB peak RAM) providing `--pop-out`, `--upscale`, and `--caption`.

---

## 🚀 Quick Reference for AI Agents

- **CLI (Single Poster)**:
  ```bash
  poster-studio -i cover.jpg -o poster.jpg --preset cyberpunk --ratios 4:5,1:1 --json
  ```
- **CLI (Persian RTL + Multi-Layer Text)**:
  ```bash
  poster-studio -i cover.jpg -o poster.jpg --preset persian_bold --title "گوست آو سوشیما" --subtitle "نسخه کارگردان" --badge "زیرنویس فارسی" --watermark "بازی پی سی" --platforms PC,PS5
  ```
- **CLI (Collage 2.0 — 22 Templates)**:
  ```bash
  poster-studio --collage c1.jpg c2.jpg c3.jpg --template trilogy --fit smart -o trilogy.jpg
  ```
- **CLI (Stdin / Stdout Pipe)**:
  ```bash
  cat raw.jpg | poster-studio -i - -o - --preset horror > out.jpg
  ```
- **Python API**:
  ```python
  from poster_studio.telegram_bridge import create_game_poster, create_game_collage
  ```

---

## 🎨 10 Built-in Genre Presets (`--preset`)

`bazyepc_default`, `sports`, `horror`, `fantasy_rpg`, `cyberpunk`, `military_shooter`, `retro_pixel`, `cozy_indie`, `racing`, `persian_bold`, or `auto` (automatic HSV/luminance genre classifier).

---

## 🧩 22 Built-in Collage Templates (`--template`)

- **2 Images**: `duo_split`, `duo_stack`, `versus` (with `VS` badge), `diagonal_split`
- **3 Images**: `trilogy` (with `I / II / III` numerals), `hero_left` (default for 3 images), `hero_top`
- **4 Images**: `grid_2x2`, `hero_plus_3`, `quad_strip`, `timeline`
- **5–9 Images**: `spotlight` (5), `mosaic_5` (5), `grid_3x2` (6), `magazine` (6), `grid_3x3` (9)
- **Creative / 3D**: `fan_stack`, `polaroid_scatter`, `film_strip`, `staircase`, `hexagon_hive`, `box_shelf`

Fit modes (`--fit`): `cover`, `contain`, `smart` (edge-entropy aware).

---

## 🌈 Backdrops & Visual Effects

- `--bg-mode`: `gradient` (2-color + Bayer dithering), `blur` (glassmorphic cover blur), `radial`, `mesh` (3-color with `--color3`)
- `--pattern`: `dots`, `scanlines`, `diagonal`, `hex`
- Card effects: `--glow`, `--glow-color`, `--border`, `--border-color`, `--reflection`, `--vignette`, `--grain`, `--auto-trim`
- Overlays: `--logo <path>`, `--platforms PC,PS5,XBOX,SWITCH,STEAM`
- Pro AI flags: `--pop-out`, `--upscale 2`, `--caption`
