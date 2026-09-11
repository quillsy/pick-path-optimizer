import unittest
import os
import json
import tempfile
from unittest.mock import patch
from datetime import datetime
from modules.picks import save_batch, Pick, PickOrder

class TestBatchSaveSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name
        self.file_path = os.path.join(self.test_dir, "test_batches.json")

        self.order = PickOrder(
            order_id="TEST-01",
            timestamp_str="2026-09-12T00:00:00",
            raw_picks_list=["10.001.01", "10.001.02", "10.001.01"],
            warehouse=None,
            source="test"
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_new_file(self):
        save_batch(self.file_path, self.order)
        self.assertTrue(os.path.exists(self.file_path))
        with open(self.file_path, "r") as f:
            data = json.load(f)
        self.assertIn("TEST-01", data)
        self.assertEqual(data["TEST-01"]["picks"], ["10.001.01", "10.001.02", "10.001.01"])

    def test_append_existing_file(self):
        initial_data = {
            "OLD-01": {
                "order_id": "OLD-01",
                "custom_meta": "keep_me"
            }
        }
        with open(self.file_path, "w") as f:
            json.dump(initial_data, f)

        save_batch(self.file_path, self.order)
        with open(self.file_path, "r") as f:
            data = json.load(f)
        self.assertIn("TEST-01", data)
        self.assertIn("OLD-01", data)
        self.assertEqual(data["OLD-01"]["custom_meta"], "keep_me")

    def test_duplicate_picks(self):
        save_batch(self.file_path, self.order)
        with open(self.file_path, "r") as f:
            data = json.load(f)
        picks = data["TEST-01"]["picks"]
        self.assertEqual(len(picks), 3)
        self.assertEqual(picks, ["10.001.01", "10.001.02", "10.001.01"])

    def test_corrupted_file(self):
        cases = [b"{ bad json", b""]
        for case in cases:
            with self.subTest(case=case):
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                with open(self.file_path, "wb") as f:
                    f.write(case)

                with self.assertRaises(json.JSONDecodeError):
                    save_batch(self.file_path, self.order)

                with open(self.file_path, "rb") as f:
                    self.assertEqual(f.read(), case)

                files = os.listdir(self.test_dir)
                self.assertEqual(len(files), 1)

    def test_invalid_json_type(self):
        cases = [b"[1, 2, 3]", b"null"]
        for case in cases:
            with self.subTest(case=case):
                if os.path.exists(self.file_path):
                    os.remove(self.file_path)
                with open(self.file_path, "wb") as f:
                    f.write(case)

                with self.assertRaises(ValueError):
                    save_batch(self.file_path, self.order)

                with open(self.file_path, "rb") as f:
                    self.assertEqual(f.read(), case)

                files = os.listdir(self.test_dir)
                self.assertEqual(len(files), 1)

    @patch("modules.picks.json.dump")
    def test_write_failure(self, mock_dump):
        initial_content = b'{"OLD": {}}'
        with open(self.file_path, "wb") as original:
            original.write(initial_content)

        simulated_error = OSError("Simulated write error")
        partial_bytes = b'{ "partial_json": '
        observed_paths = []

        def dump_side_effect(data, f_obj, **kwargs):
            tmp_path = os.path.abspath(os.fspath(f_obj.name))
            target_path = os.path.abspath(self.file_path)

            self.assertNotEqual(tmp_path, target_path)
            self.assertEqual(
                os.path.dirname(tmp_path), os.path.dirname(target_path)
            )
            observed_paths.append(tmp_path)

            f_obj.write(partial_bytes.decode("utf-8"))
            f_obj.flush()

            with open(tmp_path, "rb") as partial_file:
                self.assertEqual(partial_file.read(), partial_bytes)

            with open(self.file_path, "rb") as original:
                self.assertEqual(original.read(), initial_content)

            raise simulated_error

        mock_dump.side_effect = dump_side_effect

        with patch("modules.picks.os.replace") as mock_replace:
            with self.assertRaises(OSError) as caught:
                save_batch(self.file_path, self.order)

            self.assertIs(caught.exception, simulated_error)
            mock_replace.assert_not_called()

        mock_dump.assert_called_once()
        self.assertEqual(len(observed_paths), 1)
        self.assertFalse(os.path.exists(observed_paths[0]))

        with open(self.file_path, "rb") as original:
            self.assertEqual(original.read(), initial_content)

        self.assertEqual(os.listdir(self.test_dir), ["test_batches.json"])

    def test_replace_failure(self):
        initial_content = b'{"OLD": {}}'
        with open(self.file_path, "wb") as f:
            f.write(initial_content)

        with patch('os.replace', side_effect=OSError("Simulated replace error")):
            with self.assertRaises(OSError):
                save_batch(self.file_path, self.order)

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), initial_content)

        files = os.listdir(self.test_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "test_batches.json")

    def test_filename_only(self):
        cwd = os.getcwd()
        os.chdir(self.test_dir)
        try:
            save_batch("just_name.json", self.order)
            self.assertTrue(os.path.exists("just_name.json"))
            with open("just_name.json", "r") as f:
                data = json.load(f)
            self.assertIn("TEST-01", data)
        finally:
            os.chdir(cwd)

    def test_temp_file_valid_and_same_dir(self):
        tmp_path_captured = []
        original_replace = os.replace
        def mock_replace(src, dst):
            tmp_path_captured.append(src)
            with open(src, "r") as f:
                data = json.load(f)
                assert "TEST-01" in data
            original_replace(src, dst)

        with patch('os.replace', side_effect=mock_replace):
            save_batch(self.file_path, self.order)

        self.assertEqual(len(tmp_path_captured), 1)
        tmp_path = tmp_path_captured[0]
        self.assertEqual(os.path.dirname(tmp_path), os.path.dirname(self.file_path))

    @patch('modules.picks.uuid.uuid4')
    def test_tmp_collision(self, mock_uuid):
        initial_content = b'{"OLD": {}}'
        with open(self.file_path, "wb") as f:
            f.write(initial_content)

        class FakeUUID:
            hex = "FIXED_UUID"
        mock_uuid.return_value = FakeUUID()

        dir_name = os.path.dirname(self.file_path)
        base_name = os.path.basename(self.file_path)
        tmp_path = os.path.join(dir_name, f"{base_name}.tmp.FIXED_UUID")

        foreign_content = b"FOREIGN_CONTENT"
        with open(tmp_path, "wb") as f:
            f.write(foreign_content)

        with patch('os.replace') as mock_replace:
            with self.assertRaises(FileExistsError):
                save_batch(self.file_path, self.order)
            mock_replace.assert_not_called()

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), initial_content)

        with open(tmp_path, "rb") as f:
            self.assertEqual(f.read(), foreign_content)

if __name__ == '__main__':
    unittest.main()
