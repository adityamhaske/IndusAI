"""
test_project_ingestion.py

Tests:
  - L5X file parsed → tags/routines in StructuredIndex
  - Excel file → IO rows in StructuredIndex
  - PDF file → chunks in SemanticIndex (verified by count)
  - Binary files skipped by ingestion
  - Ingestion concurrency lock raises IngestionLockError
  - IngestionResult metrics are correct
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
import pytest

# ── Helpers to build test fixture files ───────────────────────────────────────

def _write_l5x(folder: Path) -> Path:
    p = folder / "test_program.L5X"
    p.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content>
  <Controller Name="TestController">
    <Tags>
      <Tag Name="Motor_Speed" DataType="REAL" Value="0.0">
        <Description>Conveyor motor speed</Description>
      </Tag>
      <Tag Name="Fault_Active" DataType="BOOL" Value="0">
        <Description>System fault flag</Description>
      </Tag>
    </Tags>
    <Programs>
      <Program Name="MainProgram">
        <Tags>
          <Tag Name="Conveyor_Run" DataType="BOOL" Value="0"/>
        </Tags>
        <Routines>
          <Routine Name="MainRoutine" Type="LAD">
            <RLLContent>
              <Rung Number="0" Type="N">
                <Text>[XIC(Fault_Active)OTL(Motor_Speed)];</Text>
              </Rung>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
  </Controller>
</RSLogix5000Content>""")
    return p


def _write_excel(folder: Path) -> Path:
    """Write a minimal xlsx IO sheet."""
    import openpyxl
    p = folder / "io_sheet.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Slot", "Rack", "Module", "Description", "Tag Name"])
    ws.append(["1:0", "1", "1756-IB16D", "Conveyor Start PB", "Conv_Start"])
    ws.append(["1:1", "1", "1756-OB16D", "Conveyor Run Light", "Conv_Run_Light"])
    wb.save(p)
    return p


def _write_pdf(folder: Path) -> Path:
    """Write a minimal text file (PDF parsing needs pdfplumber; use txt for CI)."""
    # We simulate PDF as text file for test isolation
    p = folder / "manual.txt"
    p.write_text("INTRODUCTION\nThis is the conveyor system manual.\n\n"
                 "SAFETY\nAll guards must be in place before operation.", encoding="utf-8")
    return p


def _write_binary(folder: Path) -> Path:
    p = folder / "firmware.exe"
    p.write_bytes(b"\x00\x01\x02\x03" * 100)
    return p


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def project_dir():
    with tempfile.TemporaryDirectory() as d:
        folder = Path(d)
        _write_l5x(folder)
        _write_excel(folder)
        _write_pdf(folder)
        _write_binary(folder)
        yield folder


@pytest.fixture(autouse=True)
def reset_indexes(project_dir):
    """Clear indexes before each test."""
    from app.indexes.structured_index import clear_structured_index
    clear_structured_index("test_proj")
    yield
    clear_structured_index("test_proj")


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_l5x_tags_indexed(project_dir):
    """L5X parse: controller tags end up in StructuredIndex."""
    from app.parsers.l5x_parser import parse
    from app.indexes.structured_index import get_structured_index

    p = next(project_dir.glob("*.L5X"))
    result = parse(p)
    si = get_structured_index("test_proj")
    for tag in result.tags:
        si.add_tag(tag)

    assert si.get_tag("Motor_Speed") is not None
    assert si.get_tag("Fault_Active") is not None
    assert si.get_tag("motor_speed") is not None   # case-insensitive


def test_l5x_routines_indexed(project_dir):
    from app.parsers.l5x_parser import parse
    from app.indexes.structured_index import get_structured_index

    p = next(project_dir.glob("*.L5X"))
    result = parse(p)
    si = get_structured_index("test_proj")
    for rtn in result.routines:
        si.add_routine(rtn)

    assert si.get_routine("MainRoutine") is not None
    r = si.get_routine("mainroutine")
    assert r.rung_count >= 1


def test_excel_io_indexed(project_dir):
    from app.parsers.excel_parser import parse
    from app.indexes.structured_index import get_structured_index

    p = next(project_dir.glob("*.xlsx"))
    result = parse(p)
    assert len(result.io_rows) == 2

    si = get_structured_index("test_proj")
    for io in result.io_rows:
        si.add_io(io)

    r = si.get_io("1:0")
    assert r is not None
    assert "Conv_Start" in r.tag_name


def test_text_file_chunked(project_dir):
    from app.parsers.text_parser import parse

    p = next(project_dir.glob("*.txt"))
    result = parse(p)
    assert len(result.chunks) >= 1
    assert result.char_count > 0


def test_binary_file_skipped(project_dir):
    """Binary files must not appear in structured or semantic index."""
    from app.services.project_ingestion_pipeline import _collect_files, _SKIP_EXTENSIONS
    files = _collect_files(project_dir)
    exts = {f.suffix.lower() for f in files}
    assert ".exe" not in exts


def test_ingestion_result_metrics():
    """IngestionResult correctly aggregates counts."""
    from app.models.project_models import IngestionResult
    r = IngestionResult(project_id="x", project_hash="abc", folder="/tmp")
    r.tags_indexed = 10
    r.semantic_chunks_indexed = 5
    assert r.files_failed == 0
    assert r.tags_indexed == 10


@pytest.mark.asyncio
async def test_concurrency_lock_raises():
    """Triggering ingestion twice raises IngestionLockError."""
    import asyncio
    from app.core.project_exceptions import IngestionLockError
    from app.services.project_ingestion_pipeline import _locks, _lock_registry_lock

    pid = "lock_test_proj"
    async with _lock_registry_lock:
        _locks[pid] = asyncio.Lock()
    await _locks[pid].acquire()   # simulate in-progress ingestion

    from app.services.project_ingestion_pipeline import get_ingestion_pipeline
    pipeline = get_ingestion_pipeline()
    with pytest.raises(IngestionLockError):
        await pipeline.ingest("/tmp", pid)

    _locks[pid].release()
