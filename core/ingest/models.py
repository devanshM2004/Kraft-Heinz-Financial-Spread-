"""
Raw extraction data models (Phase 2).

These represent the DETERMINISTIC output of table extraction — before any LLM is
involved. Nothing here is mapped to a standardized category yet (that is Phase 3)
and no calculation normalization has happened (Phase 3/4). We only preserve what
the filing literally contains, plus source references.

Grain:
    RawDocument -> RawTable -> RawRow -> RawCell

Every RawCell keeps:
    - raw_text        : the exact cell text as found
    - source_value    : the number parsed from raw_text (or None if not present)
    - value_is_present: False for blanks / dashes
    - column_index    : position among the table's *value* columns (0-based)
    - period_label    : the period header aligned to that column (if detected)

`calculation_value` deliberately does NOT exist at this stage — sign
normalization requires the standardized category, which is decided in Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SourceFormat(str, Enum):
    HTML = "html"
    PDF = "pdf"
    UNSUPPORTED = "unsupported"


@dataclass
class RawCell:
    column_index: int                 # 0-based index among value columns
    raw_text: str                     # exact source text
    source_value: Optional[float]     # parsed number, or None if not present
    value_is_present: bool
    is_negative_paren: bool = False   # True when source showed (1,234) style
    is_percent: bool = False
    period_label: Optional[str] = None
    grid_column_index: Optional[int] = None  # raw column position in the table grid

    def to_dict(self) -> dict:
        return {
            "column_index": self.column_index,
            "raw_text": self.raw_text,
            "source_value": self.source_value,
            "value_is_present": self.value_is_present,
            "is_negative_paren": self.is_negative_paren,
            "is_percent": self.is_percent,
            "period_label": self.period_label,
            "grid_column_index": self.grid_column_index,
        }


@dataclass
class RawRow:
    row_index: int                    # 0-based index within the table
    label: str                        # leftmost text (the line-item caption)
    cells: list[RawCell] = field(default_factory=list)
    is_label_only: bool = False       # section header / no numeric cells
    grid_row_index: Optional[int] = None

    def to_dict(self) -> dict:
        return {
            "row_index": self.row_index,
            "label": self.label,
            "is_label_only": self.is_label_only,
            "grid_row_index": self.grid_row_index,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class RawTable:
    table_index: int                  # 0-based index within the document
    source_format: SourceFormat
    period_labels: list[str] = field(default_factory=list)  # by value-column index
    rows: list[RawRow] = field(default_factory=list)
    heading: Optional[str] = None     # nearby heading/caption to help identify the statement
    page_number: Optional[int] = None  # PDF only
    n_value_columns: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def n_data_rows(self) -> int:
        return sum(1 for r in self.rows if not r.is_label_only)

    def to_dict(self) -> dict:
        return {
            "table_index": self.table_index,
            "source_format": self.source_format.value,
            "heading": self.heading,
            "page_number": self.page_number,
            "period_labels": list(self.period_labels),
            "n_value_columns": self.n_value_columns,
            "n_data_rows": self.n_data_rows,
            "warnings": list(self.warnings),
            "rows": [r.to_dict() for r in self.rows],
        }

    def preview_rows(self) -> list[dict]:
        """
        Flatten to display-friendly rows for the Streamlit preview. One dict per
        table row: the label, each period's parsed value, and source references.
        """
        out: list[dict] = []
        for r in self.rows:
            rec: dict = {
                "row_index": r.row_index,
                "label": r.label,
                "kind": "section" if r.is_label_only else "data",
            }
            by_col = {c.column_index: c for c in r.cells}
            for col in range(self.n_value_columns):
                header = (
                    self.period_labels[col]
                    if col < len(self.period_labels)
                    else f"col_{col}"
                )
                cell = by_col.get(col)
                rec[header or f"col_{col}"] = (
                    cell.source_value if cell and cell.value_is_present else None
                )
            rec["source_ref"] = f"table {self.table_index}, row {r.row_index}"
            out.append(rec)
        return out


@dataclass
class RawDocument:
    filename: str
    source_format: SourceFormat
    size_bytes: int
    tables: list[RawTable] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "source_format": self.source_format.value,
            "size_bytes": self.size_bytes,
            "n_tables": len(self.tables),
            "warnings": list(self.warnings),
            "notes": list(self.notes),
            "tables": [t.to_dict() for t in self.tables],
        }
