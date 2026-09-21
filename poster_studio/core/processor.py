"""
poster_studio.core.processor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Master pipeline orchestrator compositing all image layers:
Gradient Background -> Gaussian Drop Shadow -> Rounded Poster Card -> Watermark.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
from PIL import Image

from poster_studio.core.palette import (
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
    extract_dominant_colors,
    parse_hex_color,
)
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.geometry import (
    PosterPlacement,
    calculate_poster_placement,
    resolve_canvas_size,
)
from poster_studio.core.mask import create_rounded_mask
from poster_studio.core.shadow import apply_drop_shadow, create_drop_shadow
from poster_studio.core.watermark import apply_watermark

logger = logging.getLogger("poster_studio.processor")

ColorType = Union[Tuple[int, int, int], str]


@dataclass
class PosterConfig:
    """
    Configuration parameters for Game Poster Studio pipeline.

    All parameters provide sensible defaults matching the Collage Maker layout:
    - 4:5 aspect ratio (1080x1350)
    - 50px margins
    - 45px corner radius
    - 135.0 degree gradient angle
    - Auto-extracted vibrant background colors
    - 3D Gaussian drop shadow enabled
    - "BAZYEPC" watermark enabled
    """
    # Canvas Geometry & Aspect Ratio
    ratio: str = "4:5"
    hd: bool = False
    custom_canvas_size: Optional[Tuple[int, int]] = None

    # Poster Framing & Placement
    margin: Union[int, float] = 50
    curve: int = 45
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    # Background & Gradient
    auto_colors: bool = True
    color1: Optional[ColorType] = None
    color2: Optional[ColorType] = None
    swap_colors: bool = False
    angle: float = 135.0

    # 3D Drop Shadow
    drop_shadow: bool = True
    shadow_offset_y: int = 15
    shadow_blur: int = 25
    shadow_opacity: float = 0.48

    # Watermark / Branding
    watermark: Optional[str] = "BAZYEPC"
    watermark_size: Optional[int] = None
    watermark_font: Optional[str] = None
    watermark_x: Optional[float] = None
    watermark_y: Optional[float] = None
    watermark_color: ColorType = (255, 255, 255)
    watermark_stroke_color: ColorType = (15, 23, 42)
    watermark_stroke_width: int = 3

    # Supersampling & Export Quality
    supersample_factor: int = 2
    quality: int = 95

    def __post_init__(self) -> None:
        """Validate and normalize configuration parameters upon creation."""
        self.normalize()

    def normalize(self) -> PosterConfig:
        """
        Normalizes aliases, color representations, and boundary limits.

        Returns:
            self for method chaining.
        """
        # 1. Normalize angle into [0.0, 360.0)
        self.angle = float(self.angle) % 360.0

        # 2. Clamp numeric boundaries
        self.curve = max(0, int(self.curve))
        if isinstance(self.margin, int):
            self.margin = max(0, self.margin)
        elif isinstance(self.margin, float):
            self.margin = max(0.0, min(0.45, self.margin))
        self.zoom = max(0.1, min(3.0, float(self.zoom)))
        self.quality = max(1, min(100, int(self.quality)))
        self.supersample_factor = max(1, min(4, int(self.supersample_factor)))
        self.watermark_stroke_width = max(0, min(20, int(self.watermark_stroke_width)))

        # 3. Normalize colors if strings provided
        if isinstance(self.color1, str):
            self.color1 = parse_hex_color(self.color1)
        if isinstance(self.color2, str):
            self.color2 = parse_hex_color(self.color2)
        if isinstance(self.watermark_color, str):
            self.watermark_color = parse_hex_color(self.watermark_color)
        if isinstance(self.watermark_stroke_color, str):
            self.watermark_stroke_color = parse_hex_color(self.watermark_stroke_color)

        # 4. Normalize watermark string (treat empty string as None)
        if self.watermark is not None and not str(self.watermark).strip():
            self.watermark = None

        return self

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs: Any) -> PosterConfig:
        """
        Instantiates PosterConfig from dictionary and keyword arguments with alias support.
        """
        combined = {**data, **kwargs}

        # Resolve aliases
        if "shadow" in combined and "drop_shadow" not in combined:
            combined["drop_shadow"] = combined.pop("shadow")
        if "no_shadow" in combined:
            combined["drop_shadow"] = not combined.pop("no_shadow")
        if "watermark_text" in combined and "watermark" not in combined:
            combined["watermark"] = combined.pop("watermark_text")
        if "spacing" in combined and "margin" not in combined:
            combined["margin"] = combined.pop("spacing")
        if "radius" in combined and "curve" not in combined:
            combined["curve"] = combined.pop("radius")

        # Filter only valid dataclass fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in combined.items() if k in valid_fields}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        """Returns dictionary representation of configuration."""
        return {
            "ratio": self.ratio,
            "hd": self.hd,
            "custom_canvas_size": self.custom_canvas_size,
            "margin": self.margin,
            "curve": self.curve,
            "zoom": self.zoom,
            "pan_x": self.pan_x,
            "pan_y": self.pan_y,
            "auto_colors": self.auto_colors,
            "color1": self.color1,
            "color2": self.color2,
            "swap_colors": self.swap_colors,
            "angle": self.angle,
            "drop_shadow": self.drop_shadow,
            "shadow_offset_y": self.shadow_offset_y,
            "shadow_blur": self.shadow_blur,
            "shadow_opacity": self.shadow_opacity,
            "watermark": self.watermark,
            "watermark_size": self.watermark_size,
            "watermark_font": self.watermark_font,
            "watermark_x": self.watermark_x,
            "watermark_y": self.watermark_y,
            "watermark_color": self.watermark_color,
            "watermark_stroke_color": self.watermark_stroke_color,
            "watermark_stroke_width": self.watermark_stroke_width,
            "supersample_factor": self.supersample_factor,
            "quality": self.quality,
        }


class PosterProcessingError(RuntimeError):
    """Raised when poster processing fails due to corrupted inputs or execution errors."""
    pass


class PosterProcessor:
    """
    Stateful processor providing poster composition and resource caching.
    """

    def __init__(self, default_config: Optional[PosterConfig] = None) -> None:
        self.default_config = default_config or PosterConfig()

    def process(
        self,
        input_image: Union[str, Path, Image.Image],
        config: Optional[PosterConfig] = None,
        output_path: Optional[Union[str, Path]] = None,
        **kwargs: Any
    ) -> Image.Image:
        """
        Executes the full 8-stage image composition pipeline.

        Args:
            input_image: File path or PIL Image object.
            config: PosterConfig dataclass. If None, uses defaults or kwargs.
            output_path: Optional destination file path to save output.
            **kwargs: Overrides for configuration fields.

        Returns:
            Composited RGB PIL Image.
        """
        # Resolve configuration
        if config is None:
            active_config = PosterConfig.from_dict(self.default_config.to_dict(), **kwargs)
        elif kwargs:
            active_config = PosterConfig.from_dict(config.to_dict(), **kwargs)
        else:
            active_config = config
        active_config.normalize()

        # Stage 1: Load and normalize image
        raw_image = self._load_image(input_image)

        # Stage 2: Resolve canvas size and background colors
        canvas_w, canvas_h = resolve_canvas_size(
            ratio=active_config.ratio,
            custom_size=active_config.custom_canvas_size,
            hd=active_config.hd
        )

        c1 = active_config.color1
        c2 = active_config.color2

        if active_config.auto_colors or (c1 is None or c2 is None):
            extracted_c1, extracted_c2 = extract_dominant_colors(raw_image)
            c1 = c1 or extracted_c1
            c2 = c2 or extracted_c2

        if active_config.swap_colors:
            c1, c2 = c2, c1

        # Generate linear gradient canvas
        canvas = generate_linear_gradient(
            width=canvas_w,
            height=canvas_h,
            color1=c1,
            color2=c2,
            angle=active_config.angle
        )

        # Stage 3: Containment scaling & placement (with pan offset)
        placement = calculate_poster_placement(
            canvas_size=(canvas_w, canvas_h),
            raw_size=raw_image.size,
            margin=active_config.margin,
            zoom=active_config.zoom,
            pan=(active_config.pan_x, active_config.pan_y)
        )

        # Resize poster card using high-fidelity Lanczos
        resized_poster = raw_image.resize(
            placement.size,
            resample=Image.Resampling.LANCZOS
        )

        # Stage 4: Supersampled rounded corner mask
        card_mask = create_rounded_mask(
            size=placement.size,
            radius=active_config.curve,
            supersample=active_config.supersample_factor
        )

        # Stage 5: 3D Gaussian drop shadow
        if active_config.drop_shadow:
            _, shadow_mask = create_drop_shadow(
                mask=card_mask,
                canvas_size=(canvas_w, canvas_h),
                offset=(0, active_config.shadow_offset_y),
                blur_radius=active_config.shadow_blur,
                opacity=active_config.shadow_opacity,
                card_position=placement.position
            )
            apply_drop_shadow(canvas, shadow_mask, shadow_color=(0, 0, 0))

        # Stage 6: Composite poster card onto canvas
        canvas.paste(resized_poster, placement.position, mask=card_mask)

        # Stage 7: Apply watermark branding (with custom position and color support)
        if active_config.watermark:
            font_size = (
                active_config.watermark_size
                if active_config.watermark_size is not None
                else max(18, canvas_h // 42)
            )
            custom_wm_pos = (
                (active_config.watermark_x, active_config.watermark_y)
                if active_config.watermark_x is not None and active_config.watermark_y is not None
                else None
            )
            apply_watermark(
                canvas=canvas,
                text=active_config.watermark,
                font_size=font_size,
                font_name=active_config.watermark_font,
                stroke_width=active_config.watermark_stroke_width,
                text_color=active_config.watermark_color,
                stroke_color=active_config.watermark_stroke_color,
                card_placement=placement.box,
                custom_position=custom_wm_pos
            )

        # Stage 8: Save if requested
        if output_path is not None:
            self._save_image(canvas, output_path, quality=active_config.quality)

        return canvas

    @staticmethod
    def _load_image(image_input: Union[str, Path, Image.Image]) -> Image.Image:
        """Loads and normalizes input image to RGB format."""
        if isinstance(image_input, Image.Image):
            img = image_input
        elif isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                raise FileNotFoundError(f"Input image file not found: {path}")
            try:
                img = Image.open(path)
                img.load()  # Ensure file handles closed
            except Exception as e:
                raise PosterProcessingError(f"Could not open or decode image at '{path}': {e}") from e
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        # Mode normalization to RGB
        if img.mode == "RGBA":
            # Composite over opaque black background to preserve translucent edges cleanly
            bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
            return Image.alpha_composite(bg, img).convert("RGB")
        elif img.mode != "RGB":
            return img.convert("RGB")
        return img

    @staticmethod
    def _save_image(image: Image.Image, output_path: Union[str, Path], quality: int = 95) -> None:
        """Saves image to disk with format detection and directory creation."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        ext = path.suffix.lower()
        if ext in (".jpg", ".jpeg"):
            image.save(path, format="JPEG", quality=quality, subsampling=0)
        elif ext == ".png":
            image.save(path, format="PNG", optimize=True)
        else:
            image.save(path, quality=quality)


_global_processor = PosterProcessor()


def process_poster(
    input_image: Union[str, Path, Image.Image],
    config: Optional[PosterConfig] = None,
    output_path: Optional[Union[str, Path]] = None,
    **kwargs: Any
) -> Image.Image:
    """
    Main entrypoint function to process and style a game poster.

    Example:
        >>> from poster_studio import process_poster, PosterConfig
        >>> poster = process_poster("game.jpg", ratio="4:5", curve=45, margin=50)
        >>> poster.save("output_framed.jpg", quality=95)
    """
    return _global_processor.process(
        input_image=input_image,
        config=config,
        output_path=output_path,
        **kwargs
    )
