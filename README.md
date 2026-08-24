# AI Financial Statement Spreader

A local **Streamlit** app that "spreads" a public-company financial statement the
way a bank credit analyst would. You upload a **10-K / 10-Q** filing; the tool
extracts the financial-statement tables, uses **Claude to map raw line items to
standardized spread categories**, computes credit ratios and validation checks
**deterministically in Python**, lets a **human review and correct** the mapping,
and exports a clean **Excel credit-spread workbook**.

> Educational portfolio project. **Public-company or synthetic data only — never
> real borrower data.** Not a real bank credit model and not a credit decision.
> The output always requires human review.

---

## 1. Project overview

**What it does** — turns a messy filing into a standardized, auditable credit
spread: normalized income-statement and balance-sheet line items, computed ratios
(current ratio, debt-to-equity, debt-to-EBITDA, EBITDA margin, net margin,
revenue growth, and an **Approximate DSCR**), validation checks (balance-sheet
balance, subtotal footing, missing categories, low-confidence/unmapped rows), and
an Excel workbook in the spirit of a bank spread.

**Who it's for** — credit analysts, commercial-banking / underwriting teams, and
anyone who spreads financials and wants an AI assist without handing the numbers
to an AI. It's also a portfolio piece demonstrating responsible, auditable use of
an LLM in a finance workflow.

**Why it's relevant to credit analysis** — spreading is repetitive and
error-prone: the same line items get re-keyed and re-categorized for every
borrower. An LLM is genuinely good at the *classification* part (which raw label
is "SG&A"?) but must **never** be trusted with the arithmetic. This tool draws
that line hard: AI classifies, Python computes, a human signs off.

---

## 2. Responsible AI design (the core principle)

This matters more than any feature:

- **Claude maps/classifies only.** Its entire job is to pick which standardized
  category a raw line item belongs to (with a confidence flag and a short
  rationale).
- **Claude never returns, invents, adjusts, or "corrects" a number.** The strict
  JSON contract it must return has *no field for a value* — a numeric value in the
  response is rejected by schema validation before it is ever trusted.
- **Python owns every number.** Extraction reads the source values; Python binds
  them to categories by `row_id`, derives the calculation-normalized values,
  computes all subtotals/ratios, runs all validation checks, and writes the Excel.
- **Every figure is traceable** to a source cell (page/table/row/column, raw
  label, mapped category, confidence).
- **Human-in-the-loop.** The analyst reviews and can override any mapping; the
  reviewed mapping (not Claude's original) drives the computed spread. Export is
  gated behind that review.

`source_value` (exactly as displayed in the filing) is preserved separately from
`calculation_value` (Python's sign-normalized figure used for math), so the audit
trail always shows the original figure.

---

## 3. Workflow

1. **Upload** a filing (HTML or text-based PDF).
2. **Preview** the deterministically extracted tables (raw rows, parsed values,
   source references).
3. **Select** which table is the Income Statement and which is the Balance Sheet.
4. **Run AI mapping** — Claude classifies each raw row into a standardized
   category (classification only).
5. **Review / edit** the mapping — override any category; overrides persist and
   are audited (original vs. reviewed, confidence, reviewer note).
6. **View deterministic calculations & validations** — ratios per period and a
   pass/fail validation summary, recomputed from your reviewed mapping.
7. **Export** the Excel credit-spread workbook.

---

## 4. How to run

```bash
pip install -r requirements.txt
```

Set your Anthropic API key (used only for the mapping step; read from the
environment, never stored or committed):

```bash
# macOS / Linux
export ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app/streamlit_app.py
```

```powershell
# Windows PowerShell
$env:ANTHROPIC_API_KEY="sk-ant-..."
streamlit run app/streamlit_app.py
```

The app opens at http://localhost:8501. A synthetic filing you can upload lives at
`tests/fixtures/synthetic_filing.html`.

**Without an API key** the app still runs — upload, extraction, and preview work;
the AI mapping step shows a clear message and is disabled until the key is set.

Run the test suite (no network, no API calls, no extra dependencies):

```bash
python run_tests.py           # or run any tests/test_*.py file directly
```

---

## 5. Environment variables

| Variable | Purpose | Required |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude API key for the mapping step. Read from the environment only; never stored or committed. | Yes, for AI mapping |
| `SEC_USER_AGENT` | Descriptive User-Agent (`"Your Name your.email@example.com"`) for the **optional/future** SEC EDGAR fetcher only. Not needed for the app. | No |

Copy `.env.example` if you prefer a `.env` file (it is gitignored — never commit it).

---

## 6. Current MVP scope

- Uploaded **HTML** filings (the primary path; SEC 10-K primary documents are HTML).
- **Text-based PDFs** where extraction works (unreliable geometry is surfaced,
  never faked).
- **Income Statement** and **Balance Sheet**.
- **Claude mapping** with a strict JSON contract + confidence + rationale.
- **Human review / edit** of mappings with a full override audit trail.
- **Deterministic** ratios and validation checks.
- **Excel export** (7 tabs: Overview, Income Statement Spread, Balance Sheet
  Spread, Ratios, Validation Checks, Mapping Audit Trail, Raw Extracted Rows).

---

## 7. Intentionally excluded / future work

- Scanned / image PDFs via Claude **vision**.
- **SEC / XBRL** cross-check of extracted figures against ground truth. *(A Phase-0
  EDGAR fetcher exists — `src/edgar_fetcher.py`, `run_phase0.py` — as optional
  scaffolding for this, gated behind `SEC_USER_AGENT`.)*
- **Cash flow statement** (and a CFADS-based DSCR).
- Hosted / multi-user web app.
- Real borrower data.
- Bank-policy-validated scoring or covenant logic.

---

## 8. Disclaimer

This is an **educational portfolio project**. It works on **public-company or
synthetic data only**. It is **not** a real bank credit model, **not** a credit
decision or recommendation, and its output **requires human review**. The
"Approximate DSCR" is a rough estimate from income-statement/balance-sheet inputs
— **not** a bank-quality or CFADS-based DSCR.

---

## 9. Demo checklist

A short run-through before showing the project to someone is in
[`docs/demo_checklist.md`](docs/demo_checklist.md).

---

## Project structure

```
app/streamlit_app.py        # the Streamlit app (upload → preview → map → review → calc → export)
core/
  ingest/                   # deterministic extraction (HTML/PDF), number parsing, scale detection
  schema/                   # standardized categories, strict AI mapping contract, ratio specs
  mapping/                  # Claude mapping step (classification only) + validation/binding
  compute/                  # binding, sign normalization, ratios, validation engine
  review/                   # human review/edit state + override audit trail
  export/                   # openpyxl Excel workbook
scripts/live_mapping_smoke.py   # optional live API smoke test (not part of the suite)
src/edgar_fetcher.py, run_phase0.py   # optional/future SEC EDGAR fetcher
tests/                      # deterministic tests (no network, mocked Claude)
docs/schema.md              # schema & contract documentation
```

## How the number-integrity guarantee is enforced

- The AI response schema (`core/schema/mapping_contract.py`) has
  `additionalProperties: false` and **no value field** — a smuggled number is
  rejected (tested).
- `core/mapping/` validates every response, rejects out-of-vocabulary categories,
  duplicate/hallucinated/missing `row_id`s, and fills omitted rows as `unmapped`
  for review rather than guessing.
- `core/compute/` binds Python-owned source values by `row_id` and derives every
  calculation and ratio deterministically.
