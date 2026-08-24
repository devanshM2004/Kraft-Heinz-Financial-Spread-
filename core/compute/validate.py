"""
Deterministic validation checks (Phase 4).

Produces ValidationFindings; NEVER mutates or "fixes" a number. Checks:
  * balance sheet balance: total_assets = total_liabilities + total_equity
  * subtotal footing (where components are available)
  * missing required categories
  * duplicate mappings
  * low-confidence mappings
  * unmapped rows
  * ratios that cannot be calculated
"""

from __future__ import annotations

from typing import Optional

from core.schema import (
    CATEGORY_CATALOG,
    CATALOG_BY_CATEGORY,
    Confidence,
    DEFAULT_SEVERITY,
    Severity,
    SpreadItem,
    StandardizedCategory as SC,
    ValidationCode,
    ValidationFinding,
)

from .aggregate import SpreadValues
from .ratios import RatioValue, STATUS_NOT_CALCULABLE

# Categories a meaningful credit spread should contain.
REQUIRED_CATEGORIES = (
    SC.REVENUE, SC.NET_INCOME,
    SC.TOTAL_CURRENT_ASSETS, SC.TOTAL_CURRENT_LIABILITIES,
    SC.TOTAL_ASSETS, SC.TOTAL_LIABILITIES, SC.TOTAL_EQUITY,
)


def _close(a: float, b: float, abstol: float = 1.0, reltol: float = 1e-4) -> bool:
    return abs(a - b) <= max(abstol, reltol * max(abs(a), abs(b)))


def _finding(code: ValidationCode, message: str, *, severity: Optional[Severity] = None,
             period: Optional[str] = None, rows=None, cats=None, details=None) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        severity=severity or DEFAULT_SEVERITY[code],
        message=message,
        fiscal_year=period,
        related_row_ids=list(rows or []),
        related_categories=list(cats or []),
        details=details or {},
    )


def validate_spread(
    items: list[SpreadItem],
    values: SpreadValues,
    ratios: list[RatioValue],
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []

    # --- per-row flags (dedupe by row_id) ---
    seen_rows: set[str] = set()
    for it in items:
        if it.row_id in seen_rows:
            continue
        seen_rows.add(it.row_id)
        if it.standardized_category == SC.UNMAPPED:
            findings.append(_finding(
                ValidationCode.UNMAPPED_ROW,
                f"Row {it.row_id} ({it.raw_label!r}) is unmapped — needs review.",
                rows=[it.row_id]))
        if it.confidence == Confidence.LOW:
            findings.append(_finding(
                ValidationCode.LOW_CONFIDENCE_MAPPING,
                f"Row {it.row_id} ({it.raw_label!r}) mapped with low confidence to "
                f"{it.standardized_category.value}.",
                rows=[it.row_id], cats=[it.standardized_category.value]))

    # --- duplicate mappings (same real category twice in a period) ---
    for meta in CATEGORY_CATALOG:
        cat = meta.category
        if cat in (SC.UNMAPPED, SC.IGNORE):
            continue
        dup_periods = [p for p in values.periods if values.count(cat, p) > 1]
        if dup_periods:
            findings.append(_finding(
                ValidationCode.DUPLICATE_MAPPING,
                f"Category {cat.value} is mapped by multiple rows "
                f"(periods: {', '.join(dup_periods)}). Values were summed; verify.",
                cats=[cat.value],
                details={"periods": dup_periods}))

    # --- missing required categories ---
    for cat in REQUIRED_CATEGORIES:
        if not any(values.present(cat, p) for p in values.periods):
            findings.append(_finding(
                ValidationCode.MISSING_REQUIRED_CATEGORY,
                f"Required category {cat.value} is not present in any period.",
                cats=[cat.value]))

    # --- balance sheet balance per period ---
    for p in values.periods:
        ta = values.calc(SC.TOTAL_ASSETS, p)
        tl = values.calc(SC.TOTAL_LIABILITIES, p)
        te = values.calc(SC.TOTAL_EQUITY, p)
        if ta is not None and tl is not None and te is not None:
            if not _close(ta, tl + te):
                findings.append(_finding(
                    ValidationCode.BALANCE_SHEET_IMBALANCE,
                    f"Balance sheet does not balance for {p}: total_assets "
                    f"({ta}) != total_liabilities + total_equity ({tl + te}).",
                    period=p,
                    cats=["total_assets", "total_liabilities", "total_equity"],
                    details={"total_assets": ta, "liabilities_plus_equity": tl + te,
                             "difference": ta - (tl + te)}))
        tle = values.calc(SC.TOTAL_LIABILITIES_AND_EQUITY, p)
        if ta is not None and tle is not None and not _close(ta, tle):
            findings.append(_finding(
                ValidationCode.BALANCE_SHEET_IMBALANCE,
                f"total_liabilities_and_equity ({tle}) != total_assets ({ta}) for {p}.",
                period=p, cats=["total_assets", "total_liabilities_and_equity"],
                details={"total_assets": ta, "total_liabilities_and_equity": tle,
                         "difference": tle - ta}))

    # --- subtotal footing where components are available ---
    for meta in CATEGORY_CATALOG:
        if not meta.is_subtotal or not meta.foots_from:
            continue
        for p in values.periods:
            subtotal = values.calc(meta.category, p)
            if subtotal is None:
                continue
            present_components = [(c, values.calc(c, p)) for c in meta.foots_from
                                  if values.present(c, p)]
            if not present_components:
                continue
            expected = sum(v for _c, v in present_components)
            if _close(expected, subtotal):
                continue
            comp_str = ", ".join(f"{c.value}={v}" for c, v in present_components)
            if expected > subtotal:
                findings.append(_finding(
                    ValidationCode.SUBTOTAL_FOOTING_ISSUE,
                    f"{meta.category.value} for {p} ({subtotal}) is less than the sum "
                    f"of its captured components ({expected}). Possible double mapping.",
                    period=p, cats=[meta.category.value],
                    details={"reported": subtotal, "sum_of_components": expected,
                             "components": comp_str}))
            else:
                findings.append(_finding(
                    ValidationCode.SUBTOTAL_FOOTING_ISSUE,
                    f"{meta.category.value} for {p} ({subtotal}) exceeds the sum of its "
                    f"captured components ({expected}); some components may be missing "
                    "or unmapped.",
                    severity=Severity.WARNING,
                    period=p, cats=[meta.category.value],
                    details={"reported": subtotal, "sum_of_components": expected,
                             "components": comp_str}))

    # --- ratios not calculable ---
    for r in ratios:
        if r.status == STATUS_NOT_CALCULABLE:
            findings.append(_finding(
                ValidationCode.RATIO_NOT_CALCULABLE,
                f"{r.display_name} not calculated for {r.period}: {r.message}",
                period=r.period, details={"ratio": r.name}))

    return findings
