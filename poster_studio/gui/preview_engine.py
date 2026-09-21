"""
poster_studio.gui.preview_engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Ultra-fast, thread-safe real-time preview pipeline for Game Poster Studio.
Features proportional viewport downsampling, throttled debouncing,
cached color palette quantization, and generation-token race invalidation.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Any, Callable, Optional, Tuple
from PIL import Image

from poster_studio.core.processor import PosterConfig, process_poster
from poster_studio.core.geometry import resolve_canvas_size
from poster_studio.core.palette import extract_dominant_colors

logger = logging.getLogger("poster_studio.gui.preview")


def calculate_preview_dimensions(
    full_canvas_size: Tuple[int, int],
    viewport_max_size: Tuple[int, int] = (640, 750)
) -> Tuple[int, int, float]:
    """
    Calculates downscaled preview canvas dimensions and uniform scaling ratio S.

    Args:
        full_canvas_size: (width, height) of the full-resolution target canvas.
        viewport_max_size: Maximum bounding box (width, height) available in viewport.

    Returns:
        (preview_w, preview_h, scale_factor)
    """
    full_w, full_h = full_canvas_size
    max_w, max_h = viewport_max_size

    if full_w <= 0 or full_h <= 0:
        return (max(100, max_w), max(100, max_h), 1.0)

    scale = min(max_w / full_w, max_h / full_h)
    preview_w = max(100, int(round(full_w * scale)))
    preview_h = max(100, int(round(full_h * scale)))

    scale_factor = preview_w / full_w
    return preview_w, preview_h, scale_factor


class ThrottledDebouncer:
    """
    Guarantees steady ~30-60fps rendering during continuous slider dragging
    while ensuring the final resting slider value is ALWAYS rendered.
    """

    def __init__(
        self,
        root: Any,
        callback: Callable[..., None],
        interval_ms: int = 33
    ) -> None:
        self.root = root
        self.callback = callback
        self.interval_ms = interval_ms
        self._last_exec_time = 0.0
        self._after_id: Optional[str] = None
        self._pending_args: Optional[Tuple[Tuple[Any, ...], dict]] = None

    def trigger(self, *args: Any, **kwargs: Any) -> None:
        """Schedules or immediately executes the throttled callback."""
        now = time.monotonic()
        elapsed_ms = (now - self._last_exec_time) * 1000.0
        self._pending_args = (args, kwargs)

        if self.root is None:
            # Headless or direct execution
            self._last_exec_time = now
            self.callback(*args, **kwargs)
            self._pending_args = None
            return

        if elapsed_ms >= self.interval_ms and self._after_id is None:
            # Immediate leading-edge execution: interval has elapsed
            self._last_exec_time = now
            args_to_run, kwargs_to_run = self._pending_args
            self._pending_args = None
            self.callback(*args_to_run, **kwargs_to_run)
        else:
            # Schedule trailing execution if not already scheduled
            if self._after_id is None:
                remaining_ms = max(1, int(self.interval_ms - elapsed_ms))
                self._after_id = self.root.after(remaining_ms, self._on_trailing)

    def _on_trailing(self) -> None:
        self._after_id = None
        self._last_exec_time = time.monotonic()
        if self._pending_args is not None:
            args, kwargs = self._pending_args
            self._pending_args = None
            self.callback(*args, **kwargs)

    def cancel(self) -> None:
        """Cancels any pending trailing execution."""
        if self._after_id is not None and self.root is not None:
            try:
                self.root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        self._pending_args = None


class CanvasDisplayManager:
    """
    Manages canvas image placement, centering, and PhotoImage lifetime
    to prevent Tkinter garbage collection bitmap loss.
    """

    def __init__(self, canvas: Any) -> None:
        self.canvas = canvas
        self.image_item_id: Optional[int] = None
        self._active_photo: Any = None  # Retains reference preventing Python GC
        self.current_image: Optional[Image.Image] = None
        self.bounds: Tuple[int, int, int, int] = (0, 0, 0, 0)

    def update_image(self, pil_image: Image.Image) -> None:
        """Displays PIL Image centered in canvas, maintaining strong PhotoImage ref."""
        # Defer import to prevent display check issues in headless tests
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(pil_image)
        self._active_photo = photo
        self.current_image = pil_image

        # Calculate canvas center
        try:
            c_w = self.canvas.winfo_width()
            c_h = self.canvas.winfo_height()
        except Exception:
            c_w, c_h = pil_image.width, pil_image.height

        cx = max(c_w // 2, pil_image.width // 2)
        cy = max(c_h // 2, pil_image.height // 2)

        x0 = cx - pil_image.width // 2
        y0 = cy - pil_image.height // 2
        self.bounds = (x0, y0, x0 + pil_image.width, y0 + pil_image.height)

        if self.image_item_id is None:
            self.image_item_id = self.canvas.create_image(
                cx, cy, image=photo, anchor="center"
            )
        else:
            self.canvas.coords(self.image_item_id, cx, cy)
            self.canvas.itemconfig(self.image_item_id, image=photo)

    def clear(self) -> None:
        """Clears displayed image and releases PhotoImage reference."""
        if self.image_item_id is not None:
            try:
                self.canvas.delete(self.image_item_id)
            except Exception:
                pass
            self.image_item_id = None
        self._active_photo = None
        self.current_image = None
        self.bounds = (0, 0, 0, 0)


class PreviewEngine:
    """
    Manages live interactive canvas rendering with downsampling,
    palette caching, throttled debouncing, and background threading.
    """

    def __init__(
        self,
        root: Any = None,
        on_preview_rendered: Optional[Callable[[Image.Image], None]] = None,
        viewport_max_size: Tuple[int, int] = (640, 750),
        throttle_interval_ms: int = 33
    ) -> None:
        self.root = root
        self.on_preview_rendered = on_preview_rendered
        self.viewport_max_size = viewport_max_size
        self.throttle_interval_ms = throttle_interval_ms

        # Cached image assets
        self.raw_image: Optional[Image.Image] = None
        self.preview_raw_image: Optional[Image.Image] = None
        self.cached_palette: Optional[Tuple[Tuple[int, int, int], Tuple[int, int, int]]] = None

        # Threading & generation control
        self._generation = 0
        self._lock = threading.Lock()
        self._queue: queue.Queue = queue.Queue(maxsize=1)
        self._is_running = True

        # Debouncing helper
        self._debouncer = ThrottledDebouncer(
            root=self.root,
            callback=self._dispatch_render_task,
            interval_ms=self.throttle_interval_ms
        )

        # Start background worker only if root / callback is active
        self._worker_thread: Optional[threading.Thread] = None
        if self.root is not None and self.on_preview_rendered is not None:
            self._worker_thread = threading.Thread(
                target=self._worker_loop, daemon=True, name="PosterStudio-PreviewWorker"
            )
            self._worker_thread.start()

    def set_source_image(self, image: Image.Image) -> None:
        """Sets new master raw image and prepares downscaled preview working copy."""
        self.raw_image = image.copy().convert("RGB")

        # Pre-scale working thumbnail to max 800px dimension
        max_dim = max(self.raw_image.width, self.raw_image.height)
        if max_dim > 800:
            scale = 800.0 / max_dim
            new_w = max(10, int(round(self.raw_image.width * scale)))
            new_h = max(10, int(round(self.raw_image.height * scale)))
            self.preview_raw_image = self.raw_image.resize(
                (new_w, new_h), Image.Resampling.BILINEAR
            )
        else:
            self.preview_raw_image = self.raw_image.copy()

        # Cache dominant colors once for subsequent fast preview rendering
        self.cached_palette = extract_dominant_colors(self.preview_raw_image)

    def trigger_preview(self, config: PosterConfig) -> None:
        """Entrypoint called whenever UI sliders or controls change."""
        if self.preview_raw_image is None:
            return
        self._debouncer.trigger(config)

    def render_sync(
        self,
        config: PosterConfig,
        viewport_size: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """
        Synchronously renders preview image. Ideal for initial frame or headless tests.
        """
        if self.preview_raw_image is None:
            if self.raw_image is not None:
                self.set_source_image(self.raw_image)
            else:
                raise ValueError("Cannot render preview: no source image loaded.")

        return self._render_scaled_preview(config, viewport_size=viewport_size)

    def _dispatch_render_task(self, config: PosterConfig) -> None:
        with self._lock:
            self._generation += 1
            gen = self._generation

        # Replace unstarted task in single-slot queue
        try:
            self._queue.get_nowait()
        except queue.Empty:
            pass

        self._queue.put((gen, config))

    def _worker_loop(self) -> None:
        while self._is_running:
            try:
                gen, config = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue

            with self._lock:
                if gen != self._generation:
                    self._queue.task_done()
                    continue

            try:
                result_image = self._render_scaled_preview(config)
            except Exception as e:
                logger.error("Preview render exception: %s", e, exc_info=True)
                self._queue.task_done()
                continue

            with self._lock:
                if gen != self._generation:
                    # Superseded while rendering
                    self._queue.task_done()
                    continue

            # Schedule UI update on main GUI thread
            if self.root is not None:
                try:
                    self.root.after(0, self._dispatch_to_gui, gen, result_image)
                except Exception as e:
                    logger.debug("Failed dispatching preview to GUI: %s", e)
            self._queue.task_done()

    def _render_scaled_preview(
        self,
        config: PosterConfig,
        viewport_size: Optional[Tuple[int, int]] = None
    ) -> Image.Image:
        """Renders scaled composition with proportional parameters in ~13ms."""
        full_w, full_h = resolve_canvas_size(ratio=config.ratio, hd=config.hd)
        max_box = viewport_size or self.viewport_max_size
        prev_w, prev_h, S = calculate_preview_dimensions(
            full_canvas_size=(full_w, full_h),
            viewport_max_size=max_box
        )

        # Resolve colors using palette cache
        c1 = config.color1
        c2 = config.color2
        if config.auto_colors or (c1 is None or c2 is None):
            if self.cached_palette is not None:
                extracted_c1, extracted_c2 = self.cached_palette
            else:
                extracted_c1, extracted_c2 = extract_dominant_colors(self.preview_raw_image)
                self.cached_palette = (extracted_c1, extracted_c2)
            c1 = c1 or extracted_c1
            c2 = c2 or extracted_c2

        # Scale margin
        if isinstance(config.margin, int):
            scaled_margin = max(0, int(round(config.margin * S)))
        else:
            scaled_margin = config.margin

        scaled_curve = max(0, int(round(config.curve * S)))
        scaled_offset_y = max(1, int(round(config.shadow_offset_y * S)))
        scaled_blur = max(1, int(round(config.shadow_blur * S)))
        scaled_watermark_size = (
            max(10, int(round(config.watermark_size * S)))
            if config.watermark_size is not None
            else None
        )
        scaled_pan_x = config.pan_x * S
        scaled_pan_y = config.pan_y * S
        scaled_stroke_width = max(1, int(round(config.watermark_stroke_width * S))) if config.watermark_stroke_width > 0 else 0

        preview_config = PosterConfig(
            ratio=config.ratio,
            hd=False,
            custom_canvas_size=(prev_w, prev_h),
            margin=scaled_margin,
            curve=scaled_curve,
            zoom=config.zoom,
            pan_x=scaled_pan_x,
            pan_y=scaled_pan_y,
            auto_colors=False,
            color1=c1,
            color2=c2,
            swap_colors=config.swap_colors,
            angle=config.angle,
            drop_shadow=config.drop_shadow,
            shadow_offset_y=scaled_offset_y,
            shadow_blur=scaled_blur,
            shadow_opacity=config.shadow_opacity,
            watermark=config.watermark,
            watermark_size=scaled_watermark_size,
            watermark_font=config.watermark_font,
            watermark_x=config.watermark_x,
            watermark_y=config.watermark_y,
            watermark_color=config.watermark_color,
            watermark_stroke_color=config.watermark_stroke_color,
            watermark_stroke_width=scaled_stroke_width,
            supersample_factor=1,  # Fast 1x supersampling for real-time 60fps preview
            quality=85
        )

        return process_poster(
            input_image=self.preview_raw_image,
            config=preview_config
        )

    def _dispatch_to_gui(self, gen: int, result_image: Image.Image) -> None:
        with self._lock:
            if gen != self._generation:
                return
        if self.on_preview_rendered is not None:
            self.on_preview_rendered(result_image)

    def shutdown(self) -> None:
        """Terminates worker thread and clears debouncer."""
        self._is_running = False
        self._debouncer.cancel()
