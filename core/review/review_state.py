"""
Human review state (Phase 5).

Holds the reviewed mapping — the human's final category choice per row — plus a
full override audit trail. The compute engine consumes THIS (via
`to_decisions_by_id()`), so a human edit actually changes the numbers computed.

Number-control rules are unchanged: the human only changes the *category*.
Python still derives every value; Claude still supplies nothing numeric.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from core.schema import (
    Confidence,
    MappingDecision,
    StandardizedCategory,
    StatementType,
)
from core.mapping.models import MappingResult


@dataclass
class ReviewedMapping:
    """One row's review record, including the human override audit trail."""
    row_id: str
    raw_label: str
    statement_type: StatementType
    original_category: StandardizedCategory      # Claude's suggestion
    original_confidence: Confidence              # Claude's confidence (preserved)
    original_rationale: str
    reviewed_category: StandardizedCategory       # the final, human-reviewed choice
    source_ref: str
    human_override: bool = False
    reviewer_note: Optional[str] = None
    values: dict[str, Optional[float]] = field(default_factory=dict)  # for display

    def to_audit_dict(self) -> dict:
        return {
            "row_id": self.row_id,
            "raw_label": self.raw_label,
            "statement_type": self.statement_type.value,
            "original_category": self.original_category.value,
            "reviewed_category": self.reviewed_category.value,
            "original_confidence": self.original_confidence.value,
            "human_override": self.human_override,
            "reviewer_note": self.reviewer_note,
            "source_ref": self.source_ref,
        }


class ReviewState:
    """A mutable, ordered collection of ReviewedMappings keyed by row_id."""

    def __init__(self, rows: list[ReviewedMapping]):
        self._order = [r.row_id for r in rows]
        self._by_id: dict[str, ReviewedMapping] = {r.row_id: r for r in rows}

    # -- construction --
    @classmethod
    def from_mapping_result(cls, result: MappingResult) -> "ReviewState":
        rows = [
            ReviewedMapping(
                row_id=rr.row_id,
                raw_label=rr.raw_label,
                statement_type=rr.statement_type,
                original_category=rr.standardized_category,
                original_confidence=rr.confidence,
                original_rationale=rr.rationale,
                reviewed_category=rr.standardized_category,  # seed = Claude's choice
                source_ref=rr.source_ref,
                values=dict(rr.values),
            )
            for rr in result.review_rows
        ]
        return cls(rows)

    # -- edits --
    def set_category(self, row_id: str, category: StandardizedCategory,
                     note: Optional[str] = None) -> None:
        r = self._by_id[row_id]
        r.reviewed_category = category
        r.human_override = category != r.original_category
        if note is not None:
            r.reviewer_note = note or None

    def set_note(self, row_id: str, note: Optional[str]) -> None:
        self._by_id[row_id].reviewer_note = note or None

    def reset(self, row_id: str) -> None:
        r = self._by_id[row_id]
        r.reviewed_category = r.original_category
        r.human_override = False
        r.reviewer_note = None

    def reset_all(self) -> None:
        for rid in self._order:
            self.reset(rid)

    # -- access --
    def get(self, row_id: str) -> ReviewedMapping:
        return self._by_id[row_id]

    def rows(self) -> list[ReviewedMapping]:
        return [self._by_id[rid] for rid in self._order]

    # -- feed the compute engine --
    def to_decisions_by_id(self) -> dict[str, MappingDecision]:
        """Reviewed categories, with the ORIGINAL confidence preserved."""
        out: dict[str, MappingDecision] = {}
        for r in self.rows():
            rationale = (
                f"Human override from {r.original_category.value}"
                + (f": {r.reviewer_note}" if r.reviewer_note else "")
                if r.human_override else r.original_rationale
            )
            out[r.row_id] = MappingDecision(
                row_id=r.row_id,
                standardized_category=r.reviewed_category,
                confidence=r.original_confidence,
                rationale=rationale,
            )
        return out

    def notes_by_id(self) -> dict[str, str]:
        """Override annotations to stamp onto SpreadItem.notes."""
        notes: dict[str, str] = {}
        for r in self.rows():
            if r.human_override:
                text = (f"Human override: {r.original_category.value} -> "
                        f"{r.reviewed_category.value}")
                if r.reviewer_note:
                    text += f" ({r.reviewer_note})"
                notes[r.row_id] = text
        return notes

    # -- status --
    def summary(self) -> dict:
        rows = self.rows()
        n_unmapped = sum(1 for r in rows
                         if r.reviewed_category == StandardizedCategory.UNMAPPED)
        n_low_conf = sum(1 for r in rows if r.original_confidence == Confidence.LOW)
        n_overrides = sum(1 for r in rows if r.human_override)
        # "Clean" = nothing left unmapped for a human to resolve.
        clean = n_unmapped == 0
        return {
            "total_rows": len(rows),
            "unmapped_rows": n_unmapped,
            "low_confidence_rows": n_low_conf,
            "human_overrides": n_overrides,
            "clean": clean,
        }

    def audit_rows(self) -> list[dict]:
        return [r.to_audit_dict() for r in self.rows()]
