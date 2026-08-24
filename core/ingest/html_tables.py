"""
Deterministic HTML table extraction (Phase 2).

Parses an HTML filing with BeautifulSoup/lxml and turns each <table> into a
RawTable (via the shared grid builder), preserving table index, row index,
column index, raw labels, period labels, and parsed values. No LLM involved.

Real-world 10-K tables can be messier than this handles (rowspans, deeply nested
layout). Those are surfaced as warnings rather than silently mis-parsed.
"""

from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from ._grid import Grid, build_table_from_grid
from .models import RawTable, SourceFormat
from .scale import detect_scale_currency

_MIN_VALUE_COLUMNS = 1
_MIN_DATA_ROWS = 2
_HEADING_TAGS = ["h1", "h2", "h3", "h4", "h5", "p", "b", "strong", "font",
                 "caption", "div", "span"]


def _cell_text(cell) -> str:
    return cell.get_text(separator=" ", strip=True)


def _row_to_grid(tr) -> list[tuple[str, bool]]:
    """Expand one <tr> into (text, is_header) tuples, honouring colspan."""
    out: list[tuple[str, bool]] = []
    for cell in tr.find_all(["td", "th"], recursive=False):
        text = _cell_text(cell)
        is_header = cell.name == "th"
        try:
            span = int(cell.get("colspan", 1))
        except (TypeError, ValueError):
            span = 1
        span = max(1, min(span, 50))
        out.append((text, is_header))
        out.extend(("", is_header) for _ in range(span - 1))
    return out


_SCALE_NOTE_MARKERS = (
    "in millions", "in thousands", "in billions", "except per share",
    "unaudited", "see accompanying", "amounts in",
)


def _is_scale_note(text: str) -> bool:
    low = text.lower().strip()
    if low.startswith("(") and low.endswith(")"):
        return True
    return any(m in low for m in _SCALE_NOTE_MARKERS)


def _find_heading(table) -> Optional[str]:
    """
    Nearest preceding short text block that identifies the statement. Skips
    scale/parenthetical notes like "(in millions)" so the statement title
    (e.g. "Consolidated Statements of Income") is preferred.
    """
    node = table
    first_seen: Optional[str] = None
    for _ in range(12):
        node = node.find_previous(_HEADING_TAGS)
        if node is None:
            break
        text = node.get_text(separator=" ", strip=True)
        if not text or not (3 <= len(text) <= 140):
            continue
        if first_seen is None:
            first_seen = text
        if not _is_scale_note(text):
            return text
    return first_seen


def _table_grid(table) -> Grid:
    trs = table.find_all("tr", recursive=False) or table.find_all("tr")
    return [_row_to_grid(tr) for tr in trs]


def _nearby_text(table) -> str:
    """Preceding text + the table's own top for scale/currency detection."""
    parts: list[str] = []
    node = table
    for _ in range(8):
        node = node.find_previous(_HEADING_TAGS)
        if node is None:
            break
        txt = node.get_text(separator=" ", strip=True)
        if txt:
            parts.append(txt)
    parts.append(table.get_text(separator=" ", strip=True)[:300])
    return " ".join(parts)


def extract_html_tables(html: str) -> tuple[list[RawTable], list[str]]:
    """
    Extract candidate financial tables from HTML.

    Returns (tables, warnings). `tables` are re-indexed 0..N in document order
    after filtering out non-financial tables.
    """
    soup = BeautifulSoup(html or "", "lxml")
    all_tables = soup.find_all("table")
    warnings: list[str] = []

    result: list[RawTable] = []
    for raw_tbl in all_tables:
        # Skip tables nested inside another table's cell to avoid double-counting.
        if raw_tbl.find_parent("table") is not None:
            continue
        grid = _table_grid(raw_tbl)
        parsed = build_table_from_grid(
            grid,
            table_index=len(result),
            source_format=SourceFormat.HTML,
            heading=_find_heading(raw_tbl),
            min_value_columns=_MIN_VALUE_COLUMNS,
            min_data_rows=_MIN_DATA_ROWS,
        )
        if parsed is None:
            continue
        scale, currency = detect_scale_currency(_nearby_text(raw_tbl))
        parsed.detected_scale = scale.value if scale else None
        parsed.detected_currency = currency
        if any(c.has_attr("rowspan") for c in raw_tbl.find_all(["td", "th"])):
            parsed.warnings.append(
                "Table uses rowspan; extraction ignores rowspans and columns "
                "may be misaligned — verify before relying on it."
            )
        result.append(parsed)

    skipped = len(all_tables) - len(result)
    if skipped > 0:
        warnings.append(
            f"{skipped} of {len(all_tables)} HTML tables were skipped as "
            "non-financial (no value columns / too few data rows / nested)."
        )
    if not result:
        warnings.append("No financial-looking tables were found in this HTML.")
    return result, warnings
