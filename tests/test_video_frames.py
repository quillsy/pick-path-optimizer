import unittest
import os
import json
import math
import tempfile
import shutil
import hashlib
from unittest.mock import patch, MagicMock
import subprocess

from modules.video_frames import (
    probe_video,
    calculate_sample_timestamps,
    temporary_extracted_frames,
    select_preview_frames,
    VideoMetadata,
    ExtractedFrame,
    VideoFramesError,
    MAX_EXTRACTED_FRAMES,
    MAX_PREVIEW_FRAMES
)

class TestVideoFramesMetadata(unittest.TestCase):
    def setUp(self):
        self.valid_ffprobe_data = {
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "r_frame_rate": "30/1",
                    "duration": "10.5",
                    "nb_frames": "315"
                }
            ],
            "format": {
                "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
                "duration": "10.5"
            }
        }

    @patch('modules.video_frames.subprocess.run')
    def test_a_valid_json_parsed(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(self.valid_ffprobe_data))
        meta = probe_video("fake.mp4")
        self.assertEqual(meta.duration_seconds, 10.5)
        self.assertEqual(meta.width, 1920)
        self.assertEqual(meta.height, 1080)
        self.assertEqual(meta.fps, 30.0)
        self.assertEqual(meta.frame_count, 315)
        self.assertEqual(meta.video_codec, "h264")
        self.assertEqual(meta.container_format, "mov,mp4,m4a,3gp,3g2,mj2")

    @patch('modules.video_frames.subprocess.run')
    def test_b_fps_fractional(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["r_frame_rate"] = "30000/1001"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        meta = probe_video("fake.mp4")
        self.assertAlmostEqual(meta.fps, 29.97, places=2)

    @patch('modules.video_frames.subprocess.run')
    def test_c_frame_count_missing(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        del data["streams"][0]["nb_frames"]
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        meta = probe_video("fake.mp4")
        self.assertIsNone(meta.frame_count)

    @patch('modules.video_frames.subprocess.run')
    def test_d_no_video_stream(self, mock_run):
        data = {"streams": [{"codec_type": "audio"}]}
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_e_duration_invalid(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["duration"] = "-5.0"
        data["format"]["duration"] = "-5.0"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_f_dimensions_invalid(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["width"] = "0"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_g_fps_invalid(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["r_frame_rate"] = "0/0"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_h_ffprobe_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_i_ffprobe_nonzero(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j_invalid_json(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="{broken")
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")


    @patch('modules.video_frames.subprocess.run')
    def test_j2_stdout_null(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="null")
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j3_stdout_empty_array(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="[]")
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j4_streams_not_array(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": "string"}')
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j5_duration_nan(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["duration"] = "nan"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j6_duration_inf(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["duration"] = "inf"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

    @patch('modules.video_frames.subprocess.run')
    def test_j7_shell_false(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(self.valid_ffprobe_data))
        probe_video("fake.mp4")
        kwargs = mock_run.call_args.kwargs
        self.assertFalse(kwargs.get("shell", False))
        self.assertIn("timeout", kwargs)
        args = mock_run.call_args.args[0]
        self.assertIsInstance(args, list)
        self.assertEqual(args[0], "ffprobe")


    @patch('modules.video_frames.subprocess.run')
    def test_j6_duration_minus_inf(self, mock_run):
        data = dict(self.valid_ffprobe_data)
        data["streams"][0]["duration"] = "-inf"
        mock_run.return_value = MagicMock(returncode=0, stdout=json.dumps(data))
        with self.assertRaises(VideoFramesError):
            probe_video("fake.mp4")

class TestVideoFramesSampling(unittest.TestCase):

    def test_a_max_frames_1(self):
        self.assertEqual(calculate_sample_timestamps(10.0, 0.5, 1), [0.0])

    def test_b_duration_nan_inf(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(float('nan'))
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(float('inf'))
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(float('-inf'))

    def test_c_interval_nan_inf(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, float('nan'))
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, float('inf'))
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, float('-inf'))

    def test_d_boolean_args(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(True, 0.5, 10)
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, True, 10)
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, 0.5, True)

    def test_e_extreme_sampling(self):
        samples = calculate_sample_timestamps(1_000_000_000.0, 0.0001, 300)
        self.assertLessEqual(len(samples), 300)
        self.assertEqual(samples[0], 0.0)
        self.assertLess(samples[-1], 1_000_000_000.0)
        self.assertGreater(samples[-1], 900_000_000.0)
        self.assertEqual(samples, sorted(list(set(samples))))


    def test_e2_overflow_sampling(self):
        samples = calculate_sample_timestamps(1e308, 1e-308, 300)
        self.assertEqual(len(samples), 300)
        self.assertEqual(samples[0], 0.0)
        self.assertTrue(all(math.isfinite(s) for s in samples))
        self.assertTrue(all(0 <= s < 1e308 for s in samples))
        self.assertEqual(samples, sorted(list(set(samples))))

    def test_e3_normal_raster_preservation(self):
        self.assertEqual(calculate_sample_timestamps(2.0, 0.5), [0.0, 0.5, 1.0, 1.5])
        self.assertEqual(calculate_sample_timestamps(2.2, 0.5), [0.0, 0.5, 1.0, 1.5, 2.0])
        self.assertEqual(calculate_sample_timestamps(0.3, 0.5), [0.0])
        self.assertEqual(calculate_sample_timestamps(10.0, 0.5, 1), [0.0])

    def test_f_not_exact_multiple(self):
        samples = calculate_sample_timestamps(2.2, 0.5)
        self.assertTrue(all(s < 2.2 for s in samples))
        self.assertEqual(samples, [0.0, 0.5, 1.0, 1.5, 2.0])

    def test_k_standard_interval(self):
        samples = calculate_sample_timestamps(2.0, 0.5)
        self.assertEqual(samples, [0.0, 0.5, 1.0, 1.5])

    def test_l_short_video(self):
        samples = calculate_sample_timestamps(0.3, 0.5)
        self.assertEqual(samples, [0.0])

    def test_m_no_sample_beyond_duration(self):
        samples = calculate_sample_timestamps(1.0, 0.5)
        self.assertTrue(all(s < 1.0 for s in samples))

    def test_n_very_long_video(self):
        samples = calculate_sample_timestamps(1000.0, 0.5, 300)
        self.assertLessEqual(len(samples), 300)
        self.assertEqual(samples[0], 0.0)
        self.assertLess(samples[-1], 1000.0)
        self.assertGreater(samples[-1], 900.0) # Should reach the end

    def test_o_strictly_ascending(self):
        samples = calculate_sample_timestamps(1000.0, 0.5, 300)
        self.assertEqual(samples, sorted(list(set(samples))))

    def test_p_duration_invalid(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(0.0)

    def test_q_interval_invalid(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, 0.0)

    def test_r_max_frames_invalid(self):
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, 0.5, 0)
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, 0.5, 10.5)
        with self.assertRaises(ValueError):
            calculate_sample_timestamps(10.0, 0.5, True)

    def test_s_deterministic(self):
        s1 = calculate_sample_timestamps(1000.0, 0.5, 300)
        s2 = calculate_sample_timestamps(1000.0, 0.5, 300)
        self.assertEqual(s1, s2)

class TestVideoFramesExtraction(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = self.temp_dir_obj.name
        self.original_mkdtemp = tempfile.mkdtemp
        self.captured_temp_dir = None

    def tearDown(self):
        if self.captured_temp_dir and os.path.exists(self.captured_temp_dir):
            shutil.rmtree(self.captured_temp_dir, ignore_errors=True)
        self.temp_dir_obj.cleanup()

    def patched_mkdtemp(self, **kwargs):
        kwargs['dir'] = self.temp_dir
        path = self.original_mkdtemp(**kwargs)
        self.captured_temp_dir = path
        return path

    @patch('modules.video_frames.subprocess.run')
    def test_t_three_timestamps(self, mock_run):
        timestamps = [0.0, 0.5, 1.0]

        def side_effect(cmd, **kwargs):
            if cmd[0] == "ffmpeg":
                out_path = cmd[-1]
                with open(out_path, "wb") as f:
                    f.write(b"fake jpeg data")
                return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
            elif cmd[0] == "ffprobe":
                return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')

        mock_run.side_effect = side_effect

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with temporary_extracted_frames("fake.mp4", timestamps) as frames:
                self.assertEqual(len(frames), 3)
                self.assertEqual(mock_run.call_count, 6)
                for i, f in enumerate(frames):
                    self.assertEqual(f.sequence_index, i)
                    self.assertEqual(f.timestamp_seconds, timestamps[i])
                    self.assertTrue(os.path.exists(f.path))
                    self.assertGreater(f.size_bytes, 0)

    @patch('modules.video_frames.subprocess.run')
    def test_u_files_exist_in_context(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                self.assertTrue(os.path.exists(frames[0].path))

    @patch('modules.video_frames.subprocess.run')
    def test_v_files_removed_after_context(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                saved_path = frames[0].path
            self.assertFalse(os.path.exists(saved_path))
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    @patch('modules.video_frames.subprocess.run')
    def test_w_ffmpeg_nonzero(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with self.assertRaises(VideoFramesError):
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    @patch('modules.video_frames.subprocess.run')
    def test_x_ffmpeg_missing(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with self.assertRaises(VideoFramesError):
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    @patch('modules.video_frames.subprocess.run')
    def test_y_ffmpeg_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="ffmpeg", timeout=30)
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with self.assertRaises(VideoFramesError):
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    @patch('modules.video_frames.subprocess.run')
    def test_z_output_missing(self, mock_run):
        mock_run.side_effect = lambda cmd, **k: MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}') # But file is not created
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with self.assertRaises(VideoFramesError):
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    @patch('modules.video_frames.subprocess.run')
    def test_aa_output_empty(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: pass # Empty
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with self.assertRaises(VideoFramesError):
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            self.assertFalse(os.path.exists(self.captured_temp_dir))

    def test_ab_too_many_timestamps(self):
        ts = [0.0] * (MAX_EXTRACTED_FRAMES + 1)
        with self.assertRaises(VideoFramesError):
            with temporary_extracted_frames("fake.mp4", ts):
                pass

    def test_ac_negative_timestamp(self):
        with self.assertRaises(VideoFramesError):
            with temporary_extracted_frames("fake.mp4", [-1.0]):
                pass

    @patch('modules.video_frames.subprocess.run')
    def test_ad_timestamp_beyond_duration(self, mock_run):
        # Die obere Grenze zur Videodauer liegt bewusst beim Sampling-Aufrufer;
        # diese API kennt keine Videodauer.
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with temporary_extracted_frames("fake.mp4", [9999.0]) as frames:
                self.assertEqual(frames[0].timestamp_seconds, 9999.0)
                found = any("9999.0" in c.args[0] for c in mock_run.call_args_list)
                self.assertTrue(found)
                kwargs = mock_run.call_args.kwargs
                self.assertFalse(kwargs.get("shell", False))
                self.assertIn("timeout", kwargs)
                self.assertEqual(mock_run.call_args_list[0].args[0][0], "ffmpeg")

    @patch('modules.video_frames.subprocess.run')
    def test_ae_foreign_file_protected(self, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect

        foreign_path = os.path.join(self.temp_dir, "foreign.jpg")
        with open(foreign_path, "wb") as f:
            f.write(b"foreign data")

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                self.assertTrue(os.path.exists(foreign_path))

        self.assertTrue(os.path.exists(foreign_path))
        with open(foreign_path, "rb") as f:
            self.assertEqual(f.read(), b"foreign data")

    @patch('modules.video_frames.subprocess.run')
    @patch('modules.video_frames.shutil.rmtree')
    def test_af_primary_error_and_cleanup_error(self, mock_rmtree, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect
        mock_rmtree.side_effect = OSError("cleanup error")

        primary_exception = RuntimeError("Primary error")
        caught = None

        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            try:
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    raise primary_exception
            except BaseException as e:
                caught = e

        self.assertIs(caught, primary_exception)

    @patch('modules.video_frames.subprocess.run')
    @patch('modules.video_frames.shutil.rmtree')
    def test_ag_cleanup_error_after_success(self, mock_rmtree, mock_run):
        def side_effect(cmd, **kwargs):
            with open(cmd[-1], "wb") as f: f.write(b"data")
            return MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        mock_run.side_effect = side_effect
        cleanup_exception = OSError("cleanup error")
        mock_rmtree.side_effect = cleanup_exception

        caught = None
        with patch('modules.video_frames.tempfile.mkdtemp', side_effect=self.patched_mkdtemp):
            try:
                with temporary_extracted_frames("fake.mp4", [0.0]) as frames:
                    pass
            except BaseException as e:
                caught = e

        self.assertIs(caught, cleanup_exception)

class TestPreviewSelection(unittest.TestCase):

    def test_select_preview_empty(self):
        self.assertEqual(select_preview_frames([]), [])

    def test_select_preview_max_1(self):
        frames = [ExtractedFrame(i, i*0.5, "path", 100, "hash", 1920, 1080) for i in range(5)]
        selected = select_preview_frames(frames, 1)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0].sequence_index, 0)

    def test_select_preview_max_invalid(self):
        frames = [ExtractedFrame(i, i*0.5, "path", 100, "hash", 1920, 1080) for i in range(5)]
        with self.assertRaises(ValueError):
            select_preview_frames(frames, 0)
        with self.assertRaises(ValueError):
            select_preview_frames(frames, -1)
        with self.assertRaises(ValueError):
            select_preview_frames(frames, 1.5)
        with self.assertRaises(ValueError):
            select_preview_frames(frames, True)

    def test_select_preview_less_than_max(self):
        frames = [ExtractedFrame(i, i*0.5, "path", 100, "hash", 1920, 1080) for i in range(5)]
        selected = select_preview_frames(frames, 12)
        self.assertEqual(selected, frames)

    def test_select_preview_more_than_max(self):
        frames = [ExtractedFrame(i, i*0.5, "path", 100, "hash", 1920, 1080) for i in range(100)]
        selected = select_preview_frames(frames, 12)
        self.assertEqual(len(selected), 12)
        self.assertEqual(selected[0].sequence_index, 0)
        self.assertEqual(selected[-1].sequence_index, 99)
        self.assertEqual(len(set(f.sequence_index for f in selected)), 12)

    def test_select_preview_invalid(self):
        with self.assertRaises(ValueError):
            select_preview_frames([], 0)

if __name__ == '__main__':
    unittest.main()

class TestImageProbing(unittest.TestCase):
    @patch('modules.video_frames.subprocess.run')
    def test_a_valid_portrait(self, mock_run):
        from modules.video_frames import _probe_image_dimensions
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": 2160, "height": 3840}]}')
        w, h = _probe_image_dimensions("test.jpg")
        self.assertEqual(w, 2160)
        self.assertEqual(h, 3840)

    @patch('modules.video_frames.subprocess.run')
    def test_b_valid_landscape(self, mock_run):
        from modules.video_frames import _probe_image_dimensions
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": 3840, "height": 2160}]}')
        w, h = _probe_image_dimensions("test.jpg")
        self.assertEqual(w, 3840)
        self.assertEqual(h, 2160)

    @patch('modules.video_frames.subprocess.run')
    def test_c_missing_dimensions(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{}]}')
        with self.assertRaisesRegex(VideoFramesError, "Bildbreite aus ffprobe ist ungültig"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_d_zero_dimensions(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": 0, "height": 1080}]}')
        with self.assertRaisesRegex(VideoFramesError, "Bildbreite aus ffprobe ist ungültig"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_e_float_dimensions(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": 1920.5, "height": 1080}]}')
        with self.assertRaisesRegex(VideoFramesError, "Bildbreite aus ffprobe ist ungültig"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_f_bool_dimensions(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": true, "height": 1080}]}')
        with self.assertRaisesRegex(VideoFramesError, "Bildbreite aus ffprobe ist ungültig"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_g_nonzero_exit(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        import subprocess
        mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
        with self.assertRaisesRegex(VideoFramesError, "Fehler beim Lesen der Bilddimensionen"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_h_missing_ffprobe(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.side_effect = FileNotFoundError()
        with self.assertRaisesRegex(VideoFramesError, "nicht installiert"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_i_invalid_json(self, mock_run):
        from modules.video_frames import _probe_image_dimensions, VideoFramesError
        mock_run.return_value = MagicMock(returncode=0, stdout='invalid json')
        with self.assertRaisesRegex(VideoFramesError, "Ungültiges JSON-Format"):
            _probe_image_dimensions("test.jpg")

    @patch('modules.video_frames.subprocess.run')
    def test_j_subprocess_args(self, mock_run):
        from modules.video_frames import _probe_image_dimensions
        mock_run.return_value = MagicMock(returncode=0, stdout='{"streams": [{"width": 1920, "height": 1080}]}')
        _probe_image_dimensions("test.jpg")
        kwargs = mock_run.call_args.kwargs
        self.assertTrue(kwargs.get("capture_output"))
        self.assertTrue(kwargs.get("text"))
        self.assertFalse(kwargs.get("shell"))
        self.assertTrue(kwargs.get("check"))
        self.assertEqual(kwargs.get("timeout"), 10)

class TestCommonFrameDimensions(unittest.TestCase):
    def test_valid(self):
        from modules.video_frames import get_common_frame_dimensions, ExtractedFrame
        frames = [
            ExtractedFrame(0, 0.0, "p", 1, "h", 1920, 1080),
            ExtractedFrame(1, 1.0, "p", 1, "h", 1920, 1080)
        ]
        self.assertEqual(get_common_frame_dimensions(frames), (1920, 1080))
        
    def test_inconsistent(self):
        from modules.video_frames import get_common_frame_dimensions, ExtractedFrame, VideoFramesError
        frames = [
            ExtractedFrame(0, 0.0, "p", 1, "h", 1920, 1080),
            ExtractedFrame(1, 1.0, "p", 1, "h", 1080, 1920)
        ]
        with self.assertRaisesRegex(VideoFramesError, "Inkonsistente Frame-Dimensionen"):
            get_common_frame_dimensions(frames)
            
    def test_empty(self):
        from modules.video_frames import get_common_frame_dimensions, VideoFramesError
        with self.assertRaisesRegex(VideoFramesError, "Keine Frames übergeben"):
            get_common_frame_dimensions([])
