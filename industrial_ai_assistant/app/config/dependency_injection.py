"""
Dependency Injection — Per-request factory for cloud-native architecture.

No more global singletons for user-scoped resources.
System-level singletons (Firestore, Qdrant connection) are OK.
User-scoped resources (LLM provider, embedder, collections) are created per-request.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from app.config.settings import settings

# Interfaces
from app.core.interfaces.embedding_interface import EmbeddingInterface
from app.core.interfaces.vector_store_interface import VectorStoreInterface
from app.core.interfaces.retriever_interface import RetrieverInterface
from app.core.interfaces.chunker_interface import ChunkerInterface

# Implementations
from app.vector_store.qdrant_store import QdrantStore
from app.retrieval.hybrid_retriever import HybridRetriever
from app.retrieval.keyword_search import KeywordSearch
from app.retrieval.reranker import Reranker
from app.chunking.semantic_chunker import SemanticChunker
from app.ingestion.processors import PDFProcessor, L5XProcessor, ExcelProcessor

from app.services.validation_service import ValidationService
from app.services.history_service import HistoryService
from app.services.project_service import ProjectService

from app.services.rag_service import RAGService
from app.services.fault_response_validator import FaultResponseValidator
from app.services.fault_analysis_orchestrator import FaultAnalysisOrchestrator

from app.storage.firestore_client import FirestoreClient, get_firestore


class Container:
    """
    System-level container for shared, non-user-scoped resources.
    
    User-scoped resources (LLM, embeddings, per-user Qdrant collections)
    are created via the BYOK factory in Phase 3, not stored here.
    """

    def __init__(self):
        # 1. Firestore (replaces SQLite)
        self._db = get_firestore()

        # 2. Default Embedder — will be overridden per-user in Phase 3 (BYOK)
        from app.embeddings.gemini_embedder import GeminiEmbedder
        self._embedder = GeminiEmbedder()

        # 3. Vector Store (Qdrant Cloud — shared connection, per-user collections)
        if settings.QDRANT_URL:
            self._vector_store = QdrantStore(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY,
                collection_name="industrial_docs",  # default; overridden per-user
            )
        else:
            # Fallback: no vector store configured
            self._vector_store = None

        # 4. Retrieval
        self._keyword_retriever = KeywordSearch()
        self._reranker = Reranker()

        if self._vector_store and self._embedder:
            self._retriever = HybridRetriever(
                vector_store=self._vector_store,
                embedder=self._embedder,
                keyword_retriever=self._keyword_retriever,
                reranker=self._reranker,
            )
        else:
            self._retriever = HybridRetriever(
                vector_store=self._vector_store,
                embedder=self._embedder,
                keyword_retriever=self._keyword_retriever,
            )

        # 5. Services (Firestore-backed)
        self._validator = ValidationService()
        self._history_service = HistoryService(db=self._db)
        self._project_service = ProjectService(db=self._db)

        # 6. Ingestion processors
        self._chunker = SemanticChunker()
        self._processors = {
            "pdf": PDFProcessor(self._chunker, api_key=""),
            "l5x": L5XProcessor(self._chunker),
            "xlsx": ExcelProcessor(self._chunker),
        }

        # 7. RAG + Fault Analysis
        self._rag_service = RAGService(retriever=self._retriever)
        self._fault_response_validator = FaultResponseValidator()

        # AI Gateway will be initialized lazily per-user in Phase 3.
        # For now, keep a default gateway for backward compatibility.
        self._llm_gateway = None
        self._fault_orchestrator = None

    def _ensure_gateway(self):
        """Lazy-init a default AI gateway for backward compat during Phase 2."""
        if self._llm_gateway is None:
            from app.services.ai_gateway import AIGatewayService, FallbackPolicy
            from app.ai_providers.gemini_provider import GeminiProvider
            import os
            
            providers = {}
            gemini_key = os.getenv("GEMINI_API_KEY", "")
            if gemini_key:
                providers["gemini"] = GeminiProvider(api_key=gemini_key)
            
            policy = FallbackPolicy(
                primary="gemini",
                secondary=None,
                timeout_ms=8000,
                json_enforced=True,
            )
            self._llm_gateway = AIGatewayService(
                providers=providers,
                fallback_policy=policy,
            )
            self._fault_orchestrator = FaultAnalysisOrchestrator(
                llm=self._llm_gateway,
                rag_service=self._rag_service,
                validator=self._fault_response_validator,
            )

    # Accessors
    @property
    def firestore(self) -> FirestoreClient:
        return self._db

    @property
    def ai_gateway(self):
        self._ensure_gateway()
        return self._llm_gateway

    @property
    def history_service(self) -> HistoryService:
        return self._history_service

    @property
    def project_service(self) -> ProjectService:
        return self._project_service

    @property
    def fault_orchestrator(self) -> FaultAnalysisOrchestrator:
        self._ensure_gateway()
        return self._fault_orchestrator

    @property
    def rag_service(self) -> RAGService:
        return self._rag_service

    @property
    def vector_store(self):
        return self._vector_store

    @property
    def embedder(self):
        return self._embedder


# Singleton instance
@lru_cache()
def get_container() -> Container:
    return Container()
