import copy
import json
import os
import statistics
import sys
import tempfile
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.optimizer_benchmark import (
    HISTORY_OBJECTIVE_FIELDS,
    HISTORY_SUMMARY_FIELDS,
    OPTIMIZER_VERSION,
    benchmark_batch,
    get_comparable_history_runs,
    get_history_objective_summary,
    load_benchmark_history,
    save_benchmark_run,
    summarize_benchmark_results,
    summarize_objective_distances,
)
from modules.picks import Pick
from modules.warehouse import Warehouse


class TestBenchmarkHistory(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(self.base_dir, "data", "warehouse.json")
        self.warehouse = Warehouse(config_path)

        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_history_path = os.path.join(self.temp_dir.name, "benchmark_history.json")
        self.temp_results_path = os.path.join(self.temp_dir.name, "benchmark_results.json")

        test_codes = ["05.056.50", "06.008.30", "07.004.30", "20.080.10"]
        self.picks = [Pick(code, self.warehouse) for code in test_codes]

    def tearDown(self):
        self.temp_dir.cleanup()

    def _modern_run(self, batch_id, distances, source="historical"):
        run = {
            "batch_id": batch_id,
            "timestamp": "2026-08-30T12:00:00",
            "optimizer_version": OPTIMIZER_VERSION,
            "source": source,
            "pick_count": 4,
            "baseline_backtracking_m": 10.0,
            "grouped_backtracking_m": 8.0,
            "greedy_backtracking_m": 6.0,
            "end_aware_backtracking_m": 5.0,
            "physical_distance_backtracking_m": 4.0,
            "physical_operational_backtracking_m": 3.0,
        }
        for method, field in HISTORY_OBJECTIVE_FIELDS.items():
            run[field] = distances[method]
        run.update(summarize_objective_distances(distances))
        return run

    def _temp_snapshot(self):
        snapshot = {}
        for root, _, files in os.walk(self.temp_dir.name):
            for filename in files:
                path = os.path.join(root, filename)
                relative_path = os.path.relpath(path, self.temp_dir.name)
                with open(path, "rb") as file_handle:
                    snapshot[relative_path] = file_handle.read()
        return snapshot

    def test_optimizer_version_is_v02(self):
        self.assertEqual(OPTIMIZER_VERSION, "v0.2")

    def test_benchmark_persists_calculated_objectives_and_winner_semantics(self):
        original_codes = [pick.raw_code for pick in self.picks]

        results = benchmark_batch(
            self.picks,
            self.warehouse,
            "BATCH-TEST-HIST",
            "historical",
            history_path=self.temp_history_path,
            results_path=self.temp_results_path,
        )

        self.assertEqual([pick.raw_code for pick in self.picks], original_codes)
        expected_summary = summarize_benchmark_results(results)
        history = load_benchmark_history(self.temp_history_path)
        history_key = f"BATCH-TEST-HIST::{OPTIMIZER_VERSION}"
        self.assertEqual(list(history), [history_key])
        stored_run = history[history_key]

        for method, field in HISTORY_OBJECTIVE_FIELDS.items():
            result = next(item for item in results if item["method_name"] == method)
            self.assertEqual(stored_run[field], result["distance_with_exit_m"])
        for field in HISTORY_SUMMARY_FIELDS:
            self.assertEqual(stored_run[field], expected_summary[field])
        self.assertEqual(
            get_history_objective_summary(stored_run)["best_overall_method"],
            expected_summary["best_overall_method"],
        )

        with open(self.temp_results_path, "r", encoding="utf-8") as file_handle:
            stored_results = json.load(file_handle)
        self.assertEqual(list(stored_results), [history_key])
        result_record = stored_results[history_key]
        for field in HISTORY_SUMMARY_FIELDS:
            self.assertEqual(result_record[field], expected_summary[field])
        persisted_runs = {item["method_name"]: item for item in result_record["runs"]}
        for result in results:
            self.assertEqual(
                persisted_runs[result["method_name"]]["distance_with_exit_m"],
                result["distance_with_exit_m"],
            )

        benchmark_batch(
            self.picks,
            self.warehouse,
            "BATCH-TEST-HIST",
            "historical",
            history_path=self.temp_history_path,
            results_path=self.temp_results_path,
        )
        self.assertEqual(len(load_benchmark_history(self.temp_history_path)), 1)

    def test_saving_v02_preserves_existing_v01_entry(self):
        v01_record = {
            "batch_id": "BATCH-VERSIONED",
            "optimizer_version": "v0.1",
            "source": "historical",
            "pick_count": 4,
            "sentinel": {"must": "remain unchanged"},
        }
        save_benchmark_run(self.temp_history_path, v01_record)
        original_v01 = copy.deepcopy(v01_record)

        benchmark_batch(
            self.picks,
            self.warehouse,
            "BATCH-VERSIONED",
            history_path=self.temp_history_path,
            results_path=self.temp_results_path,
        )

        history = load_benchmark_history(self.temp_history_path)
        self.assertEqual(history["BATCH-VERSIONED::v0.1"], original_v01)
        self.assertIn("BATCH-VERSIONED::v0.2", history)
        self.assertEqual(len(history), 2)

    def test_history_path_without_results_path_is_rejected_before_writing(self):
        before = self._temp_snapshot()

        with self.assertRaisesRegex(ValueError, "history_path and results_path"):
            benchmark_batch(
                self.picks,
                self.warehouse,
                "BATCH-PARTIAL-HISTORY",
                history_path=self.temp_history_path,
            )

        self.assertEqual(self._temp_snapshot(), before)

    def test_results_path_without_history_path_is_rejected_before_writing(self):
        before = self._temp_snapshot()

        with self.assertRaisesRegex(ValueError, "history_path and results_path"):
            benchmark_batch(
                self.picks,
                self.warehouse,
                "BATCH-PARTIAL-RESULTS",
                results_path=self.temp_results_path,
            )

        self.assertEqual(self._temp_snapshot(), before)

    def test_current_v01_history_entries_are_excluded_as_legacy(self):
        production_history_path = os.path.join(
            self.base_dir, "data", "benchmark_history.json"
        )
        history = load_benchmark_history(production_history_path)
        v01_runs = [
            run for run in history.values()
            if run.get("optimizer_version") == "v0.1"
        ]

        self.assertTrue(v01_runs)
        self.assertEqual(get_comparable_history_runs(v01_runs), [])
        for run in v01_runs:
            self.assertEqual(get_history_objective_summary(run), {})

    def test_partial_objective_fields_are_legacy(self):
        distances = {
            "Baseline": 100.0,
            "Grouped Aisle": 90.0,
            "Greedy Nearest": 95.0,
            "End Aware": 96.0,
            "Physical Aisle - Distance Optimum": 97.0,
            "Physical Aisle - Operational Optimum": 98.0,
        }
        run = self._modern_run("PARTIAL", distances)
        del run["end_aware_distance_with_exit_m"]

        self.assertEqual(get_history_objective_summary(run), {})
        self.assertEqual(get_comparable_history_runs([run]), [])

    def test_invalid_objective_values_are_legacy(self):
        distances = {
            "Baseline": 100.0,
            "Grouped Aisle": 90.0,
            "Greedy Nearest": 95.0,
            "End Aware": 96.0,
            "Physical Aisle - Distance Optimum": 97.0,
            "Physical Aisle - Operational Optimum": 98.0,
        }
        valid_run = self._modern_run("INVALID", distances)

        for invalid_value in (None, "90.0", True, float("nan"), float("inf"), -1.0):
            with self.subTest(invalid_value=invalid_value):
                run = copy.deepcopy(valid_run)
                run["grouped_aisle_distance_with_exit_m"] = invalid_value
                self.assertEqual(get_history_objective_summary(run), {})
                self.assertEqual(get_comparable_history_runs([run]), [])

    def test_invalid_best_heuristic_objective_summary_is_legacy(self):
        distances = {
            "Baseline": 100.0,
            "Grouped Aisle": 90.0,
            "Greedy Nearest": 95.0,
            "End Aware": 96.0,
            "Physical Aisle - Distance Optimum": 97.0,
            "Physical Aisle - Operational Optimum": 98.0,
        }
        valid_run = self._modern_run("INVALID-SUMMARY", distances)

        for invalid_value in (None, "90.0", True, float("nan"), float("inf"), -1.0):
            with self.subTest(invalid_value=invalid_value):
                run = copy.deepcopy(valid_run)
                run["best_heuristic_distance_with_exit_m"] = invalid_value
                self.assertEqual(get_history_objective_summary(run), {})

    def test_aggregation_uses_exit_distance_and_excludes_legacy(self):
        runs = [
            self._modern_run(
                "B1",
                {
                    "Baseline": 100.0,
                    "Grouped Aisle": 80.0,
                    "Greedy Nearest": 70.0,
                    "End Aware": 90.0,
                    "Physical Aisle - Distance Optimum": 95.0,
                    "Physical Aisle - Operational Optimum": 96.0,
                },
            ),
            self._modern_run(
                "B2",
                {
                    "Baseline": 200.0,
                    "Grouped Aisle": 150.0,
                    "Greedy Nearest": 160.0,
                    "End Aware": 170.0,
                    "Physical Aisle - Distance Optimum": 180.0,
                    "Physical Aisle - Operational Optimum": 190.0,
                },
            ),
            self._modern_run(
                "B3",
                {
                    "Baseline": 300.0,
                    "Grouped Aisle": 210.0,
                    "Greedy Nearest": 220.0,
                    "End Aware": 230.0,
                    "Physical Aisle - Distance Optimum": 240.0,
                    "Physical Aisle - Operational Optimum": 250.0,
                },
            ),
            {
                "batch_id": "LEGACY",
                "optimizer_version": "v0.1",
                "baseline_distance_m": 1.0,
                "greedy_distance_m": 0.0,
                "best_distance_method": "Greedy Nearest",
            },
        ]

        comparable_runs = get_comparable_history_runs(runs)
        summaries = [get_history_objective_summary(run) for run in comparable_runs]
        differences_m = [
            summary["baseline_distance_with_exit_m"]
            - summary["best_heuristic_distance_with_exit_m"]
            for summary in summaries
        ]
        method_counts = {}
        for summary in summaries:
            method = summary["best_heuristic_method"]
            method_counts[method] = method_counts.get(method, 0) + 1

        self.assertEqual(len(comparable_runs), 3)
        self.assertEqual(differences_m, [30.0, 50.0, 90.0])
        self.assertAlmostEqual(statistics.mean(differences_m), 56.666666666)
        self.assertEqual(statistics.median(differences_m), 50.0)
        self.assertEqual(method_counts, {"Greedy Nearest": 1, "Grouped Aisle": 2})

    def test_simulation_and_historical_sources_remain_separate(self):
        save_benchmark_run(
            self.temp_history_path,
            {
                "batch_id": "BATCH-HIST-1",
                "optimizer_version": OPTIMIZER_VERSION,
                "source": "historical",
            },
        )
        save_benchmark_run(
            self.temp_history_path,
            {
                "batch_id": "BATCH-SIM-1",
                "optimizer_version": OPTIMIZER_VERSION,
                "source": "simulation",
            },
        )

        runs = list(load_benchmark_history(self.temp_history_path).values())
        historical_runs = [run for run in runs if run["source"] == "historical"]
        simulation_runs = [run for run in runs if run["source"] == "simulation"]
        self.assertEqual([run["batch_id"] for run in historical_runs], ["BATCH-HIST-1"])
        self.assertEqual([run["batch_id"] for run in simulation_runs], ["BATCH-SIM-1"])


if __name__ == "__main__":
    unittest.main()
