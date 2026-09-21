"""
poster_studio.gui.export_engine
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
High-resolution asynchronous export engine supporting 95% JPEG (4:4:4 subsampling)
and lossless PNG with native Windows file dialog integration.
"""

from __future__ import annotations

import logging
from pathlib import Path
import threading
import time
from typing import Any, Callable, Optional, Tuple, Union
from PIL import Image

from poster_studio.core.processor import PosterConfig, process_poster

logger = logging.getLogger("poster_studio.gui.export")


def prompt_save_path(
    parent: Any = None,
    source_image_path: Optional[Union[str, Path]] = None,
    default_format: str = "JPEG"
) -> Optional[Path]:
    """
    Opens native Save File Dialog with automatic extension filtering.
    Defers Tkinter import for headless safety.

    Args:
        parent: Parent Tk/CTk window or None.
        source_image_path: Path of the loaded image (used for initial filename stem).
        default_format: "JPEG" or "PNG".

    Returns:
        Selected Path or None if cancelled.
    """
    try:
        from tkinter import filedialog
    except ImportError:
        logger.warning("tkinter.filedialog not available.")
        return None

    norm_fmt = default_format.upper()
    ext = ".jpg" if norm_fmt in ("JPEG", "JPG") else ".png"

    if source_image_path:
        stem = Path(source_image_path).stem
        initial_dir = str(Path(source_image_path).parent)
        initial_file = f"{stem}_poster{ext}"
    else:
        initial_dir = str(Path.home())
        initial_file = f"game_poster{ext}"

    filetypes = [
        ("JPEG Image (*.jpg;*.jpeg)", "*.jpg;*.jpeg"),
        ("PNG Image (*.png)", "*.png"),
        ("All Files (*.*)", "*.*")
    ]

    selected = filedialog.asksaveasfilename(
        parent=parent,
        title="Export Game Poster",
        initialdir=initial_dir,
        initialfile=initial_file,
        filetypes=filetypes,
        defaultextension=ext
    )

    if not selected:
        return None

    path = Path(selected)
    if not path.suffix:
        path = path.with_suffix(ext)

    return path


class ExportEngine:
    """
    Handles full-resolution poster rendering and disk export.
    Supports both synchronous and asynchronous execution.
    """

    def __init__(self, root: Any = None) -> None:
        self.root = root
        self._is_exporting = False
        self._lock = threading.Lock()

    @property
    def is_exporting(self) -> bool:
        with self._lock:
            return self._is_exporting

    def export_sync(
        self,
        raw_image: Image.Image,
        config: PosterConfig,
        output_path: Union[str, Path],
        format: Optional[str] = None,
        quality: Optional[int] = None
    ) -> Tuple[Path, int]:
        """
        Synchronously renders full-resolution poster and saves to disk.

        Args:
            raw_image: Original full-resolution image.
            config: Desired poster configuration.
            output_path: Destination file path.
            format: "JPEG", "PNG", or None (inferred from suffix).
            quality: JPEG quality (default: config.quality or 95).

        Returns:
            (saved_path, file_size_bytes)
        """
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        target_quality = quality if quality is not None else (config.quality or 95)

        # Build full-resolution configuration (preserve ratio/hd presets and custom canvas size)
        cfg_dict = config.to_dict()
        if config.custom_canvas_size is not None:
            cfg_dict["custom_canvas_size"] = config.custom_canvas_size
        else:
            cfg_dict["custom_canvas_size"] = None
        cfg_dict["supersample_factor"] = 2
        cfg_dict["quality"] = target_quality
        export_cfg = PosterConfig.from_dict(cfg_dict)

        # Execute full-resolution composition pipeline
        rendered = process_poster(raw_image, config=export_cfg)

        # Determine encoding format
        ext = out_p.suffix.lower()
        save_format = (format.upper() if format else None)
        if save_format is None:
            if ext in (".jpg", ".jpeg"):
                save_format = "JPEG"
            elif ext == ".png":
                save_format = "PNG"
            else:
                save_format = "JPEG"

        if save_format in ("JPEG", "JPG"):
            # Extract EXIF from raw_image if present and populate standard metadata tags
            raw_exif = raw_image.getexif() if hasattr(raw_image, "getexif") else None
            exif = Image.Exif()
            if raw_exif:
                exif.update(raw_exif)

            exif[0x0131] = "Game Poster Studio"  # Software
            exif[0x0100] = rendered.width        # ImageWidth
            exif[0x0101] = rendered.height       # ImageLength
            exif[0xA002] = rendered.width        # ExifImageWidth
            exif[0xA003] = rendered.height       # ExifImageHeight
            exif_bytes = exif.tobytes()

            rendered.save(
                out_p,
                format="JPEG",
                quality=target_quality,
                subsampling=0,  # 4:4:4 chroma subsampling for sharp text & edges
                optimize=True,
                exif=exif_bytes
            )
        elif save_format == "PNG":
            rendered.save(
                out_p,
                format="PNG",
                optimize=True,
                compress_level=6
            )
        else:
            rendered.save(out_p, quality=target_quality)

        file_size = out_p.stat().st_size
        return out_p, file_size

    def export_async(
        self,
        raw_image: Image.Image,
        config: PosterConfig,
        output_path: Union[str, Path],
        format: Optional[str] = None,
        quality: Optional[int] = None,
        on_progress: Optional[Callable[[str], None]] = None,
        on_success: Optional[Callable[[Path, int], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ) -> None:
        """
        Executes full-resolution export on a background thread.
        Dispatches UI completion callbacks via root.after(0, ...).
        """
        with self._lock:
            if self._is_exporting:
                if on_error:
                    on_error(RuntimeError("An export task is already running."))
                return
            self._is_exporting = True

        if on_progress:
            on_progress("Rendering full-resolution poster...")

        dest_path = Path(output_path)

        def _worker() -> None:
            start_time = time.monotonic()
            try:
                saved_path, file_size = self.export_sync(
                    raw_image=raw_image,
                    config=config,
                    output_path=dest_path,
                    format=format,
                    quality=quality
                )
                elapsed = time.monotonic() - start_time
                logger.info(
                    "Export completed in %.2fs: %s (%d bytes)",
                    elapsed, saved_path, file_size
                )

                def _notify_success() -> None:
                    with self._lock:
                        self._is_exporting = False
                    if on_success:
                        on_success(saved_path, file_size)

                if self.root is not None:
                    self.root.after(0, _notify_success)
                else:
                    _notify_success()

            except Exception as exc:
                logger.error("Export failed: %s", exc, exc_info=True)

                def _notify_error() -> None:
                    with self._lock:
                        self._is_exporting = False
                    if on_error:
                        on_error(exc)

                if self.root is not None:
                    self.root.after(0, _notify_error)
                else:
                    _notify_error()

        thread = threading.Thread(
            target=_worker, daemon=True, name="PosterStudio-ExportWorker"
        )
        thread.start()
