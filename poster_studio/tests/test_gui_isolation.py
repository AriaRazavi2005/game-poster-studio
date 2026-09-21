"""
poster_studio.tests.test_gui_isolation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Headless Architectural Isolation & Non-Regression Invariant Guard.
Enforces zero display dependencies on:
- telegram_bridge.py
- cli.py
- poster_studio (core package)
And validates that test_pipeline.py (51/51 tests) passes with zero regressions.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestHeadlessIsolation:
    """Invariant guard confirming GUI imports never leak into headless pipelines."""

    def test_telegram_bridge_zero_display_leak(self) -> None:
        """telegram_bridge must import and execute cleanly with tkinter explicitly banned."""
        test_code = """
import sys
sys.modules['tkinter'] = None
sys.modules['_tkinter'] = None
sys.modules['customtkinter'] = None

from telegram_bridge import create_game_poster
from PIL import Image

img = Image.new('RGB', (100, 100), (200, 50, 50))
out = create_game_poster(img, ratio='4:5')
assert out.size == (1080, 1350)
print('TELEGRAM_ISOLATION_OK')
"""
        res = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        assert res.returncode == 0, f"Leakage detected:\n{res.stderr}"
        assert "TELEGRAM_ISOLATION_OK" in res.stdout

    def test_cli_zero_display_leak(self) -> None:
        """cli.py must import cleanly with tkinter explicitly banned."""
        test_code = """
import sys
sys.modules['tkinter'] = None
sys.modules['_tkinter'] = None
sys.modules['customtkinter'] = None

import cli
print('CLI_ISOLATION_OK')
"""
        res = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        assert res.returncode == 0, f"CLI display leak detected:\n{res.stderr}"
        assert "CLI_ISOLATION_OK" in res.stdout

    def test_core_package_zero_display_leak(self) -> None:
        """poster_studio core package must never import GUI subpackage."""
        test_code = """
import sys
sys.modules['tkinter'] = None
sys.modules['_tkinter'] = None

import poster_studio
assert 'poster_studio.gui' not in sys.modules
print('CORE_ISOLATION_OK')
"""
        res = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        assert res.returncode == 0, f"Core import failed:\n{res.stderr}"
        assert "CORE_ISOLATION_OK" in res.stdout

    def test_gui_module_lazy_loading(self) -> None:
        """import poster_studio.gui must not trigger tkinter import before attribute access."""
        test_code = """
import sys
import poster_studio.gui
# Check that neither tkinter nor customtkinter was automatically imported
assert 'tkinter' not in sys.modules
assert 'customtkinter' not in sys.modules
print('LAZY_LOADING_OK')
"""
        res = subprocess.run(
            [sys.executable, "-c", test_code],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        assert res.returncode == 0, f"Lazy loading failed:\n{res.stderr}"
        assert "LAZY_LOADING_OK" in res.stdout

    def test_pipeline_non_regression(self) -> None:
        """All 51 baseline tests in test_pipeline.py must pass 100%."""
        res = subprocess.run(
            [sys.executable, "test_pipeline.py"],
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT)
        )
        assert res.returncode == 0, f"test_pipeline.py failed!\n{res.stdout}\n{res.stderr}"
        assert "SUMMARY: Total=51 | Passed=51" in res.stdout
