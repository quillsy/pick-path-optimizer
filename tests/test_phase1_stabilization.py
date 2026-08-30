import ast
import hashlib
import os
import sys
import tempfile
import unittest


sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.optimizer_benchmark import (
    benchmark_batch,
    select_best_result,
    summarize_benchmark_results,
)
from modules.picks import Pick
from modules.routing import calculate_route_metrics
from modules.warehouse import Warehouse


class TestPhaseOneStabilization(unittest.TestCase):
    def setUp(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.data_dir = os.path.join(self.base_dir, "data")
        self.warehouse = Warehouse(os.path.join(self.data_dir, "warehouse.json"))
        self.picks = [
            Pick("05.056.50", self.warehouse),
            Pick("06.008.30", self.warehouse),
            Pick("20.080.10", self.warehouse),
            Pick("20.020.10", self.warehouse),
        ]

    def _data_hashes(self):
        hashes = {}
        for filename in os.listdir(self.data_dir):
            path = os.path.join(self.data_dir, filename)
            if os.path.isfile(path):
                with open(path, "rb") as file_handle:
                    hashes[filename] = hashlib.sha256(file_handle.read()).hexdigest()
        return hashes

    def test_app_imports_pick_order_and_datetime_at_module_level(self):
        app_path = os.path.join(self.base_dir, "app.py")
        with open(app_path, "r", encoding="utf-8") as file_handle:
            tree = ast.parse(file_handle.read())

        imported_names = set()
        for node in tree.body:
            if isinstance(node, ast.ImportFrom):
                imported_names.update(alias.name for alias in node.names)

        self.assertIn("PickOrder", imported_names)
        self.assertIn("datetime", imported_names)

    def test_winner_uses_distance_including_exit(self):
        results = [
            {
                "method_name": "Short picks, bad exit",
                "is_valid": True,
                "total_distance_m": 80.0,
                "distance_with_exit_m": 180.0,
            },
            {
                "method_name": "Longer picks, good exit",
                "is_valid": True,
                "total_distance_m": 100.0,
                "distance_with_exit_m": 120.0,
            },
        ]

        winner = select_best_result(results)

        self.assertEqual(winner["method_name"], "Longer picks, good exit")

    def test_no_heuristic_beats_baseline_semantics(self):
        results = [
            {"method_name": "Baseline", "is_valid": True, "distance_with_exit_m": 100.0},
            {"method_name": "Heuristic A", "is_valid": True, "distance_with_exit_m": 110.0},
            {"method_name": "Heuristic B", "is_valid": True, "distance_with_exit_m": 120.0},
        ]

        summary = summarize_benchmark_results(results)

        self.assertEqual(summary["best_heuristic_method"], "Heuristic A")
        self.assertEqual(summary["best_heuristic_distance_with_exit_m"], 110.0)
        self.assertEqual(summary["baseline_distance_with_exit_m"], 100.0)
        self.assertFalse(summary["heuristic_improves_baseline"])
        self.assertEqual(summary["best_overall_method"], "Baseline")

    def test_heuristic_beats_baseline_semantics(self):
        results = [
            {"method_name": "Baseline", "is_valid": True, "distance_with_exit_m": 100.0},
            {"method_name": "Heuristic A", "is_valid": True, "distance_with_exit_m": 90.0},
            {"method_name": "Heuristic B", "is_valid": True, "distance_with_exit_m": 80.0},
        ]

        summary = summarize_benchmark_results(results)

        self.assertEqual(summary["best_heuristic_method"], "Heuristic B")
        self.assertEqual(summary["best_heuristic_distance_with_exit_m"], 80.0)
        self.assertEqual(summary["baseline_distance_with_exit_m"], 100.0)
        self.assertTrue(summary["heuristic_improves_baseline"])
        self.assertEqual(summary["best_overall_method"], "Heuristic B")

    def test_heuristic_tie_keeps_baseline_as_overall_method(self):
        results = [
            {"method_name": "Heuristic A", "is_valid": True, "distance_with_exit_m": 100.0},
            {"method_name": "Baseline", "is_valid": True, "distance_with_exit_m": 100.0},
            {"method_name": "Heuristic B", "is_valid": True, "distance_with_exit_m": 120.0},
        ]

        summary = summarize_benchmark_results(results)

        self.assertEqual(summary["best_heuristic_method"], "Heuristic A")
        self.assertFalse(summary["heuristic_improves_baseline"])
        self.assertEqual(summary["best_overall_method"], "Baseline")

    def test_app_route_comparison_uses_persist_false(self):
        app_path = os.path.join(self.base_dir, "app.py")
        with open(app_path, "r", encoding="utf-8") as file_handle:
            tree = ast.parse(file_handle.read())

        read_only_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not isinstance(node.func, ast.Name) or node.func.id != "benchmark_batch":
                continue
            persist_keywords = [keyword for keyword in node.keywords if keyword.arg == "persist"]
            if persist_keywords:
                read_only_calls.append(
                    isinstance(persist_keywords[0].value, ast.Constant)
                    and persist_keywords[0].value.value is False
                )

        self.assertIn(True, read_only_calls)

    def test_app_uses_shared_winner_semantics_and_clear_labels(self):
        app_path = os.path.join(self.base_dir, "app.py")
        with open(app_path, "r", encoding="utf-8") as file_handle:
            source = file_handle.read()
            tree = ast.parse(source)

        shared_summary_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "summarize_benchmark_results"
        ]
        self.assertGreaterEqual(len(shared_summary_calls), 2)
        self.assertIn("Keine getestete Heuristik verbessert die Baseline.", source)
        self.assertIn("Pick-Distanz", source)
        self.assertIn("Weg zum Ausgang", source)
        self.assertIn("Gesamtdistanz inklusive Ausgang", source)
        self.assertNotIn('st.metric("Berechneter Weg"', source)

    def test_read_only_benchmark_does_not_modify_data_files(self):
        before = self._data_hashes()

        results = benchmark_batch(
            self.picks,
            self.warehouse,
            "BATCH-READ-ONLY-REGRESSION",
            persist=False,
        )

        self.assertEqual(len(results), 6)
        self.assertEqual(self._data_hashes(), before)

    def test_read_only_benchmark_does_not_modify_explicit_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = os.path.join(temp_dir, "benchmark_history.json")
            results_path = os.path.join(temp_dir, "benchmark_results.json")
            sentinels = {
                history_path: b'{"history": "unchanged"}',
                results_path: b'{"results": "unchanged"}',
            }
            for path, content in sentinels.items():
                with open(path, "wb") as file_handle:
                    file_handle.write(content)

            results = benchmark_batch(
                self.picks,
                self.warehouse,
                "BATCH-READ-ONLY-EXPLICIT",
                persist=False,
                history_path=history_path,
                results_path=results_path,
            )

            self.assertEqual(len(results), 6)
            for path, content in sentinels.items():
                with open(path, "rb") as file_handle:
                    self.assertEqual(file_handle.read(), content)

    def test_all_benchmark_results_calculate_distance_including_exit(self):
        results = benchmark_batch(
            self.picks,
            self.warehouse,
            "BATCH-OBJECTIVE-CALCULATION",
            persist=False,
        )

        for result in results:
            route = [Pick(code, self.warehouse) for code in result["route_codes"]]
            metrics = calculate_route_metrics(route, self.warehouse)
            self.assertEqual(
                result["distance_with_exit_m"],
                round(metrics.total_distance_m + metrics.end_distance_to_20_001_m, 2),
            )


if __name__ == "__main__":
    unittest.main()
