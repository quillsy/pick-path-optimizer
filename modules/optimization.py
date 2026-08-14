import itertools
from typing import List, Tuple, Dict
from modules.warehouse import Warehouse
from modules.picks import Pick
from modules.routing import calculate_distance, calculate_route_metrics, RouteMetrics, calculate_distance_with_type

class OptimizationResult:
    def __init__(self, method_name: str, route: List[Pick], metrics: RouteMetrics, is_valid: bool = True):
        self.method_name = method_name
        self.route = route
        self.metrics = metrics
        self.is_valid = is_valid


def validate_optimized_route(original_route: List[Pick], optimized_route: List[Pick]) -> bool:
    """
    Validates optimized route against hard constraints:
    1. Pick counts must be unchanged.
    2. All original pick codes must be present (correct duplicate count).
    3. First pick must remain unchanged.
    """
    if len(original_route) != len(optimized_route):
        return False
        
    if not original_route or not optimized_route:
        return False
        
    if original_route[0].raw_code != optimized_route[0].raw_code:
        return False
        
    # Count occurrences of each pick code
    orig_counts = {}
    for p in original_route:
        orig_counts[p.raw_code] = orig_counts.get(p.raw_code, 0) + 1
        
    opt_counts = {}
    for p in optimized_route:
        opt_counts[p.raw_code] = opt_counts.get(p.raw_code, 0) + 1
        
    if orig_counts != opt_counts:
        return False
        
    return True


def calculate_backtracking_distance(route: List[Pick]) -> float:
    """
    Calculates the total backtracking distance in meters.
    Backtracking occurs when the picker reverses direction within the same physical aisle.
    Calculated as sum(walk_distance - span) for each aisle.
    """
    # Group coordinates by physical aisle ID
    aisle_visits: Dict[int, List[float]] = {}
    for p in route:
        if p.physical_aisle_id is not None and p.physical_aisle_id > 0:
            if p.physical_aisle_id not in aisle_visits:
                aisle_visits[p.physical_aisle_id] = []
            aisle_visits[p.physical_aisle_id].append(p.y)
            
    total_backtracking = 0.0
    for a_id, y_coords in aisle_visits.items():
        if len(y_coords) <= 1:
            continue
        # Total distance walked in this aisle
        walk_dist = sum(abs(y_coords[i+1] - y_coords[i]) for i in range(len(y_coords) - 1))
        # Span of the picks in this aisle
        span = max(y_coords) - min(y_coords)
        
        backtracking = walk_dist - span
        if backtracking > 0.0:
            total_backtracking += backtracking
            
    return total_backtracking


class BaselineOptimizer:
    def optimize(self, picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
        """Returns the picks in their original order (no optimization)."""
        return list(picks)


class GroupedAisleOptimizer:
    def optimize(self, picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
        """
        Groups remaining picks by physical aisle.
        Traverses aisles greedily, choosing the aisle group that minimizes distance to enter.
        Within each aisle, tests ascending vs. descending row sorting, choosing the direction
        closer to the current picker position.
        """
        if len(picks) <= 2:
            return list(picks)
            
        start_pick = picks[0]
        remaining = list(picks[1:])
        
        # Group remaining picks by physical aisle ID
        aisle_groups: Dict[int, List[Pick]] = {}
        for p in remaining:
            a_id = p.physical_aisle_id if p.physical_aisle_id is not None else 0
            if a_id not in aisle_groups:
                aisle_groups[a_id] = []
            aisle_groups[a_id].append(p)
            
        optimized = [start_pick]
        current_pos = start_pick
        
        while aisle_groups:
            best_aisle_id = None
            best_distance = float('inf')
            best_sorted_group = []
            
            # Find the best aisle group to visit next
            for a_id, group_picks in aisle_groups.items():
                # Test ascending order
                picks_asc = sorted(group_picks, key=lambda p: p.row)
                dist_asc = calculate_distance(current_pos, picks_asc[0], warehouse)
                
                # Test descending order
                picks_desc = list(reversed(picks_asc))
                dist_desc = calculate_distance(current_pos, picks_desc[0], warehouse)
                
                # Pick the order that minimizes entrance distance
                if dist_asc <= dist_desc:
                    cand_group = picks_asc
                    cand_dist = dist_asc
                else:
                    cand_group = picks_desc
                    cand_dist = dist_desc
                    
                if cand_dist < best_distance:
                    best_distance = cand_dist
                    best_aisle_id = a_id
                    best_sorted_group = cand_group
                    
            # Append the chosen group
            optimized.extend(best_sorted_group)
            current_pos = best_sorted_group[-1]
            del aisle_groups[best_aisle_id]
            
        return optimized


class GreedyNearestOptimizer:
    def optimize(self, picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
        """
        Greedily builds the route by choosing the next nearest pick
        using the network distance function.
        """
        if len(picks) <= 2:
            return list(picks)
            
        start_pick = picks[0]
        remaining = list(picks[1:])
        
        optimized = [start_pick]
        while remaining:
            current_pick = optimized[-1]
            best_idx = 0
            best_distance = float('inf')
            
            for idx, p in enumerate(remaining):
                dist = calculate_distance(current_pick, p, warehouse)
                if dist < best_distance:
                    best_distance = dist
                    best_idx = idx
                    
            optimized.append(remaining[best_idx])
            remaining.pop(best_idx)
            
        return optimized


class EndAwareOptimizer:
    def optimize(self, picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
        """
        Identifies and separates picks in Aisle 9 (side 20).
        Optimizes other picks using GroupedAisleOptimizer logic.
        Appends Aisle 9 picks sorted descendingly by row at the end
        to finish the route heading towards the exit (row 001).
        """
        if len(picks) <= 2:
            return list(picks)
            
        start_pick = picks[0]
        remaining = list(picks[1:])
        
        # Separate Gang 20 picks
        aisle_9_picks = [p for p in remaining if p.physical_aisle_id == 9]
        other_picks = [p for p in remaining if p.physical_aisle_id != 9]
        
        if not aisle_9_picks:
            # Fall back to GroupedAisleOptimizer if no Gang 20 picks exist
            return GroupedAisleOptimizer().optimize(picks, warehouse)
            
        # Optimize non-Gang-20 picks using GroupedAisle logic
        # We simulate this by optimizing [start_pick] + other_picks
        grouped_optimizer = GroupedAisleOptimizer()
        optimized_other = grouped_optimizer.optimize([start_pick] + other_picks, warehouse)
        
        # Sort Gang 20 picks descending (high rows -> low rows)
        sorted_aisle_9 = sorted(aisle_9_picks, key=lambda p: p.row, reverse=True)
        
        # Combine
        return optimized_other + sorted_aisle_9


class PhysicalAisleOptimizer:
    def __init__(self, mode: str = "distance"):
        self.mode = mode

    def optimize(self, picks: List[Pick], warehouse: Warehouse) -> List[Pick]:
        """
        Enumerates all 2^K combinations of direction choices for the physical aisles.
        Filters and evaluates candidate routes:
        - Distance mode: Minimizes only total walking distance (picks-to-picks).
        - Operational mode: Minimizes total distance including exit return to 20.001,
                            penalizing backtracking and direction changes.
        """
        if len(picks) <= 2:
            return list(picks)
            
        start_pick = picks[0]
        remaining = list(picks[1:])
        
        # Identify unique physical aisles in the batch
        unique_aisles = sorted(list(set(p.physical_aisle_id for p in picks if p.physical_aisle_id is not None)))
        start_aisle = start_pick.physical_aisle_id if start_pick.physical_aisle_id is not None else 0
        
        # Sort remaining aisles by Aisle ID (natural S-Shape sweep layout)
        # If Aisle 9 is present, it is forced to the end of the sweep sequence.
        other_aisles = [a for a in unique_aisles if a != start_aisle and a != 9]
        
        aisle_sequence = [start_aisle] + other_aisles
        if 9 in unique_aisles and start_aisle != 9:
            aisle_sequence.append(9)
            
        # Group remaining picks by aisle ID
        groups: Dict[int, List[Pick]] = {}
        for p in remaining:
            a_id = p.physical_aisle_id if p.physical_aisle_id is not None else 0
            if a_id not in groups:
                groups[a_id] = []
            groups[a_id].append(p)
            
        # Generate direction combinations (UP = 0, DOWN = 1) for each aisle.
        # If Aisle 9 is present, force its direction to DOWN (1) to exit towards row 001.
        ranges = []
        for a_id in aisle_sequence:
            if a_id == 9 and start_aisle != 9:
                ranges.append([1])  # Forced to DOWN
            else:
                ranges.append([0, 1])
                
        best_route = []
        best_score = float('inf')
        exit_pick = Pick("20.001.01", warehouse)
        
        # Enumeration of direction states
        for comb in itertools.product(*ranges):
            candidate = [start_pick]
            
            for idx, a_id in enumerate(aisle_sequence):
                direction = comb[idx]
                aisle_picks = groups.get(a_id, [])
                if not aisle_picks:
                    continue
                    
                sorted_picks = sorted(aisle_picks, key=lambda p: p.row)
                if direction == 1:
                    sorted_picks = list(reversed(sorted_picks))
                    
                candidate.extend(sorted_picks)
                
            if not validate_optimized_route(picks, candidate):
                continue
                
            # Calculate distance
            dist = 0.0
            for i in range(len(candidate) - 1):
                dist += calculate_distance(candidate[i], candidate[i+1], warehouse)
                
            dist_to_exit = calculate_distance(candidate[-1], exit_pick, warehouse)
            dist_with_exit = dist + dist_to_exit
            
            backtracking = calculate_backtracking_distance(candidate)
            
            # Count direction changes
            dir_changes = 0
            last_dir = None
            for i in range(len(candidate) - 1):
                p_a, p_b = candidate[i], candidate[i+1]
                if (p_a.physical_aisle_id == p_b.physical_aisle_id and 
                        p_a.physical_aisle_id is not None and 
                        p_a.physical_aisle_id > 0):
                    if p_b.y != p_a.y:
                        curr_dir = 1 if p_b.y > p_a.y else -1
                        if last_dir is not None and curr_dir != last_dir:
                            dir_changes += 1
                        last_dir = curr_dir
                else:
                    last_dir = None
                    
            # Check repeated aisle visits
            blocks = []
            for p in candidate:
                a_id = p.physical_aisle_id if p.physical_aisle_id is not None else -1
                if not blocks or blocks[-1] != a_id:
                    blocks.append(a_id)
            counts = {}
            for a_id in blocks:
                if a_id > 0:
                    counts[a_id] = counts.get(a_id, 0) + 1
            repeated_visits = sum(c - 1 for c in counts.values() if c > 1)
            
            # Evaluate objective scores
            if self.mode == "distance":
                score = dist
            else:
                # Operational: Penalize backtracking, repeated visits, and direction changes
                score = dist_with_exit + (1000.0 * backtracking) + (100.0 * repeated_visits) + (5.0 * dir_changes)
                
            if score < best_score:
                best_score = score
                best_route = candidate
                
        return best_route if best_route else list(picks)


class PhysicalAisleDistanceOptimizer(PhysicalAisleOptimizer):
    def __init__(self):
        super().__init__(mode="distance")


class PhysicalAisleOperationalOptimizer(PhysicalAisleOptimizer):
    def __init__(self):
        super().__init__(mode="operational")
