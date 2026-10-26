# 🎮 Game Poster Studio v2.0

> **High-performance, automated game poster framing, 22-template collage engine & styling framework for Telegram channel publishing pipelines (`@BazyePc`) and Windows Desktop.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/Lite-Pillow%20%7C%20NumPy-orange.svg)](#editions-lite-vs-pro)
[![Headless](https://img.shields.io/badge/Headless-Linux%20Safe%20(No%20X11)-brightgreen.svg)](#quick-start)

---

## 🌟 Editions: Lite vs Pro

1. **Game Poster Studio Lite (`game-poster-studio`) — Default**:
   - **Dependencies**: ONLY `Pillow>=10.0.0` and `numpy>=1.24.0` (<15 MB total).
   - **Performance**: <170ms per 1080p poster on standard CPU, <250MB RAM, zero X11/display dependency.
   - Includes **Persian/Arabic RTL typography**, **10 Genre Presets**, **22 Collage Templates**, **4 Backdrop Modes**, **Patterns/Glow/Reflection**, **CLI**, **Telegram Bot**, **REST API**, and **Desktop GUI**.
2. **Game Poster Studio Pro (`game-poster-studio-pro`) — Optional 4GB RAM AI Plugin**:
   - Located in `poster_studio_pro/`, engineered specifically for **4GB RAM CPU-only Linux VPS** (<1.5GB peak RAM via ONNX CPU threads + `_AI_LOCK`).
   - Adds **3D Character Pop-out (`--pop-out`)**, **2x/4x Detail Upscaling (`--upscale`)**, and **Gemini Vision Persian Telegram Caption Generator (`--caption`)**.

---

## 🚀 Quick Start

```bash
# 1. Clone repository
git clone https://github.com/AriaRazavi2005/game-poster-studio.git
cd game-poster-studio

# 2. Install Lite (or pass --pro for 4GB RAM AI edition)
chmod +x setup.sh
./setup.sh          # Lite
# ./setup.sh --pro  # Pro AI Edition
```

Or via `pip`:
```bash
pip install -e .
poster-studio -i examples/raw_cover.jpg -o out.jpg --preset cyberpunk --ratios 4:5,1:1
```

---

## 🎨 10 Smart Genre Presets (`--preset`)

| Preset Name | Style | Font | Backdrop & Effects |
| :--- | :--- | :--- | :--- |
| `bazyepc_default` | Official `@BazyePc` Gold & Navy | `bebas_neue` | 135° Auto Gradient, Drop Shadow |
| `sports` | Stadium Gold & Energetic Frame | `teko` | Diagonal Pattern, Gold Border |
| `horror` | Blood Crimson & Dark Vignette | `creepster` | Heavy Vignette (`0.45`), Film Grain |
| `fantasy_rpg` | Medieval Royal Gold & Obsidian | `unifraktur_maguntia` | Radial Backdrop, Double Gold Border |
| `cyberpunk` | Neon Cyan & Magenta Synth | `audiowide` | Mesh Backdrop, Hex Pattern, Neon Glow |
| `military_shooter`| Tactical Stencil & Olive | `black_ops_one` | Scanlines Pattern, Grain (`0.06`) |
| `retro_pixel` | 8-Bit Arcade Synthwave | `press_start_2p` | Scanlines Pattern, Neon Border |
| `cozy_indie` | Warm Glassmorphic Blur | `pacifico` | Blurred Cover Backdrop, High Curve (`60px`) |
| `racing` | High-Octane Mirror Floor | `bungee` | Diagonal Pattern, 3D Floor Reflection |
| `persian_bold` | Persian RTL Lalezar Display | `lalezar` | Auto Gradient, Gold Persian Typography |

Use `--preset auto` to automatically classify image brightness/saturation into the best matching preset, or `--list-presets` to inspect all presets.

---

## 🧩 Collage 2.0: 22 Multi-Image Templates (`--collage` & `--template`)

| Category | Template IDs |
| :--- | :--- |
| **2 Images (Duo)** | `duo_split`, `duo_stack`, `versus` (with `VS` badge), `diagonal_split` |
| **3 Images (Trio)** | `trilogy` (with `I / II / III` badges), `hero_left` (auto default for 3 images), `hero_top` |
| **4 Images (Quad)** | `grid_2x2`, `hero_plus_3`, `quad_strip`, `timeline` (with timeline bar) |
| **5–9 Images (Mega)**| `spotlight` (5), `mosaic_5` (5), `grid_3x2` (6), `magazine` (6), `grid_3x3` (9) |
| **Creative / 3D** | `fan_stack`, `polaroid_scatter`, `film_strip`, `staircase`, `hexagon_hive`, `box_shelf` |

### Collage Fit Modes (`--fit`)
- `cover`: Fills cell edge-to-edge.
- `contain`: Preserves full cover inside a mini blurred sub-card without cropping logos.
- `smart`: Automatically crops toward highest edge-entropy center of gravity.

```bash
poster-studio --collage c1.jpg c2.jpg c3.jpg --template trilogy --fit smart -o trilogy.jpg
```

---

## 🔤 Persian RTL & Multi-Layer Typography

Full support for Persian/Arabic right-to-left (`RTL`) contextual glyph shaping (`shape_rtl_text`) out of the box with zero external dependencies, plus multi-layer text:

```bash
poster-studio -i cover.jpg -o poster.jpg \
  --preset persian_bold \
  --title "گوست آو سوشیما" \
  --subtitle "نسخه کارگردان" \
  --badge "زیرنویس فارسی" \
  --watermark "بازی پی سی" \
  --platforms PC,PS5,STEAM
```

---

## 🤖 Ready-to-Run Telegram Bot & FastAPI Server

### Run Telegram Bot (`aiogram 3.x`)
Supports single posters, media-group albums (2–9 photos → automatic collage), `Title | Subtitle | Badge` captions, and interactive inline buttons:
```bash
pip install -e ".[bot]"
export BOT_TOKEN="your_telegram_bot_token"
poster-studio-bot
```

### Run FastAPI Microservice
```bash
pip install -e ".[api]"
poster-studio-api
```

### Docker (`lite` and `pro` targets)
```bash
docker compose up -d poster-bot-lite
# Or with 4GB RAM Pro AI features:
docker compose --profile pro up -d poster-bot-pro
```

---

## 🧪 Testing & Verification

```bash
python test_pipeline.py
pytest -q
```

---

## 📄 License
MIT License.
