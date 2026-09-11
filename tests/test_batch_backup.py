import unittest
import os
import tempfile
from unittest.mock import patch
from modules.batch_backup import read_batch_backup

class TestBatchBackup(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = self.temp_dir.name
        self.file_path = os.path.join(self.test_dir, "test_batches.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_valid_json_exact_bytes(self):
        content = (
            '{\r\n'
            '  "BATCH-TEST": {\n'
            '    "order_id": "BATCH-TEST",\r\n'
            '    "picks": ["20.080.30", "04.002.10", "20.080.30"],\n'
            '    "custom_meta": {"note": "Prüfung ✓", "values": [2, 1]}\n'
            '  }\r\n'
            '}\n'
        ).encode("utf-8")

        with open(self.file_path, "wb") as source:
            source.write(content)

        result = read_batch_backup(self.file_path)

        self.assertIsInstance(result, bytes)
        self.assertEqual(result, content)
        self.assertEqual(os.listdir(self.test_dir), ["test_batches.json"])

        with open(self.file_path, "rb") as source:
            self.assertEqual(source.read(), content)

    def test_corrupted_json_exact_bytes(self):
        content = b'{ bad json '
        with open(self.file_path, "wb") as f:
            f.write(content)

        result = read_batch_backup(self.file_path)
        self.assertEqual(result, content)

    def test_empty_file_exact_bytes(self):
        content = b""
        with open(self.file_path, "wb") as f:
            f.write(content)

        result = read_batch_backup(self.file_path)
        self.assertEqual(result, content)

    def test_missing_file_raises_filenotfounderror(self):
        with self.assertRaises(FileNotFoundError):
            read_batch_backup(self.file_path)

    @patch('modules.batch_backup.open')
    def test_read_error_propagated(self, mock_open):
        content = b'{"test": 1}'
        with open(self.file_path, "wb") as f:
            f.write(content)

        # Mock the specific open call
        simulated_error = OSError("Simulated read error")
        mock_open.side_effect = simulated_error

        with self.assertRaises(OSError) as ctx:
            read_batch_backup(self.file_path)

        self.assertIs(ctx.exception, simulated_error)

if __name__ == '__main__':
    unittest.main()
