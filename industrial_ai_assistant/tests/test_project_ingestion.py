"""
Tests — Project ingestion pipeline.
"""
import os
import tempfile
import textwrap
from pathlib import Path

import pytest

from app.indexes.structured_index import StructuredIndex, get_structured_index, delete_structured_index
from app.indexes.semantic_index import SemanticIndex
from app.services.project_ingestion_pipeline import ProjectIngestionPipeline, get_ingestion_pipeline
from app.core.project_exceptions import IngestionAlreadyRunningError


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture
def tmp_project(tmp_path):
    """Create a minimal project folder with sample files."""
    # L5X file
    l5x = tmp_path / "plc.L5X"
    l5x.write_text(textwrap.dedent("""\
        <?xml version="1.0"?>
        <RSLogix5000Content>
          <Controller>
            <Tags>
              <Tag Name="Motor_Speed" DataType="REAL" TagType="Base">
                <Description>Conveyor motor speed setpoint</Description>
              </Tag>
              <Tag Name="Conv_1_Fault" DataType="BOOL" TagType="Base">
                <Description>Conveyor 1 fault status</Description>
              </Tag>
            </Tags>
            <Programs>
              <Program Name="MainProgram">
                <Tags>
                  <Tag Name="Step_Counter" DataType="INT" TagType="Base"/>
                </Tags>
                <Routines>
                  <Routine Name="MainRoutine" Type="RLL">
                    <RLLContent>
                      <Rung><Text>XIC(Conv_1_Fault)OTE(Alarm_Output);</Text></Rung>
                    </RLLContent>
                  </Routine>
                </Routines>
              </Program>
            </Programs>
          </Controller>
        </RSLogix5000Content>
    """))

    # Excel IO sheet
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Slot", "Rack", "Module", "Description", "Tag"])
    ws.append(["1", "0", "1769-IF4", "Analog Input Module", "AI_Speed"])
    ws.append(["2", "0", "1769-OW8", "Output Relay Module", "DO_Conveyor"])
    wb.save(str(tmp_path / "io_sheet.xlsx"))

    # Text file
    (tmp_path / "notes.txt").write_text(
        "Commissioning notes for line 1.\n"
        "Motor speed setpoint should be 1200 RPM at startup.\n"
        "Verify Conv_1_Fault clears before enabling output."
    )

    return tmp_path


@pytest.fixture(autouse=True)
def clean_index(tmp_project):
    pid = "test_ingest_proj"
    delete_structured_index(pid)
    yield pid
    delete_structured_index(pid)


# ── Tests ──────────────────────────────────────────────────────────────────────

def test_l5x_tags_ingested(tmp_project, clean_index):
    pid = clean_index
    pipe = ProjectIngestionPipeline()

    # Inject a no-op semantic index to avoid Qdrant dependency
    _inject_mock_semantic(pipe)

    result = pipe.ingest(str(tmp_project), pid)

    idx = get_structured_index(pid)
    assert idx.get_tag("Motor_Speed") is not None
    assert idx.get_tag("Conv_1_Fault") is not None
    assert idx.get_tag("Step_Counter") is not None
    assert result.tags_indexed >= 3


def test_l5x_routines_ingested(tmp_project, clean_index):
    pid = clean_index
    pipe = ProjectIngestionPipeline()
    _inject_mock_semantic(pipe)
    pipe.ingest(str(tmp_project), pid)

    idx = get_structured_index(pid)
    r = idx.get_routine("MainRoutine")
    assert r is not None
    assert r.program == "MainProgram"
    assert "XIC" in r.content


def test_excel_io_ingested(tmp_project, clean_index):
    pid = clean_index
    pipe = ProjectIngestionPipeline()
    _inject_mock_semantic(pipe)
    result = pipe.ingest(str(tmp_project), pid)

    idx = get_structured_index(pid)
    io = idx.get_io("1")
    assert io is not None
    assert "1769-IF4" in io.module
    assert result.io_rows_indexed >= 2


def test_files_indexed_count(tmp_project, clean_index):
    pid = clean_index
    pipe = ProjectIngestionPipeline()
    _inject_mock_semantic(pipe)
    result = pipe.ingest(str(tmp_project), pid)

    assert result.files_indexed >= 3   # L5X + xlsx + txt
    assert result.files_failed == 0


def test_ingestion_result_metrics(tmp_project, clean_index):
    pid = clean_index
    pipe = ProjectIngestionPipeline()
    _inject_mock_semantic(pipe)
    result = pipe.ingest(str(tmp_project), pid)

    assert result.tags_indexed >= 2
    assert result.routines_indexed >= 1
    assert result.duration_s > 0
    assert isinstance(result.errors, list)


def test_double_ingest_raises_409(tmp_project, clean_index):
    """Concurrent ingest attempt should raise IngestionAlreadyRunningError."""
    import threading
    pid = clean_index
    pipe = get_ingestion_pipeline()
    _inject_mock_semantic(pipe)

    lock = pipe._get_lock(pid)
    lock.acquire()
    try:
        with pytest.raises(IngestionAlreadyRunningError):
            pipe.ingest(str(tmp_project), pid)
    finally:
        lock.release()


def test_skip_binary_files(tmp_project, clean_index):
    """Binary files like .db should be skipped, not cause failures."""
    pid = clean_index
    (tmp_project / "data.db").write_bytes(b"\x00\x01\x02binary")
    pipe = ProjectIngestionPipeline()
    _inject_mock_semantic(pipe)
    result = pipe.ingest(str(tmp_project), pid)
    assert result.files_failed == 0


# ── Helpers ───────────────────────────────────────────────────────────────────

def _inject_mock_semantic(pipe):
    """Patch semantic index to avoid Qdrant during unit tests."""
    import app.indexes.semantic_index as sem_module
    mock = _MockSemanticIndex()
    sem_module._instance = mock


class _MockSemanticIndex:
    def upsert_chunks(self, project_id, chunks):
        return len(chunks)
    def delete_project(self, project_id):
        pass
    def chunk_count(self, project_id):
        return 0
    def search(self, *a, **kw):
        return []
