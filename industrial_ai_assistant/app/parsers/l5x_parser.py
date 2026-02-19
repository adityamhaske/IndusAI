"""
L5X Parser — Rockwell Studio 5000 project file parser.

Parses XML structure of .L5X files to extract:
  - Controller-scoped and Program-scoped Tags
  - Routines (LAD / FBD / SFC / ST)
  - Add-On Instructions (AOIs)

Uses stdlib xml.etree.ElementTree — no external dependency needed.
"""
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple
import logging

from app.models.project_models import AOIRecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)

# Data-type synonyms Rockwell uses internally
_KNOWN_TYPES = {
    "BOOL", "SINT", "INT", "DINT", "LINT", "REAL", "LREAL",
    "STRING", "TIMER", "COUNTER", "CONTROL", "MESSAGE", "AXIS_GENERIC",
}


def parse_l5x(file_path: str) -> Tuple[List[TagRecord], List[RoutineRecord], List[AOIRecord]]:
    """
    Parse a Studio 5000 L5X file.

    Returns:
        (tags, routines, aois)

    Raises:
        ValueError if file cannot be parsed as valid L5X XML.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"L5X file not found: {file_path}")

    try:
        tree = ET.parse(file_path)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid L5X XML in {file_path}: {exc}") from exc

    root = tree.getroot()
    source = path.name
    tags: List[TagRecord] = []
    routines: List[RoutineRecord] = []
    aois: List[AOIRecord] = []

    # ── Controller-scoped tags ────────────────────────────────────────────────
    for tag_el in root.findall(".//Tags/Tag"):
        tr = _parse_tag_element(tag_el, scope="Controller", source=source)
        if tr:
            tags.append(tr)

    # ── Program-scoped tags ───────────────────────────────────────────────────
    for prog_el in root.findall(".//Programs/Program"):
        prog_name = prog_el.get("Name", "Unknown")
        for tag_el in prog_el.findall(".//Tags/Tag"):
            tr = _parse_tag_element(tag_el, scope=prog_name, source=source)
            if tr:
                tags.append(tr)

    # ── Routines ──────────────────────────────────────────────────────────────
    for prog_el in root.findall(".//Programs/Program"):
        prog_name = prog_el.get("Name", "Unknown")
        for rtn_el in prog_el.findall(".//Routines/Routine"):
            name = rtn_el.get("Name", "")
            if not name:
                continue
            rung_count = len(rtn_el.findall(".//Rung"))
            routines.append(RoutineRecord(
                name=name,
                program_name=prog_name,
                type=rtn_el.get("Type", "LAD"),
                description=_get_description(rtn_el),
                rung_count=rung_count,
                source_file=source,
            ))

    # ── AOIs ──────────────────────────────────────────────────────────────────
    for aoi_el in root.findall(".//AddOnInstructionDefinitions/AddOnInstructionDefinition"):
        name = aoi_el.get("Name", "")
        if not name:
            continue
        params = []
        for p in aoi_el.findall(".//Parameters/Parameter"):
            params.append({
                "name": p.get("Name", ""),
                "data_type": p.get("DataType", ""),
                "usage": p.get("Usage", ""),
                "description": _get_description(p),
            })
        aois.append(AOIRecord(
            name=name,
            description=_get_description(aoi_el),
            parameters=params,
            source_file=source,
        ))

    logger.info(
        "L5X parsed: %s → %d tags, %d routines, %d AOIs",
        path.name, len(tags), len(routines), len(aois),
    )
    return tags, routines, aois


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_tag_element(el: ET.Element, scope: str, source: str) -> TagRecord | None:
    name = el.get("Name", "")
    data_type = el.get("DataType", "")
    if not name or not data_type:
        return None
    return TagRecord(
        name=name,
        data_type=data_type,
        description=_get_description(el),
        scope=scope,
        external_access=el.get("ExternalAccess", "Read/Write"),
        source_file=source,
    )


def _get_description(el: ET.Element) -> str:
    desc_el = el.find("Description")
    if desc_el is not None and desc_el.text:
        return desc_el.text.strip()
    return ""


def l5x_to_text_chunks(tags: List[TagRecord], routines: List[RoutineRecord], aois: List[AOIRecord]) -> str:
    """
    Convert parsed L5X data to a plain-text representation suitable
    for semantic chunking and indexing.
    """
    lines = []
    if tags:
        lines.append("## Tags")
        for t in tags:
            lines.append(f"- {t.name} ({t.data_type}) [{t.scope}]: {t.description}")
    if routines:
        lines.append("\n## Routines")
        for r in routines:
            lines.append(f"- {r.name} in {r.program_name} ({r.type}, {r.rung_count} rungs): {r.description}")
    if aois:
        lines.append("\n## Add-On Instructions")
        for a in aois:
            params_str = ", ".join(p["name"] for p in a.parameters)
            lines.append(f"- {a.name}({params_str}): {a.description}")
    return "\n".join(lines)
