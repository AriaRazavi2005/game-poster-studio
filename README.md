# 🎮 Game Poster Studio

> **High-performance, automated game poster framing & styling framework for Telegram channel publishing pipelines (@BazyePc) and Windows Desktop.**

[![Python](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Dependencies](https://img.shields.io/badge/Dependencies-Pillow%20%7C%20NumPy-orange.svg)](#dependencies)
[![Headless](https://img.shields.io/badge/Headless-Linux%20Safe%20(No%20X11)-brightgreen.svg)](#headless-automation-guide)

---

## 🌟 Overview

**Game Poster Studio** brings professional photo styling and framing (inspired by Windows Collage Maker) into a dual-track architecture:

1. **Headless Linux Cloud Server (Zero X11 / Display Dependency)**:
   - Optimized for cloud bots and automated Telegram publishers (`@BazyePc`).
   - Ultra-fast image processing (<100ms per 1080p image on standard CPU).
   - Pure Pillow + NumPy — zero heavyweight frameworks (no PyTorch, no OpenCV, no TensorFlow).
2. **Windows Desktop GUI**:
   - Modern dark-mode interface with live real-time preview.
   - Interactive canvas: **Mouse-drag panning**, **Mouse-wheel zooming**, and **Draggable watermark positioning**.
   - One-click launcher (`run_gui.bat`).

---

## 🚀 Quick Start for AI Agents & Linux Servers

Any AI agent on a remote Linux server can set up and run this repository in under 15 seconds:

```bash
# 1. Clone repository
git clone https://github.com/AriaRazavi2005/game-poster-studio.git
cd game-poster-studio

# 2. Run automated 1-click setup & self-test
chmod +x setup.sh
./setup.sh
```

Or manually:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 cli.py --input examples/raw_cover.jpg --output examples/framed_poster_4x5.jpg --ratio 4:5
```

---

## 🛠️ Key Capabilities

- **🎨 Smart Palette AI**: Color quantization & clustering in RGB/HSV that strips away dull neutral grays, pure blacks, and whites, extracting high-contrast dominant color pairs.
- **🌈 Dynamic 2-Color Linear Gradient**: Vectorized NumPy linear gradient generator at arbitrary rotation angles (0–360°) with instant color inversion.
- **📐 Social & Telegram Ratios**: Native presets for `4:5` (Telegram post default: 1080×1350), `1:1` (Square: 1080×1080), `9:16` (Stories / Reels: 1080×1920), `16:9`, `4:3`, and `21:9`.
- **✂️ Supersampled Anti-Aliased Corners**: Smooth rounded corners (0–120px radius) with Lanczos filtering eliminating all jagged staircasing.
- **🌑 3D Gaussian Drop Shadow**: Realistic elevation shadow layer for card depth effect.
- **🔤 Anti-Collision Typography Layer**:
  - Bundled with 10 Google Gaming Fonts (no OS font installation needed).
  - Dark stroke outline and drop shadow ensuring readability across any background.
  - **Smart Border Collision Detection**: If the poster fills the frame (low margin), the watermark automatically nests safely inside the lower card foreground.

---

## 🔤 Bundled Font Catalog

| Key (`font_name`) | Style / Category | Recommended Game Genres |
| :--- | :--- | :--- |
| `bebas_neue` | Bold, Clean, Athletic Condensed | Sports (EA FC, NBA), Action, Blockbusters |
| `audiowide` | Futuristic, Tech, Geometric | Cyberpunk, Sci-Fi, Mecha, Simulators |
| `luckiest_guy` | Chunky, Friendly, Fun | Casual, Party games, Fall Guys, Platformers |
| `black_ops_one` | Military, Stencil, Heavy Duty | Tactical Shooters, Call of Duty, Battlefield |
| `creepster` | Dripping, Ghoulish, Horror | Survival Horror, Zombies, Resident Evil |
| `pacifico` | Smooth Script, Brush, Casual | Cozy games, Narrative, Indie, Adventure |
| `bungee` | Blocky, Urban, Street-art | Arcade, Fighting games, Beat-em-ups |
| `press_start_2p`| 8-Bit Pixel Art, Retro | Retro, Roguelikes, Metroidvania, Pixel art |
| `special_elite` | Vintage Typewriter, Gritty | Noir, Detective, Mafia, Post-Apocalyptic |
| `unifraktur_maguntia`| Gothic Blackletter, Medieval | Dark Souls, Elden Ring, Medieval, Fantasy RPG |

---

## 💻 CLI Usage (`cli.py`)

### 1. Basic 4:5 Poster for Telegram Post
```bash
python cli.py --input poster.jpg --output framed.jpg --ratio 4:5
```

### 2. Custom Fire Gradient & Gold Typography (e.g. RuneScape / Fantasy)
```bash
python cli.py --input poster.jpg --output framed.jpg \
  --ratio 4:5 \
  --margin 48 \
  --curve 40 \
  --color1 "#E64A19" \
  --color2 "#140502" \
  --font bebas_neue \
  --watermark "BAZYEPC" \
  --watermark-color "#FFD54F" \
  --stroke-color "#1A0802"
```

### 3. Panning and Zooming
```bash
python cli.py --input raw.jpg --output framed.jpg \
  --zoom 1.25 \
  --pan-y -50 \
  --curve 45
```

### 4. Batch Process an Entire Directory
```bash
python cli.py --batch-dir ./raw_covers/ --output ./ready_posters/ --ratio 4:5
```

---

## 🤖 Telegram Bot Integration (`telegram_bridge.py`)

### Async `aiogram 3.x` Drop-in Handler
```python
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from telegram_bridge import create_game_poster

router = Router()

@router.message(F.photo)
async def handle_game_poster(message: Message, bot):
    photo = message.photo[-1]
    raw_path = f"/tmp/{photo.file_id}.jpg"
    out_path = f"/tmp/out_{photo.file_id}.jpg"
    
    await bot.download(photo, destination=raw_path)
    
    # Process headlessly with zero X11 dependency
    create_game_poster(
        input_image=raw_path,
        output_image=out_path,
        ratio="4:5",
        margin=45,
        curve=40,
        watermark="BAZYEPC",
        watermark_font="bebas_neue",
        watermark_color="#F4C430",
        watermark_stroke_color="#0B192C"
    )
    
    await message.reply_photo(photo=FSInputFile(out_path), caption="🎮 @BazyePc")
```

---

## 🖥️ Windows Desktop GUI

Run via batch launcher:
```cmd
run_gui.bat
```
Or directly via Python:
```bash
python gui.py
```

### Interactive Canvas Controls
- **Left Mouse Click & Drag on Poster**: Pan / translate image position (`pan_x`, `pan_y`).
- **Mouse Scroll Wheel**: Zoom in and out (`zoom`).
- **Left Mouse Click & Drag on Watermark**: Reposition the watermark text freely on the canvas.
- **Sliders**: Instant live debounced preview of Spacing, Curve Radius, Gradient Rotation Angle, and Colors.

---

## 📂 Project Structure

```
game-poster-studio/
├── poster_studio/
│   ├── core/
│   │   ├── palette.py          # Dominant color extraction & dead-color filtering
│   │   ├── gradient.py         # Vectorized NumPy 2-color linear gradient generator
│   │   ├── geometry.py         # Aspect ratio scaling & fit-in-box positioning
│   │   ├── mask.py             # Supersampled anti-aliased rounded corner mask
│   │   ├── shadow.py           # 3D Gaussian drop shadow layer
│   │   ├── watermark.py        # Typography layer with 10 fonts & collision avoidance
│   │   └── processor.py        # Pipeline orchestrator
│   ├── assets/
│   │   └── fonts/              # 10 bundled Google Gaming TTF fonts
│   └── gui/
│       ├── main_window.py      # CustomTkinter interactive GUI
│       ├── preview_engine.py   # Async preview renderer
│       └── export_engine.py    # Background export worker
├── skills/
│   └── game-poster-studio/
│       └── SKILL.md            # Comprehensive Agent Skill documentation
├── examples/                   # Sample raw input and output posters
├── cli.py                      # Headless CLI for terminal & batch operations
├── telegram_bridge.py          # Headless Python API for Telegram automation
├── gui.py                      # Desktop GUI launcher
├── run_gui.bat                 # Windows 1-click batch launcher
├── setup.sh                    # Linux server 1-click setup script
├── test_pipeline.py            # Comprehensive automated test suite (56 tests)
└── requirements.txt            # Lightweight dependencies
```

---

## 🧪 Testing & Verification

Run the comprehensive test suite verifying aspect ratios, anti-aliased corners, gradient generation, and headless execution:
```bash
python test_pipeline.py
```
*All 56 automated tests pass with 100% assertions.*

---

## 📄 License
MIT License. Free for personal and commercial game automation projects.
