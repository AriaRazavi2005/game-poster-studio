"""
poster_studio.core.processor
~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Master pipeline orchestrator compositing all image layers:
Preset Resolution -> Auto-Trim / Upscale -> Backdrop (Gradient/Blur/Radial/Mesh) ->
Pattern -> Drop Shadow / Neon Glow -> Reflection -> Rounded Poster Card ->
Border -> Pop-out Character (Pro) -> Vignette/Grain -> Logo/Platforms ->
Typography Layers (Title/Subtitle/Badge/Watermark).
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from PIL import Image, ImageOps

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
from poster_studio.core.watermark import apply_watermark, apply_typography_layers
from poster_studio.core.effects import (
    auto_trim_borders,
    generate_backdrop,
    apply_pattern,
    apply_glow,
    apply_reflection,
    apply_card_border,
    apply_vignette_and_grain,
    apply_logo_and_platforms,
)
from poster_studio.core.presets import get_preset
from poster_studio.plugins import get_pro_plugin

logger = logging.getLogger("poster_studio.processor")

ColorType = Union[Tuple[int, int, int], str]


@dataclass
class PosterConfig:
    """Configuration parameters for Game Poster Studio pipeline."""
    # Preset
    preset: Optional[str] = None

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
    auto_trim: bool = False

    # Background & Gradient
    bg_mode: str = "gradient"
    auto_colors: bool = True
    color1: Optional[ColorType] = None
    color2: Optional[ColorType] = None
    color3: Optional[ColorType] = None
    swap_colors: bool = False
    angle: float = 135.0
    dither: bool = True
    pattern: Optional[str] = None

    # 3D Drop Shadow & Card Effects
    drop_shadow: bool = True
    shadow_offset_y: int = 15
    shadow_blur: int = 25
    shadow_opacity: float = 0.48
    glow: bool = False
    glow_color: Optional[ColorType] = None
    border: int = 0
    border_color: Optional[ColorType] = None
    reflection: bool = False
    vignette: float = 0.0
    grain: float = 0.0

    # Multi-Layer Typography & Branding
    title: Optional[str] = None
    subtitle: Optional[str] = None
    badge: Optional[str] = None
    badge_color: ColorType = "#EF4444"
    watermark: Optional[str] = "BAZYEPC"
    watermark_size: Optional[int] = None
    watermark_font: Optional[str] = None
    watermark_x: Optional[float] = None
    watermark_y: Optional[float] = None
    watermark_pos_mode: Optional[str] = "auto"
    watermark_color: ColorType = (255, 255, 255)
    watermark_stroke_color: ColorType = (15, 23, 42)
    watermark_stroke_width: int = 3

    # Overlays & Pro AI Features
    logo: Optional[str] = None
    logo_pos: str = "top_right"
    platforms: Optional[List[str]] = None
    pop_out: bool = False
    upscale: int = 1

    # Supersampling & Export Quality
    supersample_factor: int = 2
    quality: int = 95

    def __post_init__(self) -> None:
        self.normalize()

    def normalize(self) -> PosterConfig:
        self.angle = float(self.angle) % 360.0
        self.curve = max(0, int(self.curve))
        if isinstance(self.margin, int):
            self.margin = max(0, self.margin)
        elif isinstance(self.margin, float):
            self.margin = max(0.0, min(0.45, self.margin))
        self.zoom = max(0.1, min(3.0, float(self.zoom)))
        self.quality = max(1, min(100, int(self.quality)))
        self.supersample_factor = max(1, min(4, int(self.supersample_factor)))
        self.watermark_stroke_width = max(0, min(20, int(self.watermark_stroke_width)))
        self.border = max(0, min(30, int(self.border)))
        self.vignette = max(0.0, min(1.0, float(self.vignette)))
        self.grain = max(0.0, min(0.5, float(self.grain)))
        self.upscale = max(1, min(4, int(self.upscale)))

        if isinstance(self.color1, str):
            self.color1 = parse_hex_color(self.color1)
        if isinstance(self.color2, str):
            self.color2 = parse_hex_color(self.color2)
        if isinstance(self.color3, str):
            self.color3 = parse_hex_color(self.color3)
        if isinstance(self.watermark_color, str) and self.watermark_color.strip().lower() != "auto":
            self.watermark_color = parse_hex_color(self.watermark_color)
        if isinstance(self.watermark_stroke_color, str):
            self.watermark_stroke_color = parse_hex_color(self.watermark_stroke_color)
        if isinstance(self.glow_color, str) and self.glow_color.strip().lower() != "auto":
            self.glow_color = parse_hex_color(self.glow_color)
        if isinstance(self.border_color, str) and self.border_color.strip().lower() != "auto":
            self.border_color = parse_hex_color(self.border_color)

        if self.watermark is not None and not str(self.watermark).strip():
            self.watermark = None

        return self

    @classmethod
    def from_dict(cls, data: Dict[str, Any], **kwargs: Any) -> PosterConfig:
        combined = {**data, **kwargs}
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

        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in combined.items() if k in valid_fields}
        return cls(**filtered)

    def to_dict(self) -> Dict[str, Any]:
        return {f: getattr(self, f) for f in self.__dataclass_fields__}


class PosterProcessingError(RuntimeError):
    """Raised when poster processing fails due to corrupted inputs or execution errors."""
    pass


class PosterProcessor:
    """Stateful processor providing poster composition and resource caching."""

    def __init__(self, default_config: Optional[PosterConfig] = None) -> None:
        self.default_config = default_config or PosterConfig()

    def process(
        self,
        input_image: Union[str, Path, Image.Image],
        config: Optional[PosterConfig] = None,
        output_path: Optional[Union[str, Path]] = None,
        **kwargs: Any,
    ) -> Image.Image:
        # Stage 1: Load and normalize image (with EXIF transpose)
        raw_image = self._load_image(input_image)

        # Resolve configuration & optional genre preset
        base_dict = (config or self.default_config).to_dict()
        preset_name = kwargs.get("preset") or base_dict.get("preset")
        if preset_name:
            preset_overrides = get_preset(str(preset_name), image=raw_image)
            for pk, pv in preset_overrides.items():
                if pk not in kwargs:
                    base_dict[pk] = pv

        active_config = PosterConfig.from_dict(base_dict, **kwargs).normalize()

        # Optional Auto-Trim letterbox bars
        if active_config.auto_trim:
            raw_image = auto_trim_borders(raw_image)

        # Optional Pro Upscale
        if active_config.upscale > 1:
            pro = get_pro_plugin()
            if pro and hasattr(pro, "upscale_image"):
                raw_image = pro.upscale_image(raw_image, scale=active_config.upscale)

        # Stage 2: Resolve canvas size and background colors
        canvas_w, canvas_h = resolve_canvas_size(
            ratio=active_config.ratio,
            custom_size=active_config.custom_canvas_size,
            hd=active_config.hd,
        )

        c1 = active_config.color1
        c2 = active_config.color2

        if active_config.auto_colors or (c1 is None or c2 is None):
            extracted_c1, extracted_c2 = extract_dominant_colors(raw_image)
            c1 = c1 or extracted_c1
            c2 = c2 or extracted_c2

        if active_config.swap_colors:
            c1, c2 = c2, c1

        # Generate backdrop (gradient, blur, radial, or mesh)
        if active_config.bg_mode == "gradient" and active_config.color3 is None:
            canvas = generate_linear_gradient(
                width=canvas_w,
                height=canvas_h,
                color1=c1,
                color2=c2,
                angle=active_config.angle,
                dither=active_config.dither,
            )
        else:
            canvas = generate_backdrop(
                size=(canvas_w, canvas_h),
                raw_image=raw_image,
                c1=c1,
                c2=c2,
                color3=active_config.color3,
                angle=active_config.angle,
                bg_mode=active_config.bg_mode,
                dither=active_config.dither,
            )

        if active_config.pattern:
            apply_pattern(canvas, active_config.pattern)

        # Stage 3: Containment scaling & placement
        placement = calculate_poster_placement(
            canvas_size=(canvas_w, canvas_h),
            raw_size=raw_image.size,
            margin=active_config.margin,
            zoom=active_config.zoom,
            pan=(active_config.pan_x, active_config.pan_y),
        )

        resized_poster = raw_image.resize(placement.size, resample=Image.Resampling.LANCZOS)

        # Stage 4: Supersampled rounded corner mask
        card_mask = create_rounded_mask(
            size=placement.size,
            radius=active_config.curve,
            supersample=active_config.supersample_factor,
        )

        # Stage 5: 3D Gaussian drop shadow & optional neon glow
        if active_config.drop_shadow:
            _, shadow_mask = create_drop_shadow(
                mask=card_mask,
                canvas_size=(canvas_w, canvas_h),
                offset=(0, active_config.shadow_offset_y),
                blur_radius=active_config.shadow_blur,
                opacity=active_config.shadow_opacity,
                card_position=placement.position,
            )
            apply_drop_shadow(canvas, shadow_mask, shadow_color=(0, 0, 0))

        if active_config.glow:
            g_col = (
                c1
                if (active_config.glow_color is None or active_config.glow_color == "auto")
                else active_config.glow_color
            )
            apply_glow(canvas, card_mask, placement.position, g_col)

        if active_config.reflection:
            apply_reflection(canvas, resized_poster, card_mask, placement.position)

        # Stage 6: Composite poster card onto canvas
        canvas.paste(resized_poster, placement.position, mask=card_mask)

        if active_config.border > 0:
            b_col = (
                c1
                if (active_config.border_color is None or active_config.border_color == "auto")
                else active_config.border_color
            )
            apply_card_border(canvas, placement.position, placement.size, active_config.curve, active_config.border, b_col)

        # Optional Pro 3D Character Pop-out
        if active_config.pop_out:
            pro = get_pro_plugin()
            if pro and hasattr(pro, "apply_pop_out"):
                pro.apply_pop_out(canvas, resized_poster, placement.position)

        if active_config.vignette > 0.0 or active_config.grain > 0.0:
            apply_vignette_and_grain(canvas, active_config.vignette, active_config.grain)

        if active_config.logo or active_config.platforms:
            apply_logo_and_platforms(canvas, active_config.logo, active_config.logo_pos, active_config.platforms)

        # Stage 7: Multi-layer typography (Title, Subtitle, Badge) & Watermark
        if active_config.title or active_config.subtitle or active_config.badge:
            apply_typography_layers(
                canvas=canvas,
                title=active_config.title,
                subtitle=active_config.subtitle,
                badge=active_config.badge,
                badge_color=active_config.badge_color,
                font_name=active_config.watermark_font,
                text_color=active_config.watermark_color,
                stroke_color=active_config.watermark_stroke_color,
                card_box=placement.box,
            )

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
                custom_position=custom_wm_pos,
                pos_mode=active_config.watermark_pos_mode,
            )

        # Stage 8: Save if requested
        if output_path is not None:
            self._save_image(canvas, output_path, quality=active_config.quality)

        return canvas

    @staticmethod
    def _load_image(image_input: Union[str, Path, Image.Image, bytes, bytearray, Any]) -> Image.Image:
        """Loads, rotates according to EXIF, and normalizes input image to RGB format."""
        if isinstance(image_input, Image.Image):
            img = image_input
        elif isinstance(image_input, (bytes, bytearray)):
            try:
                img = Image.open(io.BytesIO(image_input))
                img.load()
            except Exception as e:
                raise PosterProcessingError(f"Could not decode image from bytes: {e}") from e
        elif hasattr(image_input, "read") and hasattr(image_input, "seek"):
            try:
                img = Image.open(image_input)
                img.load()
            except Exception as e:
                raise PosterProcessingError(f"Could not decode image from stream: {e}") from e
        elif isinstance(image_input, (str, Path)):
            path = Path(image_input)
            if not path.is_file():
                raise FileNotFoundError(f"Input image file not found: {path}")
            try:
                img = Image.open(path)
                img.load()
            except Exception as e:
                raise PosterProcessingError(f"Could not open or decode image at '{path}': {e}") from e
        else:
            raise TypeError(f"Unsupported image input type: {type(image_input)}")

        try:
            transposed = ImageOps.exif_transpose(img)
            if transposed is not None:
                img = transposed
        except Exception:
            pass

        if img.mode == "RGBA":
            bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
            return Image.alpha_composite(bg, img).convert("RGB")
        elif img.mode != "RGB":
            return img.convert("RGB")
        return img

    @staticmethod
    def _save_image(image: Image.Image, output_path: Union[str, Path], quality: int = 95) -> None:
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
    **kwargs: Any,
) -> Image.Image:
    """Main entrypoint function to process and style a game poster."""
    return _global_processor.process(
        input_image=input_image,
        config=config,
        output_path=output_path,
        **kwargs,
    )
