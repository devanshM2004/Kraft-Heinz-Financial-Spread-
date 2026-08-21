"""
Standardized credit-spread schema (Phase 1).

Public surface:
    categories      -- the standardized category vocabulary + metadata
    status          -- confidence, severity, validation codes, ValidationFinding
    records         -- MappingDecision (Contract A), SpreadItem (Contract B),
                       StandardizedSpread
    mapping_contract-- strict JSON Schema for Claude's output
    ratios          -- ratio + derived-quantity specifications
"""

from .categories import (
    ALLOWED_CATEGORY_VALUES,
    CATALOG_BY_CATEGORY,
    CATEGORY_CATALOG,
    CategoryMeta,
    CategoryRole,
    StandardizedCategory,
    StatementType,
    categories_for_statement,
    categories_with_role,
    component_categories,
    subtotal_categories,
)
from .mapping_contract import (
    MAPPING_OUTPUT_SCHEMA,
    build_mapping_output_schema,
)
from .ratios import (
    DERIVED_QUANTITIES,
    DERIVED_BY_NAME,
    NOT_CALCULATED,
    RATIO_SPECS,
    RATIO_SPECS_BY_NAME,
    DerivedQuantity,
    RatioSpec,
)
from .records import (
    MappingDecision,
    SpreadItem,
    StandardizedSpread,
)
from .status import (
    Confidence,
    DEFAULT_SEVERITY,
    Severity,
    ValidationCode,
    ValidationFinding,
)

__all__ = [
    # categories
    "StandardizedCategory",
    "StatementType",
    "CategoryRole",
    "CategoryMeta",
    "CATEGORY_CATALOG",
    "CATALOG_BY_CATEGORY",
    "ALLOWED_CATEGORY_VALUES",
    "categories_for_statement",
    "categories_with_role",
    "subtotal_categories",
    "component_categories",
    # status
    "Confidence",
    "Severity",
    "ValidationCode",
    "ValidationFinding",
    "DEFAULT_SEVERITY",
    # records
    "MappingDecision",
    "SpreadItem",
    "StandardizedSpread",
    # mapping contract
    "MAPPING_OUTPUT_SCHEMA",
    "build_mapping_output_schema",
    # ratios
    "RatioSpec",
    "DerivedQuantity",
    "RATIO_SPECS",
    "RATIO_SPECS_BY_NAME",
    "DERIVED_QUANTITIES",
    "DERIVED_BY_NAME",
    "NOT_CALCULATED",
]
