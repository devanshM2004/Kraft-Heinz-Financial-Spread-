"""
Excel export (Phase 6).

Public surface:
    build_workbook(...)        -- openpyxl Workbook from reviewed, computed data
    build_workbook_bytes(...)  -- same, returned as .xlsx bytes
    workbook_to_bytes(wb)
"""

from .excel import build_workbook, build_workbook_bytes, workbook_to_bytes

__all__ = ["build_workbook", "build_workbook_bytes", "workbook_to_bytes"]
