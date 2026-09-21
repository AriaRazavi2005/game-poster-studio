"""
poster_studio.assets.fonts
~~~~~~~~~~~~~~~~~~~~~~~~~~
Bundled font assets and path resolution for typography and watermarks.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

FONTS_DIR = Path(__file__).resolve().parent
DEFAULT_FONT_FILE = "Anton-Regular.ttf"


def get_bundled_font_path(font_filename: str = DEFAULT_FONT_FILE) -> Optional[Path]:
    """Returns the absolute path to a bundled font file, or None if not found."""
    target = FONTS_DIR / font_filename
    if target.is_file():
        return target
    return None
