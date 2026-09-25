#!/usr/bin/env python3
"""
Game Poster Studio — Headless CLI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Full-featured headless command-line interface for styling game posters with
dynamic linear gradients, 3D drop shadows, anti-aliased rounded corners,
and branding watermarks.

Supports single-image styling and robust directory batch processing.
Zero display / GUI dependencies (Linux headless server ready).
"""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path
import sys
from typing import Any, List, Optional, Set, Union
from PIL import Image

# Ensure repository root and package are in sys.path dynamically
REPO_ROOT = Path(__file__).resolve().parent
POSTER_STUDIO_DIR = REPO_ROOT / "poster_studio"

for p in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Import master image processing pipeline
try:
    from poster_studio.core.processor import (
        PosterConfig,
        PosterProcessingError,
        process_poster,
    )
except ImportError:
    try:
        from core.processor import (
            PosterConfig,
            PosterProcessingError,
            process_poster,
        )
    except ImportError as err:
        sys.stderr.write(f"[FATAL] Failed to import core processing engine: {err}\n")
        sys.exit(1)

# Supported image file extensions for batch processing
IMAGE_EXTENSIONS: Set[str] = {".jpg", ".jpeg", ".png", ".webp"}


def parse_bool(value: Any) -> bool:
    """Parses shell boolean representations into a Python boolean."""
    if isinstance(value, bool):
        return value
    val_str = str(value).strip().lower()
    if val_str in ("yes", "true", "t", "y", "1"):
        return True
    elif val_str in ("no", "false", "f", "n", "0"):
        return False
    raise argparse.ArgumentTypeError(f"Boolean value expected, got {value!r}")


def parse_margin(value: Any) -> Union[int, float]:
    """
    Parses margin string or numeric into pixel integer or float fraction.
    Supports: '50', '50px', '10%', '0.05'.
    """
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
    """Parses corner radius curve into integer pixels, stripping optional 'px' suffix."""
    val_str = str(value).strip().lower()
    if val_str.endswith("px"):
        return int(float(val_str[:-2]))
    return int(val_str)


def build_arg_parser() -> argparse.ArgumentParser:
    """Constructs and returns the comprehensive command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="cli.py",
        description="Game Poster Studio — Headless CLI & Batch Poster Generator",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # I/O Target Options
    io_group = parser.add_argument_group("Input / Output Targets")
    io_group.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help="Path to single input image file.",
    )
    io_group.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Destination path for output image (single mode) or directory (batch mode).",
    )
    io_group.add_argument(
        "--batch-dir", "-b",
        type=str,
        default=None,
        help="Path to directory containing images to process in batch mode.",
    )
    io_group.add_argument(
        "--collage",
        nargs="+",
        type=str,
        default=None,
        help="List of 2 to 4 image paths to generate a multi-image gaming collage.",
    )

    # Canvas & Framing Options
    canvas_group = parser.add_argument_group("Canvas & Framing")
    canvas_group.add_argument(
        "--ratio", "-r",
        type=str,
        default="4:5",
        help="Target canvas aspect ratio (4:5, 1:1, 9:16, 16:9, 4:3, 21:9).",
    )
    canvas_group.add_argument(
        "--curve", "-c",
        type=parse_curve,
        default=45,
        help="Corner curvature radius in pixels (e.g. 45 or 45px).",
    )
    canvas_group.add_argument(
        "--margin", "-m",
        type=parse_margin,
        default=50,
        help="Margin spacing around poster in pixels (e.g. 50, 50px) or percentage (e.g. 5%%).",
    )
    canvas_group.add_argument(
        "--zoom", "-z",
        type=float,
        default=1.0,
        help="Poster zoom factor (0.1 to 3.0).",
    )
    canvas_group.add_argument(
        "--pan-x",
        type=float,
        default=0.0,
        help="Poster horizontal pan offset in canvas pixels.",
    )
    canvas_group.add_argument(
        "--pan-y",
        type=float,
        default=0.0,
        help="Poster vertical pan offset in canvas pixels.",
    )
    canvas_group.add_argument(
        "--hd",
        action="store_true",
        default=False,
        help="Generate high-definition canvas (e.g. 1440x1800 for 4:5).",
    )

    # Background & Gradient Options
    bg_group = parser.add_argument_group("Background & Gradient")
    bg_group.add_argument(
        "--auto-colors",
        nargs="?",
        const=True,
        default=True,
        type=parse_bool,
        help="Auto-extract vibrant dominant colors from image (flag or boolean).",
    )
    bg_group.add_argument(
        "--no-auto-colors",
        dest="auto_colors",
        action="store_false",
        help="Disable auto color extraction (use with --color1 and --color2).",
    )
    bg_group.add_argument(
        "--color1",
        type=str,
        default=None,
        help="Primary background color in hex (e.g. #FF5733).",
    )
    bg_group.add_argument(
        "--color2",
        type=str,
        default=None,
        help="Secondary background color in hex (e.g. #1E3A8A).",
    )
    bg_group.add_argument(
        "--swap-colors", "--swap",
        dest="swap_colors",
        action="store_true",
        default=False,
        help="Swap primary and secondary gradient colors.",
    )
    bg_group.add_argument(
        "--angle", "-a",
        type=float,
        default=135.0,
        help="Linear gradient rotation angle in degrees (0.0 to 360.0).",
    )

    # Effects & Branding Options
    fx_group = parser.add_argument_group("Effects & Branding")
    fx_group.add_argument(
        "--no-shadow",
        action="store_true",
        default=False,
        help="Disable realistic 3D Gaussian drop shadow.",
    )
    fx_group.add_argument(
        "--shadow",
        nargs="?",
        const=True,
        default=None,
        type=parse_bool,
        help="Explicitly enable/disable drop shadow (--shadow true / --shadow false).",
    )
    fx_group.add_argument(
        "--watermark", "-w",
        type=str,
        default="BAZYEPC",
        help="Watermark branding text. Use empty string '' or 'none' to disable.",
    )
    fx_group.add_argument(
        "--no-watermark",
        dest="watermark",
        action="store_const",
        const=None,
        help="Disable watermark branding.",
    )
    fx_group.add_argument(
        "--font",
        type=str,
        default="Anton",
        help="Gaming watermark font name or TTF file path (e.g. 'Anton', 'Bebas Neue', 'Orbitron', 'Russo One').",
    )
    fx_group.add_argument(
        "--watermark-size",
        type=int,
        default=None,
        help="Watermark font size in pixels.",
    )
    fx_group.add_argument(
        "--watermark-color", "--text-color",
        dest="watermark_color",
        type=str,
        default="#ffffff",
        help="Watermark text fill color in hex (e.g. #ffffff).",
    )
    fx_group.add_argument(
        "--stroke-color",
        type=str,
        default="#0f172a",
        help="Watermark stroke outline color in hex (e.g. #0f172a).",
    )
    fx_group.add_argument(
        "--stroke-width",
        type=int,
        default=3,
        help="Watermark stroke outline width in pixels.",
    )
    fx_group.add_argument(
        "--watermark-x",
        type=float,
        default=None,
        help="Custom watermark horizontal center (0.0 to 1.0 normalized or absolute px).",
    )
    fx_group.add_argument(
        "--watermark-y",
        type=float,
        default=None,
        help="Custom watermark vertical center (0.0 to 1.0 normalized or absolute px).",
    )

    # Export & Diagnostics Options
    diag_group = parser.add_argument_group("Export & Diagnostics")
    diag_group.add_argument(
        "--quality",
        type=int,
        default=95,
        help="Export JPEG / WebP quality (1 to 100).",
    )
    diag_group.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress non-error progress output on stdout.",
    )
    diag_group.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable detailed diagnostic logging to stderr.",
    )

    return parser


def create_poster_config(args: argparse.Namespace) -> PosterConfig:
    """Constructs and normalizes PosterConfig from parsed CLI arguments."""
    # Resolve shadow toggle
    drop_shadow = True
    if args.no_shadow:
        drop_shadow = False
    if args.shadow is not None:
        drop_shadow = args.shadow

    # Resolve watermark text
    watermark = args.watermark
    if watermark is not None and (watermark.strip() == "" or watermark.strip().lower() == "none"):
        watermark = None

    # Resolve auto_colors vs explicit color specifications
    auto_colors = args.auto_colors
    if args.color1 and args.color2 and "--auto-colors" not in sys.argv:
        auto_colors = False

    config = PosterConfig(
        ratio=args.ratio,
        hd=args.hd,
        margin=args.margin,
        curve=args.curve,
        zoom=args.zoom,
        pan_x=args.pan_x,
        pan_y=args.pan_y,
        auto_colors=auto_colors,
        color1=args.color1,
        color2=args.color2,
        swap_colors=args.swap_colors,
        angle=args.angle,
        drop_shadow=drop_shadow,
        watermark=watermark,
        watermark_size=args.watermark_size,
        watermark_font=args.font,
        watermark_x=args.watermark_x,
        watermark_y=args.watermark_y,
        watermark_color=args.watermark_color,
        watermark_stroke_color=args.stroke_color,
        watermark_stroke_width=args.stroke_width,
        quality=args.quality,
    )
    return config.normalize()


def process_single_image(args: argparse.Namespace, config: PosterConfig) -> int:
    """Handles processing of a single input image."""
    input_path = Path(args.input)
    if not input_path.is_file():
        sys.stderr.write(f"Error: Input file does not exist: {input_path}\n")
        return 1

    # Determine destination output path
    if args.output:
        out_target = Path(args.output)
        if out_target.is_dir() or str(args.output).endswith(("/", "\\")):
            out_target.mkdir(parents=True, exist_ok=True)
            output_path = out_target / f"{input_path.stem}_poster{input_path.suffix}"
        else:
            out_target.parent.mkdir(parents=True, exist_ok=True)
            output_path = out_target
    else:
        output_path = input_path.parent / f"{input_path.stem}_poster{input_path.suffix}"

    try:
        process_poster(
            input_image=input_path,
            config=config,
            output_path=output_path,
        )
        if not args.quiet:
            print(f"Successfully processed poster: {output_path}")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error processing poster '{input_path}': {err}\n")
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


def process_batch(args: argparse.Namespace, config: PosterConfig) -> int:
    """Handles directory batch processing with extension filtering and corrupt file skipping."""
    batch_path = Path(args.batch_dir)
    if not batch_path.is_dir():
        sys.stderr.write(f"Error: Batch directory does not exist or is not a directory: {batch_path}\n")
        return 1

    # Resolve output directory
    if args.output:
        out_dir = Path(args.output)
    else:
        out_dir = batch_path / "output"

    out_dir.mkdir(parents=True, exist_ok=True)

    # Scan directory
    try:
        entries = sorted(list(batch_path.iterdir()))
    except Exception as err:
        sys.stderr.write(f"Error reading directory '{batch_path}': {err}\n")
        return 1

    # Filter files
    files = [e for e in entries if e.is_file()]
    image_files: List[Path] = []
    non_image_files: List[Path] = []

    for f in files:
        if f.suffix.lower() in IMAGE_EXTENSIONS:
            image_files.append(f)
        else:
            non_image_files.append(f)

    # Log skipped non-image files
    for n in non_image_files:
        sys.stderr.write(f"[INFO] Skipping non-image file: {n.name}\n")

    if not image_files:
        sys.stderr.write(f"[WARNING] No supported image files found in '{batch_path}'.\n")
        return 0

    success_count = 0
    failure_count = 0

    for img_path in image_files:
        # Determine output file name
        if out_dir == batch_path:
            out_file = out_dir / f"{img_path.stem}_poster{img_path.suffix}"
        else:
            out_file = out_dir / img_path.name

        try:
            process_poster(
                input_image=img_path,
                config=config,
                output_path=out_file,
            )
            success_count += 1
            if not args.quiet:
                print(f"Processed: {img_path.name} -> {out_file.name}")
        except Exception as err:
            sys.stderr.write(f"[WARNING] Skipping corrupt or unreadable image '{img_path.name}': {err}\n")
            failure_count += 1

    if not args.quiet:
        print(f"\nBatch processing complete: {success_count} succeeded, {failure_count} failed.")

    # Return 0 if at least one image succeeded or if there were no corruptions
    if success_count == 0 and failure_count > 0:
        sys.stderr.write("Error: All images in batch failed to process.\n")
        return 1

    return 0


def process_collage_mode(args: argparse.Namespace, config: PosterConfig) -> int:
    """Processes multiple images into a multi-image gaming collage."""
    from poster_studio.core.collage import create_game_collage

    if not args.output:
        output_path = Path("collage_output.jpg")
    else:
        output_path = Path(args.output)
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
            color1=config.color1,
            color2=config.color2,
            angle=config.angle,
            watermark=config.watermark,
            watermark_font=config.watermark_font,
            watermark_color=config.watermark_color,
            watermark_stroke_color=config.watermark_stroke_color,
            watermark_stroke_width=config.watermark_stroke_width
        )
        res.save(output_path, format="JPEG", quality=config.quality, subsampling=0)
        if not args.quiet:
            print(f"Successfully created collage with {len(pil_images)} images: {output_path}")
        return 0
    except Exception as err:
        sys.stderr.write(f"Error creating collage: {err}\n")
        if args.verbose:
            import traceback
            traceback.print_exc(file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entrypoint function."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else (logging.ERROR if args.quiet else logging.WARNING)
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s", stream=sys.stderr)

    # Mutual validation for input targets
    input_modes = sum(1 for m in [args.input, args.batch_dir, args.collage] if m is not None)
    if input_modes == 0:
        sys.stderr.write("Error: One of --input, --batch-dir, or --collage must be specified.\n\n")
        parser.print_usage(file=sys.stderr)
        return 2

    if input_modes > 1:
        sys.stderr.write("Error: Cannot specify more than one of --input, --batch-dir, or --collage.\n")
        return 2

    config = create_poster_config(args)

    if args.collage:
        return process_collage_mode(args, config)
    elif args.input:
        return process_single_image(args, config)
    else:
        return process_batch(args, config)


if __name__ == "__main__":
    sys.exit(main())
