"""
L5X parser — Studio 5000 / Logix Designer project files.

Parses XML structure to extract:
  - Controller tags (Variables)
  - Program-scoped tags
  - Routines (LAD, ST, FBD, SFC) with rung text
  - Add-On Instructions (AOI definitions)

No external dependencies beyond stdlib xml.etree.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from app.models.project_models import AOIRecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)

# Max characters of rung content stored per routine (token budget protection)
_MAX_RUNG_SNIPPET_CHARS = 1000


@dataclass
class L5XParseResult:
    tags: list[TagRecord] = field(default_factory=list)
    routines: list[RoutineRecord] = field(default_factory=list)
    aois: list[AOIRecord] = field(default_factory=list)
    source_file: str = ""
    warnings: list[str] = field(default_factory=list)


def parse(file_path: str | Path) -> L5XParseResult:
    """
    Parse an L5X file and return extracted PLC objects.
    Never raises — returns warnings in result instead.
    """
    path = Path(file_path)
    result = L5XParseResult(source_file=str(path))

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        result.warnings.append(f"XML parse error in {path.name}: {exc}")
        return result
    except OSError as exc:
        result.warnings.append(f"Cannot read {path.name}: {exc}")
        return result

    root = tree.getroot()

    # ── Controller-scope tags ──────────────────────────────────────────────────
    controller = root.find(".//Controller")
    if controller is not None:
        for tag_elem in controller.findall("Tags/Tag"):
            t = _parse_tag(tag_elem, scope="Controller", source=str(path))
            if t:
                result.tags.append(t)

    # ── Program-scope tags ────────────────────────────────────────────────────
    for prog in root.findall(".//Program"):
        prog_name = prog.get("Name", "UnknownProgram")
        for tag_elem in prog.findall("Tags/Tag"):
            t = _parse_tag(tag_elem, scope=f"Program:{prog_name}", source=str(path))
            if t:
                result.tags.append(t)

        # ── Routines ──────────────────────────────────────────────────────────
        for rtn in prog.findall("Routines/Routine"):
            r = _parse_routine(rtn, program=prog_name, source=str(path))
            if r:
                result.routines.append(r)

    # ── AOI definitions ───────────────────────────────────────────────────────
    for aoi_def in root.findall(".//AddOnInstructionDefinition"):
        a = _parse_aoi(aoi_def, source=str(path))
        if a:
            result.aois.append(a)

    logger.debug(
        "L5X parsed: %s → %d tags, %d routines, %d AOIs",
        path.name, len(result.tags), len(result.routines), len(result.aois),
    )
    return result


# ── Private helpers ────────────────────────────────────────────────────────────

def _parse_tag(elem: ET.Element, scope: str, source: str) -> TagRecord | None:
    name = elem.get("Name", "").strip()
    if not name:
        return None
    return TagRecord(
        name=name,
        data_type=elem.get("DataType", "UNKNOWN"),
        scope=scope,
        description=_first_text(elem, "Description"),
        value=elem.get("Value") or _first_text(elem, "Data"),
        source_file=source,
    )


def _parse_routine(elem: ET.Element, program: str, source: str) -> RoutineRecord | None:
    name = elem.get("Name", "").strip()
    if not name:
        return None

    rtype = elem.get("Type", "LAD")
    rungs = elem.findall(".//Rung") or elem.findall(".//Line")
    rung_texts: list[str] = []
    for rung in rungs:
        text_elem = rung.find("Text")
        if text_elem is not None and text_elem.text:
            rung_texts.append(text_elem.text.strip())

    snippet = "\n".join(rung_texts)[:_MAX_RUNG_SNIPPET_CHARS]
    return RoutineRecord(
        name=name,
        program=program,
        routine_type=rtype,
        rung_count=len(rungs),
        content_snippet=snippet,
        source_file=source,
    )


def _parse_aoi(elem: ET.Element, source: str) -> AOIRecord | None:
    name = elem.get("Name", "").strip()
    if not name:
        return None
    params = [
        p.get("Name", "") for p in elem.findall("Parameters/Parameter")
        if p.get("Name")
    ]
    return AOIRecord(
        name=name,
        revision=elem.get("Revision", "1.0"),
        description=_first_text(elem, "Description"),
        parameters=params,
        source_file=source,
    )


def _first_text(elem: ET.Element, tag: str) -> str:
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return ""
