---
name: game-poster-studio
description: Automated framing, 2-color gradient backdrop generation, smart palette extraction, interactive panning/zooming, and watermark typography for game posters and Telegram publishing pipelines (@BazyePc).
---

# 🎮 Game Poster Studio - Agent Skill Guide

This skill guides AI agents on using, configuring, and automating **Game Poster Studio** — a cross-platform Python framework that turns raw gaming posters into framed artworks with 2-color gradient backdrops, supersampled rounded corners, realistic drop shadows, and anti-collision watermark branding.

The framework runs in two modes:
1. **Headless Linux Server / CLI / Python API**: Designed for cloud pipelines and Telegram publishing bots (`@BazyePc`). Pure Pillow + NumPy, 100% headless with **zero X11/display server dependencies**.
2. **Windows Desktop GUI**: Interactive CustomTkinter application with live preview, canvas mouse-drag panning, wheel zoom, and draggable watermark text.

---

## 🚀 Quick Reference for AI Agents

Whenever a user or autonomous agent needs to generate or format a game poster:
- **In Python scripts / Telegram bots**: Import and call `create_game_poster()` from `telegram_bridge.py`.
- **From Terminal / Bash / PowerShell**: Run `python cli.py --input <path> --output <path> [options]`.
- **For Batch conversion**: Run `python cli.py --batch-dir <input_dir> --output <output_dir>`.
- **On Windows Desktop**: Launch `run_gui.bat` or `python gui.py`.

---

## 📂 Core Architecture & File Map

| File / Directory | Scope | Purpose |
| :--- | :--- | :--- |
| `telegram_bridge.py` | Headless API | Single entrypoint `create_game_poster()` for Telegram bots, backend jobs, and agents. |
| `cli.py` | Headless CLI | Full CLI interface with batch processing, color override, zoom/pan, and font options. |
| `poster_studio/core/engine.py` | Core Engine | `PosterProcessor` and `PosterConfig` pipeline orchestrating all layers. |
| `poster_studio/core/color_extractor.py` | Color AI | Quantizes poster, removes dark/light neutrals, selects harmonious dominant 2-color pairs. |
| `poster_studio/core/gradient.py` | Backdrop | Vectorized 2-color linear gradient generator with arbitrary angle (0–360°). |
| `poster_studio/core/card.py` | Poster Card | Supersampled anti-aliased rounded corners (0–120px), Gaussian drop shadow, zoom & pan offsets. |
| `poster_studio/core/watermark.py` | Typography | 10 TTF fonts, stroke outline, shadow, smart auto-placement, and card border collision avoidance. |
| `poster_studio/assets/fonts/` | Asset Storage | Bundled TTF fonts (no OS font dependencies). |
| `gui.py` / `poster_studio/gui/` | Desktop UI | Interactive desktop app with live canvas, mouse drag/pan, zoom, and text positioning. |

---

## 🛠️ Headless Python API (`telegram_bridge.py`)

This is the primary module agents should call in automated backend code.

### Function Signature
```python
from telegram_bridge import create_game_poster

output_path = create_game_poster(
    input_path="raw_cover.jpg",          # str or Path: source poster image
    output_path="framed_poster.jpg",    # str or Path: destination output path
    aspect_ratio="4:5",                  # '4:5', '1:1', '9:16', '16:9', '4:3', '21:9'
    margin=50,                           # Outer frame margin (0 to 150 px)
    curve=40,                            # Corner radius (0 to 120 px)
    zoom=1.0,                            # Scale factor (0.5 to 3.0)
    pan_x=0,                             # Horizontal offset in px
    pan_y=0,                             # Vertical offset in px
    auto_colors=True,                    # Auto-extract palette from image
    color1=None,                         # Optional hex '#RRGGBB' override
    color2=None,                         # Optional hex '#RRGGBB' override
    angle=135.0,                         # Gradient angle in degrees
    watermark="BAZYEPC",                 # Watermark branding text
    font_name="bebas_neue",              # Font key (see Font Catalog below)
    font_size=52,                        # Text font size
    watermark_color="#FFFFFF",           # Text fill color (hex)
    stroke_color="#000000",              # Text outline stroke color (hex)
    stroke_width=4,                      # Outline stroke width (px)
    watermark_pos="auto",                # 'auto', 'bottom-center', 'bottom-right', etc.
    watermark_x=None,                    # Explicit X coordinate (optional)
    watermark_y=None,                    # Explicit Y coordinate (optional)
    shadow=True,                         # Render realistic 3D drop shadow
    quality=95                           # JPEG/PNG output compression quality
)
```

### In-Memory Processing (No disk write required)
To process images entirely in memory for direct Telegram bot streaming:
```python
from PIL import Image
from poster_studio.core.engine import PosterProcessor, PosterConfig

config = PosterConfig(
    aspect_ratio="4:5",
    margin=45,
    curve=35,
    watermark_text="BAZYEPC",
    font_name="bebas_neue",
    watermark_color="#F4C430",
    stroke_color="#0B192C",
    stroke_width=4
)

processor = PosterProcessor(config)
raw_img = Image.open(input_file_stream).convert("RGB")
result_img = processor.process(raw_img)

# Save result to io.BytesIO for sending via Telegram
import io
bio = io.BytesIO()
result_img.save(bio, format="JPEG", quality=95)
bio.seek(0)
```

### Multi-Image Gaming Collage API (`create_game_collage`)
Creates 2x2 or 1x2 floating rounded card collages with dynamic shadows and unified palette extraction:
```python
from telegram_bridge import create_game_collage

collage_path = create_game_collage(
    input_images=["cover1.jpg", "cover2.jpg", "cover3.jpg", "cover4.jpg"],
    output_image="franchise_collage.jpg",
    ratio="4:5",                        # 4:5 vertical Telegram standard
    gap=18,                             # Space between cards in px
    curve=28,                           # Rounded corner radius
    auto_colors=True,                   # Extract unified palette across all 4 images
    watermark="BAZYEPC",                # Branding watermark
    watermark_font="bebas_neue",
    watermark_color="#F5BA42",
    watermark_stroke_color="#0B131F",
    pans_y=[0, -30, -120, -15]          # Optional tailored per-image vertical crop offsets
)
```

---

## 💻 CLI Usage & Recipes (`cli.py`)

### 1. Basic 4:5 Poster for Telegram Post
```bash
python cli.py --input poster.jpg --output framed_poster.jpg --ratio 4:5
```

### 2. Multi-Image Gaming Collage (2 to 4 Posters)
```bash
python cli.py --collage asylum.jpg city.jpg origins.jpg knight.jpg \
  --output batman_quadrilogy_collage.jpg \
  --ratio 4:5 \
  --curve 28 \
  --watermark "BAZYEPC" \
  --font bebas_neue \
  --watermark-color "#F5BA42"
```

### 3. High-Impact Custom Colors & Font (e.g., EA SPORTS FC / Gold & Navy)
```bash
python cli.py --input fc26.jpg --output fc26_framed.jpg \
  --ratio 4:5 \
  --margin 50 \
  --curve 40 \
  --font bebas_neue \
  --watermark "BAZYEPC" \
  --watermark-color "#F4C430" \
  --stroke-color "#0B192C" \
  --stroke-width=4
```

### 3. Edge-to-Edge Poster with Inside-Card Watermark
```bash
python cli.py --input game.jpg --output poster_full.jpg \
  --margin 0 \
  --curve 0 \
  --watermark "BAZYEPC" \
  --font audiowide \
  --watermark-color "#00FFFF" \
  --stroke-color "#101020"
```

### 4. Panning and Zooming (Focus on Character Face / Center)
```bash
python cli.py --input action_shot.jpg --output framed.jpg \
  --zoom 1.25 \
  --pan-y -60 \
  --curve 50
```

### 5. Batch Process an Entire Directory
```bash
python cli.py --batch-dir ./raw_covers --output ./ready_posters \
  --ratio 4:5 \
  --margin 45 \
  --curve 35 \
  --watermark "BAZYEPC"
```

---

## 🔤 Available Font Catalog

All fonts are bundled as local TTF files in `poster_studio/assets/fonts/`:

| Key (`font_name`) | Style / Category | Recommended Game Genres |
| :--- | :--- | :--- |
| `bebas_neue` | Bold, Clean, Athletic Condensed | Sports (EA FC, NBA), Action, General Gaming |
| `audiowide` | Futuristic, Tech, Geometric | Cyberpunk, Sci-Fi, Mecha, Space, Simulators |
| `luckiest_guy` | Chunky, Friendly, Fun | Casual, Party games, Fall Guys, Platformers |
| `black_ops_one` | Military, Stencil, Heavy Duty | Tactical Shooters, Call of Duty, Battlefield |
| `creepster` | Dripping, Ghoulish, Horror | Survival Horror, Zombies, Resident Evil, Halloween |
| `pacifico` | Smooth Script, Brush, Casual | Cozy games, Narrative, Indie, Adventure |
| `bungee` | Blocky, Urban, Street-art | Arcade, Fighting games, Beat-em-ups |
| `press_start_2p`| 8-Bit Pixel Art, Retro | Retro, Roguelikes, Metroidvania, Pixel art |
| `special_elite` | Vintage Typewriter, Gritty | Noir, Detective, Mafia, Post-Apocalyptic |
| `unifraktur_maguntia`| Gothic Blackletter, Medieval | Dark Souls, Elden Ring, Medieval, Fantasy RPG |

---

## 🎨 Game Genre Styling Decision Matrix

Agents should consult this table when automatically selecting framing parameters for different game genres:

| Genre | Margin | Curve | Recommended Font | Watermark Fill | Stroke Outline | Gradient Style |
| :--- | :---: | :---: | :--- | :--- | :--- | :--- |
| **Sports (FIFA / EA FC / 2K)** | 40–55px | 35–45px | `bebas_neue` | Gold (`#F4C430`) or White (`#FFFFFF`) | Deep Navy (`#0A192F`) | Auto 135° (Grass Green & Stadium Gold) |
| **Sci-Fi / Cyberpunk** | 45–60px | 25–35px | `audiowide` | Neon Cyan (`#00FFFF`) or Neon Yellow | Dark Obsidian (`#0D0D1A`) | High contrast (Magenta to Cyan) |
| **Horror / Dark Fantasy** | 50–70px | 20–30px | `creepster` / `unifraktur_maguntia` | Blood Red (`#B22222`) or Pale Bone (`#E6E6FA`) | Pure Black (`#000000`) | Dark Desaturated 150° |
| **Military / Tactical** | 40–50px | 30–40px | `black_ops_one` | Tactical Amber (`#FFBF00`) or White | Gunmetal Dark (`#1C2321`) | 120° Olive to Steel Grey |
| **Retro / Indie Pixel** | 50–65px | 15–25px | `press_start_2p` | Vibrant Lime (`#39FF14`) or Hot Pink | Deep Slate (`#1A1A1A`) | 90° Retro Synthwave |
| **Cozy / Casual / Party** | 45–55px | 50–65px | `luckiest_guy` | Sunshine Yellow (`#FFD700`) | Dark Violet (`#2E1A47`) | Warm Pastel Dual Gradient |

---

## 🤖 Telegram Bot Integration Recipes

### Recipe 1: Modern `aiogram 3.x` Handler
```python
import os
from aiogram import Router, F
from aiogram.types import Message, FSInputFile
from telegram_bridge import create_game_poster

router = Router()

@router.message(F.photo)
async def process_game_cover(message: Message, bot):
    # 1. Download highest-resolution photo from Telegram
    photo = message.photo[-1]
    raw_path = f"/tmp/raw_{photo.file_id}.jpg"
    framed_path = f"/tmp/framed_{photo.file_id}.jpg"
    
    await bot.download(photo, destination=raw_path)
    
    # 2. Process with Game Poster Studio (Headless execution)
    create_game_poster(
        input_path=raw_path,
        output_path=framed_path,
        aspect_ratio="4:5",
        margin=45,
        curve=38,
        watermark="BAZYEPC",
        font_name="bebas_neue",
        watermark_color="#F4C430",
        stroke_color="#0B192C",
        stroke_width=4
    )
    
    # 3. Send beautified poster back to channel or user
    await message.reply_photo(
        photo=FSInputFile(framed_path),
        caption="🎮 **پوستر آماده انتشار در کانال @BazyePc**",
        parse_mode="Markdown"
    )
    
    # 4. Clean up temp files
    for p in (raw_path, framed_path):
        if os.path.exists(p):
            os.remove(p)
```

### Recipe 2: `python-telegram-bot` (v20+) Async Handler
```python
import os
from telegram import Update
from telegram.ext import ContextTypes
from telegram_bridge import create_game_poster

async def handle_poster_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.photo[-1].get_file()
    raw_path = f"temp_in_{file.file_id}.jpg"
    out_path = f"temp_out_{file.file_id}.jpg"
    
    await file.download_to_drive(raw_path)
    
    # Run synchronously in executor to prevent blocking event loop
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        lambda: create_game_poster(
            input_path=raw_path,
            output_path=out_path,
            aspect_ratio="4:5",
            watermark="BAZYEPC"
        )
    )
    
    with open(out_path, "rb") as photo_file:
        await update.message.reply_photo(photo=photo_file, caption="✨ Ready!")
        
    for p in (raw_path, out_path):
        if os.path.exists(p):
            os.remove(p)
```

---

## ⚡ Technical Guardrails & Best Practices

1. **Zero Display Server Dependency**:
   - Never import `tkinter` or `gui.py` inside headless cloud scripts or Telegram bots.
   - Use only `telegram_bridge.py` or `poster_studio.core.*`.
2. **Watermark Collision-Aware Placement**:
   - The engine automatically tests whether the bottom margin is too small (< 20px). If so, it embeds the watermark directly inside the card on the lower foreground with 32px safety padding.
3. **Aspect Ratio Standards**:
   - Telegram vertical post ideal: `4:5` (1080x1350 or 1440x1800).
   - Telegram square post: `1:1` (1080x1080).
   - Telegram Stories / Reels: `9:16` (1080x1920).
4. **Fast Performance**:
   - Processing a 1080p poster executes in under **0.8 to 1.2 seconds** on standard CPU. No GPU required.
