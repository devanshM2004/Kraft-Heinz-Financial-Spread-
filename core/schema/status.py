"""
Status, confidence, and validation vocabularies (Phase 1).

These enums define the flags the review UI (later phase) will surface. Phase 1
only DEFINES them and the ValidationFinding record shape; no checks run yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Confidence(str, Enum):
    """Confidence flag the model attaches to each mapping decision."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, Enum):
    ERROR = "error"      # blocks a clean export; must be reviewed
    WARNING = "warning"  # should be reviewed, does not necessarily block
    INFO = "info"


class ValidationCode(str, Enum):
    """
    Every validation signal the app can raise. Grouped by the level they apply
    to. Phase 1 defines them; Phase 4 computes them.
    """
    # -- per-item (attach to one or more rows) --
    UNMAPPED_ROW = "unmapped_row"
    DUPLICATE_MAPPING = "duplicate_mapping"
    LOW_CONFIDENCE_MAPPING = "low_confidence_mapping"

    # -- spread-level --
    MISSING_REQUIRED_CATEGORY = "missing_required_category"
    BALANCE_SHEET_IMBALANCE = "balance_sheet_imbalance"
    SUBTOTAL_FOOTING_ISSUE = "subtotal_footing_issue"
    RATIO_NOT_CALCULABLE = "ratio_not_calculable"


# Default severity for each code (the app may escalate/deescalate in context).
DEFAULT_SEVERITY: dict[ValidationCode, Severity] = {
    ValidationCode.UNMAPPED_ROW: Severity.WARNING,
    ValidationCode.DUPLICATE_MAPPING: Severity.ERROR,
    ValidationCode.LOW_CONFIDENCE_MAPPING: Severity.WARNING,
    ValidationCode.MISSING_REQUIRED_CATEGORY: Severity.WARNING,
    ValidationCode.BALANCE_SHEET_IMBALANCE: Severity.ERROR,
    ValidationCode.SUBTOTAL_FOOTING_ISSUE: Severity.ERROR,
    ValidationCode.RATIO_NOT_CALCULABLE: Severity.INFO,
}


@dataclass
class ValidationFinding:
    """
    One issue surfaced for human review. Never mutates numbers — it only
    describes a problem and points at the rows/categories involved.
    """
    code: ValidationCode
    severity: Severity
    message: str
    fiscal_year: str | None = None
    related_row_ids: list[str] = field(default_factory=list)
    related_categories: list[str] = field(default_factory=list)
    # Free-form structured context (e.g. {"expected": ..., "reported": ...,
    # "difference": ...}). Values are Python-computed; never model-produced.
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "fiscal_year": self.fiscal_year,
            "related_row_ids": list(self.related_row_ids),
            "related_categories": list(self.related_categories),
            "details": dict(self.details),
        }
