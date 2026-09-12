import unittest
import os
import tempfile
import hashlib
from unittest.mock import patch
from modules.video_upload import temporary_uploaded_video, UploadedVideoInfo

class TestVideoUpload(unittest.TestCase):
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
                self.assertEqual(f.read(), content)

            expected_hash = hashlib.sha256(content).hexdigest()
            self.assertEqual(info.sha256, expected_hash)

            saved_temp_path = temp_path

        # File should be deleted after context exit
        self.assertFalse(os.path.exists(saved_temp_path))

    def test_b_mov_extension(self):
        with temporary_uploaded_video("test.mov", b"data") as (temp_path, info):
            self.assertEqual(info.suffix, ".mov")

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
            self.assertFalse(".." in temp_path)
            self.assertTrue(os.path.dirname(temp_path).startswith(tempfile.gettempdir()))

    def test_i_absolute_path_evil_name(self):
        evil_name = "/tmp/evil.mp4"
        with temporary_uploaded_video(evil_name, b"data") as (temp_path, info):
            self.assertEqual(info.original_filename, evil_name)
            self.assertEqual(os.path.dirname(temp_path), tempfile.gettempdir())

    @patch('modules.video_upload.os.fsync')
    def test_j_simulated_write_error(self, mock_fsync):
        mock_fsync.side_effect = OSError("Simulated write error")
        with self.assertRaises(OSError):
            with temporary_uploaded_video("test.mp4", b"data"):
                pass

        # We need to verify cleanup. The file is created by mkstemp before try block
        # We can mock mkstemp to capture the path, but standard exceptions in try clean up.
        # It's sufficiently tested if the exception bubbles up and doesn't leave files matching video_*.mp4
        # in the tempdir indefinitely, but a precise test could check directory listings.

    @patch('modules.video_upload.os.path.getsize')
    def test_k_simulated_integrity_error(self, mock_getsize):
        mock_getsize.return_value = 0 # simulate size mismatch
        with self.assertRaises(RuntimeError) as ctx:
            with temporary_uploaded_video("test.mp4", b"data"):
                pass
        self.assertIn("Integritätsprüfung fehlgeschlagen", str(ctx.exception))

    def test_l_cleanup_after_exception_in_with_block(self):
        saved_path = None
        try:
            with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                saved_path = temp_path
                self.assertTrue(os.path.exists(saved_path))
                raise RuntimeError("Inner error")
        except RuntimeError:
            pass

        self.assertFalse(os.path.exists(saved_path))

    def test_m_cleanup_does_not_delete_foreign_files(self):
        foreign_fd, foreign_path = tempfile.mkstemp(prefix="video_foreign_", suffix=".mp4")
        with os.fdopen(foreign_fd, "w") as f:
            f.write("foreign")

        try:
            with temporary_uploaded_video("test.mp4", b"data") as (temp_path, info):
                self.assertTrue(os.path.exists(foreign_path))

            self.assertTrue(os.path.exists(foreign_path))
        finally:
            os.remove(foreign_path)

    def test_n_metadata(self):
        with temporary_uploaded_video("video.mp4", b"data", "video/mp4") as (temp_path, info):
            self.assertEqual(info.original_filename, "video.mp4")
            self.assertEqual(info.suffix, ".mp4")
            self.assertEqual(info.mime_type, "video/mp4")

if __name__ == '__main__':
    unittest.main()
