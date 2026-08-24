"""
Prompts for the Claude mapping step (Phase 3).

Claude's ONLY job is classification: map each raw extracted row to one
standardized category. It must never return, invent, adjust, or correct a
number. The values shown to it are read-only disambiguation context.

The strict JSON Schema (Phase 1) is what actually constrains the output shape;
these prompts explain the task and the rules in plain language so the model
maps well.
"""

from __future__ import annotations

import json

from core.schema import CATEGORY_CATALOG, CategoryRole

SYSTEM_PROMPT = """\
You are a financial-statement classification assistant for a bank credit-spread
tool. Your ONLY job is to map each raw line item to exactly one standardized
category.

Hard rules:
1. You classify only. You must NOT output, repeat, invent, adjust, or "correct"
   any financial number. Your response schema has no field for a value — do not
   attempt to include one.
2. Return exactly one decision per input row_id. Echo each row_id back verbatim.
   Do not add, drop, merge, split, or renumber rows.
3. The numeric values shown to you are READ-ONLY context to help you disambiguate
   similar labels. They are owned by the deterministic pipeline, not by you.
4. Choose the single best category from the allowed list. When a row is a real
   financial line but you cannot confidently place it, use "unmapped". When a row
   is not a data line (a section header, a blank row, or narrative/footnote text),
   use "ignore". Never guess a specific category you are unsure of — prefer
   "unmapped" so a human can review it.
5. Confidence reflects how sure you are of THIS category choice:
   "high" = the label unambiguously matches; "medium" = a reasonable match with
   some ambiguity; "low" = weak/uncertain.
6. The rationale is one short sentence citing the label wording that drove your
   choice. Never reference or restate numeric values in the rationale.
"""


def _category_reference() -> str:
    """A compact reference of allowed categories grouped by statement."""
    lines: list[str] = []
    by_stmt: dict[str, list[str]] = {}
    for meta in CATEGORY_CATALOG:
        tag = ""
        if meta.is_subtotal:
            tag = " [subtotal]"
        elif CategoryRole.CONTROL in meta.roles:
            tag = " [control]"
        by_stmt.setdefault(meta.statement.value, []).append(
            f"  - {meta.category.value}: {meta.label}{tag}"
        )
    for stmt, rows in by_stmt.items():
        lines.append(f"{stmt}:")
        lines.extend(rows)
    return "\n".join(lines)


def build_user_prompt(input_rows: list[dict]) -> str:
    """
    Build the user message. `input_rows` is a list of dicts, each with:
        row_id, statement_type, raw_label, values (dict period_label -> number|null)
    Values are provided as read-only context only.
    """
    rows_json = json.dumps(input_rows, indent=2, ensure_ascii=False)
    return f"""\
Map each of the following raw financial-statement rows to one standardized
category. Return ONLY the structured JSON object required by the response schema
(an object with a "mappings" array; one entry per row_id).

Allowed standardized categories (choose exactly one per row):
{_category_reference()}

Rows to classify (row_id, statement_type, raw_label, and read-only values):
{rows_json}

Remember: classify only. Do not output any numbers. Echo each row_id exactly.
Use "unmapped" for uncertain financial lines and "ignore" for non-data rows.
"""
