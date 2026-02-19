"""
Tests for ProjectIngestionPipeline.

Uses a temporary directory with synthetic project files.
"""
import os
import tempfile
import textwrap
import pytest

from app.indexes.structured_index import get_structured_store, StructuredIndexStore
from app.models.project_models import IngestionStatus
from app.services.project_context_manager import ProjectContextManager
from app.services.project_ingestion_pipeline import ingest_project


# ── Fixtures ──────────────────────────────────────────────────────────────────

class _NoopSemanticIndex:
    """SemanticIndex stand-in that discards all chunks — no Qdrant needed."""
    def index_chunks(self, project_id, chunks): return len(chunks)
    def search(self, project_id, query, top_k=5): return []
    def delete_project(self, project_id): pass


def _make_project_folder(tmp_path, files: dict) -> str:
    for rel_path, content in files.items():
        fp = os.path.join(str(tmp_path), rel_path)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        if isinstance(content, bytes):
            open(fp, "wb").write(content)
        else:
            open(fp, "w", encoding="utf-8").write(textwrap.dedent(content))
    return str(tmp_path)


_MINIMAL_L5X = """\
<?xml version="1.0" encoding="UTF-8"?>
<RSLogix5000Content>
  <Controller>
    <Tags>
      <Tag Name="CONV_RUN" DataType="BOOL">
        <Description>Conveyor Running Status</Description>
      </Tag>
      <Tag Name="CONV_SPD" DataType="REAL">
        <Description>Conveyor Speed Setpoint</Description>
      </Tag>
    </Tags>
    <Programs>
      <Program Name="MainProgram">
        <Tags>
          <Tag Name="TIMER_1" DataType="TIMER">
            <Description>Cycle Timer</Description>
          </Tag>
        </Tags>
        <Routines>
          <Routine Name="MainRoutine" Type="LAD">
            <RLLContent>
              <Rung Number="0" Type="N"/>
              <Rung Number="1" Type="N"/>
            </RLLContent>
          </Routine>
          <Routine Name="StartupSeq" Type="LAD">
            <Description>Startup Sequence</Description>
            <RLLContent>
              <Rung Number="0" Type="N"/>
            </RLLContent>
          </Routine>
        </Routines>
      </Program>
    </Programs>
    <AddOnInstructionDefinitions>
      <AddOnInstructionDefinition Name="MOT_CTL">
        <Description>Motor Control AOI</Description>
        <Parameters>
          <Parameter Name="Enable" DataType="BOOL" Usage="Input"/>
          <Parameter Name="Fault" DataType="BOOL" Usage="Output"/>
        </Parameters>
      </AddOnInstructionDefinition>
    </AddOnInstructionDefinitions>
  </Controller>
</RSLogix5000Content>
"""

_DOCS_TXT = """\
Section 1: System Overview
This system controls conveyor CONV_RUN at variable speed CONV_SPD.

Section 2: Safety
Emergency stop interlock disables all motion.
"""


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_ingest_l5x_populates_structured_index(tmp_path):
    folder = _make_project_folder(tmp_path, {"project.l5x": _MINIMAL_L5X})
    ctx = ProjectContextManager()
    struct_store = StructuredIndexStore()
    ctx.set_project("p1", folder)

    ingest_project("p1", folder, ctx, struct_store, _NoopSemanticIndex())

    idx = struct_store.get("p1")
    assert idx is not None
    assert idx.tags.count() == 3           # CONV_RUN, CONV_SPD, TIMER_1
    assert idx.routines.count() == 2       # MainRoutine, StartupSeq
    assert idx.aois.count() == 1           # MOT_CTL


def test_ingest_marks_complete(tmp_path):
    folder = _make_project_folder(tmp_path, {"project.l5x": _MINIMAL_L5X})
    ctx = ProjectContextManager()
    struct_store = StructuredIndexStore()
    ctx.set_project("p2", folder)

    ingest_project("p2", folder, ctx, struct_store, _NoopSemanticIndex())
    status = ctx.get_status("p2")
    assert status.status == IngestionStatus.COMPLETE
    assert status.project_loaded is True


def test_ingest_text_doc_contributes_semantic_chunks(tmp_path):
    folder = _make_project_folder(tmp_path, {
        "project.l5x": _MINIMAL_L5X,
        "docs/manual.txt": _DOCS_TXT,
    })
    ctx = ProjectContextManager()

    chunks_seen = []
    class _CountingIndex:
        def index_chunks(self, pid, chunks):
            chunks_seen.extend(chunks)
            return len(chunks)
        def search(self, *a, **k): return []
        def delete_project(self, *a): pass

    struct_store = StructuredIndexStore()
    ctx.set_project("p3", folder)
    results = ingest_project("p3", folder, ctx, struct_store, _CountingIndex())

    assert len(chunks_seen) > 0          # text file produced semantic chunks
    assert any(r.semantic_chunks > 0 for r in results)


def test_ingest_skips_unsupported_files(tmp_path):
    folder = _make_project_folder(tmp_path, {
        "project.l5x": _MINIMAL_L5X,
        "image.png": b"\x89PNG",          # binary — should be skipped
        "archive.zip": b"PK\x03\x04",    # zip — should be skipped
    })
    ctx = ProjectContextManager()
    struct_store = StructuredIndexStore()
    ctx.set_project("p4", folder)
    results = ingest_project("p4", folder, ctx, struct_store, _NoopSemanticIndex())

    processed_exts = {os.path.splitext(r.file_path)[1].lower() for r in results}
    assert ".png" not in processed_exts
    assert ".zip" not in processed_exts


def test_ingest_continues_on_bad_l5x(tmp_path):
    folder = _make_project_folder(tmp_path, {
        "good.l5x": _MINIMAL_L5X,
        "broken.l5x": "THIS IS NOT XML <<<",
        "notes.txt": "Some commissioning notes.",
    })
    ctx = ProjectContextManager()
    struct_store = StructuredIndexStore()
    ctx.set_project("p5", folder)
    results = ingest_project("p5", folder, ctx, struct_store, _NoopSemanticIndex())

    successes = [r for r in results if r.success]
    failures = [r for r in results if not r.success]
    assert len(successes) >= 2    # good.l5x + notes.txt
    assert len(failures) == 1     # broken.l5x
    # Status must still be COMPLETE (file-level tolerance)
    assert ctx.get_status("p5").status == IngestionStatus.COMPLETE


def test_tags_indexed_metric_reported(tmp_path):
    folder = _make_project_folder(tmp_path, {"project.l5x": _MINIMAL_L5X})
    ctx = ProjectContextManager()
    struct_store = StructuredIndexStore()
    ctx.set_project("p6", folder)

    ingest_project("p6", folder, ctx, struct_store, _NoopSemanticIndex())
    status = ctx.get_status("p6")
    assert status.tags_indexed == 3
    assert status.routines_indexed == 2
