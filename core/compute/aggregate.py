"""
Aggregation of SpreadItems into per-(category, period) values (Phase 4).

Provides fast lookups for the ratio and validation layers. All arithmetic uses
calculation_value; source_value is retained for display/audit only.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

from core.schema import SpreadItem, StandardizedCategory


@dataclass
class SpreadValues:
    periods: list[str] = field(default_factory=list)
    # calculation_value summed by (category, period)
    _calc: dict[tuple[str, str], float] = field(default_factory=dict)
    # how many present rows contributed to each (category, period) — for dupes
    _counts: dict[tuple[str, str], int] = field(default_factory=dict)

    def calc(self, category: StandardizedCategory, period: str) -> Optional[float]:
        return self._calc.get((category.value, period))

    def present(self, category: StandardizedCategory, period: str) -> bool:
        return (category.value, period) in self._calc

    def count(self, category: StandardizedCategory, period: str) -> int:
        return self._counts.get((category.value, period), 0)


def aggregate(items: list[SpreadItem]) -> SpreadValues:
    calc: dict[tuple[str, str], float] = defaultdict(float)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    periods: list[str] = []
    seen_periods: set[str] = set()

    for it in items:
        if it.fiscal_year not in seen_periods:
            seen_periods.add(it.fiscal_year)
            periods.append(it.fiscal_year)
        if not it.value_is_present or it.calculation_value is None:
            continue
        key = (it.standardized_category.value, it.fiscal_year)
        calc[key] += it.calculation_value
        counts[key] += 1

    # Sort periods by numeric year descending when they look like years.
    def _key(p: str):
        return (0, -int(p)) if p.isdigit() else (1, p)
    periods = sorted(periods, key=_key)

    return SpreadValues(periods=periods, _calc=dict(calc), _counts=dict(counts))
