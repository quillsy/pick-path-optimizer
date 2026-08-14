import os
import json
from datetime import datetime
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

OPTIMIZER_VERSION = "v0.1"

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
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


def benchmark_batch(picks: List[Pick], warehouse: Warehouse, batch_id: str = "custom", source: str = "historical") -> List[Dict[str, Any]]:
    """
    Runs all 6 optimizers on the batch and calculates complete metrics.
    Saves results to data/benchmark_results.json and the run to data/benchmark_history.json.
    """
    optimizers = {
        "Baseline": BaselineOptimizer(),
        "Grouped Aisle": GroupedAisleOptimizer(),
        "Greedy Nearest": GreedyNearestOptimizer(),
        "End Aware": EndAwareOptimizer(),
        "Physical Aisle - Distance Optimum": PhysicalAisleDistanceOptimizer(),
        "Physical Aisle - Operational Optimum": PhysicalAisleOperationalOptimizer()
    }
    
    results = []
    exit_pick = Pick("20.001.01", warehouse)
    
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
        
    # Determine best methods
    best_dist = float('inf')
    best_dist_name = ""
    for r in results:
        if r["is_valid"] and r["total_distance_m"] < best_dist:
            best_dist = r["total_distance_m"]
            best_dist_name = r["method_name"]
            
    best_op_score = float('inf')
    best_op_name = ""
    for r in results:
        if r["is_valid"]:
            score = calculate_operational_score(r)
            if score < best_op_score:
                best_op_score = score
                best_op_name = r["method_name"]
                
    # Build history record
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    history_path = os.path.join(base_dir, "data", "benchmark_history.json")
    
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
        
        "baseline_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Baseline"),
        "grouped_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Grouped Aisle"),
        "greedy_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Greedy Nearest"),
        "end_aware_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "End Aware"),
        "physical_distance_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Distance Optimum"),
        "physical_operational_backtracking_m": next(r["estimated_backtracking_distance_m"] for r in results if r["method_name"] == "Physical Aisle - Operational Optimum"),
        
        "best_distance_method": best_dist_name,
        "best_operational_method": best_op_name,
        
        "batch_profile": {
            "physical_aisles_visited": len(set(p.physical_aisle_id for p in picks if p.physical_aisle_id is not None)),
            "sides_visited": len(set(p.side for p in picks)),
            "min_row": min(p.row for p in picks) if picks else 0,
            "max_row": max(p.row for p in picks) if picks else 0,
            "aisle_density": aisle_density
        }
    }
    
    save_benchmark_run(history_path, run_record)
    
    # Also save comparison cache for the UI run page
    results_path = os.path.join(base_dir, "data", "benchmark_results.json")
    existing_data = {}
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except json.JSONDecodeError:
            pass
            
    existing_data[batch_id] = {
        "batch_id": batch_id,
        "runs": [
            {
                "method_name": r["method_name"],
                "total_distance_m": r["total_distance_m"],
                "estimated_backtracking_distance_m": r["estimated_backtracking_distance_m"],
                "via_middle_count": r["via_middle_count"],
                "repeated_aisle_visit_count": r["repeated_aisle_visit_count"],
                "end_distance_to_20_001_m": r["end_distance_to_20_001_m"]
            }
            for r in results
        ]
    }
    
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=2, ensure_ascii=False)
        
    return results
