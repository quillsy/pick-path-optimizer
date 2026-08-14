import unittest
import sys
import os

# Append project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.routing import calculate_route_metrics
from modules.optimization import (
    validate_optimized_route,
    calculate_backtracking_distance,
    BaselineOptimizer,
    GroupedAisleOptimizer,
    GreedyNearestOptimizer,
    EndAwareOptimizer
)

class TestOptimizationSuite(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)
        
        # Test batch codes (includes duplicates)
        self.test_codes = [
            "05.056.50", "06.008.30", "05.056.50", "07.004.30", "08.041.30",
            "20.080.10", "20.020.10", "20.060.10"
        ]
        self.picks = [Pick(code, self.warehouse) for code in self.test_codes]

    def test_algorithms_preserve_pick_count(self):
        # A) Alle Algorithmen behalten exakt dieselbe Pick-Anzahl.
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            self.assertEqual(len(opt_route), len(self.picks))

    def test_algorithms_preserve_all_pick_codes(self):
        # B) Alle Pick-Codes bleiben vorhanden.
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        orig_sorted_codes = sorted([p.raw_code for p in self.picks])
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            opt_sorted_codes = sorted([p.raw_code for p in opt_route])
            self.assertEqual(opt_sorted_codes, orig_sorted_codes)

    def test_algorithms_preserve_first_pick(self):
        # C) Erster Pick bleibt unverändert.
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            self.assertEqual(opt_route[0].raw_code, self.picks[0].raw_code)

    def test_algorithms_preserve_duplicates(self):
        # D) Duplikate bleiben erhalten.
        # "05.056.50" appears twice in the test codes
        orig_dup_count = sum(1 for p in self.picks if p.raw_code == "05.056.50")
        self.assertEqual(orig_dup_count, 2)
        
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            opt_dup_count = sum(1 for p in opt_route if p.raw_code == "05.056.50")
            self.assertEqual(opt_dup_count, 2)

    def test_baseline_equals_original_sequence(self):
        # E) Baseline entspricht exakt der ursprünglichen Eingabereihenfolge.
        opt_route = BaselineOptimizer().optimize(self.picks, self.warehouse)
        for i in range(len(self.picks)):
            self.assertEqual(opt_route[i].raw_code, self.picks[i].raw_code)

    def test_optimized_distance_is_non_negative(self):
        # F) Optimierte Distanz darf nicht negativ sein.
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            metrics = calculate_route_metrics(opt_route, self.warehouse)
            self.assertTrue(metrics.total_distance_m >= 0.0)

    def test_optimized_routes_calculable(self):
        # G) Alle optimierten Routen können durch calculate_route_metrics() berechnet werden.
        optimizers = [
            BaselineOptimizer(),
            GroupedAisleOptimizer(),
            GreedyNearestOptimizer(),
            EndAwareOptimizer()
        ]
        for opt in optimizers:
            opt_route = opt.optimize(self.picks, self.warehouse)
            metrics = calculate_route_metrics(opt_route, self.warehouse)
            self.assertIsNotNone(metrics)
            self.assertEqual(len(metrics.segments), len(self.picks) - 1)

    def test_end_aware_optimizer_gang_20_handling(self):
        # H) Gang 20 wird bei EndAwareOptimizer berücksichtigt (placed at the end, descending rows).
        opt_route = EndAwareOptimizer().optimize(self.picks, self.warehouse)
        
        # Last three picks should be Gang 20 (side 20) picks
        # and sorted descendingly by row: 20.080 -> 20.060 -> 20.020
        last_three = opt_route[-3:]
        self.assertEqual(last_three[0].raw_code, "20.080.10")
        self.assertEqual(last_three[1].raw_code, "20.060.10")
        self.assertEqual(last_three[2].raw_code, "20.020.10")

    def test_end_aware_optimizer_no_artificial_picks(self):
        # I) Wenn kein Gang 20 vorhanden ist, wird kein künstlicher Gang-20-Pick hinzugefügt.
        picks_no_g20 = [Pick(code, self.warehouse) for code in ["05.056.50", "06.008.30", "07.004.30"]]
        opt_route = EndAwareOptimizer().optimize(picks_no_g20, self.warehouse)
        
        # Verify no side 20 picks exist
        self.assertEqual(len(opt_route), 3)
        for p in opt_route:
            self.assertNotEqual(p.side, 20)

    def test_invalid_routes_flagged(self):
        # J) Eine Optimierung darf keine ungültige Pick-Reihenfolge erzeugen.
        # Verify that validate_optimized_route correctly flags deviations:
        original = self.picks
        
        # 1. Changed length
        self.assertFalse(validate_optimized_route(original, original[:-1]))
        
        # 2. Changed first pick
        scrambled_first = [original[1]] + original[1:]
        self.assertFalse(validate_optimized_route(original, scrambled_first))
        
        # 3. Mutated code / missing code
        mutated = list(original)
        mutated[1] = Pick("04.002.30", self.warehouse)
        self.assertFalse(validate_optimized_route(original, mutated))

if __name__ == "__main__":
    unittest.main()
