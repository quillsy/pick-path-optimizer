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


class TestROICropping(unittest.TestCase):
    def setUp(self):
        self.roi = NormalizedROI(0.0, 0.0, 1.0, 1.0)
        self.frames = [
            ExtractedFrame(0, 0.0, "frame0.jpg", 100, "hash0"),
            ExtractedFrame(1, 1.5, "frame1.jpg", 100, "hash1"),
            ExtractedFrame(2, 3.0, "frame2.jpg", 100, "hash2"),
        ]
        self.temp_dir = tempfile.mkdtemp(prefix="test_roi_crops_")
        self.patched_mkdtemp = patch('modules.video_roi.tempfile.mkdtemp').start()
        self.patched_mkdtemp.return_value = self.temp_dir

        # Write dummy files to represent inputs (though subprocess will be mocked anyway)
        for f in self.frames:
            with open(os.path.join(self.temp_dir, f.path), 'wb') as fp:
                fp.write(b"dummy_input")

    def tearDown(self):
        patch.stopall()
        if os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)

    @patch('modules.video_roi.subprocess.run')
    def test_s_three_frames(self, mock_run):
        def side_effect(cmd, **kwargs):
            # Create a fake output file
            output_path = cmd[-1]
            with open(output_path, "wb") as f:
                f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        with temporary_roi_crops(self.frames, self.roi, 100, 100) as crops:
            self.assertEqual(len(crops), 3)
            self.assertEqual(mock_run.call_count, 3)
            for i, crop in enumerate(crops):
                self.assertEqual(crop.sequence_index, i)
                self.assertEqual(crop.timestamp_seconds, self.frames[i].timestamp_seconds)
                self.assertTrue(os.path.exists(crop.crop_path))
                self.assertGreater(crop.size_bytes, 0)
                self.assertIsInstance(crop.sha256, str)

    @patch('modules.video_roi.subprocess.run')
    def test_t_crop_pixels(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        roi = NormalizedROI(0.25, 0.25, 0.75, 0.75)
        with temporary_roi_crops([self.frames[0]], roi, 1000, 1000) as crops:
            cmd = mock_run.call_args.args[0]
            self.assertIn("crop=500:500:250:250", cmd)

    @patch('modules.video_roi.subprocess.run')
    def test_u_subprocess_args(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100) as crops:
            args = mock_run.call_args.args[0]
            kwargs = mock_run.call_args.kwargs
            self.assertIsInstance(args, list)
            self.assertFalse(kwargs.get('shell', False))

    @patch('modules.video_roi.subprocess.run')
    def test_v_subprocess_timeout(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100) as crops:
            kwargs = mock_run.call_args.kwargs
            self.assertIn('timeout', kwargs)

    @patch('modules.video_roi.subprocess.run')
    def test_w_output_missing(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        with self.assertRaises(VideoROIError):
            with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                pass
        self.assertFalse(os.path.exists(self.temp_dir))

    @patch('modules.video_roi.subprocess.run')
    def test_x_output_empty(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: pass
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect
        with self.assertRaises(VideoROIError):
            with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                pass

    @patch('modules.video_roi.subprocess.run')
    def test_y_subprocess_nonzero(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffmpeg")
        with self.assertRaises(VideoROIError):
            with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                pass

    @patch('modules.video_roi.subprocess.run')
    def test_z_ffmpeg_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaises(VideoROIError):
            with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                pass

    @patch('modules.video_roi.subprocess.run')
    def test_aa_ffmpeg_timeout(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("ffmpeg", 30)
        with self.assertRaises(VideoROIError):
            with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                pass

    @patch('modules.video_roi.subprocess.run')
    def test_ab_exist_in_context(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100) as crops:
            self.assertTrue(os.path.exists(crops[0].crop_path))

    @patch('modules.video_roi.subprocess.run')
    def test_ac_removed_after_context(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        crop_path = None
        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100) as crops:
            crop_path = crops[0].crop_path

        self.assertFalse(os.path.exists(crop_path))
        self.assertFalse(os.path.exists(self.temp_dir))

    @patch('modules.video_roi.subprocess.run')
    def test_ad_original_frames_preserved(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        import tempfile
        import shutil
        # Get a real temp dir bypassing the mock
        import os
        foreign_dir = os.path.realpath(tempfile._mkdtemp_inner(tempfile.gettempdir(), tempfile.gettempprefix(), None, None, None)[1]) if hasattr(tempfile, '_mkdtemp_inner') else '/tmp/test_roi_foreign'
        os.makedirs(foreign_dir, exist_ok=True)
        frame_path = os.path.join(foreign_dir, self.frames[0].path)
        with open(frame_path, 'wb') as fp:
            fp.write(b"original")

        old_path = self.frames[0].path
        object.__setattr__(self.frames[0], 'path', frame_path) # ExtractedFrame is frozen

        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100) as crops:
            pass

        self.assertTrue(os.path.exists(frame_path))
        object.__setattr__(self.frames[0], 'path', old_path)
        shutil.rmtree(foreign_dir)

    @patch('modules.video_roi.subprocess.run')
    def test_ae_foreign_file_protected(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        fd, foreign_path = tempfile.mkstemp()
        os.close(fd)
        with open(foreign_path, 'wb') as fp:
            fp.write(b"foreign")

        with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
            pass

        self.assertTrue(os.path.exists(foreign_path))
        with open(foreign_path, 'rb') as fp:
            self.assertEqual(fp.read(), b"foreign")
        os.remove(foreign_path)

    @patch('modules.video_roi.subprocess.run')
    def test_af_primary_and_cleanup_error(self, mock_run):
        mock_run.side_effect = FileNotFoundError()

        class MockException(Exception): pass

        with patch('modules.video_roi.shutil.rmtree', side_effect=MockException):
            try:
                with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                    pass
            except Exception as e:
                caught = e
            self.assertIsInstance(caught, VideoROIError)

    @patch('modules.video_roi.subprocess.run')
    def test_ag_cleanup_error_visible(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"fakecrop")
            return MagicMock(returncode=0)
        mock_run.side_effect = side_effect

        class MockException(Exception): pass

        with patch('modules.video_roi.shutil.rmtree', side_effect=MockException):
            try:
                with temporary_roi_crops([self.frames[0]], self.roi, 100, 100):
                    pass
            except Exception as e:
                caught = e
            self.assertIsInstance(caught, MockException)
