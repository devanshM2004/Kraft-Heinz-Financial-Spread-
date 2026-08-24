"""
Lightweight scale / currency detection (Phase 5).

Scans nearby text for common notes like "in millions", "in thousands",
"dollars in millions", and a currency symbol/name. Deliberately simple — when
nothing is detected it returns (None, None) so the caller keeps 'unknown'/None
and can surface that.
"""

from __future__ import annotations

from typing import Optional

from core.schema import SourceScale

_SCALE_PATTERNS = [
    ("in thousands", SourceScale.THOUSANDS),
    ("thousands of", SourceScale.THOUSANDS),
    ("in millions", SourceScale.MILLIONS),
    ("millions of", SourceScale.MILLIONS),
    ("in billions", SourceScale.BILLIONS),
    ("billions of", SourceScale.BILLIONS),
]


def detect_scale_currency(text: str) -> tuple[Optional[SourceScale], Optional[str]]:
    """Return (scale, currency) detected in `text`, or (None, None)."""
    if not text:
        return None, None
    low = text.lower()

    scale: Optional[SourceScale] = None
    for needle, value in _SCALE_PATTERNS:
        if needle in low:
            scale = value
            break

    currency: Optional[str] = None
    if "$" in text or "u.s. dollar" in low or "us dollar" in low or \
            "in usd" in low or "dollars" in low or "usd" in low:
        currency = "USD"
    elif "€" in text or "euro" in low or "eur" in low:
        currency = "EUR"
    elif "£" in text or "gbp" in low or "pound sterling" in low:
        currency = "GBP"

    return scale, currency
