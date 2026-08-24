"""
Streamlit upload/preview app (Phase 2).

Scope (deliberately limited):
  * Upload an HTML or text-based PDF filing.
  * Detect the format; reject unsupported files clearly.
  * Deterministically extract financial-statement tables.
  * Preview every table's raw rows, parsed values, and source references.
  * Let the reviewer pick which table is the Income Statement and which is the
    Balance Sheet.

NOT in this phase: no Anthropic API call, no category mapping, no ratio
computation, no Excel export. Those are Phases 3–6.

Run:
    pip install -r requirements.txt
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import streamlit as st

# Make the project importable when run via `streamlit run app/streamlit_app.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.ingest import extract_document  # noqa: E402
from core.ingest.models import RawDocument, RawTable, SourceFormat  # noqa: E402
from core.mapping import (  # noqa: E402
    ClaudeMapper,
    MappingError,
    MissingAPIKeyError,
    build_mapping_inputs,
    is_api_key_available,
)
from core.schema import ALLOWED_CATEGORY_VALUES  # noqa: E402
from core.compute import compute_spread  # noqa: E402
from core.schema import Severity, StandardizedCategory  # noqa: E402
from core.review import ReviewState  # noqa: E402
from core.export import build_workbook_bytes  # noqa: E402
from datetime import datetime, timezone  # noqa: E402

st.set_page_config(page_title="Credit Spread Builder — Extraction", layout="wide")


def _human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{n} B"


def _table_label(t: RawTable) -> str:
    head = t.heading or "(no heading)"
    where = f" [p.{t.page_number}]" if t.page_number else ""
    return f"Table {t.table_index}: {head}{where} — {t.n_data_rows} rows, {t.n_value_columns} periods"


def render_table(t: RawTable) -> None:
    st.markdown(f"**Table {t.table_index}** — {t.heading or '(no heading)'}"
                + (f"  ·  page {t.page_number}" if t.page_number else ""))
    meta = f"periods: {t.period_labels or '—'}  ·  value columns: {t.n_value_columns}  ·  data rows: {t.n_data_rows}"
    st.caption(meta)
    for w in t.warnings:
        st.warning(w)
    df = pd.DataFrame(t.preview_rows())
    st.dataframe(df, use_container_width=True, hide_index=True)


def statement_pickers(doc: RawDocument) -> None:
    st.subheader("2 · Identify statements")
    st.write("Select which extracted table looks like each statement. "
             "(Mapping happens in a later phase — this only records your choice.)")

    options = list(range(len(doc.tables)))
    labels = {i: _table_label(doc.tables[i]) for i in options}

    def _default(keyword: str) -> int:
        for i, t in enumerate(doc.tables):
            if t.heading and keyword in t.heading.lower():
                return i
        return 0

    col1, col2 = st.columns(2)
    with col1:
        inc = st.selectbox(
            "Income Statement table",
            options, index=_default("income"),
            format_func=lambda i: labels[i], key="income_table",
        )
    with col2:
        bal = st.selectbox(
            "Balance Sheet table",
            options, index=_default("balance"),
            format_func=lambda i: labels[i], key="balance_table",
        )

    if inc == bal:
        st.error("Income Statement and Balance Sheet must be different tables.")
    else:
        st.success(
            f"Recorded — Income Statement: Table {inc} "
            f"({doc.tables[inc].heading}); Balance Sheet: Table {bal} "
            f"({doc.tables[bal].heading})."
        )
        st.session_state["selected_income_table"] = inc
        st.session_state["selected_balance_table"] = bal


def ai_mapping_review(doc: RawDocument) -> None:
    st.divider()
    st.subheader("3 · AI Mapping Review")
    st.write(
        "Claude classifies each raw row into a standardized category. It only "
        "chooses a category — it never returns, creates, or adjusts a number. "
        "All values shown here come from Python's deterministic extraction."
    )

    inc = st.session_state.get("selected_income_table")
    bal = st.session_state.get("selected_balance_table")
    if inc is None or bal is None or inc == bal:
        st.info("Select distinct Income Statement and Balance Sheet tables above "
                "to enable AI mapping.")
        return

    if not is_api_key_available():
        st.warning(
            "**ANTHROPIC_API_KEY is not set**, so AI mapping is disabled. "
            "Set it and rerun:\n\n"
            "```bash\nexport ANTHROPIC_API_KEY=\"sk-ant-...\"\nstreamlit run app/streamlit_app.py\n```\n\n"
            "The key is read from the environment only — it is never stored or "
            "committed."
        )
        return

    if st.button("Run AI mapping", type="primary"):
        inputs = build_mapping_inputs(doc.tables[inc], doc.tables[bal])
        try:
            mapper = ClaudeMapper.from_env()
            with st.spinner(f"Mapping {len(inputs)} rows with Claude…"):
                result = mapper.map(inputs)
            st.session_state["mapping_result"] = result
            st.session_state["review_state"] = ReviewState.from_mapping_result(result)
            st.session_state["review_editor_nonce"] = \
                st.session_state.get("review_editor_nonce", 0) + 1
        except MissingAPIKeyError as exc:
            st.error(str(exc))
            return
        except MappingError as exc:
            st.error(f"Mapping failed: {exc}")
            details = getattr(exc, "details", None)
            if details:
                st.code("\n".join(details))
            return

    result = st.session_state.get("mapping_result")
    review: Optional[ReviewState] = st.session_state.get("review_state")
    if result is None or review is None:
        return

    if result.fallback_used:
        st.warning(
            f"⚠️ Fallback used: the primary model `{result.primary_model}` was "
            f"unavailable, so this mapping was produced by the fallback model "
            f"`{result.model_used}`."
        )
    else:
        st.caption(f"Mapping produced by `{result.model_used}` (primary model).")

    st.markdown(
        "Review and **override** the standardized category as needed. Your edits "
        "are saved and drive the calculations below — the numbers recompute from "
        "your reviewed mapping. Claude's original suggestion is kept for audit."
    )

    # Build the editable table from the persisted review state.
    review_rows = review.rows()
    period_keys: list[str] = []
    for r in review_rows:
        for p in r.values:
            if p not in period_keys:
                period_keys.append(p)

    df_rows = []
    for r in review_rows:
        rec = {
            "row_id": r.row_id,
            "statement": r.statement_type.value,
            "raw_label": r.raw_label,
            "original_category": r.original_category.value,
            "reviewed_category": r.reviewed_category.value,
            "human_override": r.human_override,
            "confidence": r.original_confidence.value,
            "reviewer_note": r.reviewer_note or "",
            "source_ref": r.source_ref,
        }
        for p in period_keys:
            rec[f"value[{p}]"] = r.values.get(p)
        df_rows.append(rec)
    df = pd.DataFrame(df_rows)

    editor_key = f"review_editor_{st.session_state.get('review_editor_nonce', 0)}"
    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "reviewed_category": st.column_config.SelectboxColumn(
                "reviewed_category", options=ALLOWED_CATEGORY_VALUES,
                help="Override Claude's suggestion here.",
            ),
            "reviewer_note": st.column_config.TextColumn("reviewer_note"),
        },
        disabled=[c for c in df.columns
                  if c not in ("reviewed_category", "reviewer_note")],
        key=editor_key,
    )

    # Reconcile edits back into the persisted review state.
    for _idx, erow in edited.iterrows():
        rid = erow["row_id"]
        try:
            new_cat = StandardizedCategory(erow["reviewed_category"])
        except ValueError:
            continue
        note = erow.get("reviewer_note") or None
        current = review.get(rid)
        if new_cat != current.reviewed_category or note != current.reviewer_note:
            review.set_category(rid, new_cat, note=note)

    # Controls.
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("Reset all to Claude suggestions"):
            review.reset_all()
            st.session_state["review_editor_nonce"] = \
                st.session_state.get("review_editor_nonce", 0) + 1
            st.rerun()
    with col_b:
        st.checkbox("Mark review complete", key="review_complete")

    # Review status summary.
    summ = review.summary()
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total mapped rows", summ["total_rows"])
    m2.metric("Unmapped", summ["unmapped_rows"])
    m3.metric("Low confidence", summ["low_confidence_rows"])
    m4.metric("Human overrides", summ["human_overrides"])

    ready = summ["clean"] and st.session_state.get("review_complete", False)
    if ready:
        st.success("Review status: **ready for export later** "
                   "(no unmapped rows and marked complete). Export is a later phase.")
    else:
        reasons = []
        if summ["unmapped_rows"]:
            reasons.append(f"{summ['unmapped_rows']} unmapped row(s)")
        if not st.session_state.get("review_complete", False):
            reasons.append("not marked complete")
        st.info("Review status: **not yet ready for export** — "
                + ", ".join(reasons) + ".")


def deterministic_calculations(doc: RawDocument) -> None:
    st.divider()
    st.subheader("4 · Deterministic Calculations & Validation")
    st.write(
        "All numbers, ratios, and checks below are computed in Python from the "
        "extracted source values — Claude is not involved. `source_value` is "
        "preserved exactly; `calculation_value` is the sign-normalized figure "
        "used for the math."
    )

    review: Optional[ReviewState] = st.session_state.get("review_state")
    inc = st.session_state.get("selected_income_table")
    bal = st.session_state.get("selected_balance_table")
    if review is None or inc is None or bal is None or inc == bal:
        st.info("Run AI mapping above (with distinct statements selected) to enable "
                "deterministic calculations.")
        return

    # Use the HUMAN-REVIEWED mapping, not just Claude's original decisions.
    decisions_by_id = review.to_decisions_by_id()
    compute = compute_spread(doc.tables[inc], doc.tables[bal], decisions_by_id,
                             notes_by_id=review.notes_by_id())
    n_over = review.summary()["human_overrides"]
    st.caption(f"Calculations are based on the **reviewed** mapping "
               f"({n_over} human override(s) applied).")

    # Validation summary.
    summ = compute.validation_summary()
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Validation", "PASS" if summ["passed"] else "FAIL")
    s2.metric("Errors", summ["n_errors"])
    s3.metric("Warnings", summ["n_warnings"])
    s4.metric("Info", summ["n_info"])
    if summ["passed"]:
        st.success("No blocking validation errors. Review warnings below before export.")
    else:
        st.error("Validation found blocking errors — see the balance / footing "
                 "findings below. Numbers are NOT auto-corrected.")

    # Ratios by period.
    st.markdown("**Ratios by period**")
    ratios_by_period = compute.ratios_by_period()
    ordered_names = ["current_ratio", "debt_to_equity", "debt_to_ebitda",
                     "ebitda_margin", "net_margin", "approximate_dscr", "revenue_growth"]
    display_names = {}
    rows = []
    for name in ordered_names:
        row = {"ratio": name}
        for period in compute.periods:
            rv = ratios_by_period.get(period, {}).get(name)
            if rv is None:
                row[period] = "—"
            elif rv.status == "ok":
                row[period] = round(rv.value, 4)
                display_names[name] = rv.display_name
            else:
                row[period] = "not calculated"
                display_names[name] = rv.display_name
        row["ratio"] = display_names.get(name, name)
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("DSCR is an **approximate** estimate (EBITDA / (interest expense + "
               "current portion of LTD)); it is not a bank-quality/CFADS DSCR. "
               "Missing inputs show 'not calculated'.")

    # Findings grouped by severity.
    st.markdown("**Validation findings**")
    if not compute.findings:
        st.success("No findings.")
    else:
        buckets = {Severity.ERROR: [], Severity.WARNING: [], Severity.INFO: []}
        for f in compute.findings:
            buckets[f.severity].append(f)
        for sev, emoji in ((Severity.ERROR, "🔴"), (Severity.WARNING, "🟠"),
                           (Severity.INFO, "🔵")):
            fs = buckets[sev]
            if not fs:
                continue
            with st.expander(f"{emoji} {sev.value.title()} ({len(fs)})",
                             expanded=(sev == Severity.ERROR)):
                for f in fs:
                    line = f"**{f.code.value}**"
                    if f.fiscal_year:
                        line += f" · {f.fiscal_year}"
                    st.write(f"- {line} — {f.message}")


def excel_export(doc: RawDocument) -> None:
    st.divider()
    st.subheader("5 · Excel Export")

    review: Optional[ReviewState] = st.session_state.get("review_state")
    inc = st.session_state.get("selected_income_table")
    bal = st.session_state.get("selected_balance_table")
    if review is None or inc is None or bal is None or inc == bal:
        st.info("Complete AI mapping and review above to enable Excel export.")
        return

    # Recompute from the reviewed mapping so the workbook matches the app.
    compute = compute_spread(doc.tables[inc], doc.tables[bal],
                             review.to_decisions_by_id(),
                             notes_by_id=review.notes_by_id())
    summ = review.summary()
    vsumm = compute.validation_summary()

    # Only truly block when there is nothing mapped to export.
    n_mapped = sum(1 for r in review.rows()
                   if r.reviewed_category not in (StandardizedCategory.UNMAPPED,
                                                  StandardizedCategory.IGNORE))
    if n_mapped == 0:
        st.error("Nothing to export yet — no rows are mapped to a standardized "
                 "category. Map/review at least one row first.")
        return

    complete = st.session_state.get("review_complete", False)
    c1, c2, c3 = st.columns(3)
    c1.metric("Review complete", "Yes" if complete else "No")
    c2.metric("Validation errors", vsumm["n_errors"])
    c3.metric("Warnings", vsumm["n_warnings"])

    if not complete:
        st.info("Review is not marked complete. You can still export, but mark it "
                "complete above once you've reviewed the mappings.")
    if vsumm["n_errors"] > 0:
        st.warning(f"⚠️ {vsumm['n_errors']} validation error(s) present "
                   "(e.g. balance-sheet imbalance). You can still export, but the "
                   "workbook will contain unresolved errors — resolve them first "
                   "if possible.")
    st.caption("The exported workbook still **requires human review**. It is for "
               "synthetic/public-company data only.")

    if st.button("Generate Excel workbook", type="primary"):
        data = build_workbook_bytes(
            source_filename=doc.filename,
            income_table=doc.tables[inc],
            balance_table=doc.tables[bal],
            compute=compute,
            review=review,
            generated_at=datetime.now(timezone.utc),
        )
        st.session_state["xlsx_bytes"] = data

    data = st.session_state.get("xlsx_bytes")
    if data:
        stem = Path(doc.filename).stem or "spread"
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "⬇️ Download credit spread (.xlsx)",
            data=data,
            file_name=f"credit_spread_{stem}_{ts}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


def main() -> None:
    st.title("Credit Spread Builder")
    st.caption("Phase 2 — deterministic extraction & preview. No AI mapping, "
               "ratios, or Excel yet.")

    st.subheader("1 · Upload a filing")
    uploaded = st.file_uploader(
        "Upload a 10-K / 10-Q as HTML or text-based PDF",
        type=["html", "htm", "xhtml", "pdf"],
        accept_multiple_files=False,
    )

    if uploaded is None:
        st.info("Upload an HTML or text-based PDF filing to begin. "
                "A synthetic example lives in tests/fixtures/synthetic_filing.html.")
        return

    data = uploaded.getvalue()
    st.write(f"**File:** `{uploaded.name}`  ·  **Size:** {_human_size(len(data))}")

    with st.spinner("Detecting format and extracting tables…"):
        doc = extract_document(uploaded.name, data)

    st.write(f"**Detected format:** `{doc.source_format.value}`")
    for note in doc.notes:
        st.caption(note)

    if doc.source_format == SourceFormat.UNSUPPORTED:
        st.error("Unsupported file. Please upload a text-based HTML or PDF filing.")
        return

    for w in doc.warnings:
        st.warning(w)

    if not doc.tables:
        st.error("No financial tables could be extracted. See the warnings above.")
        return

    st.success(f"Extracted {len(doc.tables)} candidate financial table(s).")

    st.subheader("Extracted tables")
    for t in doc.tables:
        with st.expander(_table_label(t), expanded=(len(doc.tables) <= 2)):
            render_table(t)

    statement_pickers(doc)
    ai_mapping_review(doc)
    deterministic_calculations(doc)
    excel_export(doc)

    st.divider()
    st.caption(
        "Numbers are always Python-owned; Claude only classifies. Scanned-PDF "
        "(vision) support and SEC/XBRL cross-check are future work."
    )


# Streamlit executes this module top-to-bottom as __main__ on every rerun.
main()
