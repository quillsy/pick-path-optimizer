"""
tests/test_section_geometry.py
================================
Tests for modules/section_geometry.py

These tests import ONLY SectionGeometry from the new standalone module.
They do NOT depend on warehouse.json, routing, optimization, benchmarking
or any other existing module.

All expected values are stated explicitly and independently;
they are NOT derived by calling the method under test.
"""

import math
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.section_geometry import SectionGeometry


# ---------------------------------------------------------------------------
# Helper: warehouse-confirmed instance
#   shelf_length_m      = 1.30 m
#   shelves_per_section = 7
#   cross_aisle_width_m = 1.43 m
# ---------------------------------------------------------------------------
WAREHOUSE = SectionGeometry(
    shelf_length_m=1.30,
    shelves_per_section=7,
    cross_aisle_width_m=1.43,
)

# ---------------------------------------------------------------------------
# Helper: alternative instance used in parametric tests
#   shelf_length_m      = 2.00 m
#   shelves_per_section = 3
#   cross_aisle_width_m = 1.00 m
# ---------------------------------------------------------------------------
ALT = SectionGeometry(
    shelf_length_m=2.00,
    shelves_per_section=3,
    cross_aisle_width_m=1.00,
)

TOLERANCE = 1e-9


class TestWarehouseValues(unittest.TestCase):
    """Exact numerical checks for the confirmed warehouse geometry (7 × 1.30 m, 1.43 m gap)."""

    def test_section_length(self):
        # 7 × 1.30 = 9.10 m
        self.assertAlmostEqual(WAREHOUSE.section_length_m, 9.10, delta=TOLERANCE)

    def test_section1_start(self):
        # Front edge of section 1 is the coordinate origin: 0.00 m
        self.assertAlmostEqual(WAREHOUSE.section1_start_m, 0.00, delta=TOLERANCE)

    def test_section1_end(self):
        # Rear of section 1 / start of cross-aisle: 9.10 m
        self.assertAlmostEqual(WAREHOUSE.section1_end_m, 9.10, delta=TOLERANCE)

    def test_cross_aisle_start(self):
        # cross_aisle_start_m is an alias for section1_end_m: 9.10 m
        self.assertAlmostEqual(WAREHOUSE.cross_aisle_start_m, 9.10, delta=TOLERANCE)

    def test_cross_aisle_centre(self):
        # 9.10 + 1.43 / 2 = 9.10 + 0.715 = 9.815 m
        self.assertAlmostEqual(WAREHOUSE.cross_aisle_centre_m, 9.815, delta=TOLERANCE)

    def test_cross_aisle_end(self):
        # 9.10 + 1.43 = 10.53 m
        self.assertAlmostEqual(WAREHOUSE.cross_aisle_end_m, 10.53, delta=TOLERANCE)

    def test_section2_start(self):
        # section2_start_m is an alias for cross_aisle_end_m: 10.53 m
        self.assertAlmostEqual(WAREHOUSE.section2_start_m, 10.53, delta=TOLERANCE)

    def test_section2_end(self):
        # 10.53 + 9.10 = 19.63 m
        self.assertAlmostEqual(WAREHOUSE.section2_end_m, 19.63, delta=TOLERANCE)

    def test_total_length(self):
        # 9.10 + 1.43 + 9.10 = 19.63 m
        self.assertAlmostEqual(WAREHOUSE.total_length_m, 19.63, delta=TOLERANCE)


class TestCrossAisleWidthConsistency(unittest.TestCase):
    """The cross-aisle width must equal the difference of its boundary coordinates."""

    def test_warehouse_cross_aisle_width_from_boundaries(self):
        derived = WAREHOUSE.cross_aisle_end_m - WAREHOUSE.cross_aisle_start_m
        self.assertAlmostEqual(derived, WAREHOUSE.cross_aisle_width_m, delta=TOLERANCE)

    def test_alt_cross_aisle_width_from_boundaries(self):
        derived = ALT.cross_aisle_end_m - ALT.cross_aisle_start_m
        self.assertAlmostEqual(derived, ALT.cross_aisle_width_m, delta=TOLERANCE)


class TestBothSectionsEqualLength(unittest.TestCase):
    """Both shelf sections must have identical length."""

    def test_warehouse_sections_equal(self):
        section1_len = WAREHOUSE.section1_end_m - WAREHOUSE.section1_start_m
        section2_len = WAREHOUSE.section2_end_m - WAREHOUSE.section2_start_m
        self.assertAlmostEqual(section1_len, section2_len, delta=TOLERANCE)

    def test_alt_sections_equal(self):
        section1_len = ALT.section1_end_m - ALT.section1_start_m
        section2_len = ALT.section2_end_m - ALT.section2_start_m
        self.assertAlmostEqual(section1_len, section2_len, delta=TOLERANCE)


class TestBoundaryOrdering(unittest.TestCase):
    """All boundaries must be in strictly ascending order."""

    def _check_order(self, geom: SectionGeometry):
        self.assertEqual(geom.section1_start_m, 0.0)
        self.assertLess(geom.section1_start_m, geom.section1_end_m)
        self.assertEqual(geom.section1_end_m, geom.cross_aisle_start_m)
        self.assertLess(geom.cross_aisle_start_m, geom.cross_aisle_centre_m)
        self.assertLess(geom.cross_aisle_centre_m, geom.cross_aisle_end_m)
        self.assertEqual(geom.cross_aisle_end_m, geom.section2_start_m)
        self.assertLess(geom.section2_start_m, geom.section2_end_m)
        self.assertEqual(geom.section2_end_m, geom.total_length_m)

    def test_warehouse_boundary_order(self):
        self._check_order(WAREHOUSE)

    def test_alt_boundary_order(self):
        self._check_order(ALT)


class TestAlternativeInputs(unittest.TestCase):
    """Parametric test with shelf_length=2.00, shelves=3, cross_aisle=1.00."""

    def test_section_length(self):
        # 3 × 2.00 = 6.00 m
        self.assertAlmostEqual(ALT.section_length_m, 6.00, delta=TOLERANCE)

    def test_cross_aisle_centre(self):
        # 6.00 + 1.00 / 2 = 6.50 m
        self.assertAlmostEqual(ALT.cross_aisle_centre_m, 6.50, delta=TOLERANCE)

    def test_total_length(self):
        # 6.00 + 1.00 + 6.00 = 13.00 m
        self.assertAlmostEqual(ALT.total_length_m, 13.00, delta=TOLERANCE)


class TestValidation(unittest.TestCase):
    """Invalid inputs must raise TypeError or ValueError with a clear message."""

    # --- shelf_length_m ---

    def test_shelf_length_zero_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=0.0, shelves_per_section=7, cross_aisle_width_m=1.43)

    def test_shelf_length_negative_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=-1.0, shelves_per_section=7, cross_aisle_width_m=1.43)

    def test_shelf_length_inf_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=math.inf, shelves_per_section=7, cross_aisle_width_m=1.43)

    def test_shelf_length_nan_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=math.nan, shelves_per_section=7, cross_aisle_width_m=1.43)

    # --- shelves_per_section ---

    def test_shelves_zero_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=0, cross_aisle_width_m=1.43)

    def test_shelves_negative_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=-3, cross_aisle_width_m=1.43)

    def test_shelves_float_raises(self):
        with self.assertRaises(TypeError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=7.0, cross_aisle_width_m=1.43)

    def test_shelves_bool_true_raises(self):
        # bool is a subclass of int; True == 1 but bool must be rejected explicitly.
        with self.assertRaises(TypeError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=True, cross_aisle_width_m=1.43)

    def test_shelves_bool_false_raises(self):
        with self.assertRaises(TypeError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=False, cross_aisle_width_m=1.43)

    # --- cross_aisle_width_m ---

    def test_cross_aisle_zero_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=7, cross_aisle_width_m=0.0)

    def test_cross_aisle_negative_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=7, cross_aisle_width_m=-0.5)

    def test_cross_aisle_inf_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=7, cross_aisle_width_m=math.inf)

    def test_cross_aisle_nan_raises(self):
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1.30, shelves_per_section=7, cross_aisle_width_m=math.nan)

    # --- overflow guard ---

    def test_section_length_overflow_raises(self):
        # Both inputs are individually finite and positive, but their product
        # overflows to float infinity.  The guard in __post_init__ must catch this.
        import sys
        big = sys.float_info.max  # finite und positiv, aber 7×big = inf
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=big, shelves_per_section=7, cross_aisle_width_m=1.43)

    def test_total_length_overflow_via_double_section_raises(self):
        # section_length = 1e308 is finite, but total = 2*1e308 + 1.43 overflows to inf.
        # The guard must reject this at construction time.
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=1e308, shelves_per_section=1, cross_aisle_width_m=1.43)

    def test_total_length_overflow_via_large_cross_aisle_raises(self):
        # section_length = 5e307 is finite, cross_aisle = 1e308 is finite,
        # but section_length + cross_aisle + section_length overflows to inf.
        # The guard must reject this at construction time.
        with self.assertRaises(ValueError):
            SectionGeometry(shelf_length_m=5e307, shelves_per_section=1, cross_aisle_width_m=1e308)


if __name__ == "__main__":
    unittest.main()
