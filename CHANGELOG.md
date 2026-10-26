# Changelog

All notable changes to **Game Poster Studio** are documented in this file.

## [2.0.0] - 2026-10-27

### Added
- **Dual-Edition Architecture (Lite & Pro)**:
  - **Lite (`game-poster-studio`)**: Pure `Pillow` + `numpy`, <15MB, zero X11 requirement.
  - **Pro (`game-poster-studio-pro`)**: Optional plugin (`poster_studio_pro/`) engineered for 4GB RAM CPU-only Linux VPS (<1.5GB peak RAM) with 3D Character Pop-out (`--pop-out`), 2x/4x Upscaling (`--upscale`), and Gemini Vision Persian Caption Generation (`--caption`).
- **Collage 2.0 Engine (`poster_studio/core/collage.py`)**:
  - **22 Built-in Templates**: `duo_split`, `duo_stack`, `versus`, `diagonal_split`, `trilogy`, `hero_left`, `hero_top`, `grid_2x2`, `hero_plus_3`, `quad_strip`, `timeline`, `spotlight`, `mosaic_5`, `grid_3x2`, `magazine`, `grid_3x3`, `fan_stack`, `polaroid_scatter`, `film_strip`, `staircase`, `hexagon_hive`, `box_shelf`.
  - **Smart Fit Modes**: `cover`, `contain`, and `smart` (entropy/edge-aware center of gravity).
  - **Custom JSON Templates**: Pass `--template my_layout.json` to load custom normalized coordinates.
  - Fixed 3-image collage bug (automatically selects 3-slot `hero_left` instead of leaving an empty 4th slot).
- **Persian / Arabic RTL Shaping & Multi-Layer Typography**:
  - Built-in zero-dependency Unicode Contextual Shaper + BiDi visual reorder (`shape_rtl_text`), with automatic upgrade to `libraqm` or `arabic-reshaper` + `python-bidi` when available.
  - Bundled Persian & Gaming fonts: `Lalezar-Regular.ttf`, `Vazirmatn-Bold.ttf`, `Teko-Bold.ttf`.
  - Multi-layer text overlays: `--title`, `--subtitle`, and pill `--badge`.
- **Smart Genre Presets (`poster_studio/core/presets.py`)**:
  - 10 built-in presets (`bazyepc_default`, `sports`, `horror`, `fantasy_rpg`, `cyberpunk`, `military_shooter`, `retro_pixel`, `cozy_indie`, `racing`, `persian_bold`) plus `--preset auto` and user presets in `~/.poster_studio/presets/`.
- **Visual Effects & Backdrops (`poster_studio/core/effects.py`)**:
  - Backdrops: `gradient`, `blur` (glassmorphic cover blur), `radial`, `mesh` (3-color), and procedural patterns (`dots`, `scanlines`, `diagonal`, `hex`).
  - Card & Canvas effects: `--glow`, `--border`, `--reflection`, `--vignette`, `--grain`, `--auto-trim`, `--logo`, and `--platforms` (`PC,PS5,XBOX,SWITCH,STEAM`).
- **Automation, Bot & Cloud**:
  - Ready-to-run `aiogram 3` Telegram Bot (`poster_studio/bot.py` / `poster-studio-bot`) with album auto-collage and inline buttons.
  - FastAPI REST service (`poster_studio/api.py` / `poster-studio-api`).
  - Multi-ratio single-pass export (`--ratios 4:5,9:16,1:1`), `--json` agent output, `-i - -o -` stream piping, and `--watch` folder daemon.
  - Multi-stage `Dockerfile` (`lite` and `pro` targets) and `docker-compose.yml`.
- **Desktop GUI 2.0**:
  - 20-step Undo/Redo history (`Ctrl+Z` / `Ctrl+Y`), Preset & Backdrop selectors, `.gps.json` project save/load, and Multi-Ratio batch export.

### Fixed
- Consolidated duplicated root `cli.py` and `telegram_bridge.py` into thin backward-compatible shims over `poster_studio/`.
- Fixed EXIF orientation via `ImageOps.exif_transpose`.
- Fixed RGBA alpha compositing mismatch between `palette.py` and `processor.py`.
- Replaced random noise dithering with deterministic 4x4 Bayer ordered dithering (`_BAYER_4X4`) for bit-for-bit PNG parity.
