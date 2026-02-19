"""
Excel IO Sheet Parser.

Handles the wide variety of column naming conventions used across
different integrators for IO assignment / IO list workbooks.

Normalized canonical schema:
  slot | tag_name | description | rack | module_type | channel
"""
import logging
from pathlib import Path
from typing import List

from app.models.project_models import IORecord

logger = logging.getLogger(__name__)

# ── Column synonym map ────────────────────────────────────────────────────────
# Maps any known variant → canonical name
_COLUMN_MAP: dict[str, str] = {
    # slot
    "slot": "slot",
    "slot number": "slot",
    "slot no": "slot",
    "slot#": "slot",
    "module slot": "slot",
    # rack
    "rack": "rack",
    "rack number": "rack",
    "rack no": "rack",
    "chassis": "rack",
    # module_type
    "module": "module_type",
    "module type": "module_type",
    "card type": "module_type",
    "card": "module_type",
    "module description": "module_type",
    # channel
    "channel": "channel",
    "ch": "channel",
    "channel number": "channel",
    "ch#": "channel",
    "i/o": "channel",
    "point": "channel",
    # tag_name
    "tag": "tag_name",
    "tag name": "tag_name",
    "plc tag": "tag_name",
    "address": "tag_name",
    "signal tag": "tag_name",
    "tagname": "tag_name",
    # description
    "description": "description",
    "desc": "description",
    "signal name": "description",
    "function": "description",
    "signal description": "description",
    "io description": "description",
}

_CANONICAL = {"slot", "rack", "module_type", "channel", "tag_name", "description"}


def parse_excel_io(file_path: str) -> List[IORecord]:
    """
    Parse an IO assignment Excel workbook.

    Tries each sheet in order and uses the first one that has at least
    slot or tag_name after normalization.

    Returns:
        List[IORecord]

    Raises:
        ImportError if openpyxl is not installed.
        ValueError if no recognisable IO columns found.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required for Excel parsing. Run: pip install openpyxl"
        ) from exc

    path = Path(file_path)
    wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    source = path.name
    records: List[IORecord] = []

    for sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            continue

        # Find header row (first row with ≥ 2 recognisable column names)
        header_idx, col_map = _find_header(rows)
        if header_idx is None or not col_map:
            logger.debug("Sheet '%s' has no recognisable IO columns — skipping", sheet_name)
            continue

        logger.debug("Sheet '%s': header at row %d, cols=%s", sheet_name, header_idx, col_map)

        for row in rows[header_idx + 1:]:
            if not row or all(cell is None for cell in row):
                continue
            rec = _row_to_io_record(row, col_map, source)
            if rec:
                records.append(rec)

        if records:
            break   # stop at first productive sheet

    wb.close()
    logger.info("Excel IO parsed: %s → %d IO records", path.name, len(records))
    return records


def excel_to_text(records: List[IORecord]) -> str:
    """Convert IO records to plain text for semantic indexing."""
    lines = ["## IO Assignment"]
    for r in records:
        lines.append(
            f"- Slot {r.slot} Rack {r.rack} Ch {r.channel} "
            f"[{r.module_type}] {r.tag_name}: {r.description}"
        )
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_header(rows: list) -> tuple[int | None, dict[int, str]]:
    """Return (row_index, {col_index: canonical_name}) for the first header row."""
    for idx, row in enumerate(rows[:20]):   # scan first 20 rows only
        col_map: dict[int, str] = {}
        for col_idx, cell in enumerate(row):
            if cell is None:
                continue
            normalised = str(cell).strip().lower()
            canonical = _COLUMN_MAP.get(normalised)
            if canonical:
                col_map[col_idx] = canonical
        if len(col_map) >= 2:
            return idx, col_map
    return None, {}


def _row_to_io_record(row: tuple, col_map: dict[int, str], source: str) -> IORecord | None:
    values: dict[str, str] = {}
    for col_idx, canonical in col_map.items():
        cell = row[col_idx] if col_idx < len(row) else None
        values[canonical] = str(cell).strip() if cell is not None else ""

    slot = values.get("slot", "")
    tag_name = values.get("tag_name", "")
    if not slot and not tag_name:
        return None      # empty row

    return IORecord(
        slot=slot or "—",
        rack=values.get("rack", ""),
        module_type=values.get("module_type", ""),
        channel=values.get("channel", ""),
        tag_name=tag_name,
        description=values.get("description", ""),
        source_file=source,
    )
