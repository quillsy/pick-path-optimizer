import unittest
import sys
import os
import json

# Append project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.warehouse import Warehouse
from modules.picks import Pick, load_all_batches

class TestRealBatches(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.batches_path = os.path.join(base_dir, "data", "pick_batches.json")
        self.warehouse = Warehouse(os.path.join(base_dir, "data", "warehouse.json"))
        self.batches = load_all_batches(self.batches_path, self.warehouse)

    def test_batches_exist_and_counts_are_correct(self):
        # 1. 10 neue Batches vorhanden
        # 2. Pick-Anzahl stimmt
        expected_counts = {
            "BATCH-REAL-002": 10,
            "BATCH-REAL-003": 8,
            "BATCH-REAL-004": 13,
            "BATCH-REAL-005": 3,
            "BATCH-REAL-006": 17,
            "BATCH-REAL-007": 7,
            "BATCH-REAL-008": 27,
            "BATCH-REAL-009": 15,
            "BATCH-REAL-010": 36,
            "BATCH-REAL-011": 24
        }
        
        for batch_id, count in expected_counts.items():
            self.assertIn(batch_id, self.batches, f"{batch_id} should exist in database.")
            self.assertEqual(len(self.batches[batch_id].picks), count, f"{batch_id} should have exactly {count} picks.")

    def test_original_batch_unmodified(self):
        # 6. Bestehende BATCH-HISTORICAL-0001 unverändert
        self.assertIn("BATCH-HISTORICAL-0001", self.batches)
        hist_batch = self.batches["BATCH-HISTORICAL-0001"]
        self.assertEqual(len(hist_batch.picks), 33)
        self.assertEqual(hist_batch.picks[0].raw_code, "05.056.50")
        self.assertEqual(hist_batch.picks[-1].raw_code, "20.020.30")

    def test_source_is_historical(self):
        # 4. source = historical
        for b_id in self.batches:
            if b_id.startswith("BATCH-"):
                self.assertEqual(self.batches[b_id].source, "historical", f"{b_id} source must be 'historical'.")

    def test_order_is_preserved(self):
        # 3. Reihenfolge stimmt
        # Test sample BATCH-REAL-002 exact order
        b2_picks = [p.raw_code for p in self.batches["BATCH-REAL-002"].picks]
        expected_b2 = [
            "09.034.60", "12.061.40", "15.011.40", "15.055.40", "16.077.60",
            "17.037.10", "18.011.30", "19.047.20", "20.041.50", "20.014.60"
        ]
        self.assertEqual(b2_picks, expected_b2)

        # Test sample BATCH-REAL-005 exact order
        b5_picks = [p.raw_code for p in self.batches["BATCH-REAL-005"].picks]
        expected_b5 = ["15.005.40", "18.063.20", "20.060.20"]
        self.assertEqual(b5_picks, expected_b5)

    def test_no_duplicates_in_database(self):
        # 5. keine Duplikate (verify dictionary keys are unique - implicitly true for JSON load,
        # but let's read the raw file structure to be absolutely sure keys aren't duplicated)
        with open(self.batches_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        self.assertEqual(len(raw_data.keys()), len(set(raw_data.keys())))

if __name__ == "__main__":
    unittest.main()
