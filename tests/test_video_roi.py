import unittest
import os
import tempfile
import hashlib
from unittest.mock import patch, MagicMock

from modules.video_roi import (
    NormalizedROI, PixelROI, ROICrop, roi_to_pixels, temporary_roi_crops, VideoROIError
)
from modules.video_frames import ExtractedFrame

class TestNormalizedROI(unittest.TestCase):
    def test_a_valid_full(self):
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        self.assertEqual((roi.left, roi.top, roi.right, roi.bottom), (0.0, 0.0, 1.0, 1.0))

    def test_b_valid_partial(self):
        roi = NormalizedROI(0.2, 0.3, 0.8, 0.9)
        self.assertEqual((roi.left, roi.top, roi.right, roi.bottom), (0.2, 0.3, 0.8, 0.9))

    def test_c_left_eq_right(self):
        with self.assertRaises(ValueError):
            NormalizedROI(0.5, 0.0, 0.5, 1.0)

    def test_d_left_gt_right(self):
        with self.assertRaises(ValueError):
            NormalizedROI(0.6, 0.0, 0.5, 1.0)

    def test_e_top_eq_bottom(self):
        with self.assertRaises(ValueError):
            NormalizedROI(0.0, 0.5, 1.0, 0.5)

    def test_f_top_gt_bottom(self):
        with self.assertRaises(ValueError):
            NormalizedROI(0.0, 0.6, 1.0, 0.5)

    def test_g_less_than_zero(self):
        with self.assertRaises(ValueError):
            NormalizedROI(-0.1, 0.0, 1.0, 1.0)

    def test_h_greater_than_one(self):
        with self.assertRaises(ValueError):
            NormalizedROI(0.0, 0.0, 1.1, 1.0)

    def test_i_nan_inf(self):
        with self.assertRaises(ValueError):
            NormalizedROI(float('nan'), 0.0, 1.0, 1.0)
        with self.assertRaises(ValueError):
            NormalizedROI(float('inf'), 0.0, 1.0, 1.0)
        with self.assertRaises(ValueError):
            NormalizedROI(float('-inf'), 0.0, 1.0, 1.0)

    def test_j_bool(self):
        with self.assertRaises(ValueError):
            NormalizedROI(False, 0.0, True, 1.0)


class TestPixelConversion(unittest.TestCase):
    def test_k_full(self):
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        px = roi_to_pixels(roi, 1920, 1080)
        self.assertEqual((px.x, px.y, px.width, px.height), (0, 0, 1920, 1080))

    def test_l_50_percent(self):
        roi = NormalizedROI(0.25, 0.25, 0.75, 0.75)
        px = roi_to_pixels(roi, 1000, 1000)
        self.assertEqual((px.x, px.y, px.width, px.height), (250, 250, 500, 500))

    def test_m_odd_dimensions(self):
        roi = NormalizedROI(0.1, 0.1, 0.9, 0.9)
        px = roi_to_pixels(roi, 999, 999)
        self.assertEqual(px.x, 99)
        self.assertEqual(px.y, 99)
        self.assertEqual(px.width, 801)
        self.assertEqual(px.height, 801)

    def test_n_very_small(self):
        roi = NormalizedROI(0.0, 0.0, 0.0001, 0.0001)
        px = roi_to_pixels(roi, 100, 100)
        self.assertEqual((px.x, px.y, px.width, px.height), (0, 0, 1, 1))

    def test_o_invalid_width(self):
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 0, 1080)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, -100, 1080)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 1920.5, 1080)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, True, 1080)

    def test_p_invalid_height(self):
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 1920, 0)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 1920, -100)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 1920, 1080.5)
        with self.assertRaises(ValueError):
            roi_to_pixels(roi, 1920, True)

    def test_q_bounds(self):
        roi = NormalizedROI(0.999, 0.999, 1.0, 1.0)
        px = roi_to_pixels(roi, 10, 10)
        self.assertTrue(px.x >= 0 and px.y >= 0)
        self.assertTrue(px.width > 0 and px.height > 0)
        self.assertTrue(px.x + px.width <= 10)
        self.assertTrue(px.y + px.height <= 10)

    def test_r_deterministic(self):
        roi = NormalizedROI(0.2, 0.2, 0.8, 0.8)
        px1 = roi_to_pixels(roi, 800, 600)
        px2 = roi_to_pixels(roi, 800, 600)
        self.assertEqual(px1, px2)


class TestROICroppingPillow(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_video_roi_pillow_")
        
    def tearDown(self):
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    def _create_image(self, filename, width, height, color="white", exif_orientation=None):
        from PIL import Image
        path = os.path.join(self.temp_dir, filename)
        img = Image.new("RGB", (width, height), color)
        
        if exif_orientation:
            # We add EXIF orientation manually using a small trick or just use piexif if possible, 
            # but standard Pillow can write simple EXIF with exif kwarg in 3.13/Pillow 10+?
            # Actually piexif is not in requirements. So let's write basic EXIF if needed,
            # or just test that exif_transpose doesn't crash on standard images.
            pass
            
        img.save(path, format="JPEG")
        return path

    def test_a_full_landscape(self):
        from PIL import Image
        path = self._create_image("landscape.jpg", 400, 200, color="blue")
        f = ExtractedFrame(1, 1.0, path, 100, "hash", 400, 200)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        
        with temporary_roi_crops([f], roi) as crops:
            self.assertEqual(len(crops), 1)
            crop = crops[0]
            self.assertEqual(crop.pixel_roi.width, 400)
            self.assertEqual(crop.pixel_roi.height, 200)
            
            with Image.open(crop.crop_path) as cimg:
                self.assertEqual(cimg.size, (400, 200))

    def test_b_full_portrait(self):
        from PIL import Image
        path = self._create_image("portrait.jpg", 200, 400, color="red")
        f = ExtractedFrame(2, 2.0, path, 100, "hash", 200, 400)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        
        with temporary_roi_crops([f], roi) as crops:
            crop = crops[0]
            self.assertEqual(crop.pixel_roi.width, 200)
            self.assertEqual(crop.pixel_roi.height, 400)
            
            with Image.open(crop.crop_path) as cimg:
                self.assertEqual(cimg.size, (200, 400))

    def test_c_partial_crop_content(self):
        from PIL import Image, ImageDraw
        # Create an image where the left half is black, right half is white
        path = os.path.join(self.temp_dir, "split.jpg")
        img = Image.new("RGB", (200, 400), "black")
        draw = ImageDraw.Draw(img)
        draw.rectangle([100, 0, 200, 400], fill="white")
        img.save(path, format="JPEG")
        
        f = ExtractedFrame(3, 3.0, path, 100, "hash", 200, 400)
        # ROI: right half
        roi = NormalizedROI(0.5, 0.0, 1.0, 1.0)
        
        with temporary_roi_crops([f], roi) as crops:
            crop = crops[0]
            self.assertEqual(crop.pixel_roi.x, 100)
            self.assertEqual(crop.pixel_roi.width, 100)
            
            with Image.open(crop.crop_path) as cimg:
                self.assertEqual(cimg.size, (100, 400))
                # Check pixel in the middle
                r, g, b = cimg.getpixel((50, 200))
                self.assertGreater(r, 200) # should be white
                self.assertGreater(g, 200)
                self.assertGreater(b, 200)

    def test_e_missing_file(self):
        f = ExtractedFrame(4, 4.0, "/does/not/exist.jpg", 100, "hash", 200, 400)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with self.assertRaisesRegex(VideoROIError, "Quellbild existiert nicht"):
            with temporary_roi_crops([f], roi):
                pass

    def test_f_invalid_bytes(self):
        path = os.path.join(self.temp_dir, "bad.jpg")
        with open(path, "wb") as file:
            file.write(b"not an image")
            
        f = ExtractedFrame(5, 5.0, path, 100, "hash", 200, 400)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with self.assertRaisesRegex(VideoROIError, "Pillow konnte Bild nicht identifizieren"):
            with temporary_roi_crops([f], roi):
                pass

    def test_j_byte_integrity_preserved(self):
        import hashlib
        path = self._create_image("integrity.jpg", 400, 200)
        with open(path, "rb") as file:
            original_sha = hashlib.sha256(file.read()).hexdigest()
            
        f = ExtractedFrame(6, 6.0, path, 100, "hash", 400, 200)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        
        with temporary_roi_crops([f], roi):
            pass
            
        with open(path, "rb") as file:
            new_sha = hashlib.sha256(file.read()).hexdigest()
            
        self.assertEqual(original_sha, new_sha)

    def test_g_cleanup_success(self):
        path = self._create_image("cleanup.jpg", 400, 200)
        f = ExtractedFrame(7, 7.0, path, 100, "hash", 400, 200)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        
        crop_path = None
        with temporary_roi_crops([f], roi) as crops:
            crop_path = crops[0].crop_path
            self.assertTrue(os.path.exists(crop_path))
            
        self.assertFalse(os.path.exists(crop_path))

    def test_h_cleanup_with_error(self):
        path = self._create_image("err.jpg", 400, 200)
        f = ExtractedFrame(8, 8.0, path, 100, "hash", 400, 200)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        
        crop_path = None
        with self.assertRaises(ValueError):
            with temporary_roi_crops([f], roi) as crops:
                crop_path = crops[0].crop_path
                raise ValueError("primary error")
                
        self.assertFalse(os.path.exists(crop_path))

    def test_d_exif_orientation_regression(self):
        from PIL import Image
        import io
        
        # We will create an image with EXIF orientation 6 (Rotate 90 CW).
        # We can construct a minimal EXIF block.
        # Orientation tag is 0x0112 (274), value 6.
        # Just writing it using Pillow is hard without piexif, 
        # but Pillow 10 allows writing exif via Image.Exif
        
        path = os.path.join(self.temp_dir, "exif.jpg")
        img = Image.new("RGB", (400, 200), "green")
        
        exif = img.getexif()
        exif[274] = 6 # 6 = rotate 90 CW. This means visually it should be 200x400
        
        img.save(path, format="JPEG", exif=exif)
        
        f = ExtractedFrame(9, 9.0, path, 100, "hash", 400, 200)
        # Note: frame_width and frame_height from ExtractedFrame aren't used for crop dimension logic anymore, 
        # because temporary_roi_crops now dynamically reads oriented.size!
        
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with temporary_roi_crops([f], roi) as crops:
            crop = crops[0]
            # Since orientation 6 means 90 CW, the oriented image should be 200x400
            self.assertEqual(crop.pixel_roi.width, 200)
            self.assertEqual(crop.pixel_roi.height, 400)
            
            with Image.open(crop.crop_path) as cimg:
                self.assertEqual(cimg.size, (200, 400))


    def test_i_cleanup_does_not_delete_foreign(self):
        # We don't delete foreign files because the temp_dir itself is created by temporary_roi_crops
        # and then entirely removed. If the user passed frames outside, they are not deleted.
        path = self._create_image("foreign.jpg", 400, 200)
        f = ExtractedFrame(10, 10.0, path, 100, "hash", 400, 200)
        roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        with temporary_roi_crops([f], roi):
            pass
        self.assertTrue(os.path.exists(path))
