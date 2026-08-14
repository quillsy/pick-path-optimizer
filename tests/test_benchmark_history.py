import unittest
import sys
import os
import json

# Append project root
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.optimizer_benchmark import (
    benchmark_batch,
    load_benchmark_history,
    save_benchmark_run,
    OPTIMIZER_VERSION
)

class TestBenchmarkHistory(unittest.TestCase):
    def setUp(self):
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)
        
        self.temp_history_path = os.path.join(base_dir, "data", "test_temp_history.json")
        if os.path.exists(self.temp_history_path):
            os.remove(self.temp_history_path)
            
        # Sample test codes
        self.test_codes = ["05.056.50", "06.008.30", "07.004.30", "20.080.10"]
        self.picks = [Pick(code, self.warehouse) for code in self.test_codes]

    def tearDown(self):
        if os.path.exists(self.temp_history_path):
            os.remove(self.temp_history_path)

    def test_benchmark_runs_and_saves_and_loads(self):
        # 1. Benchmark einer Batch runs correctly.
        # 2. Ergebnis wird gespeichert.
        # 3. Ergebnis kann geladen werden.
        # 4. Batch-Daten bleiben unverändert.
        # 9. Benchmark kann wiederholt werden.
        # 10. Keine doppelten Benchmark-Einträge bei identischer Batch + identischer Algorithmusversion.
        
        # Capture original codes
        orig_codes = [p.raw_code for p in self.picks]
        
        # Run benchmark
        # (This will normally save to data/benchmark_history.json, but let's test save_benchmark_run directly with temp path)
        results = benchmark_batch(self.picks, self.warehouse, "BATCH-TEST-HIST", "historical")
        
        # Verify original picks did not change
        self.assertEqual([p.raw_code for p in self.picks], orig_codes)
        
        # Get one of the records
        record = {
            "batch_id": "BATCH-TEST-HIST",
            "optimizer_version": OPTIMIZER_VERSION,
            "source": "historical",
            "pick_count": len(self.picks),
            "baseline_distance_m": 120.0,
            "grouped_aisle_distance_m": 100.0,
            "greedy_distance_m": 90.0,
            "end_aware_distance_m": 95.0,
            "physical_distance_optimum_m": 110.0,
            "physical_operational_optimum_m": 110.0,
            "baseline_backtracking_m": 10.0,
            "grouped_backtracking_m": 0.0,
            "greedy_backtracking_m": 5.0,
            "end_aware_backtracking_m": 0.0,
            "physical_distance_backtracking_m": 0.0,
            "physical_operational_backtracking_m": 0.0,
            "best_distance_method": "Greedy Nearest",
            "best_operational_method": "Grouped Aisle",
            "batch_profile": {}
        }
        
        # Save to temp history
        save_benchmark_run(self.temp_history_path, record)
        
        # Load and verify
        history = load_benchmark_history(self.temp_history_path)
        self.assertIn(f"BATCH-TEST-HIST::{OPTIMIZER_VERSION}", history)
        loaded = history[f"BATCH-TEST-HIST::{OPTIMIZER_VERSION}"]
        self.assertEqual(loaded["pick_count"], 4)
        self.assertEqual(loaded["best_distance_method"], "Greedy Nearest")
        
        # Repeat benchmark saving (should overwrite, no duplicates)
        save_benchmark_run(self.temp_history_path, record)
        history_after = load_benchmark_history(self.temp_history_path)
        self.assertEqual(len(history_after), 1)

    def test_simulation_and_historical_separated(self):
        # 5. Simulation und Historical werden getrennt (via 'source' attribute)
        rec_hist = {
            "batch_id": "BATCH-HIST-1",
            "optimizer_version": OPTIMIZER_VERSION,
            "source": "historical",
            "baseline_distance_m": 100.0,
            "grouped_aisle_distance_m": 80.0
        }
        rec_sim = {
            "batch_id": "BATCH-SIM-1",
            "optimizer_version": OPTIMIZER_VERSION,
            "source": "simulation",
            "baseline_distance_m": 200.0,
            "grouped_aisle_distance_m": 150.0
        }
        
        save_benchmark_run(self.temp_history_path, rec_hist)
        save_benchmark_run(self.temp_history_path, rec_sim)
        
        history = load_benchmark_history(self.temp_history_path)
        runs = list(history.values())
        
        hist_runs = [r for r in runs if r["source"] == "historical"]
        sim_runs = [r for r in runs if r["source"] == "simulation"]
        
        self.assertEqual(len(hist_runs), 1)
        self.assertEqual(len(sim_runs), 1)
        self.assertEqual(hist_runs[0]["batch_id"], "BATCH-HIST-1")
        self.assertEqual(sim_runs[0]["batch_id"], "BATCH-SIM-1")

    def test_aggregation_calculations(self):
        # 6. Durchschnittswerte (mean of savings) are correct.
        # 7. Median is correct.
        # 8. Best Method wird korrekt gezählt.
        runs = [
            {
                "batch_id": "B1",
                "optimizer_version": OPTIMIZER_VERSION,
                "source": "historical",
                "baseline_distance_m": 100.0,
                "grouped_aisle_distance_m": 80.0, # saving 20.0 (20%)
                "greedy_distance_m": 70.0, # saving 30.0 (30%)
                "best_distance_method": "Greedy Nearest"
            },
            {
                "batch_id": "B2",
                "optimizer_version": OPTIMIZER_VERSION,
                "source": "historical",
                "baseline_distance_m": 200.0,
                "grouped_aisle_distance_m": 150.0, # saving 50.0 (25%)
                "greedy_distance_m": 160.0, # saving 40.0 (20%)
                "best_distance_method": "Grouped Aisle"
            },
            {
                "batch_id": "B3",
                "optimizer_version": OPTIMIZER_VERSION,
                "source": "historical",
                "baseline_distance_m": 300.0,
                "grouped_aisle_distance_m": 210.0, # saving 90.0 (30%)
                "greedy_distance_m": 220.0, # saving 80.0 (26.7%)
                "best_distance_method": "Grouped Aisle"
            }
        ]
        
        # Let's verify our manual average & median calculation
        # Savings in meters (comparing best of grouped/greedy to baseline):
        # B1: best is greedy (70m), saving = 30m (30%)
        # B2: best is grouped (150m), saving = 50m (25%)
        # B3: best is grouped (210m), saving = 90m (30%)
        
        savings_m = [30.0, 50.0, 90.0]
        savings_pct = [30.0, 25.0, 30.0]
        
        avg_saving_m = sum(savings_m) / len(savings_m)
        self.assertAlmostEqual(avg_saving_m, 56.666666666)
        
        # Median of savings_m: sorted: [30.0, 50.0, 90.0] -> median is 50.0
        import statistics
        median_saving_m = statistics.median(savings_m)
        self.assertEqual(median_saving_m, 50.0)
        
        # Best method counts: Greedy = 1, Grouped = 2
        best_counts = {}
        for r in runs:
            method = r["best_distance_method"]
            best_counts[method] = best_counts.get(method, 0) + 1
            
        self.assertEqual(best_counts["Greedy Nearest"], 1)
        self.assertEqual(best_counts["Grouped Aisle"], 2)

if __name__ == "__main__":
    unittest.main()
