"""
poster_studio.gui
~~~~~~~~~~~~~~~~~
Desktop Graphical User Interface for Game Poster Studio.
Provides a modern Collage Maker experience using CustomTkinter with
automatic fallback to native Tkinter in lightweight environments.
"""

from __future__ import annotations

from typing import List, Optional

__all__ = ["MainWindow", "PosterStudioModel", "launch_gui"]


def __getattr__(name: str):
    """
    Lazy loader preventing immediate Tkinter/CustomTkinter import
    unless explicitly requested. Preserves headless safety.
    """
    if name in ("MainWindow", "PosterStudioModel", "launch_gui"):
        from poster_studio.gui.main_window import MainWindow, PosterStudioModel, launch_gui
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
