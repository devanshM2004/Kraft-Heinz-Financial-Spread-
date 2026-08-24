"""
File-type detection (Phase 2).

Decides whether an uploaded file is an HTML filing or a text PDF, using both the
filename extension and a content sniff. Unsupported formats are rejected clearly
rather than being force-parsed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import SourceFormat

_HTML_EXTS = {".html", ".htm", ".xhtml"}
_PDF_EXTS = {".pdf"}


@dataclass
class DetectionResult:
    source_format: SourceFormat
    reason: str
    confident: bool

    @property
    def is_supported(self) -> bool:
        return self.source_format in (SourceFormat.HTML, SourceFormat.PDF)


def _ext(filename: str) -> str:
    name = (filename or "").lower().strip()
    dot = name.rfind(".")
    return name[dot:] if dot != -1 else ""


def detect_format(filename: str, data: bytes) -> DetectionResult:
    """
    Detect the format of an uploaded file.

    Content sniff takes priority over extension when they conflict (a real PDF
    magic number beats a misleading name), but a matching extension raises
    confidence.
    """
    ext = _ext(filename)
    head = (data or b"")[:2048]

    # --- content sniff ---
    is_pdf_magic = head[:5] == b"%PDF-"
    lowered = head.lower()
    looks_html = (
        b"<!doctype html" in lowered
        or b"<html" in lowered
        or b"<table" in lowered
        or b"<td" in lowered
        or b"<xbrl" in lowered  # inline-XBRL 10-K wrappers are HTML documents
    )

    if is_pdf_magic:
        confident = ext in _PDF_EXTS
        return DetectionResult(
            SourceFormat.PDF,
            "Detected PDF magic number (%PDF-)."
            + ("" if confident else f" (extension was '{ext or 'none'}')"),
            confident=True,
        )

    if looks_html:
        confident = ext in _HTML_EXTS
        return DetectionResult(
            SourceFormat.HTML,
            "Detected HTML markup in content."
            + ("" if confident else f" (extension was '{ext or 'none'}')"),
            confident=confident,
        )

    # --- fall back to extension when content was inconclusive ---
    if ext in _PDF_EXTS:
        return DetectionResult(
            SourceFormat.PDF, "Matched .pdf extension (no magic number seen).",
            confident=False,
        )
    if ext in _HTML_EXTS:
        return DetectionResult(
            SourceFormat.HTML, "Matched HTML extension (no markup sniffed).",
            confident=False,
        )

    return DetectionResult(
        SourceFormat.UNSUPPORTED,
        f"Unsupported file: extension '{ext or 'none'}' and no HTML/PDF content "
        "signature detected. Upload a text-based HTML or PDF filing.",
        confident=True,
    )
