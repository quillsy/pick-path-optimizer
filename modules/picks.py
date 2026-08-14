import re
import json
import os
from typing import List, Tuple, Optional, Dict
from datetime import datetime
from modules.warehouse import Warehouse

class Pick:
    # Pattern to match XX.YYY.ZZ (e.g., 19.015.20 or 02.10.3)
    PATTERN = re.compile(r"^(\d{2,3})\.(\d{2,3})\.(\d{2,3})$")

    def __init__(self, raw_code: str, warehouse: Optional[Warehouse] = None):
        self.raw_code = raw_code.strip()
        self.side: int = 0
        self.row: int = 0
        self.box: int = 0
        self.side_str: str = ""
        self.row_str: str = ""
        self.box_str: str = ""
        self.x: float = 0.0
        self.y: float = 0.0
        self.physical_aisle_id: Optional[int] = None
        
        self.parse_code()
        if warehouse:
            self.resolve_coordinates(warehouse)

    def parse_code(self) -> None:
        match = self.PATTERN.match(self.raw_code)
        if not match:
            raise ValueError(f"Ungültiges Pick-Code-Format: '{self.raw_code}'. Erwartetes Format: XX.YYY.ZZ (z.B. 19.015.20)")
        
        self.side_str, self.row_str, self.box_str = match.groups()
        
        try:
            self.side = int(self.side_str)
            self.row = int(self.row_str)
            self.box = int(self.box_str)
        except ValueError:
            raise ValueError(f"Pick-Code enthält ungültige Zeichen: '{self.raw_code}'")

        if not (1 <= self.side <= 20):
            raise ValueError(f"Ungültige Stellplatzseite: '{self.side_str}'. Erlaubt sind 01 bis 20.")
            
        if not (1 <= self.row <= 84):
            raise ValueError(f"Ungültige Reihe: '{self.row_str}'. Erlaubt sind 001 bis 084.")

    def resolve_coordinates(self, warehouse: Warehouse) -> None:
        """Looks up coordinates and physical aisle ID in the warehouse."""
        self.x, self.y = warehouse.get_coordinates(self.side, self.row)
        
        # Get physical aisle mapping
        aisle = warehouse.get_aisle_by_side(self.side)
        if aisle:
            self.physical_aisle_id = aisle.id
        else:
            # Special element (e.g. cart sides 01-03)
            self.physical_aisle_id = 0

    def __repr__(self) -> str:
        return f"Pick({self.raw_code} -> Side:{self.side}, Row:{self.row}, Box:{self.box}, Aisle:{self.physical_aisle_id}, Coord:({self.x:.2f}, {self.y:.2f}))"


class PickOrder:
    def __init__(self, order_id: str, timestamp_str: str, raw_picks_list: List[str], warehouse: Warehouse, source: str = "manual"):
        self.order_id = order_id
        self.source = source
        self.created_at = timestamp_str
        
        # Parse timestamp safely
        try:
            self.timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except ValueError:
            self.timestamp = datetime.now()
            
        self.picks: List[Pick] = []
        for code in raw_picks_list:
            if code.strip():
                # We expect parsed/validated codes.
                # If invalid, it will propagate the ValueError.
                self.picks.append(Pick(code, warehouse))
                    
        self.pick_count = len(self.picks)
        self.first_pick = self.picks[0] if self.picks else None
        self.last_input_pick = self.picks[-1] if self.picks else None
                    
    def __repr__(self) -> str:
        return f"PickOrder({self.order_id}, Picks count: {len(self.picks)}, Source: {self.source})"


def load_all_batches(file_path: str, warehouse: Warehouse) -> Dict[str, PickOrder]:
    """Loads all saved pick batches from the local JSON file."""
    if not os.path.exists(file_path):
        return {}
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return {}
            
    batches = {}
    for b_id, b_data in data.items():
        try:
            batches[b_id] = PickOrder(
                order_id=b_id,
                timestamp_str=b_data.get("created_at", ""),
                raw_picks_list=b_data.get("picks", []),
                warehouse=warehouse,
                source=b_data.get("source", "manual")
            )
        except Exception as e:
            print(f"Fehler beim Laden von Batch {b_id}: {e}")
            
    return batches


def save_batch(file_path: str, order: PickOrder) -> None:
    """Saves a single pick batch to the local JSON file."""
    data = {}
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                pass
                
    data[order.order_id] = {
        "order_id": order.order_id,
        "created_at": order.created_at,
        "source": order.source,
        "picks": [p.raw_code for p in order.picks]
    }
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def delete_batch(file_path: str, order_id: str) -> bool:
    """Deletes a batch from the local JSON database."""
    if not os.path.exists(file_path):
        return False
    with open(file_path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return False
            
    if order_id in data:
        del data[order_id]
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    return False


def generate_next_batch_id(existing_ids: List[str]) -> str:
    """Generates a unique batch ID with format BATCH-YYYYMMDD-XXXX."""
    date_str = datetime.now().strftime("%Y%m%d")
    prefix = f"BATCH-{date_str}-"
    max_counter = 0
    for b_id in existing_ids:
        if b_id.startswith(prefix):
            try:
                counter = int(b_id.split("-")[-1])
                max_counter = max(max_counter, counter)
            except ValueError:
                pass
    return f"{prefix}{max_counter + 1:04d}"
