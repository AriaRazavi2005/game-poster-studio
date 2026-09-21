"""
poster_studio.core
~~~~~~~~~~~~~~~~~~
Core Image Processing Engine for Game Poster Studio.
Provides color extraction, linear gradients, geometry containment, rounded masks,
realistic drop shadows, typography watermarking, and master compositing.
"""

from __future__ import annotations

from poster_studio.core.palette import (
    extract_dominant_colors,
    parse_hex_color,
    rgb_to_hex,
    is_dead_color,
    color_distance_rgb,
    DEFAULT_FALLBACK_C1,
    DEFAULT_FALLBACK_C2,
)
from poster_studio.core.gradient import (
    generate_linear_gradient,
)
from poster_studio.core.geometry import (
    ASPECT_RATIOS,
    ASPECT_RATIOS_HD,
    PosterPlacement,
    resolve_canvas_size,
    resolve_margin,
    calculate_poster_placement,
    calculate_fit_box,
)
from poster_studio.core.mask import (
    create_rounded_mask,
    generate_rounded_mask,
)
from poster_studio.core.shadow import (
    create_drop_shadow,
    apply_drop_shadow,
    create_drop_shadow_from_placement,
)
from poster_studio.core.watermark import (
    resolve_watermark_font,
    apply_watermark,
    calculate_watermark_position,
)
from poster_studio.core.processor import (
    PosterConfig,
    PosterProcessor,
    PosterProcessingError,
    process_poster,
)

__all__ = [
    # Palette
    "extract_dominant_colors",
    "parse_hex_color",
    "rgb_to_hex",
    "is_dead_color",
    "color_distance_rgb",
    "DEFAULT_FALLBACK_C1",
    "DEFAULT_FALLBACK_C2",
    # Gradient
    "generate_linear_gradient",
    # Geometry
    "ASPECT_RATIOS",
    "ASPECT_RATIOS_HD",
    "PosterPlacement",
    "resolve_canvas_size",
    "resolve_margin",
    "calculate_poster_placement",
    "calculate_fit_box",
    # Mask
    "create_rounded_mask",
    "generate_rounded_mask",
    # Shadow
    "create_drop_shadow",
    "apply_drop_shadow",
    "create_drop_shadow_from_placement",
    # Watermark
    "resolve_watermark_font",
    "apply_watermark",
    "calculate_watermark_position",
    # Processor
    "PosterConfig",
    "PosterProcessor",
    "PosterProcessingError",
    "process_poster",
]
