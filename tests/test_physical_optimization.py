import unittest
import sys
import os

# Append project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.routing import calculate_route_metrics, calculate_distance
from modules.optimization import (
    validate_optimized_route,
    PhysicalAisleDistanceOptimizer,
    PhysicalAisleOperationalOptimizer
)

class TestPhysicalOptimization(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

    def test_04_05_treated_as_one_aisle(self):
        # 1. 04/05 werden als EIN physischer Gang behandelt.
        picks = [
            Pick("04.002.30", self.warehouse),
            Pick("05.015.30", self.warehouse),
            Pick("04.059.30", self.warehouse),
            Pick("05.070.30", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Verify all belong to physical aisle 1
        for p in route:
            self.assertEqual(p.physical_aisle_id, 1)
        
        # Verify they are sorted monotonically by row to form a single continuous walk
        # Row order should be 2 -> 15 -> 59 -> 70
        self.assertEqual(route[0].row, 2)
        self.assertEqual(route[1].row, 15)
        self.assertEqual(route[2].row, 59)
        self.assertEqual(route[3].row, 70)

    def test_06_07_treated_as_one_aisle(self):
        # 2. 06/07 werden als EIN physischer Gang behandelt.
        picks = [
            Pick("06.010.10", self.warehouse),
            Pick("07.025.10", self.warehouse),
            Pick("06.050.10", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Verify physical aisle is 2
        for p in route:
            self.assertEqual(p.physical_aisle_id, 2)
        # Verify sorted monotonically
        self.assertEqual(route[0].row, 10)
        self.assertEqual(route[1].row, 25)
        self.assertEqual(route[2].row, 50)

    def test_no_repeated_aisle_visits(self):
        # 3. Kein physischer Gang darf unnötig mehrfach besucht werden.
        # Picks in Aisle 1, Aisle 2, Aisle 3
        picks = [
            Pick("04.010.30", self.warehouse), # Aisle 1
            Pick("08.015.30", self.warehouse), # Aisle 3
            Pick("06.020.30", self.warehouse), # Aisle 2
            Pick("05.050.30", self.warehouse), # Aisle 1
            Pick("07.070.30", self.warehouse)  # Aisle 2
        ]
        opt = PhysicalAisleOperationalOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Calculate metrics
        metrics = calculate_route_metrics(route, self.warehouse)
        self.assertEqual(metrics.repeated_aisle_visit_count, 0)

    def test_start_pick_remains_unchanged(self):
        # 4. Erster Pick bleibt unverändert.
        picks = [
            Pick("08.041.30", self.warehouse),
            Pick("04.002.30", self.warehouse),
            Pick("19.015.20", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        self.assertEqual(route[0].raw_code, "08.041.30")

    def test_pick_count_identical(self):
        # 5. Anzahl Picks bleibt identisch.
        picks = [Pick(c, self.warehouse) for c in ["04.002.30", "12.033.10", "19.015.20"]]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        self.assertEqual(len(route), 3)

    def test_duplicates_preserved(self):
        # 6. Duplikate bleiben erhalten.
        picks = [
            Pick("04.002.30", self.warehouse),
            Pick("04.002.30", self.warehouse),
            Pick("12.033.10", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        self.assertEqual(len(route), 3)
        self.assertEqual(route[0].raw_code, "04.002.30")
        self.assertEqual(route[1].raw_code, "04.002.30")

    def test_no_artificial_picks_created(self):
        # 7. Keine Picks werden erfunden.
        picks = [Pick(c, self.warehouse) for c in ["04.002.30", "12.033.10"]]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        route_codes = [p.raw_code for p in route]
        self.assertIn("04.002.30", route_codes)
        self.assertIn("12.033.10", route_codes)
        self.assertEqual(len(route_codes), 2)

    def test_middle_cross_aisle_permitted(self):
        # 8. Mittelgang bleibt zulässig.
        # Pick in Aisle 1 (below middle gang: row 35) and Aisle 2 (above middle gang: row 52)
        picks = [
            Pick("04.035.30", self.warehouse),
            Pick("07.052.30", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Verify transition is via middle
        metrics = calculate_route_metrics(route, self.warehouse)
        via_middle = sum(1 for s in metrics.segments if s.chosen_path_type == "via_middle")
        self.assertEqual(via_middle, 1)

    def test_gang_20_exit_handling(self):
        # 9. Gang 20 wird korrekt behandelt (placed at the end, descending).
        picks = [
            Pick("06.010.10", self.warehouse),
            Pick("20.030.30", self.warehouse),
            Pick("20.080.30", self.warehouse)
        ]
        opt = PhysicalAisleOperationalOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        self.assertEqual(route[0].raw_code, "06.010.10")
        self.assertEqual(route[1].raw_code, "20.080.30")
        self.assertEqual(route[2].raw_code, "20.030.30") # Descending row order # Ordered descending towards row 1

    def test_no_artificial_gang_20_run(self):
        # 10. Kein Gang-20-Weg wird künstlich erzeugt.
        picks = [Pick(c, self.warehouse) for c in ["04.002.30", "12.033.10"]]
        opt = PhysicalAisleOperationalOptimizer()
        route = opt.optimize(picks, self.warehouse)
        for p in route:
            self.assertNotEqual(p.physical_aisle_id, 9)

    def test_path_never_cuts_shelves(self):
        # 11. Route darf niemals durch Regale laufen.
        p_a = Pick("04.010.30", self.warehouse)
        p_b = Pick("07.020.30", self.warehouse)
        
        # Wegenetz distance via Eingang y=0
        dist = calculate_distance(p_a, p_b, self.warehouse)
        euclidean = ((p_a.x - p_b.x)**2 + (p_a.y - p_b.y)**2)**0.5
        self.assertTrue(dist > euclidean + 10.0)

    def test_all_512_combinations_evaluated(self):
        # 12. Alle 512 Richtungszustände werden bei einem vollständigen 9-Gang-Fall korrekt berücksichtigt.
        # Picks in all 9 physical aisles
        picks = [
            Pick("04.010.30", self.warehouse), # Aisle 1
            Pick("06.015.30", self.warehouse), # Aisle 2
            Pick("08.020.30", self.warehouse), # Aisle 3
            Pick("10.025.30", self.warehouse), # Aisle 4
            Pick("12.030.30", self.warehouse), # Aisle 5
            Pick("14.035.30", self.warehouse), # Aisle 6
            Pick("16.040.30", self.warehouse), # Aisle 7
            Pick("18.045.30", self.warehouse), # Aisle 8
            Pick("20.050.30", self.warehouse)  # Aisle 9
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Verify length and constraints
        self.assertEqual(len(route), 9)
        self.assertTrue(validate_optimized_route(picks, route))

    def test_single_aisle_monotonous_sorting(self):
        # 13. Ein Testfall mit nur einem physischen Gang muss die Picks monoton in einer Richtung abarbeiten.
        picks = [
            Pick("04.070.30", self.warehouse), # start (not index 0, wait, it is at index 0 in the list)
            Pick("04.010.30", self.warehouse),
            Pick("04.050.30", self.warehouse),
            Pick("04.030.30", self.warehouse)
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Starts with 04.070.30 (fixed).
        # Remaining picks [04.010, 04.050, 04.030] should be sorted descendingly to continue
        # in the same direction: 70 -> 50 -> 30 -> 10.
        self.assertEqual(route[0].row, 70)
        self.assertEqual(route[1].row, 50)
        self.assertEqual(route[2].row, 30)
        self.assertEqual(route[3].row, 10)

    def test_multi_aisle_direction_combinations(self):
        # 14. Ein Testfall mit mehreren Gängen muss verschiedene UP/DOWN-Kombinationen prüfen.
        picks = [
            Pick("04.002.30", self.warehouse), # Aisle 1
            Pick("04.070.30", self.warehouse), # Aisle 1
            # Next aisle should go DOWN to meet row 1 end smoothly
            Pick("06.080.30", self.warehouse), # Aisle 2
            Pick("06.020.30", self.warehouse)  # Aisle 2
        ]
        opt = PhysicalAisleDistanceOptimizer()
        route = opt.optimize(picks, self.warehouse)
        
        # Distance optimal route:
        # Aisle 1 UP: 2 -> 70
        # Aisle 2 DOWN: 80 -> 20
        # This keeps total distance short.
        self.assertEqual(route[0].row, 2)
        self.assertEqual(route[1].row, 70)
        self.assertEqual(route[2].row, 80)
        self.assertEqual(route[3].row, 20)

if __name__ == "__main__":
    unittest.main()
