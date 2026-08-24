"""
Mapping-to-spread binding (Phase 4).

Takes the extracted raw tables plus the validated category decisions and produces
SpreadItem audit records — one per (mapped row, period). Preserves source_value
exactly and derives calculation_value deterministically from the category.

Claude never supplies a number here: source_value comes from the extracted cell,
calculation_value is computed by Python from source_value + the category.
"""

from __future__ import annotations

from typing import Optional

from core.ingest.models import RawTable
from core.schema import (
    Confidence,
    MappingDecision,
    SourceScale,
    SpreadItem,
    StandardizedCategory,
    StatementType,
)

from .signs import to_calculation_value


def _row_id(table_index: int, row_index: int) -> str:
    return f"t{table_index}r{row_index}"


def bind_table(
    table: RawTable,
    statement_type: StatementType,
    decisions_by_id: dict[str, MappingDecision],
    *,
    source_scale: SourceScale = SourceScale.UNKNOWN,
    currency: Optional[str] = None,
) -> list[SpreadItem]:
    """Bind one table's rows to SpreadItems using the given decisions."""
    items: list[SpreadItem] = []
    for row in table.rows:
        rid = _row_id(table.table_index, row.row_index)
        decision = decisions_by_id.get(rid)
        category = decision.standardized_category if decision else StandardizedCategory.UNMAPPED
        confidence = decision.confidence if decision else Confidence.LOW

        # Non-data rows are excluded from the spread entirely.
        if category == StandardizedCategory.IGNORE:
            continue

        for cell in row.cells:
            period = cell.period_label or f"col_{cell.column_index}"
            present = cell.value_is_present
            source_value = cell.source_value if present else None
            calc_value = to_calculation_value(category, source_value) if present else None

            items.append(SpreadItem(
                row_id=rid,
                statement_type=statement_type,
                raw_label=row.label,
                standardized_category=category,
                fiscal_year=period,
                period_label=f"FY{period}" if period.isdigit() else period,
                confidence=confidence,
                source_value=source_value,
                calculation_value=calc_value,
                value_is_present=present,
                source_scale=source_scale,
                currency=currency,
                source_table_index=table.table_index,
                source_row_index=row.row_index,
                source_column_index=cell.column_index,
                source_location=(
                    f"{statement_type.value}, table {table.table_index}, "
                    f"row {row.row_index}, col {period}"
                ),
            ))
    return items


def bind_spread_items(
    income_table: Optional[RawTable],
    balance_table: Optional[RawTable],
    decisions_by_id: dict[str, MappingDecision],
    *,
    source_scale: SourceScale = SourceScale.UNKNOWN,
    currency: Optional[str] = None,
) -> list[SpreadItem]:
    """Bind both selected tables into a single list of SpreadItems."""
    items: list[SpreadItem] = []
    if income_table is not None:
        items += bind_table(income_table, StatementType.INCOME_STATEMENT,
                            decisions_by_id, source_scale=source_scale, currency=currency)
    if balance_table is not None:
        items += bind_table(balance_table, StatementType.BALANCE_SHEET,
                            decisions_by_id, source_scale=source_scale, currency=currency)
    return items
