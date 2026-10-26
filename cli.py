#!/usr/bin/env python3
"""
cli.py
~~~~~~
Root compatibility shim delegating to poster_studio.cli.
For backwards compatibility with existing server automation scripts and CLI pipelines.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure repository root and package are in sys.path dynamically
_REPO_ROOT = Path(__file__).resolve().parent
_PKG_DIR = _REPO_ROOT / "poster_studio"

for p in [str(_REPO_ROOT), str(_PKG_DIR)]:
    if p not in sys.path:
        sys.path.insert(0, p)

from poster_studio.cli import *
from poster_studio.cli import main

if __name__ == "__main__":
    sys.exit(main())
