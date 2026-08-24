"""
Ingest orchestrator (Phase 2).

Detects the uploaded file's format and routes to the HTML or PDF extractor,
returning a single RawDocument with all found tables plus any warnings. No LLM,
no mapping, no calculation.
"""

from __future__ import annotations

from .detect import detect_format
from .html_tables import extract_html_tables
from .models import RawDocument, SourceFormat
from .pdf_tables import PdfExtractionUnavailable, extract_pdf_tables


def extract_document(filename: str, data: bytes) -> RawDocument:
    """Detect format and extract tables from an uploaded file's bytes."""
    detection = detect_format(filename, data)
    doc = RawDocument(
        filename=filename,
        source_format=detection.source_format,
        size_bytes=len(data or b""),
    )
    doc.notes.append(detection.reason)

    if detection.source_format == SourceFormat.UNSUPPORTED:
        doc.warnings.append(
            "Unsupported file format. Upload a text-based HTML or PDF filing."
        )
        return doc

    if detection.source_format == SourceFormat.HTML:
        try:
            text = data.decode("utf-8", errors="replace")
        except Exception:
            text = data.decode("latin-1", errors="replace")
        tables, warnings = extract_html_tables(text)
        doc.tables = tables
        doc.warnings.extend(warnings)
        return doc

    # PDF
    try:
        tables, warnings = extract_pdf_tables(data)
    except PdfExtractionUnavailable as exc:
        doc.warnings.append(str(exc))
        return doc
    doc.tables = tables
    doc.warnings.extend(warnings)
    return doc
