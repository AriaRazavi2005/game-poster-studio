"""
poster_studio.plugins
~~~~~~~~~~~~~~~~~~~~~
Lightweight plugin discovery bridging Game Poster Studio Lite with Game Poster Studio Pro.
"""

from __future__ import annotations

from importlib import metadata
from typing import Any, Optional

_pro_module: Optional[Any] = None
_checked: bool = False


def get_pro_plugin() -> Optional[Any]:
    """Discovers and returns the poster_studio_pro plugin module if available."""
    global _pro_module, _checked
    if _checked:
        return _pro_module
    _checked = True

    try:
        eps = metadata.entry_points()
        group = eps.select(group="poster_studio.plugins") if hasattr(eps, "select") else eps.get("poster_studio.plugins", [])
        for ep in group:
            _pro_module = ep.load()
            return _pro_module
    except Exception:
        pass

    try:
        import poster_studio_pro
        _pro_module = poster_studio_pro
        return _pro_module
    except ImportError:
        return None
