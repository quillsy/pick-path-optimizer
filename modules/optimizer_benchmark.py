import os
import json
import math
from datetime import datetime
from numbers import Real
from typing import List, Dict, Any
from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.routing import calculate_route_metrics, calculate_distance
from modules.optimization import (
    validate_optimized_route,
    calculate_backtracking_distance,
    BaselineOptimizer,
    GroupedAisleOptimizer,
    GreedyNearestOptimizer,
    EndAwareOptimizer,
    PhysicalAisleDistanceOptimizer,
    PhysicalAisleOperationalOptimizer
)

OPTIMIZER_VERSION = "v0.2"
OBJECTIVE_DISTANCE_KEY = "distance_with_exit_m"
HISTORY_OBJECTIVE_FIELDS = {
    "Baseline": "baseline_distance_with_exit_m",
    "Grouped Aisle": "grouped_aisle_distance_with_exit_m",
    "Greedy Nearest": "greedy_distance_with_exit_m",
    "End Aware": "end_aware_distance_with_exit_m",
    "Physical Aisle - Distance Optimum": "physical_distance_optimum_with_exit_m",
    "Physical Aisle - Operational Optimum": "physical_operational_optimum_with_exit_m",
}
HISTORY_SUMMARY_FIELDS = (
    "best_heuristic_method",
    "best_heuristic_distance_with_exit_m",
    "baseline_distance_with_exit_m",
    "heuristic_improves_baseline",
    "best_overall_method",
)


def is_valid_objective_value(value: Any) -> bool:
    """Returns whether a persisted objective distance is a finite non-negative number."""
    if not isinstance(value, Real) or isinstance(value, bool) or value < 0:
        return False
    if isinstance(value, int):
        return True
    try:
        return math.isfinite(value)
    except (TypeError, ValueError, OverflowError):
        return False


def select_best_result(results: List[Dict[str, Any]], exclude_baseline: bool = False) -> Dict[str, Any]:
    """Returns the valid result with the shortest route including the exit at 20.001."""
    candidates = [
        result for result in results
        if result.get("is_valid", False)
        and is_valid_objective_value(result.get(OBJECTIVE_DISTANCE_KEY))
        and (not exclude_baseline or result.get("method_name") != "Baseline")
    ]
    if not candidates:
        raise ValueError("No valid benchmark result available.")
    return min(candidates, key=lambda result: result[OBJECTIVE_DISTANCE_KEY])


def summarize_benchmark_results(results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Builds the binding baseline, heuristic and overall winner semantics."""
    baseline_results = [
        result for result in results
        if result.get("method_name") == "Baseline"
        and result.get("is_valid", False)
        and is_valid_objective_value(result.get(OBJECTIVE_DISTANCE_KEY))
    ]
    if len(baseline_results) != 1:
        raise ValueError("Exactly one valid Baseline result is required.")

    baseline_result = baseline_results[0]
    best_heuristic = select_best_result(results, exclude_baseline=True)
    baseline_distance = baseline_result[OBJECTIVE_DISTANCE_KEY]
    best_heuristic_distance = best_heuristic[OBJECTIVE_DISTANCE_KEY]
    heuristic_improves_baseline = best_heuristic_distance < baseline_distance

    return {
        "best_heuristic_method": best_heuristic["method_name"],
        "best_heuristic_distance_with_exit_m": best_heuristic_distance,
        "baseline_distance_with_exit_m": baseline_distance,
        "heuristic_improves_baseline": heuristic_improves_baseline,
        "best_overall_method": (
            best_heuristic["method_name"] if heuristic_improves_baseline else "Baseline"
        ),
    }


def summarize_objective_distances(distances: Dict[str, float]) -> Dict[str, Any]:
    """Builds winner semantics from validated persisted objective distances."""
    baseline_distance = distances["Baseline"]
    heuristic_distances = {
        method: distance for method, distance in distances.items()
        if method != "Baseline"
    }
    best_heuristic_method = min(heuristic_distances, key=heuristic_distances.get)
    best_heuristic_distance = heuristic_distances[best_heuristic_method]
    heuristic_improves_baseline = best_heuristic_distance < baseline_distance

    return {
        "best_heuristic_method": best_heuristic_method,
        "best_heuristic_distance_with_exit_m": best_heuristic_distance,
        "baseline_distance_with_exit_m": baseline_distance,
        "heuristic_improves_baseline": heuristic_improves_baseline,
        "best_overall_method": (
            best_heuristic_method if heuristic_improves_baseline else "Baseline"
        ),
    }


def get_history_objective_summary(run: Dict[str, Any]) -> Dict[str, Any]:
    """Returns a validated modern history summary, or an empty dict for legacy data."""
    if run.get("optimizer_version") != OPTIMIZER_VERSION:
        return {}
    if not all(field in run for field in HISTORY_OBJECTIVE_FIELDS.values()):
        return {}
    if not all(field in run for field in HISTORY_SUMMARY_FIELDS):
        return {}

    distances = {
        method_name: run[field]
        for method_name, field in HISTORY_OBJECTIVE_FIELDS.items()
    }
    if not all(is_valid_objective_value(value) for value in distances.values()):
        return {}

    expected_summary = summarize_objective_distances(distances)
    if not is_valid_objective_value(run["best_heuristic_distance_with_exit_m"]):
        return {}
    if not isinstance(run["heuristic_improves_baseline"], bool):
        return {}
    for field in HISTORY_SUMMARY_FIELDS:
        if run[field] != expected_summary[field]:
            return {}

    return {**expected_summary, "distances": distances}


def get_history_objective_distances(run: Dict[str, Any]) -> Dict[str, float]:
    """Returns validated comparable distances, or an empty dict for legacy data."""
    summary = get_history_objective_summary(run)
    return summary.get("distances", {})


def get_comparable_history_runs(runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters history records to fully validated modern objective records."""
    return [run for run in runs if get_history_objective_summary(run)]


def calculate_direction_changes(route: List[Pick]) -> int:
    """Calculates the number of direction changes within the same physical aisles."""
    changes = 0
    last_dir = None
    for i in range(len(route) - 1):
        p_a, p_b = route[i], route[i+1]
        if (p_a.physical_aisle_id == p_b.physical_aisle_id and 
                p_a.physical_aisle_id is not None and 
                p_a.physical_aisle_id > 0):
            if p_b.y != p_a.y:
                curr_dir = 1 if p_b.y > p_a.y else -1
                if last_dir is not None and curr_dir != last_dir:
                    changes += 1
                last_dir = curr_dir
        else:
            last_dir = None
    return changes


def calculate_operational_score(run: Dict[str, Any]) -> float:
    """Computes a penalty-based operational score to prioritize good logistics."""
    backtracking = run.get("estimated_backtracking_distance_m", 0.0)
    repeated = run.get("repeated_aisle_visit_count", 0)
    dir_changes = run.get("direction_changes", 0)
    dist_exit = run.get("distance_with_exit_m", 0.0)
    
    # 0 backtracking is heavily favored, then 0 repeated aisle visits, then direction changes, then distance
    score = dist_exit + (1000.0 * backtracking) + (100.0 * repeated) + (5.0 * dir_changes)
    return score


def load_benchmark_history(file_path: str) -> Dict[str, Dict[str, Any]]:
    """Loads the benchmark history database."""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}


def save_benchmark_run(file_path: str, run_data: Dict[str, Any]) -> None:
    """Saves a benchmark run to the history file. Overwrites if batch_id and version match."""
    history = load_benchmark_history(file_path)
    
    batch_id = run_data.get("batch_id", "unknown")
    opt_version = run_data.get("optimizer_version", OPTIMIZER_VERSION)
    key = f"{batch_id}::{opt_version}"
    
    history[key] = run_data
    
    history_parent = os.path.dirname(file_path)
    if history_parent:
        os.makedirs(history_parent, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def benchmark_batch(
        picks: List[Pick], warehouse: Warehouse, batch_id: str = "custom",
        source: str = "historical", persist: bool = True,
        history_path: str = None, results_path: str = None) -> List[Dict[str, Any]]:
    """
    Runs all 6 optimizers on the batch and calculates complete metrics.
    Persists results only when ``persist`` is true. Custom paths keep tests and
    other isolated callers away from the production files under ``data/``.
    """
    if (history_path is None) != (results_path is None):
        raise ValueError(
            "history_path and results_path must either both be provided or both be omitted."
        )

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if history_path is None and results_path is None:
        history_path = os.path.join(base_dir, "data", "benchmark_history.json")
        results_path = os.path.join(base_dir, "data", "benchmark_results.json")

    optimizers = {
        "Baseline": BaselineOptimizer(),
        "Grouped Aisle": GroupedAisleOptimizer(),
        "Greedy Nearest": GreedyNearestOptimizer(),
        "End Aware": EndAwareOptimizer(),
        "Physical Aisle - Distance Optimum": PhysicalAisleDistanceOptimizer(),
        "Physical Aisle - Operational Optimum": PhysicalAisleOperationalOptimizer()
    }
    
    results = []
    for name, opt in optimizers.items():
        optimized_route = opt.optimize(picks, warehouse)
        is_valid = validate_optimized_route(picks, optimized_route)
        
        # Calculate standard metrics
        metrics = calculate_route_metrics(optimized_route, warehouse)
        
        # Calculate transition corridor counts
        via_001_count = sum(1 for s in metrics.segments if s.chosen_path_type == "via_001")
        via_middle_count = sum(1 for s in metrics.segments if s.chosen_path_type == "via_middle")
        via_084_count = sum(1 for s in metrics.segments if s.chosen_path_type == "via_084")
        
        # Calculate backtracking
        backtracking = calculate_backtracking_distance(optimized_route)
        
        # Calculate direction changes
        dir_changes = calculate_direction_changes(optimized_route)
        
        results.append({
            "method_name": name,
            "is_valid": is_valid,
            "total_distance_m": round(metrics.total_distance_m, 2),
            "distance_with_exit_m": round(metrics.total_distance_m + metrics.end_distance_to_20_001_m, 2),
            "pick_count": metrics.pick_count,
            "physical_aisles_visited": metrics.physical_aisles_visited,
            "longest_segment_m": round(metrics.longest_segment_m, 2),
            "shortest_segment_m": round(metrics.shortest_segment_m, 2),
            "average_segment_m": round(metrics.average_segment_m, 2),
            "via_001_count": via_001_count,
            "via_middle_count": via_middle_count,
            "via_084_count": via_084_count,
            "direction_changes": dir_changes,
            "estimated_backtracking_distance_m": round(backtracking, 2),
            "max_single_aisle_traversal_m": round(metrics.max_single_aisle_traversal_m, 2),
            "repeated_aisle_visit_count": metrics.repeated_aisle_visit_count,
            "end_distance_to_20_001_m": round(metrics.end_distance_to_20_001_m, 2),
            "start_pick": optimized_route[0].raw_code if optimized_route else "",
            "end_pick": optimized_route[-1].raw_code if optimized_route else "",
            "route_codes": [p.raw_code for p in optimized_route]
        })
        
    winner_summary = summarize_benchmark_results(results)
    
    # Calculate density profile
    aisle_density = {}
    for a_id in range(10): # 0 is cart, 1 to 9 are aisles
        aisle_density[str(a_id)] = sum(1 for p in picks if p.physical_aisle_id == a_id)
        
    run_record = {
        "batch_id": batch_id,
        "timestamp": datetime.now().isoformat(),
        "optimizer_version": OPTIMIZER_VERSION,
        "pick_count": len(picks),
        "source": source,
        
        "baseline_distance_m": next(r["total_distance_m"] for r in results if r["method_name"] == "Baseline"),
        "grouped_aisle_distance_m": next(r["total_distance_m"] for r in results if r["method_name"] == "Grouped Aisle"),
        "greedy_distance_m": next(r["total_distance_m"] for r in results if r["method_name"] == "Greedy Nearest"),
        "end_aware_distance_m": next(r["total_distance_m"] for r in results if r["method_name"] == "End Aware"),
        "physical_distance_optimum_m": next(r["total_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Distance Optimum"),
        "physical_operational_optimum_m": next(r["total_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Operational Optimum"),

        "baseline_distance_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "Baseline"),
        "grouped_aisle_distance_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "Grouped Aisle"),
        "greedy_distance_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "Greedy Nearest"),
        "end_aware_distance_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "End Aware"),
        "physical_distance_optimum_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "Physical Aisle - Distance Optimum"),
        "physical_operational_optimum_with_exit_m": next(r[OBJECTIVE_DISTANCE_KEY] for r in results if r["method_name"] == "Physical Aisle - Operational Optimum"),
        
        "baseline_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Baseline"),
        "grouped_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Grouped Aisle"),
        "greedy_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Greedy Nearest"),
        "end_aware_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "End Aware"),
        "physical_distance_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Distance Optimum"),
        "physical_operational_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Operational Optimum"),
        
        **winner_summary,

        # Compatibility fields retained for existing readers.
        "best_distance_method": winner_summary["best_overall_method"],
        "best_operational_method": winner_summary["best_overall_method"],
        
        "batch_profile": {
            "physical_aisles_visited": len(set(p.physical_aisle_id for p in picks if p.physical_aisle_id is not None)),
            "sides_visited": len(set(p.side for p in picks)),
            "min_row": min(p.row for p in picks) if picks else 0,
            "max_row": max(p.row for p in picks) if picks else 0,
            "aisle_density": aisle_density
        }
    }
    
    if not persist:
        return results

    save_benchmark_run(history_path, run_record)

    # Also save comparison cache for the UI run page
    existing_data = {}
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            pass
            
    results_key = f"{batch_id}::{OPTIMIZER_VERSION}"
    existing_data[results_key] = {
        "batch_id": batch_id,
        "optimizer_version": OPTIMIZER_VERSION,
        **winner_summary,
        "runs": [
            {
                "method_name": r["method_name"],
                "total_distance_m": r["total_distance_m"],
                "distance_with_exit_m": r["distance_with_exit_m"],
                "estimated_backtracking_distance_m": r["estimated_backtracking_distance_m"],
                "via_middle_count": r["via_middle_count"],
                "repeated_aisle_visit_count": r["repeated_aisle_visit_count"],
                "end_distance_to_20_001_m": r["end_distance_to_20_001_m"]
            }
            for r in results
        ]
    }
    
    results_parent = os.path.dirname(results_path)
    if results_parent:
        os.makedirs(results_parent, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
    return results
