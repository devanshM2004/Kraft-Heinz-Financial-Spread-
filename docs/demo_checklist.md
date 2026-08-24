# Demo checklist

A quick run-through before showing the **AI Financial Statement Spreader** to
someone (boss, recruiter, hiring manager). Everything here uses synthetic or
public-company data only.

## Before the demo

- [ ] **Install dependencies**
  ```bash
  pip install -r requirements.txt
  ```
- [ ] **Set your Anthropic API key** (read from the environment; never commit it)
  ```bash
  # macOS / Linux
  export ANTHROPIC_API_KEY="sk-ant-..."
  # Windows PowerShell
  $env:ANTHROPIC_API_KEY="sk-ant-..."
  ```
- [ ] **Run the live mapping smoke test** (tiny, real API call — confirms the key
      works and Claude returns no numbers). Skips cleanly if the key is unset.
  ```bash
  python scripts/live_mapping_smoke.py
  ```
  Expect: `LIVE SMOKE TEST: PASSED` and a small mappings JSON with no numeric values.
- [ ] *(Optional)* **Run the test suite** (no network, no API):
  ```bash
  python run_tests.py
  ```

## The demo

- [ ] **Start the app**
  ```bash
  streamlit run app/streamlit_app.py
  ```
  It opens at http://localhost:8501.
- [ ] **Upload a filing** — use `tests/fixtures/synthetic_filing.html`, or a real
      public 10-K/10-Q (HTML or text-based PDF).
- [ ] **Confirm extraction** — two financial tables are found; the cover/non-data
      table is skipped; parsed values and source references show in the preview.
- [ ] **Select the statements** — pick the Income Statement table and the Balance
      Sheet table (auto-defaulted by heading).
- [ ] **Run mapping** — click *Run AI mapping (Claude)*; note the model used (and
      any fallback banner). **No API key / no credits?** Click *Use Demo Mapping*
      instead — it produces deterministic, clearly-labelled sample mappings with
      no API call, and the rest of the workflow (review, calculations, export)
      works identically.
- [ ] **Review / edit mappings** — override a category in the dropdown; watch the
      *human_override* flag set and the review status update. Try *Reset to Claude
      suggestions* and *Mark review complete*.
- [ ] **View deterministic calculations & validation** — confirm ratios by period
      and the PASS/FAIL validation summary; note DSCR shows *"Not calculated /
      requires debt service input"* when inputs are missing.
- [ ] **Generate the Excel workbook** — click *Generate Excel workbook*, then
      *Download*.
- [ ] **Open the workbook** and confirm the 7 tabs export correctly:
  - [ ] Overview (notes: synthetic-only, AI-maps-only, human-review-required)
  - [ ] Income Statement Spread (source_value in blue, calculation_value in black)
  - [ ] Balance Sheet Spread
  - [ ] Ratios (Approximate DSCR labelled; not-calculated text where applicable)
  - [ ] Validation Checks (severity-coloured findings + pass/fail summary)
  - [ ] Mapping Audit Trail (original vs. reviewed category, overrides highlighted)
  - [ ] Raw Extracted Rows

## Talking points

- Claude **only classifies**; it never returns or changes a number (enforced by
  the strict JSON schema).
- **Python owns** every extracted value, calculation, validation, and the Excel.
- **Human review** drives the final numbers and is required before export.
- Every figure is **traceable** to its source cell.
