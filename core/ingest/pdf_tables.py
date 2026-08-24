"""
Deterministic PDF table extraction (Phase 2) — text-based PDFs only.

Uses pdfplumber's table detection. PDF table extraction is inherently less
reliable than HTML (there is no real cell structure — it is inferred from
rules/whitespace), so this module is deliberately conservative and SURFACES
uncertainty rather than pretending it worked:

  * If a page has no extractable text at all, the PDF is likely scanned/image —
    reported clearly (that is Phase 6 / Claude vision territory, not Phase 2).
  * If text exists but no tables are detected, that is reported per page.
  * Detected tables are marked with a warning reminding the reviewer that PDF
    table geometry can be misaligned and should be verified.

pdfplumber is imported lazily so the rest of the app (and the HTML path) work
even if the PDF stack is unavailable in a given environment.
"""

from __future__ import annotations

import io

from ._grid import build_table_from_grid
from .models import RawTable, SourceFormat
from .scale import detect_scale_currency

_MIN_VALUE_COLUMNS = 1
_MIN_DATA_ROWS = 2


class PdfExtractionUnavailable(RuntimeError):
    """Raised when the PDF parsing stack cannot be imported."""


def _rows_to_grid(rows) -> list[list[tuple[str, bool]]]:
    """pdfplumber gives rows as lists of cell strings (or None)."""
    grid: list[list[tuple[str, bool]]] = []
    for row in rows:
        grid.append([((cell or "").strip(), False) for cell in row])
    return grid


def extract_pdf_tables(data: bytes) -> tuple[list[RawTable], list[str]]:
    """
    Extract candidate financial tables from a text-based PDF.

    Returns (tables, warnings). Raises PdfExtractionUnavailable if pdfplumber
    (or its native deps) cannot be imported in this environment.
    """
    try:
        import pdfplumber  # lazy import
    except Exception as exc:  # pragma: no cover - environment dependent
        raise PdfExtractionUnavailable(
            f"pdfplumber is not importable in this environment: {exc}"
        ) from exc

    warnings: list[str] = []
    tables: list[RawTable] = []

    pages_with_text = 0
    pages_with_tables = 0

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        n_pages = len(pdf.pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages_with_text += 1

            try:
                page_tables = page.extract_tables() or []
            except Exception as exc:
                warnings.append(f"Page {page_number}: table extraction error ({exc}).")
                continue

            if page_tables:
                pages_with_tables += 1

            for rows in page_tables:
                if not rows:
                    continue
                grid = _rows_to_grid(rows)
                parsed = build_table_from_grid(
                    grid,
                    table_index=len(tables),
                    source_format=SourceFormat.PDF,
                    page_number=page_number,
                    heading=None,
                    min_value_columns=_MIN_VALUE_COLUMNS,
                    min_data_rows=_MIN_DATA_ROWS,
                )
                if parsed is not None:
                    scale, currency = detect_scale_currency(text[:400])
                    parsed.detected_scale = scale.value if scale else None
                    parsed.detected_currency = currency
                    parsed.warnings.append(
                        "PDF table geometry is inferred, not structural — verify "
                        "column alignment and values against the source page."
                    )
                    tables.append(parsed)

    # Surface reliability signals clearly.
    if pages_with_text == 0:
        warnings.append(
            "No extractable text found on any page. This PDF looks scanned/image-"
            "based; text-PDF extraction cannot handle it. (Scanned support is a "
            "later phase via Claude vision.)"
        )
    elif not tables:
        warnings.append(
            "Text was found but no financial tables could be reliably detected. "
            "The layout may not be table-structured; do not assume extraction "
            "succeeded — inspect the source PDF."
        )
    if tables:
        warnings.append(
            "PDF extraction is best-effort: detected table structure can be "
            "misaligned. Review every extracted table before trusting it."
        )
    return tables, warnings
