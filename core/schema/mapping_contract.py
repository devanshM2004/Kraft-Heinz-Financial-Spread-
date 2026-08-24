"""
The strict JSON contract for Claude's mapping output (Phase 1).

This is the schema Claude MUST conform to. It is deliberately minimal so the
model's only degrees of freedom are: pick a category, pick a confidence, give a
short rationale — per row_id. There is no place in this schema to put a number,
by construction.

Usage in later phases (not Phase 1):
    - Passed to the Messages API as a structured-output format / strict tool
      schema so the model is constrained to exactly this shape.
    - Every response is re-validated against MAPPING_OUTPUT_SCHEMA on our side
      before we trust it (defense in depth).
"""

from __future__ import annotations

from .categories import ALLOWED_CATEGORY_VALUES
from .status import Confidence

CONFIDENCE_VALUES = [c.value for c in Confidence]

# JSON Schema (draft 2020-12 compatible) for the model's ENTIRE output.
MAPPING_OUTPUT_SCHEMA: dict = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "CreditSpreadMappingOutput",
    "description": (
        "Classification-only output. Maps each raw extracted row to a "
        "standardized category. Contains NO financial values by design."
    ),
    "type": "object",
    "additionalProperties": False,
    "required": ["mappings"],
    "properties": {
        "mappings": {
            "type": "array",
            "description": "Exactly one decision per input row_id.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "row_id",
                    "standardized_category",
                    "confidence",
                    "rationale",
                ],
                "properties": {
                    "row_id": {
                        "type": "string",
                        "description": (
                            "Echo the row_id from the input verbatim. Do not "
                            "invent, merge, or renumber rows."
                        ),
                    },
                    "standardized_category": {
                        "type": "string",
                        "enum": ALLOWED_CATEGORY_VALUES,
                        "description": (
                            "The single best category. Use 'unmapped' for a "
                            "financial line you cannot confidently place, and "
                            "'ignore' for non-data rows (headers, blanks, notes)."
                        ),
                    },
                    "confidence": {
                        "type": "string",
                        "enum": CONFIDENCE_VALUES,
                        "description": "How sure you are of THIS category choice.",
                    },
                    "rationale": {
                        "type": "string",
                        "maxLength": 280,
                        "description": (
                            "One short sentence citing the raw label wording "
                            "that drove the choice. Never reference or invent "
                            "numeric values."
                        ),
                    },
                },
            },
        }
    },
}


def build_mapping_output_schema() -> dict:
    """Return a fresh copy of the strict output schema (safe to mutate)."""
    import copy

    return copy.deepcopy(MAPPING_OUTPUT_SCHEMA)
