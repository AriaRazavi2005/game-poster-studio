# Original User Request

## 2026-09-20T19:35:16Z

Build a cross-platform Python application and library (Game Poster Studio) that recreates the photo framing and styling functionality of Windows Collage Maker, capable of running both as a desktop GUI on Windows and headlessly via CLI / Python API on a headless Linux server for the @BazyePc Telegram channel publishing automation.

Working directory: c:/Users/Lenovo/Documents/antigravity/optimistic-tesla/poster_studio
Integrity mode: development

## Requirements

### R1. Core Image Processing Engine
- Smart dominant color extraction from game posters using color quantization / clustering in RGB/HSV, filtering out near-black, near-white, and dull neutral grays.
- Dynamic 2-color linear gradient generator with configurable angle (0-360 deg, default 135 deg) and color swap.
- Aspect ratio handling supporting 4:5 (default 1080x1350 or 1440x1800), 1:1, 9:16, 16:9, 4:3, and 21:9 with clean fit-in-box scaling (no distortion).
- Configurable margins/padding (spacing) around the poster to reveal the gradient background.
- Supersampled anti-aliased rounded corners (curve radius 0-120px) preventing jagged edges.
- Realistic Gaussian drop shadow beneath the rounded poster for 3D card depth.
- Watermark / branding text layer ("BAZYEPC") with dark stroke outline and shadow for readability on all backgrounds.
- Pure lightweight dependencies (Pillow, numpy) without heavyweight frameworks (no PyTorch, no TensorFlow).

### R2. Headless CLI & Telegram Pipeline Bridge
- Command-line interface (`cli.py`) supporting flags: `--input`, `--output`, `--ratio`, `--curve`, `--margin`, `--auto-colors`, `--color1`, `--color2`, `--angle`, `--no-shadow`, `--watermark`, and batch processing `--batch-dir`.
- Headless Python bridge (`telegram_bridge.py`) exposing `create_game_poster(...)` returning output file path or PIL Image, ready for direct drop-in integration into `@BazyePc`'s `bazyepc_publisher.py` on Linux servers without any X11 or display server dependencies.

### R3. Windows Desktop GUI
- Modern desktop UI (CustomTkinter or lightweight local WebUI) matching the Collage Maker layout:
  - Sidebar with tabs/sliders for Spacing (margin), Curve (radius), and Zoom.
  - Aspect ratio selector (4:5, 1:1, 9:16, 16:9).
  - Background tab with color pickers, auto-detect button, swap button, and gradient rotation slider.
  - Text tab for branding ("BAZYEPC") with font size, stroke, and color controls.
  - Interactive canvas with fast real-time preview on slider adjustments.
  - Export/Save button saving high-quality JPEG/PNG (95% quality).
  - 1-click launcher (`run_gui.bat`).

### R4. Automated Testing & Verification Suite
- Comprehensive automated test script `test_pipeline.py` that processes sample images across all ratios (4:5, 1:1, 9:16), validates dimensions, verifies alpha masks and gradient integrity, and ensures execution under 1.5 seconds per poster.

## Acceptance Criteria

### Verification & Automated Testing
- [ ] `python test_pipeline.py` passes without errors on a headless environment.
- [ ] Processing a 1080p game poster executes in under 1.5 seconds on CPU.
- [ ] Generated 4:5 posters match exact specified dimensions (e.g. 1080x1350) with smooth rounded corners (no aliasing artifacts).
- [ ] Auto-extracted 2-color gradient produces distinct, non-dull colors from the game poster palette.
- [ ] `cli.py` successfully parses all arguments and produces valid output images without requiring a display/GUI.
- [ ] `telegram_bridge.py` can be imported and executed in a headless Python script without display dependencies.
- [ ] Windows GUI launches and reacts to slider changes with live canvas updates.
