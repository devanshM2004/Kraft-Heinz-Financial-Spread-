"""
Deterministic number parsing (Phase 2).

Turns a raw cell string into a ParsedNumber. This is pure, deterministic Python —
no LLM, no guessing beyond documented rules. It preserves the SOURCE figure:

  * Parentheses are the source's own way of showing a negative, so "(1,234)"
    parses to -1234 and is flagged is_negative_paren. This is faithful parsing of
    what the filing displays — NOT the category-based sign normalization that
    happens later in Phase 3/4.
  * Blanks and dash-only cells ("", "-", "—", "n/a") are "not present" (value
    None), which is distinct from a real zero.

Handled: thousands separators (comma), currency symbols ($ € £ ¥), leading and
unicode minus, parentheses-negatives, trailing footnote markers, percent signs,
and decimals.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Tokens that mean "no value in this cell" (after stripping/lowercasing).
_ABSENT_TOKENS = {"", "-", "–", "—", "−", "n/a", "na", "nm", "—", "n.a.", "n.m."}

# A signed decimal number: either comma-grouped thousands (1,234[,567]) or a
# plain run of digits (1000). The comma branch must come first, but the plain
# branch handles integers of any length so "1000" is not truncated to "100".
_NUMBER_RE = re.compile(r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?")

_CURRENCY_CHARS = "$€£¥"


@dataclass
class ParsedNumber:
    raw: str
    value: Optional[float]      # None when not present / unparseable
    is_present: bool            # True only when a number was successfully parsed
    is_negative_paren: bool = False
    is_percent: bool = False
    was_blank: bool = False     # True for empty / dash / n-a cells (a real absence)

    @property
    def unparseable(self) -> bool:
        """Had non-blank content but no number could be extracted (e.g. text)."""
        return (not self.is_present) and (not self.was_blank) and bool(self.raw.strip())


def parse_number(text: Optional[str]) -> ParsedNumber:
    """Parse one raw cell string into a ParsedNumber (deterministic)."""
    if text is None:
        return ParsedNumber(raw="", value=None, is_present=False, was_blank=True)

    raw = str(text)
    stripped = raw.strip()

    # Normalize whitespace and a unicode minus for token comparison.
    low = stripped.lower().replace("\xa0", " ").strip()

    if low in _ABSENT_TOKENS:
        return ParsedNumber(raw=raw, value=None, is_present=False, was_blank=True)

    is_percent = "%" in stripped

    # Detect parenthesis-negative: a leading "(" and trailing ")" wrapping.
    paren_negative = bool(re.match(r"^\(.*\)$", stripped))

    # Strip currency symbols, spaces, non-breaking spaces, and percent for parsing.
    cleaned = stripped
    for ch in _CURRENCY_CHARS:
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.replace("\xa0", " ").replace("%", "")
    # Unicode minus -> ASCII minus.
    cleaned = cleaned.replace("−", "-").replace("–", "-")

    # Find the first number token (ignores trailing footnote markers like "(a)").
    match = _NUMBER_RE.search(cleaned)
    if not match:
        # Non-blank content but no numeric token (e.g. a text label).
        return ParsedNumber(raw=raw, value=None, is_present=False, is_percent=is_percent)

    token = match.group(0).replace(",", "")
    try:
        value = float(token)
    except ValueError:
        return ParsedNumber(raw=raw, value=None, is_present=False, is_percent=is_percent)

    if paren_negative:
        value = -abs(value)

    return ParsedNumber(
        raw=raw,
        value=value,
        is_present=True,
        is_negative_paren=paren_negative,
        is_percent=is_percent,
    )


def looks_numeric(text: Optional[str]) -> bool:
    """True if the cell parses to a present number."""
    return parse_number(text).is_present
