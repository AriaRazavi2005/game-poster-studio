"""
poster_studio.telegram_bridge
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Headless Python pipeline bridge for @BazyePc Telegram channel publishing automation.
Exposes create_game_poster(...) for direct in-memory (BytesIO) and on-disk poster generation
with zero display/X11 dependencies.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path
import sys
from typing import Any, Dict, Optional, Tuple, Union

from PIL import Image

# Ensure repository root and package directory are in sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
POSTER_STUDIO_DIR = Path(__file__).resolve().parent
for p in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Robust import: works from root or when installed as package
try:
    from poster_studio.core.processor import (
        PosterConfig,
        PosterProcessor,
        PosterProcessingError,
        process_poster,
    )
except ImportError:
    from core.processor import (
        PosterConfig,
        PosterProcessor,
        PosterProcessingError,
        process_poster,
    )

logger = logging.getLogger("poster_studio.telegram_bridge")


# ==============================================================================
# EXCEPTION HIERARCHY
# ==============================================================================

class TelegramBridgeError(RuntimeError):
    """Base exception for telegram_bridge operations."""
    pass


class InvalidImageError(TelegramBridgeError, ValueError):
    """Raised when the input image is missing, corrupt, or unsupported."""
    pass


class ConfigurationError(TelegramBridgeError, ValueError):
    """Raised when configuration parameters (ratio, margin, curve, etc.) are invalid."""
    pass


class ExportError(TelegramBridgeError, IOError):
    """Raised when saving the processed image to disk fails."""
    pass


# ==============================================================================
# MAIN BRIDGE API
# ==============================================================================

def create_game_poster(
    input_image: Union[str, Path, Image.Image, bytes, bytearray, io.BytesIO],
    output_image: Optional[Union[str, Path]] = None,
    ratio: str = "4:5",
    curve: int = 45,
    margin: Union[int, float] = 50,
    auto_colors: bool = True,
    color1: Optional[str] = None,
    color2: Optional[str] = None,
    swap_colors: bool = False,
    angle: float = 135.0,
    no_shadow: bool = False,
    watermark: Optional[str] = "BAZYEPC",
    zoom: float = 1.0,
    quality: int = 95,
    **kwargs: Any
) -> Union[Path, Image.Image]:
    """
    Headless game poster generation pipeline for @BazyePc Telegram publishing.

    Transforms raw game posters/screenshots into aesthetically framed promotional
    cards with dynamic 2-color linear gradients, supersampled rounded corners,
    realistic 3D Gaussian drop shadows, and branding watermark.

    Parameters:
        input_image: File path (str/Path), PIL Image, raw bytes, or BytesIO stream.
        output_image: Optional destination path. If None, returns PIL.Image.Image.
                      If specified, saves the poster to disk and returns pathlib.Path.
        ratio: Canvas aspect ratio preset ('4:5', '1:1', '9:16', '16:9', '4:3', '21:9').
        curve: Corner curvature radius in pixels (default: 45).
        margin: Margin spacing around poster card (default: 50).
        auto_colors: Automatically extract 2 dominant vibrant colors from poster.
        color1: Optional hex override for primary gradient color.
        color2: Optional hex override for secondary gradient color.
        swap_colors: Invert gradient endpoint orientation.
        angle: Linear gradient rotation angle in degrees (default: 135.0).
        no_shadow: Disable 3D Gaussian drop shadow if True (default: False).
        watermark: Watermark text (default: 'BAZYEPC'). None or '' disables watermark.
        zoom: Fit zoom multiplier (default: 1.0).
        quality: JPEG export quality 1-100 (default: 95).
        **kwargs: Parameter aliases and advanced styling options.

    Returns:
        PIL.Image.Image if output_image is None, else pathlib.Path to the saved file.
    """
    # 1. Input image resolution and normalization
    pil_input: Union[Image.Image, Path]
    if isinstance(input_image, (bytes, bytearray)):
        try:
            pil_input = Image.open(io.BytesIO(input_image))
            pil_input.load()
        except Exception as e:
            raise InvalidImageError(f"Failed to decode image from raw bytes: {e}") from e
    elif isinstance(input_image, io.BytesIO):
        try:
            pil_input = Image.open(input_image)
            pil_input.load()
        except Exception as e:
            raise InvalidImageError(f"Failed to decode image from BytesIO stream: {e}") from e
    elif isinstance(input_image, (str, Path)):
        in_path = Path(input_image)
        if not in_path.exists():
            raise FileNotFoundError(f"Input image file not found: {in_path}")
        if not in_path.is_file():
            raise InvalidImageError(f"Input image path is not a file: {in_path}")
        pil_input = in_path
    elif isinstance(input_image, Image.Image):
        pil_input = input_image
    else:
        raise InvalidImageError(
            f"Unsupported input_image type '{type(input_image).__name__}'. "
            "Expected str, Path, PIL.Image.Image, bytes, or BytesIO."
        )

    # 2. Alias resolution
    drop_shadow = not no_shadow
    if "shadow" in kwargs:
        drop_shadow = bool(kwargs.pop("shadow"))
    elif "no_shadow" in kwargs:
        drop_shadow = not bool(kwargs.pop("no_shadow"))

    if "watermark_text" in kwargs:
        watermark = kwargs.pop("watermark_text")

    if "swap" in kwargs:
        swap_colors = bool(kwargs.pop("swap"))

    if "spacing" in kwargs:
        margin = kwargs.pop("spacing")
    if "radius" in kwargs:
        curve = kwargs.pop("radius")

    # 3. Build PosterConfig
    try:
        config = PosterConfig.from_dict(
            {
                "ratio": ratio,
                "curve": curve,
                "margin": margin,
                "auto_colors": auto_colors,
                "color1": color1,
                "color2": color2,
                "swap_colors": swap_colors,
                "angle": angle,
                "drop_shadow": drop_shadow,
                "watermark": watermark,
                "zoom": zoom,
                "quality": quality,
            },
            **kwargs
        )
    except ValueError as e:
        raise ConfigurationError(f"Invalid configuration parameter: {e}") from e

    # 4. Resolve output destination
    dest_path: Optional[Path] = None
    if output_image is not None:
        dest_path = Path(output_image)
        if not dest_path.suffix:
            dest_path = dest_path.with_suffix(".jpg")

    # 5. Execute processing pipeline
    try:
        result_image = process_poster(
            input_image=pil_input,
            config=config,
            output_path=dest_path,
        )
    except FileNotFoundError:
        raise
    except ValueError as e:
        raise ConfigurationError(f"Configuration or geometry error: {e}") from e
    except PosterProcessingError as e:
        raise TelegramBridgeError(f"Poster processing failed: {e}") from e
    except (IOError, OSError) as e:
        if dest_path is not None:
            raise ExportError(f"Failed to export poster image to '{dest_path}': {e}") from e
        raise TelegramBridgeError(f"I/O error during poster generation: {e}") from e
    except Exception as e:
        raise TelegramBridgeError(f"Unexpected error in poster generation: {e}") from e

    # 6. Return according to contract
    if dest_path is not None:
        return dest_path
    return result_image


# ==============================================================================
# TELEGRAM BOT HELPER UTILITIES
# ==============================================================================

def poster_to_bytes(
    poster: Image.Image,
    format: str = "JPEG",
    quality: int = 95
) -> bytes:
    """
    Serializes a PIL poster Image into compressed bytes for Telegram bot transmission.
    """
    bio = io.BytesIO()
    fmt = format.upper()
    if fmt in ("JPG", "JPEG"):
        poster.save(bio, format="JPEG", quality=quality, subsampling=0)
    elif fmt == "PNG":
        poster.save(bio, format="PNG", optimize=True)
    else:
        poster.save(bio, format=fmt, quality=quality)
    return bio.getvalue()


def poster_to_bytesio(
    poster: Image.Image,
    format: str = "JPEG",
    quality: int = 95
) -> io.BytesIO:
    """
    Serializes a PIL poster Image into an in-memory BytesIO stream reset to position 0.
    """
    bio = io.BytesIO(poster_to_bytes(poster, format=format, quality=quality))
    bio.seek(0)
    return bio


__all__ = [
    "create_game_poster",
    "poster_to_bytes",
    "poster_to_bytesio",
    "TelegramBridgeError",
    "InvalidImageError",
    "ConfigurationError",
    "ExportError",
]
