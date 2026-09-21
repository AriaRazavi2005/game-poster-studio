#!/usr/bin/env python3
"""
poster_studio.cli
~~~~~~~~~~~~~~~~~
Package shim dispatching to and re-exporting root cli.py.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_root_cli_path = Path(__file__).resolve().parent.parent / "cli.py"
_spec = importlib.util.spec_from_file_location("_root_cli", _root_cli_path)
if _spec and _spec.loader:
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    for _k, _v in _mod.__dict__.items():
        if not _k.startswith("__"):
            globals()[_k] = _v

if __name__ == "__main__":
    if "main" in globals():
        sys.exit(globals()["main"]())
