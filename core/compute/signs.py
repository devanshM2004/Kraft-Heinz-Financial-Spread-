"""
Calculation-value sign normalization (Phase 4).

Rule: source_value is NEVER changed. calculation_value is derived from
source_value + the standardized category so that a subtotal equals the plain
arithmetic sum of its components.

For expense / contra categories the calculation value is the negative magnitude
(`-abs(source_value)`), which is robust whether the source displayed the figure
as a positive (17,000) or a parenthesised negative ((17,000) -> already -17000).
For every other category the source sign is preserved (so a genuinely negative
line — accumulated deficit, negative AOCI — keeps its sign).
"""

from __future__ import annotations

from typing import Optional

from core.schema import StandardizedCategory as SC

# Categories whose calculation_value is the negative magnitude of the source:
#  - income-statement expense/contra lines (so IS subtotals foot additively)
#  - treasury stock (a contra-equity that always reduces total equity)
NEGATE_CATEGORIES = frozenset({
    SC.COST_OF_GOODS_SOLD,
    SC.SELLING_GENERAL_ADMIN,
    SC.RESEARCH_DEVELOPMENT,
    SC.OTHER_OPERATING_EXPENSE,
    SC.INTEREST_EXPENSE,
    SC.INCOME_TAX_EXPENSE,
    SC.TREASURY_STOCK,
})


def to_calculation_value(
    category: SC, source_value: Optional[float]
) -> Optional[float]:
    """Deterministically derive calculation_value from source_value + category."""
    if source_value is None:
        return None
    if category in NEGATE_CATEGORIES:
        return -abs(source_value)
    return source_value
