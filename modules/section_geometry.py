"""
modules/section_geometry.py
============================
Standalone geometry module for the confirmed physical dimensions of the two
shelf sections and the cross-aisle (Mittelgang) that separates them.

Coordinate convention used here:
    y = 0  →  front edge of the first shelf section.

This module encodes ONLY confirmed measurements supplied by the user:
    - shelf_length_m      = 1.30 m  (length of one shelf unit along the walking path)
    - shelves_per_section = 7       (shelf units placed end-to-end per section)
    - cross_aisle_width_m = 1.43 m  (clear gap between the two sections)

What is NOT modelled here (still unresolved):
    - How the 42 row-numbers (001–042) map onto positions within a section.
    - Row spacing, row pitch, or compartment centres.
    - Whether row 001 aligns with the front edge or some other reference.
    - Walking-path centre lines (distinct from shelf edges).

This module is NOT yet integrated into routing, visualisation, or benchmarking.
The existing route calculations remain unchanged.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class SectionGeometry:
    """
    Immutable description of the two-section warehouse layout.

    Parameters
    ----------
    shelf_length_m : float
        Physical length of one shelf unit along the picker's walking direction,
        in metres.  Must be finite and strictly positive.
    shelves_per_section : int
        Number of shelf units placed end-to-end within one section.
        Must be a positive integer (bool values are rejected).
    cross_aisle_width_m : float
        Clear width of the cross-aisle (Mittelgang) that separates the two
        sections, in metres.  Must be finite and strictly positive.

    Derived read-only properties (all in metres, y = 0 at front of section 1):
        section_length_m          Length of one shelf section.
        section1_start_m          Front edge of section 1  (always 0.0).
        section1_end_m            Rear edge of section 1  =  start of cross-aisle.
        cross_aisle_start_m       Alias for section1_end_m.
        cross_aisle_centre_m      Geometric midpoint of the cross-aisle.
        cross_aisle_end_m         End of cross-aisle  =  front of section 2.
        section2_start_m          Alias for cross_aisle_end_m.
        section2_end_m            Rear edge of section 2.
        total_length_m            Combined span of both sections + cross-aisle.
    """

    shelf_length_m: float
    shelves_per_section: int
    cross_aisle_width_m: float

    # ------------------------------------------------------------------
    # Post-init validation (called automatically by dataclass machinery)
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        # --- shelf_length_m ---
        if isinstance(self.shelf_length_m, bool):
            raise TypeError(
                "shelf_length_m must be a number, not bool."
            )
        if not isinstance(self.shelf_length_m, (int, float)):
            raise TypeError(
                f"shelf_length_m must be a number, got {type(self.shelf_length_m).__name__!r}."
            )
        if not math.isfinite(self.shelf_length_m):
            raise ValueError(
                f"shelf_length_m must be finite, got {self.shelf_length_m!r}."
            )
        if self.shelf_length_m <= 0:
            raise ValueError(
                f"shelf_length_m must be strictly positive, got {self.shelf_length_m!r}."
            )

        # --- shelves_per_section ---
        if isinstance(self.shelves_per_section, bool):
            raise TypeError(
                "shelves_per_section must be an int, not bool."
            )
        if not isinstance(self.shelves_per_section, int):
            raise TypeError(
                f"shelves_per_section must be an int, "
                f"got {type(self.shelves_per_section).__name__!r}."
            )
        if self.shelves_per_section <= 0:
            raise ValueError(
                f"shelves_per_section must be strictly positive, "
                f"got {self.shelves_per_section!r}."
            )

        # --- cross_aisle_width_m ---
        if isinstance(self.cross_aisle_width_m, bool):
            raise TypeError(
                "cross_aisle_width_m must be a number, not bool."
            )
        if not isinstance(self.cross_aisle_width_m, (int, float)):
            raise TypeError(
                f"cross_aisle_width_m must be a number, "
                f"got {type(self.cross_aisle_width_m).__name__!r}."
            )
        if not math.isfinite(self.cross_aisle_width_m):
            raise ValueError(
                f"cross_aisle_width_m must be finite, got {self.cross_aisle_width_m!r}."
            )
        if self.cross_aisle_width_m <= 0:
            raise ValueError(
                f"cross_aisle_width_m must be strictly positive, "
                f"got {self.cross_aisle_width_m!r}."
            )

        # --- overflow guard ---
        # Each input is individually finite and positive, but derived totals can
        # still overflow to float infinity in two distinct ways:
        #   1. shelves_per_section * shelf_length_m  (product overflow)
        #   2. 2 * section_length + cross_aisle_width  (addition overflow)
        # Both are caught here so that no derived property ever silently returns inf.
        computed_section_length = self.shelves_per_section * self.shelf_length_m
        if not math.isfinite(computed_section_length):
            raise ValueError(
                f"shelves_per_section ({self.shelves_per_section}) × "
                f"shelf_length_m ({self.shelf_length_m!r}) overflows to infinity. "
                "Choose smaller values."
            )
        computed_total = computed_section_length + self.cross_aisle_width_m + computed_section_length
        if not math.isfinite(computed_total):
            raise ValueError(
                f"total_length (2 × section_length {computed_section_length!r} + "
                f"cross_aisle_width_m {self.cross_aisle_width_m!r}) overflows to infinity. "
                "Choose smaller values."
            )

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def section_length_m(self) -> float:
        """Length of one shelf section: shelves_per_section × shelf_length_m."""
        return self.shelves_per_section * self.shelf_length_m

    @property
    def section1_start_m(self) -> float:
        """Front edge of section 1.  Always 0.0 by convention."""
        return 0.0

    @property
    def section1_end_m(self) -> float:
        """Rear edge of section 1  =  front edge of the cross-aisle."""
        return self.section_length_m

    @property
    def cross_aisle_start_m(self) -> float:
        """Alias: front edge of the cross-aisle."""
        return self.section1_end_m

    @property
    def cross_aisle_centre_m(self) -> float:
        """Geometric midpoint of the cross-aisle."""
        return self.section1_end_m + self.cross_aisle_width_m / 2.0

    @property
    def cross_aisle_end_m(self) -> float:
        """Rear edge of the cross-aisle  =  front edge of section 2."""
        return self.section1_end_m + self.cross_aisle_width_m

    @property
    def section2_start_m(self) -> float:
        """Alias: front edge of section 2."""
        return self.cross_aisle_end_m

    @property
    def section2_end_m(self) -> float:
        """Rear edge of section 2."""
        return self.cross_aisle_end_m + self.section_length_m

    @property
    def total_length_m(self) -> float:
        """Combined span: section 1 + cross-aisle + section 2."""
        return self.section2_end_m
