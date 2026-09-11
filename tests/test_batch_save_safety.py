import unittest
import os
import json
import tempfile
import builtins
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
        # 1. Zieldatei fehlt -> Gültige Batch-Datei wird erstellt
        save_batch(self.file_path, self.order)
        self.assertTrue(os.path.exists(self.file_path))
        with open(self.file_path, "r") as f:
            data = json.load(f)
        self.assertIn("TEST-01", data)
        self.assertEqual(data["TEST-01"]["picks"], ["10.001.01", "10.001.02", "10.001.01"])

    def test_append_existing_file(self):
        # 2. Gültiger Bestand -> Neuer ergänzt, bestehende Metadaten erhalten
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
        # 3. Auftrag enthält doppelte Pickcodes -> Anzahl, Duplikate und Eingabereihenfolge erhalten
        save_batch(self.file_path, self.order)
        with open(self.file_path, "r") as f:
            data = json.load(f)
        picks = data["TEST-01"]["picks"]
        self.assertEqual(len(picks), 3)
        self.assertEqual(picks, ["10.001.01", "10.001.02", "10.001.01"])

    def test_corrupted_file(self):
        # 4. Beschädigte/leere JSON -> Ausnahme, ursprüngliche Bytes bleiben
        bad_content = b"{ bad json"
        with open(self.file_path, "wb") as f:
            f.write(bad_content)

        with self.assertRaises(json.JSONDecodeError):
            save_batch(self.file_path, self.order)

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), bad_content)

    def test_invalid_json_type(self):
        # 5. Liste oder null -> Ausnahme, ursprüngliche Bytes bleiben
        content = b"[1, 2, 3]"
        with open(self.file_path, "wb") as f:
            f.write(content)

        with self.assertRaises(ValueError):
            save_batch(self.file_path, self.order)

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), content)

    def test_write_failure(self):
        # 6. Fehler beim Schreiben (Teilschreibvorgang)
        initial_content = b'{"OLD": {}}'
        with open(self.file_path, "wb") as f:
            f.write(initial_content)

        original_open = builtins.open
        def mock_open(*args, **kwargs):
            if "tmp" in str(args[0]):
                raise OSError("Simulated write error")
            return original_open(*args, **kwargs)

        with patch('builtins.open', side_effect=mock_open):
            with self.assertRaises(OSError):
                save_batch(self.file_path, self.order)

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), initial_content)

        # Check no tmp files left
        files = os.listdir(self.test_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "test_batches.json")

    def test_replace_failure(self):
        # 7. os.replace() schlägt fehl
        initial_content = b'{"OLD": {}}'
        with open(self.file_path, "wb") as f:
            f.write(initial_content)

        with patch('os.replace', side_effect=OSError("Simulated replace error")):
            with self.assertRaises(OSError):
                save_batch(self.file_path, self.order)

        with open(self.file_path, "rb") as f:
            self.assertEqual(f.read(), initial_content)

        # Check no tmp files left
        files = os.listdir(self.test_dir)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0], "test_batches.json")

    def test_filename_only(self):
        # 8. Zielpfad enthält nur einen Dateinamen
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
        # Prüfe beim erfolgreichen Austausch, dass Quell- und Zieldatei im selben Verzeichnis liegen
        # und die Quelle bereits vollständiges, lesbares JSON enthält.
        # We can test this by mocking os.replace to capture the temp file path before it gets deleted,
        # checking its location and content.

        tmp_path_captured = []
        original_replace = os.replace
        def mock_replace(src, dst):
            tmp_path_captured.append(src)
            # Read content before replacing
            with open(src, "r") as f:
                data = json.load(f)
                assert "TEST-01" in data
            original_replace(src, dst)

        with patch('os.replace', side_effect=mock_replace):
            save_batch(self.file_path, self.order)

        self.assertEqual(len(tmp_path_captured), 1)
        tmp_path = tmp_path_captured[0]
        self.assertEqual(os.path.dirname(tmp_path), os.path.dirname(self.file_path))

if __name__ == '__main__':
    unittest.main()
