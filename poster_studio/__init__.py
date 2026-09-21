"""
Game Poster Studio
~~~~~~~~~~~~~~~~~~
A cross-platform Python application and library that recreates the photo
framing and styling functionality of Windows Collage Maker.
"""

from __future__ import annotations

import os
import sys

# Auto-configure TCL_LIBRARY / TK_LIBRARY on Windows if not set
if sys.platform == "win32":
    base_prefix = getattr(sys, "base_prefix", sys.prefix)
    tcl_dir = os.path.join(base_prefix, "tcl")
    if os.path.isdir(tcl_dir):
        if "TCL_LIBRARY" not in os.environ:
            tcl_lib = os.path.join(tcl_dir, "tcl8.6")
            if os.path.isdir(tcl_lib):
                os.environ["TCL_LIBRARY"] = tcl_lib
        if "TK_LIBRARY" not in os.environ:
            tk_lib = os.path.join(tcl_dir, "tk8.6")
            if os.path.isdir(tk_lib):
                os.environ["TK_LIBRARY"] = tk_lib

from poster_studio.core.processor import (
    PosterConfig,
    PosterProcessor,
    process_poster,
)

__version__ = "1.0.0"
__all__ = [
    "PosterConfig",
    "PosterProcessor",
    "process_poster",
    "__version__",
]
