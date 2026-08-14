from typing import List, Tuple, Optional, Dict
from modules.warehouse import Warehouse
from modules.picks import Pick

class RouteSegment:
    def __init__(self, start_pick: Pick, end_pick: Pick, distance_m: float, chosen_path_type: str):
        self.start_pick = start_pick
        self.end_pick = end_pick
        self.distance_m = distance_m
        self.chosen_path_type = chosen_path_type  # "same_aisle" | "via_001" | "via_middle" | "via_084"

    def __repr__(self) -> str:
        return f"RouteSegment({self.start_pick.raw_code} -> {self.end_pick.raw_code}: {self.distance_m:.2f}m via {self.chosen_path_type})"


class RouteMetrics:
    def __init__(self, route: List[Pick], segments: List[RouteSegment], total_distance_m: float, physical_aisles_visited: int, warehouse: Optional[Warehouse] = None):
        self.route = route
        self.segments = segments
        self.total_distance_m = total_distance_m
        self.pick_count = len(route)
        self.physical_aisles_visited = physical_aisles_visited
        
        # Calculate min, max, average segment distances
        segment_dists = [s.distance_m for s in segments]
        self.longest_segment_m = max(segment_dists) if segment_dists else 0.0
        self.shortest_segment_m = min(segment_dists) if segment_dists else 0.0
        self.average_segment_m = (sum(segment_dists) / len(segment_dists)) if segment_dists else 0.0

        # New metrics
        self.max_single_aisle_traversal_m = 0.0
        self.repeated_aisle_visit_count = 0
        self.end_distance_to_20_001_m = 0.0
        
        if route:
            # 1. Max single aisle traversal
            aisle_y: Dict[int, List[float]] = {}
            for p in route:
                if p.physical_aisle_id is not None and p.physical_aisle_id > 0:
                    if p.physical_aisle_id not in aisle_y:
                        aisle_y[p.physical_aisle_id] = []
                    aisle_y[p.physical_aisle_id].append(p.y)
            for a_id, y_coords in aisle_y.items():
                if len(y_coords) > 1:
                    walk_dist = sum(abs(y_coords[i+1] - y_coords[i]) for i in range(len(y_coords) - 1))
                    self.max_single_aisle_traversal_m = max(self.max_single_aisle_traversal_m, walk_dist)
                    
            # 2. Repeated aisle visit count
            blocks = []
            for p in route:
                a_id = p.physical_aisle_id if p.physical_aisle_id is not None else -1
                if not blocks or blocks[-1] != a_id:
                    blocks.append(a_id)
            counts = {}
            for a_id in blocks:
                if a_id > 0:
                    counts[a_id] = counts.get(a_id, 0) + 1
            self.repeated_aisle_visit_count = sum(c - 1 for c in counts.values() if c > 1)
            
            # 3. End distance to exit 20.001
            if warehouse:
                exit_pick = Pick("20.001.01", warehouse)
                self.end_distance_to_20_001_m = calculate_distance(route[-1], exit_pick, warehouse)

    def __repr__(self) -> str:
        return f"RouteMetrics(Total: {self.total_distance_m:.2f}m, Picks: {self.pick_count}, Aisles: {self.physical_aisles_visited})"


def calculate_distance_with_type(pick_a: Pick, pick_b: Pick, warehouse: Warehouse) -> Tuple[float, str]:
    """
    Calculates the shortest walking distance between two picks in the warehouse.
    Picker moves along physical walkways and cross-aisles. Diagonal movements through shelves are forbidden.
    Transitions are only possible at:
    - Eingang/Endbereich bei Reihe 001 (y = 0.0)
    - Mittel-/Quergang zwischen Reihe 042 und 043 (y_mittelgang)
    - Ausgang/Endbereich bei Reihe 084 (y_ausgang_084)
    
    If the picks are in the same physical aisle, the distance is simply the 1D y-distance.
    """
    # If in same physical aisle and it's not the cart (id=0), walk straight
    if (pick_a.physical_aisle_id == pick_b.physical_aisle_id and 
            pick_a.physical_aisle_id is not None and 
            pick_a.physical_aisle_id != 0):
        return abs(pick_a.y - pick_b.y), "same_aisle"
    
    # Otherwise, must transition through a corridor
    x_dist = abs(pick_a.x - pick_b.x)
    
    # Define corridor y-coordinates
    y_eingang_001 = 0.0
    
    shelf_len = warehouse.geometry.shelf_length_m
    first_section_end = warehouse.rows_config["first_section_end"]
    cross_width = warehouse.geometry.cross_aisle_width_m
    
    # Center of the middle cross-aisle (Mittel-/Quergang)
    y_mittelgang = (first_section_end * shelf_len) + (cross_width / 2.0)
    
    total_rows = warehouse.rows_config["end"] - warehouse.rows_config["start"] + 1
    y_ausgang_084 = (total_rows * shelf_len) + cross_width
    
    # Route via Eingang (Reihe 001)
    dist_eingang = abs(pick_a.y - y_eingang_001) + x_dist + abs(pick_b.y - y_eingang_001)
    
    # Route via Mittelgang (between 42 and 43)
    dist_mittelgang = abs(pick_a.y - y_mittelgang) + x_dist + abs(pick_b.y - y_mittelgang)
    
    # Route via Ausgang (Reihe 084)
    dist_ausgang = abs(pick_a.y - y_ausgang_084) + x_dist + abs(pick_b.y - y_ausgang_084)
    
    min_dist = min(dist_eingang, dist_mittelgang, dist_ausgang)
    
    if min_dist == dist_eingang:
        path_type = "via_001"
    elif min_dist == dist_mittelgang:
        path_type = "via_middle"
    else:
        path_type = "via_084"
        
    return min_dist, path_type


def calculate_distance(pick_a: Pick, pick_b: Pick, warehouse: Warehouse) -> float:
    """Backwards compatible distance check."""
    dist, _ = calculate_distance_with_type(pick_a, pick_b, warehouse)
    return dist


def calculate_route_distance(route: List[Pick], warehouse: Warehouse) -> float:
    """Calculates the total walking distance for a given route sequence."""
    if len(route) <= 1:
        return 0.0
    
    total_dist = 0.0
    for i in range(len(route) - 1):
        total_dist += calculate_distance(route[i], route[i+1], warehouse)
    return total_dist


def calculate_route_metrics(route: List[Pick], warehouse: Warehouse) -> RouteMetrics:
    """Calculates and packs comprehensive baseline statistics for a route sequence."""
    if not route:
        return RouteMetrics([], [], 0.0, 0)
        
    segments = []
    total_distance_m = 0.0
    for i in range(len(route) - 1):
        dist, path_type = calculate_distance_with_type(route[i], route[i+1], warehouse)
        segments.append(RouteSegment(route[i], route[i+1], dist, path_type))
        total_distance_m += dist
        
    physical_aisles_visited = len(set(p.physical_aisle_id for p in route if p.physical_aisle_id is not None))
    
    return RouteMetrics(route, segments, total_distance_m, physical_aisles_visited, warehouse)


def get_original_route(picks: List[Pick]) -> List[Pick]:
    """Returns the picks in their original order (as they appear in the batch)."""
    return list(picks)


def get_simple_sorted_route(picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
    """
    A simple routing heuristic (provisional test / placeholder only):
    - The first pick in the batch MUST remain the first pick (the start).
    - The remaining picks are grouped and sorted by aisle.
    - S-Shape behavior (provisional placeholder, not the final optimization logic): 
      - We group remaining picks by physical aisle.
      - Sort the aisles.
      - Within each aisle, sort rows:
        - Ascending for odd aisle indices
        - Descending for even aisle indices
    This minimizes backtracking across aisles for testing purposes.
    """
    if not picks:
        return []
    if len(picks) <= 2:
        return list(picks)
    
    start_pick = picks[0]
    remaining = list(picks[1:])
    
    # Group remaining by physical aisle ID
    aisle_groups = {}
    for pick in remaining:
        a_id = pick.physical_aisle_id if pick.physical_aisle_id is not None else 999
        if a_id not in aisle_groups:
            aisle_groups[a_id] = []
        aisle_groups[a_id].append(pick)
        
    sorted_remaining = []
    # Sort aisle IDs
    sorted_aisles = sorted(aisle_groups.keys())
    
    for a_id in sorted_aisles:
        aisle_picks = aisle_groups[a_id]
        if a_id % 2 == 1:
            aisle_picks.sort(key=lambda p: p.row)
        else:
            aisle_picks.sort(key=lambda p: p.row, reverse=True)
            
        sorted_remaining.extend(aisle_picks)
        
    return [start_pick] + sorted_remaining
