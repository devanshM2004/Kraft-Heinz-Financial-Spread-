"""
Deterministic ingestion / extraction (Phase 2).

Public surface:
    detect_format(filename, data)        -> DetectionResult
    extract_document(filename, data)     -> RawDocument   (orchestrator)
    extract_html_tables(html)            -> (tables, warnings)
    extract_pdf_tables(data)             -> (tables, warnings)
    parse_number(text)                   -> ParsedNumber
    models: RawDocument, RawTable, RawRow, RawCell, SourceFormat
"""

from .detect import DetectionResult, detect_format
from .extractor import extract_document
from .html_tables import extract_html_tables
from .models import (
    RawCell,
    RawDocument,
    RawRow,
    RawTable,
    SourceFormat,
)
from .numbers import ParsedNumber, looks_numeric, parse_number
from .pdf_tables import PdfExtractionUnavailable, extract_pdf_tables

__all__ = [
    "DetectionResult",
    "detect_format",
    "extract_document",
    "extract_html_tables",
    "extract_pdf_tables",
    "PdfExtractionUnavailable",
    "parse_number",
    "looks_numeric",
    "ParsedNumber",
    "RawCell",
    "RawRow",
    "RawTable",
    "RawDocument",
    "SourceFormat",
]
