"""
Excel Parser — IO sheets and commissioning worksheets.

Reads all sheets from an xlsx/xls file.
Normalizes column aliases to canonical names.
Returns a list of IORecord objects.
"""
import logging
from pathlib import Path
from typing import List

import openpyxl

from app.models.project_models import IORecord

logger = logging.getLogger(__name__)

# Column alias → canonical name
_COL_MAP = {
    # slot
    "slot": "slot", "slot#": "slot", "slot number": "slot",
    # rack
    "rack": "rack", "rack#": "rack", "rack number": "rack",
    # module
    "module": "module", "module type": "module", "card type": "module",
    "mod": "module", "device": "module",
    # description
    "description": "description", "desc": "description",
    "tag description": "description", "comment": "description",
    # channel
    "channel": "channel", "ch": "channel", "ch#": "channel",
    # tag
    "tag": "tag_name", "tag name": "tag_name", "plc tag": "tag_name",
    "address": "tag_name", "tag address": "tag_name",
}


def parse(path: str | Path) -> List[IORecord]:
    """
    Parse IO/commissioning Excel file.

    Returns:
        List of IORecord objects (one per data row).
    Raises:
        ValueError if file cannot be opened.
    """
    source = str(path)
    try:
        wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    except Exception as exc:
        raise ValueError(f"Cannot open Excel file {source}: {exc}") from exc

    records: List[IORecord] = []
    for sheet_name in wb.sheetnames:
        try:
            sheet = wb[sheet_name]
            rows = list(sheet.iter_rows(values_only=True))
            if len(rows) < 2:
                continue  # header only

            headers = _normalize_headers(rows[0])
            if not headers:
                continue

            for row in rows[1:]:
                rec = _row_to_record(headers, row, source)
                if rec:
                    records.append(rec)
        except Exception as exc:
            logger.warning("Excel sheet '%s' in %s: %s", sheet_name, source, exc)

    logger.debug("Excel %s → %d IO records", Path(source).name, len(records))
    return records


def _normalize_headers(header_row) -> dict:
    """Map column index → canonical name using alias table."""
    mapping = {}
    for i, cell in enumerate(header_row):
        if cell is None:
            continue
        key = str(cell).strip().lower()
        canonical = _COL_MAP.get(key)
        if canonical:
            mapping[i] = canonical
    return mapping


def _row_to_record(headers: dict, row: tuple, source: str) -> IORecord | None:
    """Convert a data row to an IORecord. Returns None if all fields empty."""
    fields = {}
    for idx, canonical in headers.items():
        if idx < len(row) and row[idx] is not None:
            fields[canonical] = str(row[idx]).strip()

    if not any(fields.values()):
        return None

    return IORecord(
        slot=fields.get("slot", ""),
        rack=fields.get("rack", ""),
        module=fields.get("module", ""),
        description=fields.get("description", ""),
        channel=fields.get("channel", ""),
        tag_name=fields.get("tag_name", ""),
        source_file=source,
    )
