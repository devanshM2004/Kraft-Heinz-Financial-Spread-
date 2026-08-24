"""
Deterministic compute + validation (Phase 4).

Public surface:
    to_calculation_value(category, source_value)  -- sign normalization
    bind_spread_items(...) / bind_table(...)       -- raw rows -> SpreadItems
    compute_spread(income, balance, decisions)     -- bind + ratios + validate
    compute_from_items(items)                      -- ratios + validate on items
    ComputeResult, RatioValue
"""

from .aggregate import SpreadValues, aggregate
from .binding import bind_spread_items, bind_table
from .derived import DerivedValue, ebitda, total_debt
from .engine import ComputeResult, compute_from_items, compute_spread
from .ratios import RatioValue, compute_ratios
from .signs import NEGATE_CATEGORIES, to_calculation_value
from .validate import REQUIRED_CATEGORIES, validate_spread

__all__ = [
    "to_calculation_value",
    "NEGATE_CATEGORIES",
    "bind_spread_items",
    "bind_table",
    "aggregate",
    "SpreadValues",
    "total_debt",
    "ebitda",
    "DerivedValue",
    "compute_ratios",
    "RatioValue",
    "validate_spread",
    "REQUIRED_CATEGORIES",
    "compute_spread",
    "compute_from_items",
    "ComputeResult",
]
