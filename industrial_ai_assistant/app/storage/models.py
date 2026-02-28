"""
SQLAlchemy ORM models for the Industrial AI Assistant.
All tables are created via SQLiteClient.init_db() on startup.
"""
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship
from datetime import datetime
import uuid

Base = declarative_base()

def _uuid():
    return str(uuid.uuid4())


# ── Projects ────────────────────────────────────────────────────────────────────

class Project(Base):
    __tablename__ = "projects"

    id                      = Column(String, primary_key=True, default=_uuid)
    name                    = Column(String, nullable=False)
    root_directory          = Column(String, nullable=True)
    vector_collection_name  = Column(String, nullable=True)
    embedding_model         = Column(String, nullable=True, default="sentence-transformers")
    embedding_dimension     = Column(Integer, nullable=True, default=384)
    index_version           = Column(String, nullable=True)
    index_status            = Column(String, nullable=True, default="UNLOADED")  # READY|OUTDATED|VECTOR_MISSING|MODEL_MISMATCH|INDEXING|UNLOADED
    last_indexed_at         = Column(DateTime, nullable=True)
    created_at              = Column(DateTime, default=datetime.utcnow)
    updated_at              = Column(DateTime, default=datetime.utcnow)

    files     = relationship("ProjectFile",      back_populates="project", cascade="all, delete-orphan")
    telemetry = relationship("TelemetryDataset", back_populates="project", cascade="all, delete-orphan")


class ProjectFile(Base):
    """Per-file hash tracking for delta indexing audit trail."""
    __tablename__ = "project_files"

    id              = Column(String,   primary_key=True, default=_uuid)
    project_id      = Column(String,   ForeignKey("projects.id"), nullable=False)
    file_path       = Column(String,   nullable=False)
    file_type       = Column(String,   nullable=True)
    file_hash       = Column(String,   nullable=True)
    last_modified   = Column(Float,    nullable=True)
    indexed_at      = Column(DateTime, default=datetime.utcnow)
    embedding_count = Column(Integer,  default=0)
    status          = Column(String,   nullable=True, default="indexed")

    project = relationship("Project", back_populates="files")


class TelemetryDataset(Base):
    """Registry of uploaded PLC telemetry CSV files — no re-upload required."""
    __tablename__ = "telemetry_datasets"

    id          = Column(String,   primary_key=True, default=_uuid)
    project_id  = Column(String,   ForeignKey("projects.id"), nullable=False)
    file_name   = Column(String,   nullable=False)
    file_path   = Column(String,   nullable=False)
    file_hash   = Column(String,   nullable=True)
    row_count   = Column(Integer,  default=0)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    project = relationship("Project", back_populates="telemetry")



# ── Logs ─────────────────────────────────────────────────────────────────────────

class Log(Base):
    __tablename__ = "logs"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    level     = Column(String)
    message   = Column(String)
    module    = Column(String)


# ── AI Sessions ──────────────────────────────────────────────────────────────────

class ChatSession(Base):
    """
    Represents one complete interaction session — either a chat conversation
    or a PLC log analysis run.
    """
    __tablename__ = "sessions"

    id                   = Column(String, primary_key=True, default=_uuid)
    session_type         = Column(String, nullable=False, default="chat")   # "chat" | "plc_analysis"
    title                = Column(String)                                    # auto-generated from first message
    provider             = Column(String)                                    # "local_ollama" | "openai" | "gemini"
    project_id           = Column(String, nullable=True)
    index_version        = Column(String, nullable=True)                     # content hash of project index
    gateway_version      = Column(String, nullable=True, default="v3")
    prompt_schema_version= Column(String, nullable=True, default="v1")
    model_name           = Column(String, nullable=True)
    started_at           = Column(DateTime, default=datetime.utcnow)
    completed_at         = Column(DateTime, nullable=True)
    total_tokens         = Column(Integer, default=0)
    latency_ms           = Column(Integer, default=0)
    confidence_score     = Column(Float, nullable=True)
    integrity_status     = Column(String, nullable=True)                     # "OK" | "WARNING" | "FAILED"
    compliance_mode      = Column(Boolean, default=False)
    metadata_json        = Column(Text, nullable=True)                       # JSON blob for extra fields
    created_at           = Column(DateTime, default=datetime.utcnow)

    messages  = relationship("ChatMessage", back_populates="session",
                             cascade="all, delete-orphan",
                             order_by="ChatMessage.created_at")
    plc_snapshots = relationship("PLCAnalysisSnapshot", back_populates="session",
                                 cascade="all, delete-orphan")


class ChatMessage(Base):
    """A single turn in a chat session."""
    __tablename__ = "messages"

    id          = Column(Integer,  primary_key=True, autoincrement=True)
    session_id  = Column(String,   ForeignKey("sessions.id"), nullable=False)
    role        = Column(String,   nullable=False)   # "user" | "assistant" | "system"
    content     = Column(Text,     nullable=False)
    token_count = Column(Integer,  default=0)
    created_at  = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="messages")


class PLCAnalysisSnapshot(Base):
    """
    One complete PLC fault analysis record.
    Attached to a ChatSession of type 'plc_analysis'.
    """
    __tablename__ = "plc_snapshots"

    id               = Column(String,  primary_key=True, default=_uuid)
    session_id       = Column(String,  ForeignKey("sessions.id"), nullable=False)
    fault_id         = Column(String,  nullable=False)
    anomaly_score    = Column(Float,   default=0.0)
    burst_rate       = Column(Float,   default=0.0)
    integrity_passed = Column(Boolean, default=True)
    ai_confidence    = Column(Float,   nullable=True)
    provider         = Column(String,  nullable=True)
    analysis_version = Column(String,  nullable=True, default="v1")
    telemetry_json   = Column(Text,    nullable=True)   # JSON blob
    created_at       = Column(DateTime, default=datetime.utcnow)

    session = relationship("ChatSession", back_populates="plc_snapshots")
