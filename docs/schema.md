# Phase 1 — Standardized Spread Schema & Strict JSON Contract

This document is the human-readable companion to the code in `core/schema/`. It
defines the standardized credit-spread vocabulary and the strict contract that
governs what Claude is allowed to return. **Phase 1 defines shapes only** — no
UI, no Anthropic API call, no extraction, no Excel, no computation.

## The number-integrity design (the whole point)

There are **two** record shapes, and numbers live in only one of them:

### Contract A — `MappingDecision` (what Claude returns)
The model's entire output surface. One decision per extracted row:

| field | type | notes |
|---|---|---|
| `row_id` | string | echoed verbatim from the input row |
| `standardized_category` | enum | one of the fixed category values |
| `confidence` | `high` \| `medium` \| `low` | the confidence flag |
| `rationale` | string (≤280) | one short sentence; must not cite numbers |

There is **no field for a value** — by construction. The JSON Schema
(`core/schema/mapping_contract.py`) sets `additionalProperties: false`, so a
model response that tries to smuggle in a `value` is **rejected** on our side
before we trust it. (There's a test that proves this.)

### Contract B — `SpreadItem` (what Python produces)
After the model returns categories, Python binds the **actual extracted number**
to each `(row_id, fiscal_year)` cell. The value comes from the source table, not
the model.

Audit fields (all requested, in the record):

| field | source | notes |
|---|---|---|
| `row_id` | extraction | ties back to the source row + the mapping decision |
| `statement_type` | extraction | `income_statement` \| `balance_sheet` \| `none` |
| `raw_label` | extraction | verbatim label from the filing |
| `standardized_category` | **model** | the only model-derived field |
| `fiscal_year` | extraction | e.g. `"2024"` |
| `period_label` | extraction | human-friendly, e.g. `"FY2024"` |
| `confidence` | **model** | inherited from the mapping decision |
| `source_table_index` | extraction | provenance |
| `source_row_index` | extraction | provenance |
| `source_column_index` | extraction | which period column the value came from |
| `source_location` | extraction | human-readable pointer |
| `source_scale` | extraction | `units`/`thousands`/`millions`/… as the table reports |
| `currency` | extraction | e.g. `"USD"`, when known |
| `notes` | any | free-form |

**Two numeric fields — source is preserved separately from calculation:**

| field | source | notes |
|---|---|---|
| `source_value` | **Python (extraction)** | the figure **exactly as displayed** in the filing after deterministic parsing — **not** sign-adjusted |
| `calculation_value` | **Python (normalization)** | signed value used for footing/ratios; may differ in sign from `source_value` |
| `value_is_present` | **Python** | distinguishes a real `0` from a blank / "—" cell |

> The only field in a `SpreadItem` that originates from the LLM is
> `standardized_category` (and the `confidence` flag on it). Every number and
> every source reference is produced deterministically by Python. Any output
> number can be walked back to `source_table_index / source_row_index /
> source_column_index`.

## Source value vs. calculation value

The audit trail must preserve the source figure **exactly as extracted**. So the
record keeps two numbers:

- **`source_value`** — the figure as the filing displays it after deterministic
  parsing. It is **never** sign-flipped to make a formula convenient. If the
  income statement shows COGS as a positive `17,000`, `source_value = 17000`.
- **`calculation_value`** — the Python-normalized, signed value used so that a
  subtotal equals the plain arithmetic sum of its `foots_from` components (COGS
  becomes `-17000`, so `revenue + cost_of_goods_sold = gross_profit`). Derived
  deterministically by Python from `source_value` and the standardized category
  — **never** by Claude.

The Excel output (Phase 5) can show either or both. Ratio formulas that intend a
positive debt-service figure (e.g. DSCR) take magnitudes in the compute layer.
`source_scale` records the table's reported scale (thousands/millions); values
are stored **as displayed** — the scale is metadata, not applied to the stored
figure.

## Standardized categories

Defined in `core/schema/categories.py`. Each category carries metadata:
`statement`, `is_subtotal`, `foots_from` (components, for subtotals), and
`roles` (semantic tags like `debt`, `ebitda_input`, `debt_service_input`).

**Income statement:** revenue, cost_of_goods_sold, **gross_profit**,
selling_general_admin, research_development, depreciation_amortization,
other_operating_expense, **operating_income**, interest_expense, interest_income,
other_nonoperating_income_expense, **income_before_taxes**, income_tax_expense,
**net_income**. *(bold = subtotal)*

**Balance sheet — assets:** cash_and_equivalents, short_term_investments,
accounts_receivable, inventory, prepaid_expenses, other_current_assets,
**total_current_assets**, property_plant_equipment_net, goodwill,
intangible_assets, long_term_investments, other_noncurrent_assets,
**total_noncurrent_assets**, **total_assets**.

**Balance sheet — liabilities:** accounts_payable, short_term_debt,
current_portion_long_term_debt, accrued_liabilities, income_taxes_payable,
other_current_liabilities, **total_current_liabilities**, long_term_debt,
deferred_tax_liabilities, other_noncurrent_liabilities,
**total_noncurrent_liabilities**, **total_liabilities**.

**Balance sheet — equity:** common_stock, additional_paid_in_capital,
retained_earnings, treasury_stock, accumulated_oci, noncontrolling_interest,
**total_equity**, **total_liabilities_and_equity**.

**Control categories (always valid choices):**
- `unmapped` — a real financial line the model cannot confidently place.
- `ignore` — a non-data row (section header, blank, footnote text).

## Ratios (specifications only)

Defined in `core/schema/ratios.py`. Phase 1 declares each ratio, its inputs, and
what to emit when inputs are missing. Phase 4 computes them in Python.

| ratio | definition | required inputs |
|---|---|---|
| Current ratio | `total_current_assets / total_current_liabilities` | those two subtotals |
| Debt-to-equity | `total_debt / total_equity` | total_debt*, total_equity |
| Debt-to-EBITDA (approx) | `total_debt / EBITDA` | total_debt*, EBITDA* |
| **Approximate DSCR** | `EBITDA / (interest_expense + current_portion_long_term_debt)` | EBITDA*, interest_expense, current_portion_long_term_debt |
| Revenue growth (YoY) | `revenue_t / revenue_prior − 1` | revenue (two periods) |

`*` **Derived quantities** (also in `ratios.py`):
- **total_debt** = short_term_debt + current_portion_long_term_debt + long_term_debt
- **EBITDA (approx)** = operating_income + depreciation_amortization
  *(fallback: net_income + interest_expense + income_tax_expense + depreciation_amortization)*

### DSCR wording (deliberate)
The MVP's DSCR is labelled **"Approximate DSCR (Estimated Debt Service
Coverage)"** and is **not** a bank-quality / CFADS-based DSCR. If
`interest_expense` or `current_portion_long_term_debt` is not clearly available,
the compute layer reports **"Not calculated / requires debt service input"**
rather than estimating.

## Validation codes (definitions only)

Defined in `core/schema/status.py`. Phase 1 defines them and the
`ValidationFinding` record; Phase 4 computes them.

| code | level | default severity |
|---|---|---|
| `unmapped_row` | item | warning |
| `duplicate_mapping` | item | error |
| `low_confidence_mapping` | item | warning |
| `missing_required_category` | spread | warning |
| `balance_sheet_imbalance` | spread | error |
| `subtotal_footing_issue` | spread | error |
| `ratio_not_calculable` | spread | info |

Findings **describe** problems for the human reviewer; they never mutate
numbers or silently "fix" the spread.

## Examples

Generated by `python examples/generate_examples.py` (synthetic, round numbers —
**not** real Kraft Heinz data):

- `examples/example_mapping_output.json` — Contract A (no numbers).
- `examples/example_spread_items.json` — Contract B (Python-bound, balances and
  foots).

## Files

```
core/schema/
  __init__.py            # public exports
  categories.py          # StandardizedCategory + CATEGORY_CATALOG metadata
  status.py              # Confidence, Severity, ValidationCode, ValidationFinding
  records.py             # MappingDecision (A), SpreadItem (B), StandardizedSpread
  mapping_contract.py    # strict JSON Schema for Claude's output
  ratios.py              # RatioSpec + DerivedQuantity specifications
examples/generate_examples.py
tests/test_schema.py
```

## Tests

`python tests/test_schema.py` verifies catalog consistency, that the strict
contract is valid **and rejects any injected number or bad category**, record
round-trips, and that the synthetic example foots and balances.
