"""
Compute engine (Phase 4) — orchestrates binding, ratios, and validation.

Given the selected raw tables and the validated category decisions, produce a
ComputeResult: bound SpreadItems, computed ratios per period, and validation
findings. Deterministic Python only; no LLM, no numbers from Claude.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.ingest.models import RawTable
from core.schema import (
    MappingDecision,
    Severity,
    SourceScale,
    SpreadItem,
)

from .aggregate import aggregate
from .binding import bind_spread_items
from .ratios import RatioValue, compute_ratios
from .validate import validate_spread
from core.schema import ValidationFinding


@dataclass
class ComputeResult:
    items: list[SpreadItem] = field(default_factory=list)
    periods: list[str] = field(default_factory=list)
    ratios: list[RatioValue] = field(default_factory=list)
    findings: list[ValidationFinding] = field(default_factory=list)
    currency: Optional[str] = None

    # -- validation summary --
    @property
    def n_errors(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.ERROR)

    @property
    def n_warnings(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.WARNING)

    @property
    def n_info(self) -> int:
        return sum(1 for f in self.findings if f.severity == Severity.INFO)

    @property
    def passed(self) -> bool:
        """True when no ERROR-severity findings exist."""
        return self.n_errors == 0

    def validation_summary(self) -> dict:
        return {
            "passed": self.passed,
            "n_errors": self.n_errors,
            "n_warnings": self.n_warnings,
            "n_info": self.n_info,
        }

    def ratios_by_period(self) -> dict[str, dict[str, RatioValue]]:
        out: dict[str, dict[str, RatioValue]] = {}
        for r in self.ratios:
            out.setdefault(r.period, {})[r.name] = r
        return out

    def to_dict(self) -> dict:
        return {
            "periods": self.periods,
            "currency": self.currency,
            "validation_summary": self.validation_summary(),
            "items": [it.to_dict() for it in self.items],
            "ratios": [r.to_dict() for r in self.ratios],
            "findings": [f.to_dict() for f in self.findings],
        }


def compute_from_items(items: list[SpreadItem]) -> ComputeResult:
    """Compute ratios + validations from already-bound SpreadItems."""
    values = aggregate(items)
    ratios = compute_ratios(values)
    findings = validate_spread(items, values, ratios)
    currency = next((it.currency for it in items if it.currency), None)
    return ComputeResult(
        items=items,
        periods=values.periods,
        ratios=ratios,
        findings=findings,
        currency=currency,
    )


def compute_spread(
    income_table: Optional[RawTable],
    balance_table: Optional[RawTable],
    decisions_by_id: dict[str, MappingDecision],
    *,
    source_scale: SourceScale = SourceScale.UNKNOWN,
    currency: Optional[str] = None,
    notes_by_id: Optional[dict[str, str]] = None,
) -> ComputeResult:
    """Bind the selected tables + decisions, then compute ratios and validations."""
    items = bind_spread_items(
        income_table, balance_table, decisions_by_id,
        source_scale=source_scale, currency=currency, notes_by_id=notes_by_id,
    )
    return compute_from_items(items)
