"""
L5X Parser — Studio 5000 Logix Designer project files.

Extracts:
  - Tags (Controller-scoped and Program-scoped)
  - Routines (RLL/ST/FBD)
  - Add-On Instruction definitions (AOI)

L5X is an XML format; no external library needed beyond stdlib.
"""
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import List, Tuple

from app.models.project_models import AOIRecord, RoutineRecord, TagRecord

logger = logging.getLogger(__name__)

# Max rung content stored per routine (bytes)
_MAX_RUNG_CONTENT = 8_192


def parse(path: str | Path) -> Tuple[List[TagRecord], List[RoutineRecord], List[AOIRecord]]:
    """
    Parse a Studio 5000 L5X file.

    Returns:
        (tags, routines, aois) — lists of typed records.
    Raises:
        ValueError if file is not parseable XML.
    """
    source = str(path)
    try:
        tree = ET.parse(source)
    except ET.ParseError as exc:
        raise ValueError(f"L5X parse error in {source}: {exc}") from exc

    root = tree.getroot()

    tags: List[TagRecord] = []
    routines: List[RoutineRecord] = []
    aois: List[AOIRecord] = []

    _extract_controller_tags(root, tags, source)
    _extract_program_tags(root, tags, source)
    _extract_routines(root, routines, source)
    _extract_aois(root, aois, source)

    logger.debug(
        "L5X %s → %d tags, %d routines, %d AOIs",
        Path(source).name, len(tags), len(routines), len(aois),
    )
    return tags, routines, aois


# ── Internal helpers ──────────────────────────────────────────────────────────

def _text(elem, tag: str, default: str = "") -> str:
    """Safe child-element text extractor."""
    child = elem.find(tag)
    if child is not None and child.text:
        return child.text.strip()
    return default


def _extract_controller_tags(root: ET.Element, out: List[TagRecord], source: str) -> None:
    """Extract tags from <Controller><Tags> section."""
    for tags_elem in root.iter("Tags"):
        parent = _get_parent_name(root, tags_elem)
        if parent.lower() == "controller" or parent == "":
            for tag in tags_elem.findall("Tag"):
                _append_tag(tag, scope="Controller", source=source, out=out)


def _extract_program_tags(root: ET.Element, out: List[TagRecord], source: str) -> None:
    """Extract tags from each <Program><Tags> section."""
    for prog in root.iter("Program"):
        prog_name = prog.get("Name", "")
        for tags_elem in prog.findall("Tags"):
            for tag in tags_elem.findall("Tag"):
                _append_tag(tag, scope=f"Program:{prog_name}", source=source, out=out)


def _append_tag(tag: ET.Element, scope: str, source: str, out: List[TagRecord]) -> None:
    name = tag.get("Name", "")
    if not name:
        return
    out.append(TagRecord(
        name=name,
        data_type=tag.get("DataType", ""),
        tag_type=tag.get("TagType", "Base"),
        scope=scope,
        description=_text(tag, "Description"),
        source_file=source,
    ))


def _extract_routines(root: ET.Element, out: List[RoutineRecord], source: str) -> None:
    for prog in root.iter("Program"):
        prog_name = prog.get("Name", "")
        for routine in prog.iter("Routine"):
            name = routine.get("Name", "")
            if not name:
                continue
            rtype = routine.get("Type", "RLL")
            rungs = routine.findall(".//Rung")
            rung_texts = []
            total_len = 0
            for rung in rungs:
                txt = _text(rung, "Text")
                if txt and total_len + len(txt) < _MAX_RUNG_CONTENT:
                    rung_texts.append(txt)
                    total_len += len(txt)
            out.append(RoutineRecord(
                name=name,
                program=prog_name,
                routine_type=rtype,
                rung_count=len(rungs),
                content="\n".join(rung_texts),
                source_file=source,
            ))


def _extract_aois(root: ET.Element, out: List[AOIRecord], source: str) -> None:
    for aoi_def in root.iter("AddOnInstructionDefinition"):
        name = aoi_def.get("Name", "")
        if not name:
            continue
        params = [
            p.get("Name", "")
            for p in aoi_def.findall(".//Parameter")
            if p.get("Name")
        ]
        out.append(AOIRecord(
            name=name,
            description=_text(aoi_def, "Description"),
            revision=aoi_def.get("Revision", ""),
            parameters=params,
            source_file=source,
        ))


def _get_parent_name(root: ET.Element, target: ET.Element) -> str:
    """Walk tree to find parent element name."""
    for parent in root.iter():
        if target in list(parent):
            return parent.tag
    return ""
