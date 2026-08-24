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
from core.schema import Severity  # noqa: E402

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
    if result is None:
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Rows mapped", len(result.review_rows))
    c2.metric("Unmapped", result.n_unmapped)
    c3.metric("Low confidence", result.n_low_confidence)
    c4.metric("Model used", result.model_used or "—")

    if result.fallback_used:
        st.warning(
            f"⚠️ Fallback used: the primary model "
            f"`{result.primary_model}` was unavailable, so this mapping was "
            f"produced by the fallback model `{result.model_used}`."
        )
    else:
        st.caption(f"Mapping produced by `{result.model_used}` (primary model).")

    df = pd.DataFrame([r.to_dict() for r in result.review_rows])
    st.caption(
        "Suggested mappings — review below. You can override the "
        "`standardized_category` in-place; full edit persistence lands in a "
        "later phase."
    )
    st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "standardized_category": st.column_config.SelectboxColumn(
                "standardized_category", options=ALLOWED_CATEGORY_VALUES,
            ),
        },
        disabled=[c for c in df.columns if c != "standardized_category"],
        key="mapping_editor",
    )

    if result.findings:
        with st.expander(f"Review flags ({len(result.findings)})"):
            for f in result.findings:
                st.write(f"- **{f.severity.value}** · {f.code.value} — {f.message}")


def deterministic_calculations(doc: RawDocument) -> None:
    st.divider()
    st.subheader("4 · Deterministic Calculations & Validation")
    st.write(
        "All numbers, ratios, and checks below are computed in Python from the "
        "extracted source values — Claude is not involved. `source_value` is "
        "preserved exactly; `calculation_value` is the sign-normalized figure "
        "used for the math."
    )

    result = st.session_state.get("mapping_result")
    inc = st.session_state.get("selected_income_table")
    bal = st.session_state.get("selected_balance_table")
    if result is None or inc is None or bal is None or inc == bal:
        st.info("Run AI mapping above (with distinct statements selected) to enable "
                "deterministic calculations.")
        return

    decisions_by_id = {d.row_id: d for d in result.decisions}
    compute = compute_spread(doc.tables[inc], doc.tables[bal], decisions_by_id)

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

    st.divider()
    st.caption(
        "Next phase (not built yet): export the reviewed spread to Excel. "
        "Numbers are always Python-owned; Claude only classifies."
    )


# Streamlit executes this module top-to-bottom as __main__ on every rerun.
main()
