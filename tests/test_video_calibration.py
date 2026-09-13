import unittest
import os
import tempfile
import shutil
import hashlib
import json
import zipfile
import io

from modules.video_frames import ExtractedFrame, VideoMetadata
from modules.video_roi import ROICrop, PixelROI, NormalizedROI
from modules.video_calibration import (
    CalibrationFrame,
    select_calibration_pairs,
    build_calibration_zip,
    verify_calibration_zip,
    CalibrationPackageError
)

class TestCalibrationPairing(unittest.TestCase):
    def setUp(self):
        self.pixel_roi = PixelROI(10, 10, 50, 50)
        self.frames = [
            ExtractedFrame(i, i * 1.5, f"frame_{i}.jpg", 100, f"hash_{i}")
            for i in range(10)
        ]
        self.crops = [
            ROICrop(i, i * 1.5, f"frame_{i}.jpg", f"crop_{i}.jpg", self.pixel_roi, 50, f"chash_{i}")
            for i in range(10)
        ]

    def test_a_correct_pairing(self):
        pairs = select_calibration_pairs(self.frames[:3], self.crops[:3], max_pairs=3)
        self.assertEqual(len(pairs), 3)
        for i, p in enumerate(pairs):
            self.assertEqual(p.sequence_index, i)
            self.assertEqual(p.timestamp_seconds, i * 1.5)

    def test_b_unsorted_input(self):
        frames_rev = list(reversed(self.frames[:4]))
        crops_shuffled = [self.crops[2], self.crops[0], self.crops[3], self.crops[1]]
        pairs = select_calibration_pairs(frames_rev, crops_shuffled, max_pairs=10)
        self.assertEqual([p.sequence_index for p in pairs], [0, 1, 2, 3])

    def test_c_crop_missing(self):
        with self.assertRaises(ValueError):
            select_calibration_pairs(self.frames[:3], self.crops[:2])

    def test_d_frame_missing(self):
        with self.assertRaises(ValueError):
            select_calibration_pairs(self.frames[:2], self.crops[:3])

    def test_e_duplicate_frame(self):
        frames = self.frames[:3] + [self.frames[1]]
        with self.assertRaises(ValueError):
            select_calibration_pairs(frames, self.crops[:3])

    def test_f_duplicate_crop(self):
        crops = self.crops[:3] + [self.crops[1]]
        with self.assertRaises(ValueError):
            select_calibration_pairs(self.frames[:3], crops)

    def test_g_timestamp_mismatch(self):
        bad_crop = ROICrop(0, 99.9, "f.jpg", "c.jpg", self.pixel_roi, 50, "h")
        with self.assertRaises(ValueError):
            select_calibration_pairs([self.frames[0]], [bad_crop])

    def test_h_max_pairs_1(self):
        pairs = select_calibration_pairs(self.frames, self.crops, max_pairs=1)
        self.assertEqual(len(pairs), 1)
        self.assertEqual(pairs[0].sequence_index, 0)

    def test_i_more_than_max_pairs(self):
        pairs = select_calibration_pairs(self.frames, self.crops, max_pairs=3)
        self.assertEqual(len(pairs), 3)
        self.assertEqual(pairs[0].sequence_index, 0)
        self.assertEqual(pairs[-1].sequence_index, 9)
        self.assertTrue(pairs[1].sequence_index > 0 and pairs[1].sequence_index < 9)

    def test_j_first_last_included(self):
        pairs = select_calibration_pairs(self.frames, self.crops, max_pairs=5)
        self.assertEqual(pairs[0].sequence_index, 0)
        self.assertEqual(pairs[-1].sequence_index, 9)

    def test_k_invalid_max_pairs(self):
        for bad in [0, -1, 3.5, True]:
            with self.assertRaises(ValueError):
                select_calibration_pairs(self.frames, self.crops, max_pairs=bad)

    def test_l_empty_inputs(self):
        self.assertEqual(select_calibration_pairs([], []), [])
        with self.assertRaises(ValueError):
            select_calibration_pairs(self.frames[:1], [])
        with self.assertRaises(ValueError):
            select_calibration_pairs([], self.crops[:1])



    def test_e_f_pairing_sort_order(self):
        # E. Timestamps reverse
        f1 = ExtractedFrame(1, 10.0, "f1.jpg", 100, "h1")
        f2 = ExtractedFrame(2, 5.0, "f2.jpg", 100, "h2")
        c1 = ROICrop(1, 10.0, "f1.jpg", "c1.jpg", self.pixel_roi, 50, "ch1")
        c2 = ROICrop(2, 5.0, "f2.jpg", "c2.jpg", self.pixel_roi, 50, "ch2")
        pairs = select_calibration_pairs([f1, f2], [c1, c2])
        self.assertEqual(pairs[0].sequence_index, 2)
        self.assertEqual(pairs[1].sequence_index, 1)

        # F. Same timestamp, sequence tie-breaker
        f3 = ExtractedFrame(3, 5.0, "f3.jpg", 100, "h3")
        c3 = ROICrop(3, 5.0, "f3.jpg", "c3.jpg", self.pixel_roi, 50, "ch3")
        pairs2 = select_calibration_pairs([f3, f2], [c3, c2])
        self.assertEqual(pairs2[0].sequence_index, 2)
        self.assertEqual(pairs2[1].sequence_index, 3)
class TestCalibrationZIP(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_calib_zip_")
        self.pixel_roi = PixelROI(10, 10, 50, 50)
        self.norm_roi = NormalizedROI(0.1, 0.1, 0.6, 0.6)
        self.meta = VideoMetadata(duration_seconds=10.0, width=100, height=100, fps=1.0, frame_count=10, video_codec="h264", container_format="mp4")

        # Create fake image files
        self.pairs = []
        for i in range(2):
            orig_path = os.path.join(self.temp_dir, f"orig_{i}.jpg")
            crop_path = os.path.join(self.temp_dir, f"crop_{i}.jpg")

            with open(orig_path, "wb") as f: f.write(f"orig_data_{i}".encode())
            with open(crop_path, "wb") as f: f.write(f"crop_data_{i}".encode())

            self.pairs.append(CalibrationFrame(
                sequence_index=i,
                timestamp_seconds=float(i),
                original_filename=f"original/frame_{i:04d}.jpg",
                crop_filename=f"crop/frame_{i:04d}.jpg",
                original_size_bytes=len(f"orig_data_{i}".encode()),
                crop_size_bytes=len(f"crop_data_{i}".encode()),
                original_sha256=hashlib.sha256(f"orig_data_{i}".encode()).hexdigest(),
                crop_sha256=hashlib.sha256(f"crop_data_{i}".encode()).hexdigest(),
                pixel_roi=self.pixel_roi,
                source_original_path=orig_path,
                source_crop_path=crop_path
            ))

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_m_valid_package_and_verify(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        verify_calibration_zip(zip_bytes) # Should not raise

    def test_n_expected_filenames(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            names = set(zf.namelist())
            self.assertEqual(names, {"manifest.json", "original/frame_0000.jpg", "crop/frame_0000.jpg", "original/frame_0001.jpg", "crop/frame_0001.jpg"})

    def test_o_p_q_no_absolute_or_relative_or_video(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in zf.namelist():
                self.assertFalse(name.startswith("/"))
                self.assertNotIn("..", name)
                self.assertNotEqual(name, "test.mp4")

    def test_r_bytes_identical(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            self.assertEqual(zf.read("original/frame_0000.jpg"), b"orig_data_0")

    def test_s_t_u_v_w_x_manifest_contents(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["purpose"], "pick_video_calibration")
            self.assertEqual(manifest["video"]["duration_seconds"], 10.0)
            self.assertEqual(manifest["roi"]["normalized"]["left"], 0.1)
            self.assertEqual(manifest["roi"]["pixel"]["x"], 10)
            self.assertEqual(len(manifest["frames"]), 2)

    def test_y_z_aa_frame_metadata(self):
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
            f0 = manifest["frames"][0]
            self.assertEqual(f0["sequence_index"], 0)
            self.assertEqual(f0["original_sha256"], self.pairs[0].original_sha256)
            self.assertEqual(f0["original_size_bytes"], self.pairs[0].original_size_bytes)

    def test_ab_evil_video_name(self):
        evil_name = "../../secret.mov"
        zip_bytes = build_calibration_zip(self.pairs, self.meta, self.norm_roi, evil_name)
        verify_calibration_zip(zip_bytes)
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            manifest = json.loads(zf.read("manifest.json").decode('utf-8'))
            self.assertEqual(manifest["original_video_name"], evil_name)
            self.assertNotIn(evil_name, zf.namelist())



    def test_build_a_changed_file_hash(self):
        with open(self.pairs[0].source_original_path, "wb") as f:
            f.write(b"changed_data_here")
        with self.assertRaisesRegex(CalibrationPackageError, "verändert"):
            build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")

    def test_build_b_c_empty_file(self):
        with open(self.pairs[0].source_crop_path, "wb") as f:
            f.write(b"")
        with self.assertRaisesRegex(CalibrationPackageError, "leer"):
            build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")

    def test_build_d_missing_file(self):
        import os
        os.remove(self.pairs[0].source_original_path)
        with self.assertRaisesRegex(CalibrationPackageError, "Lesen der Quelldateien"):
            build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4")

    def test_build_g_different_pixel_roi(self):
        p1 = self.pairs[0]
        p2 = CalibrationFrame(
            sequence_index=1, timestamp_seconds=1.0,
            original_filename="original/frame_0001.jpg", crop_filename="crop/frame_0001.jpg",
            original_size_bytes=p1.original_size_bytes, crop_size_bytes=p1.crop_size_bytes,
            original_sha256=p1.original_sha256, crop_sha256=p1.crop_sha256,
            pixel_roi=PixelROI(0, 0, 1, 1),
            source_original_path=p1.source_original_path, source_crop_path=p1.source_crop_path
        )
        with self.assertRaisesRegex(CalibrationPackageError, "Unterschiedliche PixelROI"):
            build_calibration_zip([p1, p2], self.meta, self.norm_roi, "test.mp4")

    def test_build_h_empty_pairs(self):
        with self.assertRaisesRegex(CalibrationPackageError, "Keine Kalibrierungsframes"):
            build_calibration_zip([], self.meta, self.norm_roi, "test.mp4")

    def test_build_i_invalid_max_bytes(self):
        for bad in [0, -1, 3.14, True]:
            with self.assertRaises(ValueError):
                build_calibration_zip(self.pairs, self.meta, self.norm_roi, "test.mp4", max_bytes=bad)
class TestVerificationFailures(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_calib_zip_verify_")
        self.pixel_roi = PixelROI(10, 10, 50, 50)
        self.norm_roi = NormalizedROI(0.1, 0.1, 0.6, 0.6)
        self.meta = VideoMetadata(duration_seconds=10.0, width=100, height=100, fps=1.0, frame_count=10, video_codec="h264", container_format="mp4")

        orig_path = os.path.join(self.temp_dir, "orig_0.jpg")
        crop_path = os.path.join(self.temp_dir, "crop_0.jpg")
        with open(orig_path, "wb") as f: f.write(b"orig_data_0")
        with open(crop_path, "wb") as f: f.write(b"crop_data_0")

        self.pair = CalibrationFrame(
            0, 0.0, "original/frame_0000.jpg", "crop/frame_0000.jpg",
            11, 11,
            hashlib.sha256(b"orig_data_0").hexdigest(),
            hashlib.sha256(b"crop_data_0").hexdigest(),
            self.pixel_roi, orig_path, crop_path
        )
        self.valid_zip_bytes = build_calibration_zip([self.pair], self.meta, self.norm_roi, "test.mp4")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def _modify_zip(self, modifier_func) -> bytes:
        out = io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(self.valid_zip_bytes), "r") as zf_in:
            with zipfile.ZipFile(out, "w") as zf_out:
                modifier_func(zf_in, zf_out)
        return out.getvalue()

    def test_ad_invalid_zip(self):
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(b"not_a_zip")

    def test_ae_missing_manifest(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename != "manifest.json":
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_af_invalid_manifest(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    zf_out.writestr(item, b"{invalid json}")
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_ag_missing_image(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename != "original/frame_0000.jpg":
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_ah_hash_mismatch(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "original/frame_0000.jpg":
                    zf_out.writestr(item, b"tampered_data")
                elif item.filename == "manifest.json":
                    manifest = json.loads(zf_in.read(item.filename).decode())
                    manifest["frames"][0]["original_size_bytes"] = len(b"tampered_data")
                    zf_out.writestr(item, json.dumps(manifest).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_ai_size_mismatch(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    manifest = json.loads(zf_in.read(item.filename).decode())
                    manifest["frames"][0]["original_size_bytes"] = 9999
                    zf_out.writestr(item, json.dumps(manifest).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_aj_unexpected_file(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("unexpected.txt", b"hello")
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_ak_dangerous_path(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("../evil.txt", b"evil")
        bad_zip = self._modify_zip(modify)
        with self.assertRaises(CalibrationPackageError):
            verify_calibration_zip(bad_zip)

    def test_size_limit(self):
        # We limit to 50 bytes using the max_bytes argument to test it
        with self.assertRaises(CalibrationPackageError):
            build_calibration_zip([self.pair], self.meta, self.norm_roi, "test.mp4", max_bytes=50)

    def test_verify_j_k_extra_file(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("original/extra.jpg", b"hello")
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Dateimenge im ZIP entspricht nicht"):
            verify_calibration_zip(bad_zip)

    def test_verify_l_duplicate_entry(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("manifest.json", b"{}")
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Doppelter ZIP-Eintrag"):
            verify_calibration_zip(bad_zip)

    def test_verify_m_no_frames(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    del m["frames"]
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "frames ist keine Liste"):
            verify_calibration_zip(bad_zip)

    def test_verify_n_frames_not_array(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"] = {}
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "frames ist keine Liste"):
            verify_calibration_zip(bad_zip)

    def test_verify_o_frame_not_object(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0] = "string"
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Frameeintrag ist kein Object"):
            verify_calibration_zip(bad_zip)

    def test_verify_p_duplicate_sequence(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"].append(m["frames"][0])
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Doppelter sequence_index"):
            verify_calibration_zip(bad_zip)

    def test_verify_q_duplicate_original_file(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    f2 = m["frames"][0].copy()
                    f2["sequence_index"] = 99
                    f2["timestamp_seconds"] = 99.0
                    m["frames"].append(f2)
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Doppelter original_file-Verweis"):
            verify_calibration_zip(bad_zip)

    def test_verify_r_invalid_sha(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0]["original_sha256"] = "short"
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Ungültiges original_sha256"):
            verify_calibration_zip(bad_zip)

    def test_verify_s_size_zero(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0]["original_size_bytes"] = 0
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Ungültige original_size_bytes"):
            verify_calibration_zip(bad_zip)

    def test_verify_t_bool_sequence(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0]["sequence_index"] = True
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Ungültiger sequence_index"):
            verify_calibration_zip(bad_zip)

    def test_verify_u_timestamp_invalid(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0]["timestamp_seconds"] = "foo"
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Ungültiger timestamp_seconds"):
            verify_calibration_zip(bad_zip)

    def test_verify_v_windows_path(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("..\\evil.jpg", b"hello")
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Gefährlicher Pfad"):
            verify_calibration_zip(bad_zip)

    def test_verify_w_dotdot_path(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                zf_out.writestr(item, zf_in.read(item.filename))
            zf_out.writestr("original/../evil.jpg", b"hello")
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Gefährlicher Pfad"):
            verify_calibration_zip(bad_zip)

    def test_verify_x_invalid_schema_name(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    m["frames"][0]["original_file"] = "original/foo.jpg"
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Ungültiger original_file"):
            verify_calibration_zip(bad_zip)

    def test_verify_y_ordering_not_ascending(self):
        def modify(zf_in, zf_out):
            for item in zf_in.infolist():
                if item.filename == "manifest.json":
                    m = json.loads(zf_in.read(item.filename).decode())
                    f2 = m["frames"][0].copy()
                    f2["sequence_index"] = 2
                    f2["timestamp_seconds"] = -1.0 # not chronologically after 0
                    m["frames"].append(f2)
                    zf_out.writestr(item, json.dumps(m).encode())
                else:
                    zf_out.writestr(item, zf_in.read(item.filename))
        bad_zip = self._modify_zip(modify)
        with self.assertRaisesRegex(CalibrationPackageError, "Frame-Reihenfolge nicht zeitlich aufsteigend|Ungültiger timestamp_seconds"): # if -1 it might fail earlier
            verify_calibration_zip(bad_zip)
