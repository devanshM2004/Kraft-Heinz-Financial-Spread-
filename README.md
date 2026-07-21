# Kraft Heinz Financial Spread Builder

An AI-assisted tool that "spreads" commercial financial statements the way a
bank credit analyst would: it takes a company's filing (10-K), normalizes the
income statement and balance sheet into standardized line items, computes credit
ratios, runs validation checks, and outputs an Excel workbook.

## Core design principles (these outrank features)

1. **The LLM only classifies/maps.** It decides which raw line item maps to
   which standardized spread category. It never invents, adjusts, or "corrects"
   a number. Every figure in the output traces back to a figure in the source.
2. **All math is deterministic Python** — subtotals, ratios, growth rates, and
   validation checks. Never the LLM.
3. **Validation is surfaced, never silently fixed** — the balance sheet must
   balance, subtotals must foot, and failures are reported, not forced.
4. **Every extracted figure carries provenance** — confidence flag, source
   location (page/table/row), original raw label, and mapped category.
5. **Human-in-the-loop**, not full automation.

Test data is **public-company or synthetic only** — never real borrower data.
Primary test case: **The Kraft Heinz Company (KHC)**.

## Build phases

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Data acquisition (SEC EDGAR fetcher) | ✅ Built |
| 1 | Standardized spread schema + strict JSON contract | pending |
| 2 | Extract raw statement tables from the filing | pending |
| 3 | LLM extraction/mapping w/ confidence + source refs | pending |
| 4 | Deterministic ratios, subtotals, validation, XBRL diff | pending |
| 5 | Excel output workbook | pending |
| 6 | Scanned/image PDF support via Claude vision | pending |

---

## Phase 0 — Data acquisition (no Anthropic API)

Phase 0 pulls, for a ticker (default `KHC`):

1. The **latest 10-K primary document** (HTML) from SEC EDGAR.
2. The **XBRL companyfacts JSON** (kept as ground truth for later validation).

It does **not** call the Anthropic API or do any extraction/mapping.

### What it does, step by step

1. Fetches `https://www.sec.gov/files/company_tickers.json` and **resolves the
   CIK from the ticker** (never hardcoded).
2. Zero-pads the CIK to 10 digits and fetches the submissions API:
   `https://data.sec.gov/submissions/CIK{cik10}.json`.
3. Finds the **most recent `10-K`** in `filings.recent`.
4. Builds the primary-document URL:
   `https://www.sec.gov/Archives/edgar/data/{cik}/{accession_nodash}/{doc}`.
5. Downloads the 10-K HTML and the companyfacts JSON:
   `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik10}.json`.
6. Saves every raw artifact under `data/raw/` and prints a summary.

### SEC compliance

- **User-Agent** is sent on *every* request (SEC requires it). The default is
  `Devansh M your.email@example.com`.
  **To change the contact email**, edit `DEFAULT_USER_AGENT` in
  `src/edgar_fetcher.py`, or set the env var:
  ```bash
  export SEC_USER_AGENT="Your Name your-email@example.com"
  ```
- **Rate limiting**: a minimum interval between requests (0.15s ≈ 6.7 req/s)
  keeps us safely below SEC's ~10 req/s ceiling.
- Transient errors (network, 429, 5xx) retry with exponential backoff; policy
  denials (403/407) are reported, never retried or routed around.

### Run it

```bash
pip install -r requirements.txt          # Phase 0 only needs `requests`
python run_phase0.py                      # defaults to KHC
python run_phase0.py --ticker KHC
```

Offline logic checks (no network needed):

```bash
python tests/test_edgar_logic_offline.py
```

### HTML vs. PDF: the input-format decision

The 10-K primary document is **HTML**. The spec allowed either parsing the HTML
tables directly or converting pages to PDF for the `pdfplumber` path. **We
choose to parse the HTML directly** (Phase 2), because:

- SEC 10-K financial statements are **native HTML `<table>`** elements with real
  cell structure — rows, columns, and colspans are recoverable with
  `beautifulsoup4`/`lxml` without any layout guesswork.
- Converting HTML → PDF → text (pdfplumber) throws away that structure and
  reintroduces column-alignment ambiguity that PDF table extraction is
  notoriously fragile about. It's a lossy round trip.
- Keeping the HTML also preserves reliable **source references** (table index,
  row index) for the provenance requirement.

`pdfplumber` still earns its place for genuinely **PDF-native or scanned**
filings, and Claude vision (Phase 6) covers image-only scans. So the tool will
support both paths — but HTML filings go through the HTML parser, not a forced
PDF conversion.

> ### ⚠️ Network requirement / current environment note
> Phase 0 needs outbound HTTPS to `www.sec.gov` and `data.sec.gov`. In some
> managed/proxied environments these hosts are blocked by egress policy — the
> fetcher will report `Access ... denied by an egress proxy (policy block)` and
> exit non-zero rather than fabricate results. If you hit that, allow the SEC
> hosts in the environment's network policy and re-run.

## Project layout

```
.
├── requirements.txt
├── run_phase0.py                     # Phase 0 CLI runner
├── src/
│   └── edgar_fetcher.py              # SEC EDGAR fetcher (Phase 0)
├── tests/
│   └── test_edgar_logic_offline.py   # offline logic checks (no network)
└── data/
    └── raw/                          # fetched raw artifacts (gitignored)
```
