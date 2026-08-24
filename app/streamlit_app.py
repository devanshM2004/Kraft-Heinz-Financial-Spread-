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

    st.divider()
    st.caption(
        "Next phases (not built yet): Claude maps raw rows → standardized "
        "categories (classification only), Python computes ratios & validations, "
        "you review, then export to Excel."
    )


# Streamlit executes this module top-to-bottom as __main__ on every rerun.
main()
