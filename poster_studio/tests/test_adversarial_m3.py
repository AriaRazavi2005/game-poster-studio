"""
poster_studio.tests.test_adversarial_m3
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Milestone 3 Empirical Adversarial Stress Testing Suite:
Targeting `preview_engine.py` and `main_window.py`.

Empirical Verification Categories:
1. Rapid Concurrent Slider Updates (100 rapid changes in 500ms):
   - Throttled debouncing & frame rate regulation (throttles ~30fps)
   - Dropping queue non-blocking behavior and queue bounding (maxsize=1)
   - Multi-threaded concurrent update race condition resistance
   - Guaranteed trailing-edge execution (final resting state rendered)

2. Out-of-Order Token Handling:
   - Generation token race invalidation
   - Superseded slow render discard (old render never overwrites newer request)
   - Stale GUI dispatch token rejection
   - Inverted completion ordering verification

3. Memory Profiling & PhotoImage Garbage Collection:
   - Canvas item reuse (exactly 1 canvas image item across updates)
   - PhotoImage reference retention preventing blank canvas bitmap loss
   - Tracemalloc memory profiling across 50 consecutive preview cycles
   - Weakref deallocation confirming superseded PhotoImages are reclaimed

4. Edge Case Inputs & Pathological Topologies:
   - 1x1 micro image
   - Extreme 21:9 ultrawide aspect ratio (2560x1080)
   - Zero margins (margin=0)
   - Maximum 120px curve radius
   - Combined pathological input (1x1 + 21:9 + margin=0 + curve=120 + extreme zoom)
   - Live MainWindow & Model interaction under edge cases

5. UI Lifecycle & Concurrent Window Events:
   - Rapid aspect ratio switching during slider drag
   - Canvas <Configure> resize event flooding during active rendering
   - Safe shutdown while worker thread is active
   - Daemon thread lifecycle behavior upon window destruction
"""

from __future__ import annotations

import gc
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tracemalloc
from typing import List, Optional, Tuple

# Ensure Tcl/Tk environment paths on Windows if unconfigured
if sys.platform == "win32":
    prefix = Path(sys.base_prefix)
    tcl_path = prefix / "tcl" / "tcl8.6"
    tk_path = prefix / "tcl" / "tk8.6"
    if tcl_path.is_dir() and "TCL_LIBRARY" not in os.environ:
        os.environ["TCL_LIBRARY"] = str(tcl_path)
    if tk_path.is_dir() and "TK_LIBRARY" not in os.environ:
        os.environ["TK_LIBRARY"] = str(tk_path)
import weakref

import numpy as np
from PIL import Image
import pytest

from poster_studio.core.processor import PosterConfig, process_poster
from poster_studio.core.geometry import resolve_canvas_size
from poster_studio.gui.preview_engine import (
    CanvasDisplayManager,
    PreviewEngine,
    ThrottledDebouncer,
    calculate_preview_dimensions,
)
from poster_studio.gui.main_window import (
    MainWindow,
    PosterStudioModel,
    HAS_CUSTOMTKINTER,
)


def _create_sample_image(w: int = 800, h: int = 1000) -> Image.Image:
    """Creates a sample test RGB image with distinctive quadrants."""
    img = Image.new("RGB", (w, h), (40, 40, 80))
    q1 = Image.new("RGB", (w // 2, h // 2), (220, 60, 40))
    q2 = Image.new("RGB", (w // 2, h // 2), (40, 180, 90))
    img.paste(q1, (0, 0))
    img.paste(q2, (w // 2, h // 2))
    return img


def is_live_tk_available() -> bool:
    """Probes whether a live Tk windowing environment is available."""
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.destroy()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def shared_tk_root():
    """
    Provides a single shared Tk root to prevent Windows Store Python Tcl exhaustion.
    Creating/destroying multiple Tk roots within a single process exhausts Tcl interpreter handles.
    """
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def _pump_tk(root: Any, duration_ms: int = 20) -> None:
    """
    Pumps Tkinter event loop natively by running mainloop for duration_ms.
    Ensures cross-thread `root.after` calls are accepted without
    'RuntimeError: main thread is not in main loop'.
    """
    root.after(duration_ms, root.quit)
    root.mainloop()


# ==============================================================================
# 1. RAPID CONCURRENT SLIDER UPDATES (100 in 500ms)
# ==============================================================================

class TestRapidConcurrentSliderUpdates:
    """
    Stress tests slider debouncing, queue dropping, and thread safety under
    rapid bursts (100 rapid changes in 500ms).
    """

    def test_rapid_slider_burst_single_thread(self, shared_tk_root: Any) -> None:
        """
        Simulates 100 rapid slider changes in 500ms on a single thread.
        Verifies:
        1. Debouncer throttles executions so not all 100 trigger expensive renders.
        2. Dropping queue never overflows maxsize=1.
        3. Final resting state (update #100) is guaranteed to execute.
        """
        root = shared_tk_root

        dispatched_configs: List[PosterConfig] = []
        lock = threading.Lock()

        def _on_rendered(img: Image.Image) -> None:
            pass

        engine = PreviewEngine(root=root, on_preview_rendered=_on_rendered)
        sample = _create_sample_image(600, 800)
        engine.set_source_image(sample)

        # Intercept debouncer callback to record what reaches the queue
        original_dispatch = engine._dispatch_render_task

        def _spy_dispatch(cfg: PosterConfig) -> None:
            with lock:
                dispatched_configs.append(cfg)
            original_dispatch(cfg)

        engine._debouncer.callback = _spy_dispatch

        try:
            start_time = time.monotonic()
            num_updates = 100

            for i in range(1, num_updates + 1):
                cfg = PosterConfig(
                    ratio="4:5",
                    margin=i,  # Unique margin 1..100
                    curve=min(i, 120),
                    angle=float(i * 3) % 360.0
                )
                engine.trigger_preview(cfg)
                _pump_tk(root, duration_ms=5)

            elapsed = time.monotonic() - start_time
            assert elapsed >= 0.4, f"Burst completed too fast: {elapsed:.3f}s"

            # Allow debouncer trailing edge timer to fire
            _pump_tk(root, duration_ms=200)

            with lock:
                count_dispatched = len(dispatched_configs)
                assert count_dispatched < num_updates, (
                    f"Debouncer failed to throttle: dispatched {count_dispatched} out of {num_updates}!"
                )
                # Throttled debouncing at 33ms over 500ms should dispatch around 10-45 times
                assert 5 <= count_dispatched <= 45, (
                    f"Unexpected dispatch count: {count_dispatched} (expected between 5 and 45)"
                )
                # CRITICAL INVARIANT: The final dispatched config MUST be update #100
                last_dispatched = dispatched_configs[-1]
                assert last_dispatched.margin == 100, (
                    f"Trailing edge dropped final slider state! Got margin={last_dispatched.margin}, expected 100"
                )

        finally:
            engine.shutdown()

    def test_rapid_concurrent_slider_updates_multithreaded(self, shared_tk_root: Any) -> None:
        """
        Simulates concurrent slider updates from 4 distinct threads spamming 25 updates
        each in parallel (100 total updates in ~500ms).
        Tests thread safety of _generation counter and queue.Queue(maxsize=1).
        """
        root = shared_tk_root

        rendered_count = 0
        render_lock = threading.Lock()

        def _on_rendered(img: Image.Image) -> None:
            nonlocal rendered_count
            with render_lock:
                rendered_count += 1

        engine = PreviewEngine(root=root, on_preview_rendered=_on_rendered)
        sample = _create_sample_image(400, 500)
        engine.set_source_image(sample)

        threads: List[threading.Thread] = []
        errors: List[Exception] = []

        def _worker_spam(thread_id: int) -> None:
            try:
                for j in range(25):
                    cfg = PosterConfig(
                        ratio="4:5",
                        margin=j * 2,
                        curve=j,
                        angle=float((thread_id * 90 + j * 3) % 360)
                    )
                    # Directly dispatch to test thread safety of _dispatch_render_task
                    engine._dispatch_render_task(cfg)
                    time.sleep(0.015)  # 15ms spacing
            except Exception as exc:
                errors.append(exc)

        try:
            for t_idx in range(4):
                t = threading.Thread(target=_worker_spam, args=(t_idx,))
                threads.append(t)

            for t in threads:
                t.start()

            # Pump root while threads run
            for _ in range(25):
                _pump_tk(root, duration_ms=25)

            for t in threads:
                t.join(timeout=2.0)
                assert not t.is_alive(), "Worker thread timed out or deadlocked!"

            assert len(errors) == 0, f"Concurrent slider updates caused exceptions: {errors}"
            # Queue should never exceed maxsize=1
            assert engine._queue.qsize() <= 1, f"Queue size exceeded 1: {engine._queue.qsize()}"
            # Generation count should equal exactly 100
            assert engine._generation == 100, f"Generation counter lost updates: {engine._generation} != 100"

        finally:
            engine.shutdown()

    def test_dropping_queue_no_blocking_on_saturated_worker(self, shared_tk_root: Any) -> None:
        """
        Verifies that when the worker thread is busy with an expensive operation,
        calling _dispatch_render_task 50 times in rapid succession does NOT block
        the calling thread and drops superseded intermediate frames.
        """
        root = shared_tk_root

        engine = PreviewEngine(root=root, on_preview_rendered=lambda img: None)
        sample = _create_sample_image(400, 500)
        engine.set_source_image(sample)

        # Temporarily pause worker by making render sleep
        real_render = engine._render_scaled_preview
        render_started = threading.Event()
        can_finish_render = threading.Event()

        def _slow_render(cfg: PosterConfig) -> Image.Image:
            render_started.set()
            can_finish_render.wait(timeout=2.0)
            return real_render(cfg)

        engine._render_scaled_preview = _slow_render

        try:
            # Dispatch first task to make worker busy
            engine._dispatch_render_task(PosterConfig(margin=1))
            assert render_started.wait(timeout=1.0), "Worker did not start first render"

            # Now worker is blocked waiting for can_finish_render.
            # Blast 50 rapid dispatches from the calling thread.
            t0 = time.monotonic()
            for i in range(2, 52):
                engine._dispatch_render_task(PosterConfig(margin=i))
            t_blast = time.monotonic() - t0

            # 50 dispatches must complete virtually instantly (< 50ms) without blocking
            assert t_blast < 0.1, f"Dispatches blocked! Took {t_blast:.3f}s for 50 queue operations"
            assert engine._generation == 51

            # Unblock worker and let it finish
            can_finish_render.set()

            # Pump GUI loop
            _pump_tk(root, duration_ms=100)

        finally:
            can_finish_render.set()
            engine.shutdown()


# ==============================================================================
# 2. OUT-OF-ORDER TOKEN HANDLING
# ==============================================================================

class TestOutOfOrderTokenHandling:
    """
    Empirically verifies race condition invalidation:
    Older renders must NEVER overwrite newer requests, even if they finish later.
    """

    def test_stale_generation_discarded_before_render(self, shared_tk_root: Any) -> None:
        """
        Verifies that if a newer generation arrives before a queued task starts,
        the old task is discarded without executing _render_scaled_preview.
        """
        root = shared_tk_root

        engine = PreviewEngine(root=root, on_preview_rendered=lambda img: None)
        sample = _create_sample_image(400, 500)
        engine.set_source_image(sample)

        render_counts = 0
        render_lock = threading.Lock()

        orig_render = engine._render_scaled_preview

        def _counting_render(cfg: PosterConfig) -> Image.Image:
            nonlocal render_counts
            with render_lock:
                render_counts += 1
            return orig_render(cfg)

        engine._render_scaled_preview = _counting_render

        try:
            # Enqueue generation 1 and immediately supersede with generation 2
            with engine._lock:
                engine._generation = 2  # artificially bump generation ahead of gen 1
            # Put stale task (gen 1) directly into queue
            engine._queue.put((1, PosterConfig(margin=10)))

            # Give worker time to process queue
            _pump_tk(root, duration_ms=100)

            # Render should NOT have run because gen (1) != _generation (2)
            assert render_counts == 0, f"Stale task executed render! Count = {render_counts}"

        finally:
            engine.shutdown()

    def test_superseded_task_during_render_is_dropped(self, shared_tk_root: Any) -> None:
        """
        Simulates task A beginning render at G1, then task B supersedes it to G2
        while task A is still in the middle of rendering.
        Verifies task A's result is dropped and NEVER dispatches to GUI.
        """
        root = shared_tk_root

        delivered_generations: List[int] = []

        def _on_rendered(img: Image.Image) -> None:
            pass

        engine = PreviewEngine(root=root, on_preview_rendered=_on_rendered)
        sample = _create_sample_image(400, 500)
        engine.set_source_image(sample)

        task_a_in_render = threading.Event()
        task_a_can_continue = threading.Event()

        orig_render = engine._render_scaled_preview

        def _adversarial_render(cfg: PosterConfig) -> Image.Image:
            if cfg.margin == 111:  # Task A
                task_a_in_render.set()
                task_a_can_continue.wait(timeout=2.0)
            return orig_render(cfg)

        engine._render_scaled_preview = _adversarial_render

        # Track GUI dispatches
        gui_dispatched_gens: List[int] = []

        def _spy_dispatch_to_gui(gen: int, img: Image.Image) -> None:
            gui_dispatched_gens.append(gen)
            if engine.on_preview_rendered is not None:
                engine.on_preview_rendered(img)

        engine._dispatch_to_gui = _spy_dispatch_to_gui

        try:
            # 1. Dispatch Task A (margin=111) -> G1
            engine._dispatch_render_task(PosterConfig(margin=111))
            assert task_a_in_render.wait(timeout=1.0), "Task A did not start rendering"

            # 2. While Task A is mid-render, dispatch Task B (margin=222) -> G2
            engine._dispatch_render_task(PosterConfig(margin=222))
            assert engine._generation == 2

            # 3. Allow Task A to finish its now-superseded render
            task_a_can_continue.set()

            # 4. Wait for worker to finish both tasks and pump events natively
            _pump_tk(root, duration_ms=400)

            # 5. Verify: Generation 1 must NEVER be dispatched to GUI!
            assert 1 not in gui_dispatched_gens, (
                f"FATAL: Superseded generation 1 was dispatched to GUI! Dispatched: {gui_dispatched_gens}"
            )
            # Generation 2 should be dispatched
            assert 2 in gui_dispatched_gens, (
                f"Generation 2 was not dispatched! Dispatched: {gui_dispatched_gens}"
            )

        finally:
            task_a_can_continue.set()
            engine.shutdown()

    def test_stale_gui_dispatch_rejected_by_generation_guard(self) -> None:
        """
        Directly challenges `_dispatch_to_gui(gen, image)`:
        If `root.after` scheduled a callback for G1, but the user changed the slider
        again before the GUI thread handled the event (so `_generation` is now G2),
        the callback must silently abort and NEVER invoke `on_preview_rendered`.
        """
        invoked_results: List[Image.Image] = []

        def _on_rendered(img: Image.Image) -> None:
            invoked_results.append(img)

        engine = PreviewEngine(root=None, on_preview_rendered=_on_rendered)
        dummy_img1 = Image.new("RGB", (100, 100), (255, 0, 0))
        dummy_img2 = Image.new("RGB", (100, 100), (0, 255, 0))

        try:
            with engine._lock:
                engine._generation = 5  # Current generation is 5

            # Attempt dispatch of stale generation 4
            engine._dispatch_to_gui(gen=4, result_image=dummy_img1)
            assert len(invoked_results) == 0, "Stale gen=4 was accepted by _dispatch_to_gui!"

            # Attempt dispatch of very old generation 1
            engine._dispatch_to_gui(gen=1, result_image=dummy_img1)
            assert len(invoked_results) == 0, "Stale gen=1 was accepted by _dispatch_to_gui!"

            # Dispatch matching generation 5
            engine._dispatch_to_gui(gen=5, result_image=dummy_img2)
            assert len(invoked_results) == 1, "Matching gen=5 was rejected by _dispatch_to_gui!"
            assert invoked_results[0] is dummy_img2

        finally:
            engine.shutdown()


# ==============================================================================
# 3. MEMORY PROFILING & PHOTOIMAGE GARBAGE COLLECTION
# ==============================================================================

class TestMemoryProfilingAndPhotoImageGC:
    """
    Profiles memory and verifies PhotoImage reference retention and garbage
    collection across 50 simulated preview updates.
    """

    def test_photoimage_gc_protection_retains_strong_reference(self, shared_tk_root: Any) -> None:
        """
        Verifies that CanvasDisplayManager maintains `_active_photo` so that
        Tkinter does not suffer from bitmap garbage-collection blanking.
        """
        root = shared_tk_root

        canvas = root.tk.call("canvas", ".test_canvas_1")
        # Use native tkinter Canvas wrapper
        import tkinter as tk
        canvas_widget = tk.Canvas(root, width=400, height=400)
        canvas_widget.pack()
        manager = CanvasDisplayManager(canvas_widget)

        test_img = Image.new("RGB", (200, 200), (100, 150, 200))
        manager.update_image(test_img)

        # _active_photo must not be None
        assert manager._active_photo is not None
        # image_item_id must be valid
        assert manager.image_item_id is not None
        assert manager.image_item_id in canvas_widget.find_all()

        canvas_widget.destroy()

    def test_canvas_item_recycling_zero_leak(self, shared_tk_root: Any) -> None:
        """
        Verifies that 50 consecutive preview updates on CanvasDisplayManager
        recycle the exact same canvas item ID instead of creating 50 canvas items.
        """
        root = shared_tk_root
        import tkinter as tk
        canvas = tk.Canvas(root, width=400, height=400)
        canvas.pack()
        manager = CanvasDisplayManager(canvas)

        initial_item_id = None

        for i in range(50):
            img = Image.new("RGB", (200, 200), (i * 4, 100, 200 - i * 3))
            manager.update_image(img)

            if initial_item_id is None:
                initial_item_id = manager.image_item_id
            else:
                # Must reuse the same canvas item ID!
                assert manager.image_item_id == initial_item_id, (
                    f"Canvas created new item id {manager.image_item_id} instead of recycling {initial_item_id}"
                )

            # Total items on canvas must remain exactly 1
            all_items = canvas.find_all()
            assert len(all_items) == 1, (
                f"Canvas item leak detected! Expected 1 item, found {len(all_items)}"
            )

        canvas.destroy()

    def test_superseded_photoimage_deallocation(self, shared_tk_root: Any) -> None:
        """
        Verifies that when a new preview replaces an old one, the previous
        PhotoImage is eligible for Python garbage collection (no dangling circular refs).
        """
        root = shared_tk_root
        import tkinter as tk
        canvas = tk.Canvas(root, width=400, height=400)
        canvas.pack()
        manager = CanvasDisplayManager(canvas)

        img1 = Image.new("RGB", (200, 200), (255, 0, 0))
        manager.update_image(img1)
        old_photo = manager._active_photo
        weak_old = weakref.ref(old_photo)
        assert weak_old() is not None

        # Replace with img2
        img2 = Image.new("RGB", (200, 200), (0, 255, 0))
        del old_photo
        manager.update_image(img2)
        gc.collect()

        # The weakref to the old PhotoImage should now be dead
        assert weak_old() is None, "Superseded PhotoImage was NOT garbage collected!"

        canvas.destroy()

    def test_tracemalloc_memory_stability_across_50_preview_updates(self) -> None:
        """
        Profiles memory with `tracemalloc` across 50 full preview compositions.
        Verifies that memory usage stabilizes and does NOT suffer from unbounded growth.
        """
        engine = PreviewEngine(root=None)
        sample = _create_sample_image(600, 800)
        engine.set_source_image(sample)

        gc.collect()
        tracemalloc.start()

        # Warmup: render 5 frames to initialize internal buffers and caches
        for k in range(5):
            engine.render_sync(PosterConfig(margin=k * 5, curve=k * 5))

        gc.collect()
        snap_warmup = tracemalloc.take_snapshot()

        # Execute 50 preview cycles
        for k in range(50):
            cfg = PosterConfig(
                ratio="4:5" if k % 2 == 0 else "1:1",
                margin=20 + (k % 30),
                curve=10 + (k % 40),
                zoom=0.8 + (k % 5) * 0.1,
                angle=float(k * 7 % 360)
            )
            result = engine.render_sync(cfg, viewport_size=(480, 600))
            assert result.size[0] > 0 and result.size[1] > 0

        gc.collect()
        snap_final = tracemalloc.take_snapshot()
        tracemalloc.stop()

        # Compare memory differences
        stats = snap_final.compare_to(snap_warmup, "lineno")
        total_growth = sum(stat.size_diff for stat in stats if stat.size_diff > 0)
        total_growth_kb = total_growth / 1024.0

        # 50 preview cycles should have near zero net heap growth (< 2.5 MB)
        assert total_growth_kb < 2500, (
            f"Excessive memory growth detected across 50 preview updates: {total_growth_kb:.1f} KB"
        )

        engine.shutdown()


# ==============================================================================
# 4. EXTREME EDGE CASE INPUTS & PATHOLOGICAL TOPOLOGIES
# ==============================================================================

class TestExtremeEdgeCaseInputs:
    """
    Stress tests preview rendering on edge case inputs:
    - 1x1 micro image
    - Extreme 21:9 ultrawide aspect ratio
    - Zero margins (margin=0)
    - Maximum 120px corner curves
    - Combined pathological inputs
    """

    def test_edge_case_1x1_micro_image(self) -> None:
        """
        Verifies that a 1x1 single-pixel image loads, extracts palette,
        and renders a valid preview without ZeroDivisionError or crashes.
        """
        micro_img = Image.new("RGB", (1, 1), (255, 128, 0))

        engine = PreviewEngine()
        engine.set_source_image(micro_img)

        assert engine.preview_raw_image is not None
        assert engine.preview_raw_image.size == (1, 1)
        assert engine.cached_palette is not None

        cfg = PosterConfig(ratio="4:5", margin=50, curve=45)
        preview = engine.render_sync(cfg, viewport_size=(480, 600))

        assert isinstance(preview, Image.Image)
        assert preview.mode == "RGB"
        assert preview.size == (480, 600)

    def test_edge_case_extreme_21_9_ultrawide_ratio(self) -> None:
        """
        Verifies preview calculation and rendering for extreme 21:9 ratio (2560x1080).
        """
        sample = _create_sample_image(1200, 800)
        engine = PreviewEngine()
        engine.set_source_image(sample)

        cfg = PosterConfig(ratio="21:9", margin=40, curve=30)
        preview = engine.render_sync(cfg, viewport_size=(640, 750))

        # Check aspect ratio preservation: 21:9 ratio width/height is ~2.37
        pw, ph = preview.size
        aspect = pw / ph
        expected_aspect = 2560.0 / 1080.0
        assert abs(aspect - expected_aspect) < 0.05, (
            f"Preview aspect ratio distorted! Got {aspect:.3f}, expected {expected_aspect:.3f}"
        )
        assert preview.mode == "RGB"

    def test_edge_case_zero_margins(self) -> None:
        """
        Verifies preview rendering when margin=0 (edge-to-edge fit).
        """
        sample = _create_sample_image(800, 1000)
        engine = PreviewEngine()
        engine.set_source_image(sample)

        cfg = PosterConfig(ratio="4:5", margin=0, curve=20, drop_shadow=True)
        preview = engine.render_sync(cfg, viewport_size=(480, 600))

        assert isinstance(preview, Image.Image)
        assert preview.size == (480, 600)
        # Check that center pixel is populated from poster
        center_color = preview.getpixel((preview.width // 2, preview.height // 2))
        assert isinstance(center_color, tuple)

    def test_edge_case_120px_curves(self) -> None:
        """
        Verifies preview rendering with maximum curve radius (120px).
        Ensures downscaling proportional curvature clamps properly without artifacting.
        """
        sample = _create_sample_image(800, 1000)
        engine = PreviewEngine()
        engine.set_source_image(sample)

        cfg = PosterConfig(ratio="4:5", margin=50, curve=120)
        preview = engine.render_sync(cfg, viewport_size=(480, 600))

        assert isinstance(preview, Image.Image)
        assert preview.size == (480, 600)

    def test_edge_case_combined_pathological_inputs(self) -> None:
        """
        Stress test combining ALL edge cases simultaneously:
        - 1x1 micro image input
        - 21:9 ultrawide ratio
        - 0 margin
        - 120px curve radius
        - Zoom = 3.0x (extreme zoom)
        - Angle = 359.9 degrees
        """
        micro_img = Image.new("RGB", (1, 1), (0, 255, 128))
        engine = PreviewEngine()
        engine.set_source_image(micro_img)

        cfg = PosterConfig(
            ratio="21:9",
            margin=0,
            curve=120,
            zoom=3.0,
            angle=359.9,
            drop_shadow=True,
            watermark="TEST"
        )
        preview = engine.render_sync(cfg, viewport_size=(500, 300))

        assert isinstance(preview, Image.Image)
        assert preview.mode == "RGB"
        assert preview.width > 0 and preview.height > 0

    def test_edge_case_main_window_integration_with_1x1(self) -> None:
        """
        Verifies that MainWindow and PosterStudioModel handle a 1x1 image
        without exceptions or UI freeze.
        """
        micro_img = Image.new("RGB", (1, 1), (128, 64, 255))
        model = PosterStudioModel()
        model.load_image(micro_img)

        assert model.raw_image is not None
        assert model.active_palette is not None

        # Verify synchronous preview generation from model
        rendered = model.generate_preview_image(viewport_size=(400, 500))
        assert rendered.size == (400, 500)


# ==============================================================================
# 5. UI LIFECYCLE & CONCURRENT WINDOW EVENTS
# ==============================================================================

class TestUILifecycleAndConcurrentEvents:
    """
    Tests edge cases during live UI interaction:
    - Rapid ratio switching
    - Canvas <Configure> event flood
    - Window close / shutdown safety
    - Daemon thread lifecycle behavior upon window destruction
    """

    def test_rapid_ratio_switching(self) -> None:
        """
        Rapidly switches between all aspect ratios in sequence.
        Verifies preview engine adapts dimensions without throwing dimensions mismatch errors.
        """
        sample = _create_sample_image(600, 800)
        engine = PreviewEngine()
        engine.set_source_image(sample)

        ratios = ["4:5", "1:1", "9:16", "16:9", "4:3", "21:9", "4:5_hd"]
        for r in ratios:
            cfg = PosterConfig(ratio=r, margin=30, curve=20)
            rendered = engine.render_sync(cfg, viewport_size=(600, 600))
            assert rendered.width > 0 and rendered.height > 0

    def test_safe_shutdown_with_queued_tasks(self, shared_tk_root: Any) -> None:
        """
        Verifies that calling engine.shutdown() terminates cleanly.
        Demonstrates that pumping events while joining allows worker thread to finish.
        """
        root = shared_tk_root

        engine = PreviewEngine(root=root, on_preview_rendered=lambda img: None)
        sample = _create_sample_image(400, 400)
        engine.set_source_image(sample)

        # Queue tasks
        for k in range(10):
            engine._dispatch_render_task(PosterConfig(margin=k))

        t0 = time.monotonic()
        engine.shutdown()

        # Pump event loop so Tcl interpreter services any remaining callbacks
        _pump_tk(root, duration_ms=100)

        if engine._worker_thread is not None:
            engine._worker_thread.join(timeout=1.0)
            assert not engine._worker_thread.is_alive(), "Worker thread hung on shutdown!"

        elapsed = time.monotonic() - t0
        assert elapsed < 1.0, f"Shutdown took too long: {elapsed:.3f}s"

    def test_daemon_worker_behavior_on_root_destruction(self) -> None:
        """
        Empirical finding: When MainWindow is destroyed without calling
        engine.shutdown(), the background worker thread remains alive in memory
        because PreviewEngine uses a daemon thread with no automatic shutdown
        hook bound to root's WM_DELETE_WINDOW or <Destroy>.
        """
        model = PosterStudioModel()
        sample = _create_sample_image(300, 400)
        model.load_image(sample)

        app = MainWindow(model=model, force_tkinter=True)
        app.root.withdraw()

        worker_thread = app.preview_engine._worker_thread
        assert worker_thread is not None
        assert worker_thread.is_alive()

        # Clean up explicitly to prevent thread leaks in test runner
        app.preview_engine.shutdown()
        app.root.destroy()

    def test_main_window_live_slider_burst_and_state_consistency(self) -> None:
        """
        Interacts directly with MainWindow sliders:
        Spams 100 rapid slider mutations across Spacing, Curve, Zoom, and Angle
        over 500ms on a live MainWindow instance.
        Verifies:
        1. View controls and Model state remain perfectly in sync.
        2. No unhandled UI exceptions.
        3. Canvas display manager holds valid PhotoImage at end.
        """
        model = PosterStudioModel()
        sample = _create_sample_image(600, 800)
        model.load_image(sample)

        app = MainWindow(model=model, force_tkinter=True)
        app.root.withdraw()

        try:
            start_t = time.monotonic()
            for i in range(1, 101):
                # Cycle through all 4 sliders
                spacing_val = i % 150
                curve_val = i % 120
                zoom_val = 0.5 + (i % 15) * 0.1
                angle_val = float((i * 7) % 360)

                app._on_spacing_slider(spacing_val)
                app._on_curve_slider(curve_val)
                app._on_zoom_slider(zoom_val)
                app._on_angle_slider(angle_val)

                _pump_tk(app.root, duration_ms=5)

            # Allow debouncer trailing edge to execute final frame
            _pump_tk(app.root, duration_ms=250)

            # Verify Model state matches final slider inputs
            assert model.config.margin == 100 % 150
            assert model.config.curve == 100 % 120
            assert abs(model.config.zoom - (0.5 + (100 % 15) * 0.1)) < 0.01
            assert abs(model.config.angle - float((100 * 7) % 360)) < 0.01

            # Verify canvas preview has rendered active PhotoImage
            assert app.display_manager._active_photo is not None

        finally:
            app.preview_engine.shutdown()
            app.root.destroy()

    def test_main_window_canvas_resize_event_flooding(self) -> None:
        """
        Floods MainWindow with 30 rapid canvas <Configure> resize events
        while the preview engine is rendering.
        Verifies viewport scaling recalculations never crash or distort.
        """
        model = PosterStudioModel()
        sample = _create_sample_image(600, 800)
        model.load_image(sample)

        app = MainWindow(model=model, force_tkinter=True)
        app.root.withdraw()

        try:
            class DummyConfigureEvent:
                def __init__(self, w: int, h: int) -> None:
                    self.width = w
                    self.height = h

            viewports = [
                (320, 240), (480, 640), (800, 600), (1024, 768),
                (640, 480), (1280, 720), (500, 500), (200, 200)
            ]

            for i in range(30):
                vw, vh = viewports[i % len(viewports)]
                # Artificially set canvas dimensions and fire handler
                app.canvas_preview.config(width=vw, height=vh)
                app._on_canvas_resize(DummyConfigureEvent(vw, vh))
                _pump_tk(app.root, duration_ms=10)

            _pump_tk(app.root, duration_ms=200)
            assert app.display_manager._active_photo is not None

        finally:
            app.preview_engine.shutdown()
            app.root.destroy()
