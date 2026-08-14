import json
from typing import Dict, List, Optional, Tuple

class WarehouseGeometry:
    def __init__(self, shelf_length_m: float, shelf_height_m: float, shelf_depth_m: float,
                 main_aisle_width_m: float, cross_aisle_width_m: float):
        self.shelf_length_m = shelf_length_m
        self.shelf_height_m = shelf_height_m
        self.shelf_depth_m = shelf_depth_m
        self.main_aisle_width_m = main_aisle_width_m
        self.cross_aisle_width_m = cross_aisle_width_m

class PhysicalAisle:
    def __init__(self, aisle_id: int, left_side: int, right_side: Optional[int],
                 row_start: int, row_end: int, x_position_m: float, name: str):
        self.id = aisle_id
        self.left_side = left_side
        self.right_side = right_side
        self.row_start = row_start
        self.row_end = row_end
        self.x_position_m = x_position_m
        self.name = name

    def contains_side(self, side: int) -> bool:
        return side == self.left_side or (self.right_side is not None and side == self.right_side)

class Warehouse:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.geometry: Optional[WarehouseGeometry] = None
        self.rows_config: Dict[str, int] = {}
        self.aisles: List[PhysicalAisle] = []
        self.side_to_aisle: Dict[int, PhysicalAisle] = {}
        self.special_elements: List[dict] = []
        self.special_sides: Dict[int, dict] = {}
        self.load_config()

    def load_config(self) -> None:
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        geo = data["warehouse"]
        self.geometry = WarehouseGeometry(
            shelf_length_m=geo["shelf_length_m"],
            shelf_height_m=geo["shelf_height_m"],
            shelf_depth_m=geo["shelf_depth_m"],
            main_aisle_width_m=geo["main_aisle_width_m"],
            cross_aisle_width_m=geo["cross_aisle_width_m"]
        )

        self.rows_config = data["rows"]

        for item in data["physical_aisles"]:
            aisle = PhysicalAisle(
                aisle_id=item["id"],
                left_side=item["left_side"],
                right_side=item["right_side"],
                row_start=item["row_start"],
                row_end=item["row_end"],
                x_position_m=item["x_position_m"],
                name=item["name"]
            )
            self.aisles.append(aisle)
            if aisle.left_side is not None:
                self.side_to_aisle[aisle.left_side] = aisle
            if aisle.right_side is not None:
                self.side_to_aisle[aisle.right_side] = aisle

        self.special_elements = data.get("special_elements", [])
        for elem in self.special_elements:
            for side in elem.get("sides", []):
                self.special_sides[side] = elem

    def get_aisle_by_side(self, side: int) -> Optional[PhysicalAisle]:
        return self.side_to_aisle.get(side)

    def get_coordinates(self, side: int, row: int) -> Tuple[float, float]:
        """
        Calculates the (x, y) coordinates of a picker standing in front of the shelf
        at the specified side and row.
        Returns:
            (x_path, y_path) in meters.
        """
        # Check special elements (like rolling cart)
        if side in self.special_sides:
            elem = self.special_sides[side]
            return elem["x_position_m"], elem["y_position_m"]

        # Find aisle
        aisle = self.get_aisle_by_side(side)
        if not aisle:
            raise ValueError(f"Side {side} does not exist in warehouse layout configuration.")

        # x-coordinate is the path center of the physical aisle
        x_path = aisle.x_position_m

        # y-coordinate computation based on rows and cross-aisle
        # 1 -> 42 -> cross_aisle -> 43 -> 84
        shelf_len = self.geometry.shelf_length_m
        first_section_end = self.rows_config["first_section_end"]
        second_section_start = self.rows_config["second_section_start"]
        cross_width = self.geometry.cross_aisle_width_m

        if row <= first_section_end:
            # y position is center of the shelf
            y_path = (row - 0.5) * shelf_len
        elif row >= second_section_start:
            # y position is after the first section + cross-aisle width + offset in second section
            first_sec_len = first_section_end * shelf_len
            y_path = first_sec_len + cross_width + (row - second_section_start + 0.5) * shelf_len
        else:
            # Between 42 and 43 (should not happen for items, but fallback to cross-aisle center)
            first_sec_len = first_section_end * shelf_len
            y_path = first_sec_len + (cross_width / 2.0)

        return x_path, y_path

    def get_max_dimensions(self) -> Tuple[float, float]:
        """
        Returns the overall width and length of the warehouse layout for drawing boundaries.
        """
        # Width: max aisle x_position + some margin for the last aisle's path/shelves
        max_x = max([aisle.x_position_m for aisle in self.aisles]) if self.aisles else 25.0
        # Aisle 9 is at 21.25m, its width is ~1.9m, so max_x + 2.0 is safe
        width = max_x + 2.0

        # Length: 84 rows * shelf_len + cross_aisle_width + margins
        # Row 84 center is ~110.0m, so total length is around 111.5m
        shelf_len = self.geometry.shelf_length_m
        first_section_end = self.rows_config["first_section_end"]
        total_rows = self.rows_config["end"] - self.rows_config["start"] + 1
        cross_width = self.geometry.cross_aisle_width_m
        total_len = total_rows * shelf_len + cross_width
        
        # Add buffer for walkways at top (before row 1) and bottom (after row 84)
        return width, total_len + 2.0
