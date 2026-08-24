"""
Claude mapping step (Phase 3).

Public surface:
    ClaudeMapper                 -- calls Claude (inject client, or from_env())
    build_mapping_inputs(...)    -- selected raw tables -> MappingInputRows
    validate_and_bind(...)       -- pure: validate response + bind to raw rows
    is_api_key_available()       -- check ANTHROPIC_API_KEY without constructing
    exceptions: MappingError, MissingAPIKeyError, MappingSchemaError,
                MappingRefusalError, MappingTransportError
    models: MappingInputRow, MappingReviewRow, MappingResult
"""

from .claude_mapper import (
    ClaudeMapper,
    MappingError,
    MappingRefusalError,
    MappingSchemaError,
    MappingTransportError,
    MissingAPIKeyError,
    build_mapping_inputs,
    is_api_key_available,
    validate_and_bind,
)
from .models import MappingInputRow, MappingResult, MappingReviewRow

__all__ = [
    "ClaudeMapper",
    "build_mapping_inputs",
    "validate_and_bind",
    "is_api_key_available",
    "MappingError",
    "MissingAPIKeyError",
    "MappingSchemaError",
    "MappingRefusalError",
    "MappingTransportError",
    "MappingInputRow",
    "MappingReviewRow",
    "MappingResult",
]
