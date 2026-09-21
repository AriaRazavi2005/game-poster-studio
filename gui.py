#!/usr/bin/env python3
"""
gui.py — Root Convenience Runner for Game Poster Studio Desktop GUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Launches the CustomTkinter desktop interface with automatic path resolution
and friendly diagnostic pre-flight checks.

Usage:
  python gui.py
  python gui.py --input path/to/poster.jpg
  python gui.py --input path/to/poster.jpg --ratio 9:16
  python gui.py --fallback-tkinter  # Force native Tkinter fallback mode
"""

from __future__ import annotations

import os
from pathlib import Path
import sys

# 1. Ensure repository root and package are in sys.path
REPO_ROOT = Path(__file__).resolve().parent
POSTER_STUDIO_DIR = REPO_ROOT / "poster_studio"

for p in [str(REPO_ROOT), str(POSTER_STUDIO_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)


def _preflight_check() -> None:
    """Checks that required packages are installed before launching."""
    missing_deps = []
    try:
        import PIL
    except ImportError:
        missing_deps.append("Pillow")
    try:
        import numpy
    except ImportError:
        missing_deps.append("numpy")

    if missing_deps:
        sys.stderr.write(
            f"[FATAL] Missing mandatory core dependencies: {', '.join(missing_deps)}\n"
            "Please install them via: pip install -r requirements.txt\n"
        )
        sys.exit(1)

    # Check Tkinter availability
    try:
        import tkinter
    except ImportError:
        sys.stderr.write(
            "[FATAL] Python 'tkinter' module is not available.\n"
            "On Linux, install it via: sudo apt-get install python3-tk\n"
            "On Windows, reinstall Python and check the 'tcl/tk and IDLE' option.\n"
        )
        sys.exit(1)


def main() -> int:
    """CLI execution entrypoint."""
    _preflight_check()
    from poster_studio.gui.main_window import launch_gui
    return launch_gui(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
