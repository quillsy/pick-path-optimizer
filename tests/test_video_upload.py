import unittest
import os
import tempfile
import hashlib
from unittest.mock import patch, mock_open
from modules.video_upload import temporary_uploaded_video, UploadedVideoInfo

class TestVideoUpload(unittest.TestCase):
    def setUp(self):
        self.temp_dir_obj = tempfile.TemporaryDirectory()
        self.temp_dir = self.temp_dir_obj.name
        self.captured_temp_path = None
        self.original_mkstemp = tempfile.mkstemp

    def tearDown(self):
        if self.captured_temp_path and os.path.exists(self.captured_temp_path):
            try:
                os.remove(self.captured_temp_path)
            except Exception:
                pass
        self.temp_dir_obj.cleanup()

    def patched_mkstemp(self, *args, **kwargs):
        kwargs['dir'] = self.temp_dir
        fd, path = self.original_mkstemp(*args, **kwargs)
        self.captured_temp_path = path
        return fd, path

    def test_a_valid_mp4(self):
        content = b"fake mp4 data"
        original_name = "test_video.mp4"
        mime = "video/mp4"

        with temporary_uploaded_video(original_name, content, mime) as (temp_path, info):
            self.assertTrue(os.path.exists(temp_path))
            self.assertTrue(temp_path.endswith(".mp4"))
            self.assertEqual(info.original_filename, original_name)
            self.assertEqual(info.suffix, ".mp4")
            self.assertEqual(info.size_bytes, len(content))
            self.assertEqual(info.mime_type, mime)

            with open(temp_path, "rb") as f:
                actual_bytes = f.read()
                self.assertEqual(actual_bytes, content)

            expected_hash = hashlib.sha256(content).hexdigest()
            actual_temp_hash = hashlib.sha256(actual_bytes).hexdigest()
            self.assertEqual(expected_hash, info.sha256)
            self.assertEqual(info.sha256, actual_temp_hash)

            saved_temp_path = temp_path

        self.assertFalse(os.path.exists(saved_temp_path))

    def test_b_sha_integrity_error_same_size(self):
        content = b"AAAA"
        corrupted = b"BBBB"

        original_open = builtins_open = open

        def mock_open_read(file, mode='r', buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
            if mode == "rb" and isinstance(file, str) and "video_" in file:
                m = mock_open(read_data=corrupted)()
                m.__iter__.return_value = [corrupted]
                return m
            return original_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            with patch('builtins.open', side_effect=mock_open_read):
                with self.assertRaises(RuntimeError) as ctx:
                    with temporary_uploaded_video("test.mp4", content):
                        pass
                self.assertIn("SHA-256 stimmt nicht mit dem Upload überein", str(ctx.exception))
                self.assertIsNotNone(self.captured_temp_path)
                self.assertFalse(os.path.exists(self.captured_temp_path))

    def test_b2_mov_extension(self):
        with temporary_uploaded_video("test.mov", b"data") as (temp_path, info):
            self.assertEqual(info.suffix, ".mov")
            self.assertTrue(temp_path.endswith(".mov"))

    def test_c_m4v_extension(self):
        with temporary_uploaded_video("test.m4v", b"data") as (temp_path, info):
            self.assertEqual(info.suffix, ".m4v")

    def test_d_case_insensitive_extension(self):
        with temporary_uploaded_video("TEST.MP4", b"data") as (temp_path, info):
            self.assertEqual(info.suffix, ".mp4")

    def test_e_unsupported_extension(self):
        with self.assertRaises(ValueError):
            with temporary_uploaded_video("test.txt", b"data"):
                pass

    def test_f_empty_file(self):
        with self.assertRaises(ValueError):
            with temporary_uploaded_video("test.mp4", b""):
                pass

    def test_g_file_above_limit(self):
        with patch('modules.video_upload.MAX_VIDEO_SIZE_BYTES', 10):
            with self.assertRaises(ValueError) as ctx:
                with temporary_uploaded_video("test.mp4", b"12345678901"):
                    pass
            self.assertIn("überschreitet das Limit", str(ctx.exception))

    def test_h_path_traversal_evil_name(self):
        evil_name = "../../evil.mp4"
        with temporary_uploaded_video(evil_name, b"data") as (temp_path, info):
            self.assertEqual(info.original_filename, evil_name)
            self.assertEqual(info.suffix, ".mp4")

            dirname = os.path.dirname(temp_path)
            basename = os.path.basename(temp_path)

            self.assertEqual(os.path.realpath(dirname), os.path.realpath(tempfile.gettempdir()))
            self.assertTrue(basename.startswith("video_"))
            self.assertNotIn("evil", basename)

    def test_i_absolute_path_evil_name(self):
        evil_name = "/tmp/evil.mp4"
        with temporary_uploaded_video(evil_name, b"data") as (temp_path, info):
            self.assertEqual(info.original_filename, evil_name)

            dirname = os.path.dirname(temp_path)
            basename = os.path.basename(temp_path)

            self.assertEqual(os.path.realpath(dirname), os.path.realpath(tempfile.gettempdir()))
            self.assertTrue(basename.startswith("video_"))
            self.assertNotIn("evil", basename)

    @patch('modules.video_upload.os.fsync')
    def test_j_simulated_write_error_with_cleanup(self, mock_fsync):
        mock_fsync.side_effect = OSError("Simulated write error")

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            with self.assertRaises(OSError):
                with temporary_uploaded_video("test.mp4", b"data"):
                    pass

            self.assertIsNotNone(self.captured_temp_path)
            self.assertFalse(os.path.exists(self.captured_temp_path))

    @patch('modules.video_upload.os.path.getsize')
    def test_k_simulated_integrity_error(self, mock_getsize):
        mock_getsize.return_value = 0 # simulate size mismatch

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            with self.assertRaises(RuntimeError) as ctx:
                with temporary_uploaded_video("test.mp4", b"data"):
                    pass
            self.assertIn("Integritätsprüfung fehlgeschlagen: Geschriebene Dateigröße stimmt nicht überein", str(ctx.exception))
            self.assertIsNotNone(self.captured_temp_path)
            self.assertFalse(os.path.exists(self.captured_temp_path))

    def test_l_cleanup_after_exception_in_with_block(self):
        primary_exception = RuntimeError("Primary processing error")
        caught_exception = None

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            try:
                with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                    self.assertTrue(os.path.exists(temp_path))
                    raise primary_exception
            except Exception as e:
                caught_exception = e

            self.assertIs(caught_exception, primary_exception)
            self.assertIsNotNone(self.captured_temp_path)
            self.assertFalse(os.path.exists(self.captured_temp_path))

    @patch('modules.video_upload.os.remove')
    def test_m_cleanup_error_after_success(self, mock_remove):
        cleanup_error = OSError("Simulated cleanup error")
        mock_remove.side_effect = cleanup_error

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            with self.assertRaises(OSError) as ctx:
                with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                    self.assertTrue(os.path.exists(temp_path))

            self.assertIs(ctx.exception, cleanup_error)

            # The test must clean up its own file since os.remove was mocked
            if os.path.exists(self.captured_temp_path):
                os.unlink(self.captured_temp_path)

    @patch('modules.video_upload.os.remove')
    def test_n_cleanup_error_with_primary_error(self, mock_remove):
        primary_exception = RuntimeError("Primary processing error")
        cleanup_error = OSError("Simulated cleanup error")
        mock_remove.side_effect = cleanup_error
        caught_exception = None

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            try:
                with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                    self.assertTrue(os.path.exists(temp_path))
                    raise primary_exception
            except Exception as e:
                caught_exception = e

            self.assertIs(caught_exception, primary_exception)

            if os.path.exists(self.captured_temp_path):
                os.unlink(self.captured_temp_path)

    def test_o_cleanup_does_not_delete_foreign_files(self):
        foreign_fd, foreign_path = tempfile.mkstemp(prefix="video_foreign_", suffix=".mp4")
        foreign_content = b"foreign"
        with os.fdopen(foreign_fd, "wb") as f:
            f.write(foreign_content)

        try:
            with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                self.assertTrue(os.path.exists(foreign_path))
                self.assertNotEqual(temp_path, foreign_path)

            self.assertTrue(os.path.exists(foreign_path))
            with open(foreign_path, "rb") as f:
                self.assertEqual(f.read(), foreign_content)
        finally:
            if os.path.exists(foreign_path):
                os.remove(foreign_path)

    def test_p_metadata(self):
        with temporary_uploaded_video("video.mp4", b"data", "video/mp4") as (temp_path, info):
            self.assertEqual(info.original_filename, "video.mp4")
            self.assertEqual(info.suffix, ".mp4")
            self.assertEqual(info.mime_type, "video/mp4")

    @patch('modules.video_upload.os.remove')
    def test_q_cleanup_error_with_primary_base_exception(self, mock_remove):
        class SyntheticBaseException(BaseException):
            pass

        primary_exception = SyntheticBaseException("Primary processing base error")
        cleanup_error = OSError("Simulated cleanup error")
        mock_remove.side_effect = cleanup_error
        caught_exception = None

        with patch('modules.video_upload.tempfile.mkstemp', side_effect=self.patched_mkstemp):
            try:
                with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                    self.assertTrue(os.path.exists(temp_path))
                    raise primary_exception
            except BaseException as e:
                caught_exception = e

            self.assertIs(caught_exception, primary_exception)
            self.assertIsNotNone(self.captured_temp_path)

            self.assertTrue(os.path.exists(self.captured_temp_path))
            os.unlink(self.captured_temp_path)
            self.assertFalse(os.path.exists(self.captured_temp_path))

if __name__ == '__main__':
    unittest.main()
