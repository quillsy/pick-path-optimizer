import unittest
import sys
import os
import shutil
from datetime import datetime

# Append the project root so we can import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.picks import (
    Pick, PickOrder, load_all_batches, save_batch, delete_batch, generate_next_batch_id
)
from modules.warehouse import Warehouse
from modules.routing import calculate_distance_with_type, calculate_route_distance

class TestPickParsing(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

    def test_pick_05_056_50(self):
        pick = Pick("05.056.50", self.warehouse)
        self.assertEqual(pick.side, 5)
        self.assertEqual(pick.row, 56)
        self.assertEqual(pick.box, 50)
        self.assertEqual(pick.side_str, "05")
        self.assertEqual(pick.row_str, "056")
        self.assertEqual(pick.box_str, "50")
        self.assertEqual(pick.physical_aisle_id, 1)
        
        x, y = self.warehouse.get_coordinates(5, 56)
        self.assertEqual(pick.x, x)
        self.assertEqual(pick.y, y)

    def test_pick_06_008_30(self):
        pick = Pick("06.008.30", self.warehouse)
        self.assertEqual(pick.side, 6)
        self.assertEqual(pick.row, 8)
        self.assertEqual(pick.box, 30)
        self.assertEqual(pick.side_str, "06")
        self.assertEqual(pick.row_str, "008")
        self.assertEqual(pick.box_str, "30")
        self.assertEqual(pick.physical_aisle_id, 2)

    def test_pick_19_015_20(self):
        pick = Pick("19.015.20", self.warehouse)
        self.assertEqual(pick.side, 19)
        self.assertEqual(pick.row, 15)
        self.assertEqual(pick.box, 20)
        self.assertEqual(pick.physical_aisle_id, 8)

    def test_pick_20_028_10(self):
        pick = Pick("20.028.10", self.warehouse)
        self.assertEqual(pick.side, 20)
        self.assertEqual(pick.row, 28)
        self.assertEqual(pick.box, 10)
        self.assertEqual(pick.physical_aisle_id, 9)

    def test_pick_02_015_30(self):
        pick = Pick("02.015.30", self.warehouse)
        self.assertEqual(pick.side, 2)
        self.assertEqual(pick.row, 15)
        self.assertEqual(pick.box, 30)
        self.assertEqual(pick.physical_aisle_id, 0)
        
        # Test coordinates: should be cart coordinates (1.25, -1.0)
        self.assertEqual(pick.x, 1.25)
        self.assertEqual(pick.y, -1.0)

    def test_invalid_parsing(self):
        with self.assertRaises(ValueError):
            Pick("invalid.code")
        with self.assertRaises(ValueError):
            Pick("12.34")
        with self.assertRaises(ValueError):
            Pick("12.34.56.78")


class TestWarehouseLayout(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

    def test_aisle_pairings(self):
        aisle_04 = self.warehouse.get_aisle_by_side(4)
        aisle_05 = self.warehouse.get_aisle_by_side(5)
        self.assertEqual(aisle_04, aisle_05)

        aisle_06 = self.warehouse.get_aisle_by_side(6)
        aisle_07 = self.warehouse.get_aisle_by_side(7)
        self.assertEqual(aisle_06, aisle_07)

        aisle_18 = self.warehouse.get_aisle_by_side(18)
        aisle_19 = self.warehouse.get_aisle_by_side(19)
        self.assertEqual(aisle_18, aisle_19)

    def test_aisle_20_single_sided(self):
        aisle_20 = self.warehouse.get_aisle_by_side(20)
        self.assertIsNotNone(aisle_20)
        self.assertEqual(aisle_20.left_side, 20)
        self.assertIsNone(aisle_20.right_side)


class TestPickBatches(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)
        self.test_batch_codes = [
            "05.056.50", "06.008.30", "07.002.30", "07.004.30", "08.041.30",
            "10.051.20", "10.046.40", "10.039.30", "10.029.30", "10.027.30",
            "10.019.30", "10.001.40", "11.066.40", "12.074.40", "12.033.10",
            "13.009.10", "13.038.30", "13.073.50", "15.031.20", "15.034.30",
            "15.042.30", "15.045.30", "15.075.40", "16.031.30", "16.027.20",
            "17.027.30", "17.035.30", "17.084.40", "18.045.10", "19.015.20",
            "19.023.50", "20.028.10", "20.020.30"
        ]

    def test_33_picks_parsed_and_count_matching(self):
        # 1. 33 Picks werden korrekt erkannt.
        # 3. pick_count == 33.
        order = PickOrder("BATCH-TEST-001", "2026-08-14T00:00:00Z", self.test_batch_codes, self.warehouse)
        self.assertEqual(len(order.picks), 33)
        self.assertEqual(order.pick_count, 33)

    def test_first_pick_is_correct(self):
        # 2. first_pick ist 05.056.50.
        order = PickOrder("BATCH-TEST-001", "2026-08-14T00:00:00Z", self.test_batch_codes, self.warehouse)
        self.assertIsNotNone(order.first_pick)
        self.assertEqual(order.first_pick.raw_code, "05.056.50")
        
        # Verify coordinates of first pick
        self.assertEqual(order.first_pick.side, 5)
        self.assertEqual(order.first_pick.row, 56)

    def test_input_sequence_order_preserved(self):
        # 4. Eingabereihenfolge bleibt erhalten.
        order = PickOrder("BATCH-TEST-001", "2026-08-14T00:00:00Z", self.test_batch_codes, self.warehouse)
        for idx, pick in enumerate(order.picks):
            self.assertEqual(pick.raw_code, self.test_batch_codes[idx])

    def test_duplicates_not_removed(self):
        # 5. doppelte Picks werden nicht entfernt.
        codes_with_duplicates = ["05.056.50", "05.056.50", "12.033.10", "12.033.10"]
        order = PickOrder("BATCH-DUP-01", "2026-08-14T00:00:00Z", codes_with_duplicates, self.warehouse)
        self.assertEqual(len(order.picks), 4)
        self.assertEqual(order.picks[0].raw_code, "05.056.50")
        self.assertEqual(order.picks[1].raw_code, "05.056.50")
        self.assertEqual(order.picks[2].raw_code, "12.033.10")
        self.assertEqual(order.picks[3].raw_code, "12.033.10")

    def test_invalid_side_rejected(self):
        # 6. ungültige Seite wird abgelehnt.
        # Valid side range is 01-20
        with self.assertRaises(ValueError):
            Pick("00.042.10", self.warehouse) # Side 0 is invalid
        with self.assertRaises(ValueError):
            Pick("21.042.10", self.warehouse) # Side 21 is invalid

    def test_invalid_row_rejected(self):
        # 7. ungültige Reihe wird abgelehnt.
        # Valid row range is 001-084
        with self.assertRaises(ValueError):
            Pick("05.000.10", self.warehouse) # Row 0 is invalid
        with self.assertRaises(ValueError):
            Pick("05.085.10", self.warehouse) # Row 85 is invalid

    def test_corrupted_pick_code_rejected(self):
        # 8. beschädigter Pick-Code wird abgelehnt.
        with self.assertRaises(ValueError):
            Pick("05.056", self.warehouse) # missing box
        with self.assertRaises(ValueError):
            Pick("05.999.50", self.warehouse) # row > 84
        with self.assertRaises(ValueError):
            Pick("105.056.50", self.warehouse) # side > 20

    def test_persistence_saving_loading_deleting(self):
        # 9. Batch kann gespeichert werden.
        # 10. gespeicherte Batch kann wieder geladen werden.
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        temp_db_path = os.path.join(base_dir, "data", "test_temp_batches.json")
        
        # Clean up if exists
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)
            
        test_order = PickOrder(
            order_id="BATCH-TEST-SAVE-LOAD",
            timestamp_str="2026-08-14T01:00:00+02:00",
            raw_picks_list=["04.002.30", "17.060.40"],
            warehouse=self.warehouse,
            source="manual"
        )
        
        # Save
        save_batch(temp_db_path, test_order)
        self.assertTrue(os.path.exists(temp_db_path))
        
        # Load
        loaded_batches = load_all_batches(temp_db_path, self.warehouse)
        self.assertIn("BATCH-TEST-SAVE-LOAD", loaded_batches)
        loaded_order = loaded_batches["BATCH-TEST-SAVE-LOAD"]
        self.assertEqual(loaded_order.order_id, "BATCH-TEST-SAVE-LOAD")
        self.assertEqual(loaded_order.pick_count, 2)
        self.assertEqual(loaded_order.picks[0].raw_code, "04.002.30")
        self.assertEqual(loaded_order.picks[1].raw_code, "17.060.40")
        self.assertEqual(loaded_order.source, "manual")
        
        # Delete
        success = delete_batch(temp_db_path, "BATCH-TEST-SAVE-LOAD")
        self.assertTrue(success)
        
        loaded_after_delete = load_all_batches(temp_db_path, self.warehouse)
        self.assertNotIn("BATCH-TEST-SAVE-LOAD", loaded_after_delete)
        
        # Clean up file
        if os.path.exists(temp_db_path):
            os.remove(temp_db_path)

    def test_batch_id_uniqueness(self):
        # 11. Batch-ID ist eindeutig.
        date_str = datetime.now().strftime("%Y%m%d")
        existing_ids = [f"BATCH-{date_str}-0001", f"BATCH-{date_str}-0002"]
        next_id = generate_next_batch_id(existing_ids)
        self.assertEqual(next_id, f"BATCH-{date_str}-0003")
        self.assertNotIn(next_id, existing_ids)

    def test_flexible_first_picks_02(self):
        # 12. Pick 02 kann als erster Pick vorkommen.
        picks = [Pick("02.015.30", self.warehouse), Pick("05.056.50", self.warehouse)]
        order = PickOrder("BATCH-START-02", "2026-08-14T00:00:00Z", [p.raw_code for p in picks], self.warehouse)
        self.assertEqual(order.first_pick.side, 2)
        self.assertEqual(order.first_pick.x, 1.25)
        self.assertEqual(order.first_pick.y, -1.0)

    def test_flexible_first_picks_09(self):
        # 13. Pick 09 kann als erster Pick vorkommen.
        picks = [Pick("09.025.30", self.warehouse), Pick("05.056.50", self.warehouse)]
        order = PickOrder("BATCH-START-09", "2026-08-14T00:00:00Z", [p.raw_code for p in picks], self.warehouse)
        self.assertEqual(order.first_pick.side, 9)
        # Side 9 is right side of Aisle 3 (x_path = 6.25m)
        self.assertEqual(order.first_pick.x, 6.25)
        # Row 25 center y-position
        self.assertAlmostEqual(order.first_pick.y, (25 - 0.5) * 1.30)

    def test_flexible_first_picks_17(self):
        # 14. Pick 17 kann als erster Pick vorkommen.
        picks = [Pick("17.060.40", self.warehouse), Pick("05.056.50", self.warehouse)]
        order = PickOrder("BATCH-START-17", "2026-08-14T00:00:00Z", [p.raw_code for p in picks], self.warehouse)
        self.assertEqual(order.first_pick.side, 17)
        # Side 17 is right side of Aisle 7 (x_path = 16.25m)
        self.assertEqual(order.first_pick.x, 16.25)
        # Row 60 center y-position (row >= 43)
        # y = first_sec_len + cross_width + (row - 43 + 0.5) * shelf_len
        # y = 54.60 + 1.43 + (60 - 43 + 0.5) * 1.30 = 56.03 + 17.5 * 1.30 = 56.03 + 22.75 = 78.78m
        self.assertAlmostEqual(order.first_pick.y, 78.78)

class TestRouteDistances(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

    def test_case_a_same_aisle_same_side(self):
        # A) 04.010.20 -> 04.020.20
        # Row 10 center: 9.5 * 1.30 = 12.35m
        # Row 20 center: 19.5 * 1.30 = 25.35m
        # Expected distance: 13.00m
        p_a = Pick("04.010.20", self.warehouse)
        p_b = Pick("04.020.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 13.00)
        self.assertEqual(p_type, "same_aisle")

    def test_case_b_same_aisle_opposite_sides(self):
        # B) 04.010.20 -> 05.020.20
        # Same physical aisle (Aisle 1), opposite sides
        # Expected distance: 13.00m
        p_a = Pick("04.010.20", self.warehouse)
        p_b = Pick("05.020.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 13.00)
        self.assertEqual(p_type, "same_aisle")

    def test_case_c_different_aisles_via_001(self):
        # C) 04.010.20 -> 07.020.20
        # Different aisles (Aisle 1 & Aisle 2), via Eingang (y = 0)
        # Expected distance: 40.20m
        p_a = Pick("04.010.20", self.warehouse)
        p_b = Pick("07.020.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 40.20)
        self.assertEqual(p_type, "via_001")

    def test_case_d_different_aisles_via_middle(self):
        # D) 04.035.20 -> 07.052.20
        # Different aisles, via Mittelgang
        # Expected distance: 26.03m
        p_a = Pick("04.035.20", self.warehouse)
        p_b = Pick("07.052.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 26.03)
        self.assertEqual(p_type, "via_middle")

    def test_case_e_different_aisles_via_middle_2(self):
        # E) 04.070.20 -> 07.030.20
        # Different aisles, via Mittelgang
        # Expected distance: 55.93m
        p_a = Pick("04.070.20", self.warehouse)
        p_b = Pick("07.030.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 55.93)
        self.assertEqual(p_type, "via_middle")

    def test_case_f_same_aisle_across_middle(self):
        # F) 09.041.20 -> 09.043.20
        # Same aisle, direct vertical walk across Mittelgang
        # Expected distance: 4.03m
        p_a = Pick("09.041.20", self.warehouse)
        p_b = Pick("09.043.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 4.03)
        self.assertEqual(p_type, "same_aisle")

    def test_case_g_same_single_sided_aisle(self):
        # G) 20.020.20 -> 20.070.20
        # Same single-sided aisle (Aisle 9)
        # Expected distance: 66.43m
        p_a = Pick("20.020.20", self.warehouse)
        p_b = Pick("20.070.20", self.warehouse)
        dist, p_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertAlmostEqual(dist, 66.43)
        self.assertEqual(p_type, "same_aisle")

    def test_distance_symmetry_and_non_negativity(self):
        p_a = Pick("05.056.50", self.warehouse)
        p_b = Pick("18.045.10", self.warehouse)
        
        dist_ab, _ = calculate_distance_with_type(p_a, p_b, self.warehouse)
        dist_ba, _ = calculate_distance_with_type(p_b, p_a, self.warehouse)
        
        self.assertTrue(dist_ab >= 0.0)
        self.assertAlmostEqual(dist_ab, dist_ba)

    def test_no_diagonal_cutting_through_shelves(self):
        p_a = Pick("04.010.20", self.warehouse)
        p_b = Pick("07.020.20", self.warehouse)
        
        grid_dist, _ = calculate_distance_with_type(p_a, p_b, self.warehouse)
        euclidean_dist = ((p_a.x - p_b.x)**2 + (p_a.y - p_b.y)**2)**0.5
        self.assertTrue(grid_dist > euclidean_dist + 10.0)


class TestOptimizationScenarios(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

    def test_scenario_a_single_aisle_no_backtracking(self):
        # TEST A – EIN PHYSISCHER GANG
        # Picks: 04.002.30, 04.015.30, 04.059.30, 04.070.30
        # Ordered row-wise (ideal): 002 -> 015 -> 059 -> 070
        # Scrambled: 002 -> 070 -> 015 -> 059 (has backtracking)
        picks_ideal = [
            Pick("04.002.30", self.warehouse),
            Pick("04.015.30", self.warehouse),
            Pick("04.059.30", self.warehouse),
            Pick("04.070.30", self.warehouse)
        ]
        picks_scrambled = [
            Pick("04.002.30", self.warehouse),
            Pick("04.070.30", self.warehouse),
            Pick("04.015.30", self.warehouse),
            Pick("04.059.30", self.warehouse)
        ]
        
        dist_ideal = calculate_route_distance(picks_ideal, self.warehouse)
        dist_scrambled = calculate_route_distance(picks_scrambled, self.warehouse)
        
        # Row 2 (y=1.95) to Row 70 (y=91.78)
        # Expected ideal distance: 91.78 - 1.95 = 89.83m
        self.assertAlmostEqual(dist_ideal, 89.83)
        # Scrambled distance must be significantly longer due to backtracking
        self.assertTrue(dist_scrambled > dist_ideal + 50.0)

    def test_scenario_b_opposite_sides_same_aisle(self):
        # TEST B – GEGENÜBERLIEGENDE SEITEN
        # Picks: 04.002.30, 05.015.30, 04.059.30, 05.070.30
        # Treats side 04 (left) and 05 (right) as the same physical aisle (Aisle 1)
        picks = [
            Pick("04.002.30", self.warehouse),
            Pick("05.015.30", self.warehouse),
            Pick("04.059.30", self.warehouse),
            Pick("05.070.30", self.warehouse)
        ]
        
        # Verify physical aisle groupings
        for p in picks:
            self.assertEqual(p.physical_aisle_id, 1)
            
        dist = calculate_route_distance(picks, self.warehouse)
        # If sorted row-wise, the walk is straight along Aisle 1
        # from Row 2 to Row 70. Distance: 89.83m
        self.assertAlmostEqual(dist, 89.83)

    def test_scenario_c_alternating_aisles_s_shape(self):
        # TEST C – WECHSELNDE GÄNGE
        # Picks: 04.002.30, 04.070.30, 06.080.30, 06.020.30, 08.015.30, 08.075.30
        # Simulates going up Aisle 1, down Aisle 2, up Aisle 3 (S-Shape)
        picks = [
            Pick("04.002.30", self.warehouse), # Aisle 1 Row 2
            Pick("04.070.30", self.warehouse), # Aisle 1 Row 70
            Pick("06.080.30", self.warehouse), # Aisle 2 Row 80
            Pick("06.020.30", self.warehouse), # Aisle 2 Row 20
            Pick("08.015.30", self.warehouse), # Aisle 3 Row 15
            Pick("08.075.30", self.warehouse)  # Aisle 3 Row 75
        ]
        
        dist = calculate_route_distance(picks, self.warehouse)
        # Calculated:
        # Aisle 1: Row 2 (1.95) -> Row 70 (91.78) = 89.83m
        # Transition: Aisle 1 Row 70 -> Aisle 2 Row 80 (104.78) via y_bottom (110.63) = (110.63-91.78) + 2.5 + (110.63-104.78) = 27.20m
        # Aisle 2: Row 80 -> Row 20 (25.35) = 79.43m
        # Transition: Aisle 2 Row 20 -> Aisle 3 Row 15 (18.85) via y_top (0) = 25.35 + 2.5 + 18.85 = 46.70m
        # Aisle 3: Row 15 -> Row 75 (98.28) = 79.43m
        # Total = 89.83 + 27.20 + 79.43 + 46.70 + 79.43 = 322.59m
        self.assertAlmostEqual(dist, 322.59)

    def test_scenario_d_middle_cross_aisle(self):
        # TEST D – MITTELGANG
        # Picks: 04.035.30, 07.052.30
        # Verifies transition via middle cross-aisle
        p_a = Pick("04.035.30", self.warehouse)
        p_b = Pick("07.052.30", self.warehouse)
        
        dist, path_type = calculate_distance_with_type(p_a, p_b, self.warehouse)
        self.assertEqual(path_type, "via_middle")
        self.assertAlmostEqual(dist, 26.03)

    def test_scenario_e_gang_20_as_exit(self):
        # TEST E – GANG 20 ALS ENDE
        # Picks: 15.030.30, 18.060.30, 20.080.30, 20.060.30, 20.030.30
        # Verifies that Gang 20 picks exist and are ordered descendingly
        # (working towards Row 001) at the end of the batch
        picks = [
            Pick("15.030.30", self.warehouse),
            Pick("18.060.30", self.warehouse),
            Pick("20.080.30", self.warehouse),
            Pick("20.060.30", self.warehouse),
            Pick("20.030.30", self.warehouse)
        ]
        
        # Verify last three picks are in Aisle 9 (side 20)
        self.assertEqual(picks[2].physical_aisle_id, 9)
        self.assertEqual(picks[3].physical_aisle_id, 9)
        self.assertEqual(picks[4].physical_aisle_id, 9)
        
        # Verify descending order of row positions
        self.assertTrue(picks[2].row > picks[3].row > picks[4].row)

    def test_scenario_f_no_gang_20(self):
        # TEST F – KEIN GANG 20
        # Picks: 05.020.30, 09.060.30, 13.030.30
        # Verify none are in Gang 20 (Aisle 9)
        picks = [
            Pick("05.020.30", self.warehouse),
            Pick("09.060.30", self.warehouse),
            Pick("13.030.30", self.warehouse)
        ]
        for p in picks:
            self.assertNotEqual(p.physical_aisle_id, 9)
            self.assertNotEqual(p.side, 20)

    def test_scenario_g_single_last_pick(self):
        # TEST G – EINZELNER LETZTER PICK
        # Single pick list 17.053.01
        p = Pick("17.053.01", self.warehouse)
        self.assertEqual(p.side, 17)
        self.assertEqual(p.row, 53)


if __name__ == "__main__":
    unittest.main()
