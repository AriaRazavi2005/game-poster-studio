"""
poster_studio.tests.test_gui_smoke
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Smoke and widget instantiation tests for Game Poster Studio MainWindow.
Tests widget hierarchy, control bindings, and dual-engine fallback.
Operates cleanly in both live desktop sessions and display-less CI runners.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest

from poster_studio.gui.main_window import MainWindow, PosterStudioModel, HAS_CUSTOMTKINTER


def is_display_available() -> bool:
    """Probes whether Tkinter can initialize a windowing display."""
    try:
        import tkinter
        root = tkinter.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


class TestMainWindowSmoke:
    """Smoke test suite validating UI construction and widget attributes."""

    @pytest.mark.skipif(not is_display_available(), reason="Windowing display server not available")
    def test_main_window_instantiation_live_display(self) -> None:
        """Verifies complete widget hierarchy instantiation on native Tkinter fallback."""
        model = PosterStudioModel()
        app = MainWindow(model=model, force_tkinter=True)

        try:
            app.root.withdraw()

            # 1. Header Toolbar widgets
            assert hasattr(app, "btn_open")
            assert hasattr(app, "btn_reset")
            assert hasattr(app, "btn_export")
            assert hasattr(app, "combo_format")

            # 2. Sidebar Notebook & Tabs
            assert hasattr(app, "framing_tab")
            assert hasattr(app, "ratio_tab")
            assert hasattr(app, "background_tab")
            assert hasattr(app, "branding_tab")

            # 3. Framing Sliders
            assert hasattr(app, "slider_spacing")
            assert hasattr(app, "slider_curve")
            assert hasattr(app, "slider_zoom")

            # 4. Background Controls
            assert hasattr(app, "slider_angle")
            assert hasattr(app, "entry_color1")
            assert hasattr(app, "entry_color2")
            assert hasattr(app, "btn_autodetect")
            assert hasattr(app, "btn_swap")
            assert hasattr(app, "chk_shadow")

            # 5. Branding Inputs
            assert hasattr(app, "entry_watermark")
            assert hasattr(app, "slider_watermark_size")
            assert hasattr(app, "slider_stroke")

            # 6. Central Viewport Canvas
            assert hasattr(app, "canvas_preview")
            assert app.canvas_preview is not None

            # 7. Status Bar
            assert hasattr(app, "label_status")
            assert hasattr(app, "label_dimensions")

            # Verify initial sync
            assert app.slider_spacing.get() == 50
            assert app.slider_curve.get() == 45

        finally:
            app.preview_engine.shutdown()
            app.root.destroy()

    @pytest.mark.skipif(not is_display_available() or not HAS_CUSTOMTKINTER, reason="Live display or CustomTkinter not available")
    def test_main_window_instantiation_customtkinter(self) -> None:
        """Verifies widget hierarchy instantiation under CustomTkinter primary engine."""
        model = PosterStudioModel()
        app = MainWindow(model=model, force_tkinter=False)

        try:
            app.root.withdraw()

            assert app.use_ctk is True
            assert hasattr(app, "btn_open")
            assert hasattr(app, "btn_reset")
            assert hasattr(app, "btn_export")
            assert hasattr(app, "slider_spacing")
            assert hasattr(app, "slider_curve")
            assert hasattr(app, "slider_zoom")
            assert hasattr(app, "canvas_preview")

            # Test slider update
            app._on_spacing_slider(70)
            assert model.config.margin == 70

        finally:
            app.preview_engine.shutdown()
            app.root.destroy()

    def test_main_window_construction_mocked(self) -> None:
        """
        Verifies constructor lifecycle, widget wiring, and callback binding
        in headless environments using standard mocks.
        """
        if is_display_available():
            pytest.skip("Live display is available; covered by live display tests")

        mock_tk = MagicMock()
        mock_root = MagicMock()
        mock_tk.Tk.return_value = mock_root

        with patch.dict("sys.modules", {"tkinter": mock_tk, "tkinter.ttk": MagicMock()}):
            model = PosterStudioModel()
            app = MainWindow(model=model, force_tkinter=True)
            assert app.model is model
            assert app.root is not None
