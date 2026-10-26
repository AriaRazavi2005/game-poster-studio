#!/usr/bin/env python3
"""
poster_studio.cli
~~~~~~~~~~~~~~~~~
Full-featured headless command-line interface for Game Poster Studio v2.
Supports single-image styling, 22-template multi-image collages, genre presets,
Persian RTL typography, multi-ratio exports, JSON output, stdin/stdout piping,
and directory watch mode.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Set, Union
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
POSTER_STUDIO_DIR = Path(__file__).resolve().parent

for p in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from poster_studio import __version__
from poster_studio.core.processor import (
    PosterConfig,
    PosterProcessingError,
    process_poster,
)
from poster_studio.core.presets import list_presets, get_preset
from poster_studio.core.collage import list_collage_templates, create_game_collage
from poster_studio.core.palette import extract_dominant_colors, rgb_to_hex
from poster_studio.plugins import get_pro_plugin

logger = logging.getLogger("poster_studio.cli")

IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "t", "y", "1"):
        return True
    elif val_str in ("no", "false", "f", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got {value!r}")


def parse_margin(value: Any) -> Union[int, float]:
    val_str = str(value).strip().lower()
    if val_str.endswith("px"):
        return int(float(val_str[:-2]))
    if val_str.endswith("%"):
        pct = float(val_str[:-1])
        return pct / 100.0 if pct > 1.0 else pct
    if "." in val_str:
        return float(val_str)
    return int(val_str)


def parse_curve(value: Any) -> int:
    val_str = str(value).strip().lower()
    if val_str.endswith("px"):
        return int(float(val_str[:-2]))
    return int(val_str)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="poster-studio",
        description="Game Poster Studio v2 — Headless CLI, Collage & Automation Engine",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program's version number and exit.",
    )

    # I/O Target Options
    io_group = parser.add_argument_group("Input / Output Targets")
    io_group.add_argument("--input", "-i", type=str, default=None, help="Path to single input image file (or '-' for stdin).")
    io_group.add_argument("--output", "-o", type=str, default=None, help="Destination path for output image/directory (or '-' for stdout).")
    io_group.add_argument("--batch-dir", "-b", type=str, default=None, help="Path to directory containing images for batch processing.")
    io_group.add_argument("--collage", nargs="+", type=str, default=None, help="List of 2 to 9 image paths to generate a gaming collage.")
    io_group.add_argument("--watch", nargs=2, metavar=("INBOX", "OUTBOX"), default=None, help="Watch INBOX directory and auto-process new images to OUTBOX.")
    io_group.add_argument("--list-presets", action="store_true", help="List all available genre styling presets and exit.")
    io_group.add_argument("--list-templates", action="store_true", help="List all 22 built-in collage templates and exit.")

    # Canvas & Framing Options
    canvas_group = parser.add_argument_group("Canvas, Presets & Framing")
    canvas_group.add_argument("--preset", "-p", type=str, default=None, help="Genre styling preset (sports, horror, fantasy_rpg, cyberpunk, military_shooter, retro_pixel, cozy_indie, racing, persian_bold, auto).")
    canvas_group.add_argument("--template", "-t", type=str, default=None, help="Collage template ID (e.g. hero_left, versus, trilogy, grid_2x2, fan_stack, polaroid_scatter, hexagon_hive, auto) or JSON file.")
    canvas_group.add_argument("--fit", choices=["cover", "contain", "smart"], default="cover", help="Collage cell fitting mode ('contain' preserves full uncropped covers).")
    canvas_group.add_argument("--ratio", "-r", type=str, default="4:5", help="Target canvas aspect ratio (4:5, 1:1, 9:16, 16:9, 4:3, 21:9).")
    canvas_group.add_argument("--ratios", type=str, default=None, help="Comma-separated multi-ratio export in a single command (e.g. '4:5,1:1,9:16').")
    canvas_group.add_argument("--curve", "-c", type=parse_curve, default=45, help="Corner curvature radius in pixels.")
    canvas_group.add_argument("--margin", "-m", type=parse_margin, default=50, help="Margin spacing around poster in pixels or percentage.")
    canvas_group.add_argument("--zoom", "-z", type=float, default=1.0, help="Poster zoom factor (0.1 to 3.0).")
    canvas_group.add_argument("--pan-x", type=float, default=0.0, help="Poster horizontal pan offset in canvas pixels.")
    canvas_group.add_argument("--pan-y", type=float, default=0.0, help="Poster vertical pan offset in canvas pixels.")
    canvas_group.add_argument("--auto-trim", action="store_true", default=False, help="Auto-strip solid black/white letterbox bars around raw cover.")
    canvas_group.add_argument("--hd", action="store_true", default=False, help="Generate high-definition canvas (e.g. 1440x1800 for 4:5).")

    # Background & Gradient Options
    bg_group = parser.add_argument_group("Background & Backdrop Modes")
    bg_group.add_argument("--bg-mode", choices=["gradient", "blur", "radial", "mesh"], default="gradient", help="Canvas backdrop generation mode.")
    bg_group.add_argument("--auto-colors", nargs="?", const=True, default=True, type=parse_bool, help="Auto-extract vibrant dominant colors from image.")
    bg_group.add_argument("--no-auto-colors", dest="auto_colors", action="store_false", help="Disable auto color extraction.")
    bg_group.add_argument("--color1", type=str, default=None, help="Primary background color in hex.")
    bg_group.add_argument("--color2", type=str, default=None, help="Secondary background color in hex.")
    bg_group.add_argument("--color3", type=str, default=None, help="Optional tertiary color for 3-stop or mesh backdrops.")
    bg_group.add_argument("--swap-colors", "--swap", dest="swap_colors", action="store_true", default=False, help="Swap primary and secondary gradient colors.")
    bg_group.add_argument("--angle", "-a", type=float, default=135.0, help="Linear gradient rotation angle in degrees.")
    bg_group.add_argument("--dither", action="store_true", default=True, help="Apply deterministic Bayer dithering.")
    bg_group.add_argument("--no-dither", dest="dither", action="store_false", help="Disable gradient dithering.")
    bg_group.add_argument("--pattern", choices=["none", "dots", "scanlines", "diagonal", "hex"], default=None, help="Subtle geometric pattern overlay on background.")

    # Effects & Typography Options
    fx_group = parser.add_argument_group("Effects, Multi-Layer Text & Branding")
    fx_group.add_argument("--no-shadow", action="store_true", default=False, help="Disable 3D Gaussian drop shadow.")
    fx_group.add_argument("--shadow", nargs="?", const=True, default=None, type=parse_bool, help="Explicitly enable/disable drop shadow.")
    fx_group.add_argument("--glow", action="store_true", default=False, help="Enable colored ambient/neon glow behind poster card.")
    fx_group.add_argument("--glow-color", type=str, default=None, help="Custom glow hex color (default 'auto' uses palette color1).")
    fx_group.add_argument("--border", type=int, default=0, help="Card outline border width in pixels.")
    fx_group.add_argument("--border-color", type=str, default=None, help="Card border hex color.")
    fx_group.add_argument("--reflection", action="store_true", default=False, help="Render faded mirror reflection beneath card.")
    fx_group.add_argument("--vignette", type=float, default=0.0, help="Cinematic edge darkening strength (0.0 to 1.0).")
    fx_group.add_argument("--grain", type=float, default=0.0, help="Film grain intensity (0.0 to 0.5).")
    fx_group.add_argument("--title", type=str, default=None, help="Main game title text layer (supports Persian RTL & English).")
    fx_group.add_argument("--subtitle", type=str, default=None, help="Subtitle text layer (e.g. 'Repack • 48GB' or 'نسخه فشرده').")
    fx_group.add_argument("--badge", type=str, default=None, help="Pill badge text on card corner (e.g. 'NEW', 'UPDATE', 'FREE').")
    fx_group.add_argument("--badge-color", type=str, default="#EF4444", help="Pill badge fill color in hex.")
    fx_group.add_argument("--watermark", "-w", type=str, default="BAZYEPC", help="Watermark branding text. Use '' or 'none' to disable.")
    fx_group.add_argument("--no-watermark", dest="watermark", action="store_const", const=None, help="Disable watermark branding.")
    fx_group.add_argument("--font", type=str, default="Anton", help="Typography font name or TTF file path (e.g. 'Anton', 'Bebas Neue', 'Lalezar', 'Vazirmatn').")
    fx_group.add_argument("--watermark-size", type=int, default=None, help="Watermark font size in pixels.")
    fx_group.add_argument("--watermark-color", "--text-color", dest="watermark_color", type=str, default="#ffffff", help="Watermark text fill color in hex or 'auto' for WCAG contrast.")
    fx_group.add_argument("--stroke-color", type=str, default="#0f172a", help="Watermark stroke outline color in hex.")
    fx_group.add_argument("--stroke-width", type=int, default=3, help="Watermark stroke outline width in pixels.")
    fx_group.add_argument("--watermark-x", type=float, default=None, help="Custom watermark horizontal center.")
    fx_group.add_argument("--watermark-y", type=float, default=None, help="Custom watermark vertical center.")
    fx_group.add_argument("--watermark-pos-mode", choices=["auto", "relative", "absolute"], default="auto", help="Coordinate interpretation mode for custom watermark positioning.")
    fx_group.add_argument("--logo", type=str, default=None, help="Path to transparent PNG channel logo overlay.")
    fx_group.add_argument("--logo-pos", choices=["top_right", "top_left", "bottom_right", "bottom_left"], default="top_right", help="Logo placement corner.")
    fx_group.add_argument("--platforms", type=str, default=None, help="Comma-separated platform badges (e.g. 'pc,steam,ps5,xbox').")

    # Pro AI Options
    pro_group = parser.add_argument_group("Pro Edition (AI Plugin)")
    pro_group.add_argument("--pop-out", action="store_true", default=False, help="3D character pop-out effect above top card border.")
    pro_group.add_argument("--upscale", type=int, choices=[1, 2, 4], default=1, help="Upscale low-res cover by 2x or 4x before framing.")
    pro_group.add_argument("--caption", action="store_true", default=False, help="Generate Persian Telegram post caption (uses Gemini API if GEMINI_API_KEY is set).")

    # Export & Diagnostics Options
    diag_group = parser.add_argument_group("Export & Diagnostics")
    diag_group.add_argument("--quality", type=int, default=95, help="Export JPEG / WebP quality (1 to 100).")
    diag_group.add_argument("--json", action="store_true", default=False, help="Emit structured JSON execution report to stdout for AI agents.")
    diag_group.add_argument("--quiet", action="store_true", default=False, help="Suppress non-error progress output on stdout.")
    diag_group.add_argument("--verbose", "-v", action="store_true", default=False, help="Enable detailed diagnostic logging to stderr.")

    return parser


def create_poster_config(args: argparse.Namespace) -> PosterConfig:
    drop_shadow = True
    if args.no_shadow:
        drop_shadow = False
    if args.shadow is not None:
        drop_shadow = args.shadow

    watermark = args.watermark
    if watermark is not None and (watermark.strip() == "" or watermark.strip().lower() == "none"):
        watermark = None

    auto_colors = args.auto_colors
    if args.color1 and args.color2 and "--auto-colors" not in sys.argv:
        auto_colors = False

    platforms_list = [p.strip() for p in args.platforms.split(",") if p.strip()] if args.platforms else None

    base: Dict[str, Any] = {
        "preset": args.preset,
        "ratio": args.ratio,
        "hd": args.hd,
        "margin": args.margin,
        "curve": args.curve,
        "zoom": args.zoom,
        "pan_x": args.pan_x,
        "pan_y": args.pan_y,
        "auto_trim": args.auto_trim,
        "bg_mode": args.bg_mode,
        "auto_colors": auto_colors,
        "color1": args.color1,
        "color2": args.color2,
        "color3": args.color3,
        "swap_colors": args.swap_colors,
        "angle": args.angle,
        "dither": args.dither,
        "pattern": args.pattern,
        "drop_shadow": drop_shadow,
        "glow": args.glow,
        "glow_color": args.glow_color,
        "border": args.border,
        "border_color": args.border_color,
        "reflection": args.reflection,
        "vignette": args.vignette,
        "grain": args.grain,
        "title": args.title,
        "subtitle": args.subtitle,
        "badge": args.badge,
        "badge_color": args.badge_color,
        "watermark": watermark,
        "watermark_size": args.watermark_size,
        "watermark_font": args.font,
        "watermark_x": args.watermark_x,
        "watermark_y": args.watermark_y,
        "watermark_pos_mode": args.watermark_pos_mode,
        "watermark_color": args.watermark_color,
        "watermark_stroke_color": args.stroke_color,
        "watermark_stroke_width": args.stroke_width,
        "logo": args.logo,
        "logo_pos": args.logo_pos,
        "platforms": platforms_list,
        "pop_out": args.pop_out,
        "upscale": args.upscale,
        "quality": args.quality,
    }

    if args.preset and args.preset.strip().lower() != "auto":
        preset_vals = get_preset(args.preset)
        # Apply preset defaults only where user didn't pass explicit CLI flags
        cli_str = " ".join(sys.argv)
        flag_map = {
            "watermark_font": "--font",
            "watermark_color": "--watermark-color",
            "watermark_stroke_color": "--stroke-color",
            "curve": "--curve",
            "margin": "--margin",
            "angle": "--angle",
            "color1": "--color1",
            "color2": "--color2",
            "bg_mode": "--bg-mode",
            "glow": "--glow",
            "border": "--border",
            "border_color": "--border-color",
            "vignette": "--vignette",
            "grain": "--grain",
            "pattern": "--pattern",
            "reflection": "--reflection",
        }
        for k, v in preset_vals.items():
            flag = flag_map.get(k)
            if not flag or flag not in cli_str:
                base[k] = v

    return PosterConfig.from_dict(base).normalize()


def process_single_image(args: argparse.Namespace, config: PosterConfig) -> int:
    t0 = time.perf_counter()
    warnings_list: List[str] = []

    if args.input == "-":
        raw_bytes = sys.stdin.buffer.read()
        if not raw_bytes:
            sys.stderr.write("Error: No image data received on stdin.\n")
            return 1
        input_source: Any = raw_bytes
        stem = "stdin"
        suffix = ".jpg"
        parent_dir = Path(".")
    else:
        input_path = Path(args.input)
        if not input_path.is_file():
            sys.stderr.write(f"Error: Input file does not exist: {input_path}\n")
            return 1
        input_source = input_path
        stem = input_path.stem
        suffix = input_path.suffix or ".jpg"
        parent_dir = input_path.parent

    ratios_to_run = [r.strip() for r in args.ratios.split(",") if r.strip()] if args.ratios else [config.ratio]
    outputs_generated: List[str] = []

    try:
        for r_idx, r_str in enumerate(ratios_to_run):
            run_cfg = PosterConfig.from_dict(config.to_dict(), ratio=r_str).normalize()
            r_tag = f"_{r_str.replace(':', 'x')}" if len(ratios_to_run) > 1 else ""

            if args.output == "-":
                res_img = process_poster(input_image=input_source, config=run_cfg, output_path=None)
                bio = io.BytesIO()
                res_img.save(bio, format="JPEG", quality=run_cfg.quality, subsampling=0)
                sys.stdout.buffer.write(bio.getvalue())
                sys.stdout.buffer.flush()
                return 0

            if args.output:
                out_target = Path(args.output)
                if out_target.is_dir() or str(args.output).endswith(("/", "\\")):
                    out_target.mkdir(parents=True, exist_ok=True)
                    output_path = out_target / f"{stem}_poster{r_tag}{suffix}"
                else:
                    out_target.parent.mkdir(parents=True, exist_ok=True)
                    if r_tag:
                        output_path = out_target.parent / f"{out_target.stem}{r_tag}{out_target.suffix or '.jpg'}"
                    else:
                        output_path = out_target
            else:
                output_path = parent_dir / f"{stem}_poster{r_tag}{suffix}"

            res_img = process_poster(input_image=input_source, config=run_cfg, output_path=output_path)
            outputs_generated.append(str(output_path))

        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

        caption_info: Optional[Dict[str, Any]] = None
        if args.caption:
            pro = get_pro_plugin()
            if pro and hasattr(pro, "generate_caption_ai"):
                caption_info = pro.generate_caption_ai(res_img, title=config.title, preset=config.preset)

        if args.json:
            c1, c2 = extract_dominant_colors(res_img)
            report = {
                "status": "ok",
                "output": outputs_generated[0] if len(outputs_generated) == 1 else outputs_generated,
                "outputs": outputs_generated,
                "ratios": ratios_to_run,
                "preset": config.preset or "default",
                "colors": [rgb_to_hex(c1), rgb_to_hex(c2)],
                "elapsed_ms": elapsed_ms,
                "warnings": warnings_list,
            }
            if caption_info:
                report["caption"] = caption_info
            print(json.dumps(report, ensure_ascii=False))
        elif not args.quiet:
            for out_p in outputs_generated:
                print(f"Successfully processed poster: {out_p}")
            if caption_info and caption_info.get("caption_fa"):
                print(f"\n--- Caption ---\n{caption_info['caption_fa']}")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error processing poster '{args.input}': {err}\n")
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


def process_batch(args: argparse.Namespace, config: PosterConfig) -> int:
    batch_path = Path(args.batch_dir)
    if not batch_path.is_dir():
        sys.stderr.write(f"Error: Batch directory does not exist or is not a directory: {batch_path}\n")
        return 1

    out_dir = Path(args.output) if args.output else (batch_path / "output")
    out_dir.mkdir(parents=True, exist_ok=True)

    try:
        entries = sorted(list(batch_path.iterdir()))
    except Exception as err:
        sys.stderr.write(f"Error reading directory '{batch_path}': {err}\n")
        return 1

    files = [e for e in entries if e.is_file()]
    image_files: List[Path] = []
    for f in files:
        if f.suffix.lower() in IMAGE_EXTENSIONS:
            image_files.append(f)
        else:
            sys.stderr.write(f"[INFO] Skipping non-image file: {f.name}\n")

    if not image_files:
        sys.stderr.write(f"[WARNING] No supported image files found in '{batch_path}'.\n")
        return 0

    success_count = 0
    failure_count = 0

    for img_path in image_files:
        out_file = (out_dir / f"{img_path.stem}_poster{img_path.suffix}") if out_dir == batch_path else (out_dir / img_path.name)
        try:
            process_poster(input_image=img_path, config=config, output_path=out_file)
            success_count += 1
            if not args.quiet:
                print(f"Processed: {img_path.name} -> {out_file.name}")
        except Exception as err:
            sys.stderr.write(f"[WARNING] Skipping corrupt or unreadable image '{img_path.name}': {err}\n")
            failure_count += 1

    if not args.quiet:
        print(f"\nBatch processing complete: {success_count} succeeded, {failure_count} failed.")

    if success_count == 0 and failure_count > 0:
        sys.stderr.write("Error: All images in batch failed to process.\n")
        return 1
    return 0


def process_collage_mode(args: argparse.Namespace, config: PosterConfig) -> int:
    t0 = time.perf_counter()
    output_path = Path(args.output) if args.output else Path("collage_output.jpg")
    if not output_path.suffix:
        output_path = output_path.with_suffix(".jpg")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pil_images = [Image.open(p).convert("RGB") for p in args.collage]
        res = create_game_collage(
            images=pil_images,
            ratio=config.ratio,
            curve=config.curve,
            auto_colors=config.auto_colors,
            color1=rgb_to_hex(config.color1) if isinstance(config.color1, tuple) else config.color1,
            color2=rgb_to_hex(config.color2) if isinstance(config.color2, tuple) else config.color2,
            angle=config.angle,
            watermark=config.watermark,
            watermark_font=config.watermark_font or "bebas_neue",
            watermark_color=rgb_to_hex(config.watermark_color) if isinstance(config.watermark_color, tuple) else str(config.watermark_color),
            watermark_stroke_color=rgb_to_hex(config.watermark_stroke_color) if isinstance(config.watermark_stroke_color, tuple) else str(config.watermark_stroke_color),
            watermark_stroke_width=config.watermark_stroke_width,
            template=args.template,
            fit=args.fit,
            title=config.title,
            subtitle=config.subtitle,
            badge=config.badge,
        )
        res.save(output_path, format="JPEG", quality=config.quality, subsampling=0)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        if args.json:
            print(json.dumps({
                "status": "ok",
                "output": str(output_path),
                "template": args.template or "auto",
                "images_count": len(pil_images),
                "elapsed_ms": elapsed_ms,
            }, ensure_ascii=False))
        elif not args.quiet:
            print(f"Successfully created collage with {len(pil_images)} images: {output_path}")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error creating collage: {err}\n")
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


def process_watch_mode(args: argparse.Namespace, config: PosterConfig) -> int:
    inbox = Path(args.watch[0])
    outbox = Path(args.watch[1])
    inbox.mkdir(parents=True, exist_ok=True)
    outbox.mkdir(parents=True, exist_ok=True)
    seen: Dict[str, float] = {}
    if not args.quiet:
        print(f"Watching '{inbox}' -> '{outbox}' (Ctrl+C to stop)...")
    try:
        while True:
            for entry in os.scandir(inbox):
                if not entry.is_file():
                    continue
                p = Path(entry.path)
                if p.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                mtime = entry.stat().st_mtime
                if seen.get(p.name) == mtime:
                    continue
                out_file = outbox / p.name
                try:
                    process_poster(input_image=p, config=config, output_path=out_file)
                    seen[p.name] = mtime
                    if not args.quiet:
                        print(f"[WATCH] Processed: {p.name} -> {out_file}")
                except Exception as e:
                    sys.stderr.write(f"[WATCH ERROR] {p.name}: {e}\n")
            time.sleep(1.5)
    except KeyboardInterrupt:
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    log_level = logging.DEBUG if args.verbose else (logging.ERROR if args.quiet else logging.WARNING)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s", stream=sys.stderr)

    if args.list_presets:
        presets = list_presets()
        if args.json:
            print(json.dumps(presets, ensure_ascii=False, indent=2))
        else:
            for k, v in presets.items():
                print(f"{k:18s} - {v.get('description', 'Custom preset')}")
        return 0

    if args.list_templates:
        tpls = list_collage_templates()
        if args.json:
            print(json.dumps({k: {"name": v["name"], "slots": v["slots"]} for k, v in tpls.items()}, indent=2))
        else:
            for k, v in tpls.items():
                print(f"{k:18s} ({v['slots']} slots) - {v['name']}")
        return 0

    input_modes = sum(1 for m in [args.input, args.batch_dir, args.collage, args.watch] if m is not None)
    if input_modes == 0:
        sys.stderr.write("Error: Either --input or --batch-dir must be specified (or --collage for collages).\n\n")
        parser.print_usage(file=sys.stderr)
        return 2

    if input_modes > 1:
        if args.input and args.batch_dir:
            sys.stderr.write("Error: Cannot specify both --input and --batch-dir.\n")
        else:
            sys.stderr.write("Error: Cannot specify more than one of --input, --batch-dir, --collage, or --watch.\n")
        return 2

    config = create_poster_config(args)

    if args.watch:
        return process_watch_mode(args, config)
    elif args.collage:
        return process_collage_mode(args, config)
    elif args.input:
        return process_single_image(args, config)
    else:
        return process_batch(args, config)


if __name__ == "__main__":
    sys.exit(main())
