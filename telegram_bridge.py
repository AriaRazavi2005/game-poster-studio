"""
telegram_bridge.py
~~~~~~~~~~~~~~~~~~
Root compatibility shim re-exporting poster_studio.telegram_bridge.
For backwards compatibility with existing server automation bots.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure package directory is in sys.path
_PKG_DIR = Path(__file__).resolve().parent / "poster_studio"
if str(_PKG_DIR) not in sys.path:
    sys.path.insert(0, str(_PKG_DIR))

from poster_studio.telegram_bridge import *
from poster_studio.telegram_bridge import __all__
