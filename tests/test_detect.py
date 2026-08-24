"""Phase 2 — file type detection tests."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest.detect import detect_format
from core.ingest.models import SourceFormat

_failures: list[str] = []


def check(name: str, cond: bool) -> None:
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")
    if not cond:
        _failures.append(name)


def test_detect() -> None:
    print("file type detection:")
    html = b"<!DOCTYPE html><html><body><table><tr><td>x</td></tr></table></body></html>"
    pdf = b"%PDF-1.7\n...binary..."

    r = detect_format("filing.html", html)
    check("html by ext+content -> HTML", r.source_format == SourceFormat.HTML and r.is_supported)

    r = detect_format("filing.pdf", pdf)
    check("pdf by ext+magic -> PDF", r.source_format == SourceFormat.PDF and r.is_supported)

    # Content sniff beats a misleading extension.
    r = detect_format("mislabeled.txt", pdf)
    check("pdf magic under .txt -> PDF", r.source_format == SourceFormat.PDF)

    r = detect_format("page.htm", b"<table><tr><td>1</td></tr></table>")
    check("html content, .htm -> HTML", r.source_format == SourceFormat.HTML)

    # Unsupported.
    r = detect_format("data.csv", b"a,b,c\n1,2,3\n")
    check("csv -> UNSUPPORTED", r.source_format == SourceFormat.UNSUPPORTED and not r.is_supported)

    r = detect_format("image.png", b"\x89PNG\r\n\x1a\n")
    check("png -> UNSUPPORTED", r.source_format == SourceFormat.UNSUPPORTED)

    # HTML extension with no markup falls back on extension (low confidence).
    r = detect_format("weird.html", b"just some text, no tags")
    check("html ext, no markup -> HTML (fallback)", r.source_format == SourceFormat.HTML and not r.confident)


def main() -> int:
    test_detect()
    print()
    if _failures:
        print(f"FAILED ({len(_failures)}): " + ", ".join(_failures))
        return 1
    print("All detection checks passed.")
    return 0


def test_all():
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
