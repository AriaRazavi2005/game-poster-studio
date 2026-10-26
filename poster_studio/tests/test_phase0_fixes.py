"""
Unit tests for Phase 0 infrastructure, bug fixes, and types.
"""

import io
import unittest
from PIL import Image
import numpy as np

from poster_studio import __version__, create_game_poster, create_game_collage
from poster_studio.core.types import Box, Point, Size
from poster_studio.core.gradient import generate_linear_gradient
from poster_studio.core.processor import PosterProcessor, PosterConfig
from poster_studio.core.watermark import calculate_watermark_position, apply_watermark
from poster_studio.core.palette import extract_dominant_colors


class TestPhase0Types(unittest.TestCase):
    """Test Box, Point, Size primitives."""

    def test_box_from_ltrb(self):
        box = Box.from_ltrb(10, 20, 110, 220)
        self.assertEqual(box.left, 10)
        self.assertEqual(box.top, 20)
        self.assertEqual(box.right, 110)
        self.assertEqual(box.bottom, 220)
        self.assertEqual(box.width, 100)
        self.assertEqual(box.height, 200)
        self.assertEqual(box.center_x, 60.0)
        self.assertEqual(box.center_y, 120.0)

    def test_box_from_xywh(self):
        box = Box.from_xywh(10, 20, 100, 200)
        self.assertEqual(box.as_ltrb(), (10, 20, 110, 220))
        self.assertEqual(box.as_xywh(), (10, 20, 100, 200))

    def test_box_unpacking(self):
        box = Box.from_ltrb(5, 10, 15, 20)
        l, t, r, b = box
        self.assertEqual((l, t, r, b), (5, 10, 15, 20))
        self.assertEqual(box[0], 5)
        self.assertEqual(box[3], 20)

    def test_box_contains(self):
        box = Box.from_ltrb(0, 0, 100, 100)
        self.assertTrue(box.contains(50, 50))
        self.assertFalse(box.contains(150, 50))


class TestPhase0BugFixes(unittest.TestCase):
    """Test bug fixes: EXIF transpose, Alpha harmonization, watermark pos mode, gradient dithering."""

    def test_exif_transpose_on_load(self):
        """Image with EXIF orientation=6 (rotated 90 deg) must be transposed on load."""
        # Create non-square 100x200 image
        img = Image.new("RGB", (100, 200), color=(200, 50, 50))
        exif = img.getexif()
        # Tag 0x0112 is Orientation. 6 corresponds to 90 CW rotation
        exif[0x0112] = 6

        bio = io.BytesIO()
        img.save(bio, format="JPEG", exif=exif)
        bio.seek(0)

        # Process with PosterProcessor
        loaded = PosterProcessor._load_image(bio)
        # 100x200 rotated 90 deg becomes 200x100
        self.assertEqual(loaded.size, (200, 100))

    def test_alpha_compositing_consistency(self):
        """Palette extraction on transparent RGBA should composite on black, matching processor."""
        # Create half-transparent, half-red image
        rgba = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        for x in range(50):
            for y in range(100):
                rgba.putpixel((x, y), (255, 0, 0, 255))

        c1, c2 = extract_dominant_colors(rgba)
        # Dominant color must be pure red (255, 0, 0), not washed out white
        self.assertEqual(c1[0], 255)
        self.assertLess(c1[1], 30)
        self.assertLess(c1[2], 30)

    def test_watermark_pos_mode_explicit(self):
        """watermark_pos_mode='absolute' should not treat coordinates 1, 1 as relative 100%."""
        canvas_size = (1000, 1000)
        text_size = (100, 40)

        # In absolute mode, custom_pos=(1, 1) means pixel coordinates centered at (1, 1) -> clamped to 0, 0
        pos_abs = calculate_watermark_position(
            canvas_size=canvas_size,
            text_size=text_size,
            custom_pos=(1.0, 1.0),
            pos_mode="absolute"
        )
        self.assertEqual(pos_abs, (0, 0))

        # In relative mode, custom_pos=(1.0, 1.0) means bottom-right edge (1000 - 100, 1000 - 40)
        pos_rel = calculate_watermark_position(
            canvas_size=canvas_size,
            text_size=text_size,
            custom_pos=(1.0, 1.0),
            pos_mode="relative"
        )
        self.assertEqual(pos_rel, (900, 960))

    def test_watermark_with_box_instance(self):
        """calculate_watermark_position accepts Box instance without ambiguity."""
        canvas_size = (1080, 1350)
        text_size = (100, 30)
        card_box = Box.from_ltrb(50, 50, 1030, 1250)

        pos = calculate_watermark_position(
            canvas_size=canvas_size,
            text_size=text_size,
            position="bottom_center",
            card_placement=card_box
        )
        self.assertIsInstance(pos, tuple)
        self.assertEqual(len(pos), 2)
        # Text should be centered horizontally
        self.assertEqual(pos[0], (1080 - 100) // 2)

    def test_gradient_dithering(self):
        """Gradient generated with dither=True applies Bayer matrix to eliminate flat banding."""
        c1 = (10, 10, 10)
        c2 = (15, 15, 15)
        img_nodither = generate_linear_gradient(200, 200, c1, c2, dither=False)
        img_dither = generate_linear_gradient(200, 200, c1, c2, dither=True)

        arr_nodither = np.array(img_nodither)
        arr_dither = np.array(img_dither)

        # Dithering modifies pixel values at transition thresholds
        self.assertFalse(np.array_equal(arr_nodither, arr_dither))
        diff_count = np.count_nonzero(arr_nodither != arr_dither)
        self.assertGreater(diff_count, 100)


class TestBackwardCompatibility(unittest.TestCase):
    """Verify root shims and version."""

    def test_version_string(self):
        self.assertTrue(__version__.startswith("2.0.0"))

    def test_root_bridge_shim_imports(self):
        import telegram_bridge as tb
        self.assertTrue(hasattr(tb, "create_game_poster"))
        self.assertTrue(hasattr(tb, "create_game_collage"))
        self.assertTrue(hasattr(tb, "TelegramBridgeError"))

    def test_root_cli_shim_imports(self):
        import cli
        self.assertTrue(hasattr(cli, "main"))
        self.assertTrue(hasattr(cli, "build_arg_parser"))


if __name__ == "__main__":
    unittest.main()
