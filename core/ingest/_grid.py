"""
Shared grid -> RawTable logic (Phase 2).

Both the HTML and PDF extractors reduce a table to a rectangular grid of
(text, is_header) tuples, then hand it here to identify value columns, period
labels, and data rows. Keeping this deterministic step in one place means HTML
and PDF tables are structured identically downstream.
"""

from __future__ import annotations

from typing import Optional

from .models import RawCell, RawRow, RawTable, SourceFormat
from .numbers import parse_number

Grid = list[list[tuple[str, bool]]]


def looks_like_period(text: str) -> bool:
    """Heuristic: a period label such as a 4-digit year or a date-ish header."""
    t = (text or "").strip()
    if not t:
        return False
    if ("19" in t or "20" in t) and any(c.isdigit() for c in t):
        return sum(c.isdigit() for c in t) >= 2
    return False


def normalize_grid(grid: Grid) -> Grid:
    """Drop empty rows and pad ragged rows to a fixed width."""
    grid = [g for g in grid if g]
    if not grid:
        return grid
    width = max(len(g) for g in grid)
    for g in grid:
        g.extend(("", False) for _ in range(width - len(g)))
    return grid


def build_table_from_grid(
    grid: Grid,
    *,
    table_index: int,
    source_format: SourceFormat,
    page_number: Optional[int] = None,
    heading: Optional[str] = None,
    min_value_columns: int = 1,
    min_data_rows: int = 2,
) -> Optional[RawTable]:
    grid = normalize_grid(grid)
    if not grid:
        return None
    width = max(len(g) for g in grid)

    # Header rows: any <th> in a value position, or a labelless period-like row.
    header_set = {
        r for r, g in enumerate(grid)
        if any(is_h for (_t, is_h) in g[1:]) or (
            not g[0][0].strip()
            and sum(1 for (t, _h) in g[1:] if looks_like_period(t)) >= 1
        )
    }

    # Value columns: columns >=1 holding a present number in a non-header row.
    value_cols: list[int] = []
    for c in range(1, width):
        for r, g in enumerate(grid):
            if r in header_set:
                continue
            if parse_number(g[c][0]).is_present:
                value_cols.append(c)
                break
    if len(value_cols) < min_value_columns:
        return None

    min_value_col = min(value_cols)

    # Period labels aligned to value columns (search header rows bottom-up).
    header_rows_desc = sorted(header_set, reverse=True)
    period_labels: list[str] = []
    for c in value_cols:
        label = ""
        for r in header_rows_desc:
            txt = grid[r][c][0].strip()
            if txt:
                label = txt
                break
        period_labels.append(label)

    rows: list[RawRow] = []
    data_row_counter = 0
    for r, g in enumerate(grid):
        if r in header_set:
            continue

        label = ""
        for c in range(0, min_value_col):
            if g[c][0].strip():
                label = g[c][0].strip()
                break
        if not label:
            for c in range(0, width):
                if g[c][0].strip() and not parse_number(g[c][0]).is_present:
                    label = g[c][0].strip()
                    break

        cells: list[RawCell] = []
        any_value = False
        for col_idx, c in enumerate(value_cols):
            pn = parse_number(g[c][0])
            if pn.is_present:
                any_value = True
            cells.append(RawCell(
                column_index=col_idx,
                raw_text=g[c][0],
                source_value=pn.value,
                value_is_present=pn.is_present,
                is_negative_paren=pn.is_negative_paren,
                is_percent=pn.is_percent,
                period_label=period_labels[col_idx] if col_idx < len(period_labels) else None,
                grid_column_index=c,
            ))

        if not label and not any_value:
            continue

        rows.append(RawRow(
            row_index=data_row_counter,
            label=label,
            cells=cells,
            is_label_only=not any_value,
            grid_row_index=r,
        ))
        data_row_counter += 1

    if sum(1 for row in rows if not row.is_label_only) < min_data_rows:
        return None

    return RawTable(
        table_index=table_index,
        source_format=source_format,
        period_labels=period_labels,
        rows=rows,
        heading=heading,
        page_number=page_number,
        n_value_columns=len(value_cols),
    )
