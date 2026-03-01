"""
RAGService — Hybrid retrieval wrapper (Phase 21 upgrade).

Responsibilities:
  - Build a retrieval query from fault context + optional user question
  - Call SemanticIndex.hybrid_search() (BM25 + Vector + RRF fusion)
  - Fallback to legacy retriever if SemanticIndex unavailable
  - Return list of RetrievedDoc with relevance scores
  - Log retrieval metrics per request
"""
import logging
import time
from typing import List, Optional, Dict, Any

from app.core.interfaces.retriever_interface import RetrieverInterface
from app.models.fault_analysis_models import RetrievedDoc

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.0
DEFAULT_TOP_K = 8


class RAGService:
    """Hybrid retrieval wrapper. Uses SemanticIndex.hybrid_search() for BM25+Vector+RRF."""

    def __init__(self, retriever: RetrieverInterface):
        self._retriever = retriever
        self._semantic_index = None  # Lazy-loaded

    def _get_semantic_index(self):
        """Lazy-load SemanticIndex singleton."""
        if self._semantic_index is None:
            try:
                from app.indexes.semantic_index import get_semantic_index
                self._semantic_index = get_semantic_index()
            except Exception as exc:
                logger.warning("SemanticIndex not available, using legacy retriever: %s", exc)
        return self._semantic_index

    def retrieve_for_fault(
        self,
        fault_code: str,
        fault_message: str,
        device: str,
        user_question: Optional[str] = None,
        project_id: Optional[str] = None,
        top_k: int = DEFAULT_TOP_K,
    ) -> tuple[List[RetrievedDoc], float]:
        """
        Build a semantically rich query, retrieve docs via hybrid search,
        filter by threshold.

        Returns:
            (docs, latency_ms)
        """
        # ── Query construction ────────────────────────────────────────────────
        if user_question:
            query = f"{user_question} related to fault code {fault_code}"
        else:
            query = (
                f"Fault code {fault_code} explanation, root cause, and troubleshooting steps. "
                f"Device: {device}. Description: {fault_message}"
            )

        t0 = time.perf_counter()
        sem = self._get_semantic_index()

        # ── Phase 21: Hybrid Search (BM25 + Vector + RRF) ────────────────────
        if sem is not None and project_id:
            try:
                scored_chunks = sem.hybrid_search(
                    query=query,
                    project_id=project_id,
                    top_k=top_k,
                )

                # Dynamic Top-K Expansion if coverage is suspiciously low
                if len(scored_chunks) < 3 and top_k < 15:
                    logger.info("Hybrid RAG: Low coverage (%d chunks). Expanding to top_k=15.", len(scored_chunks))
                    expanded = sem.hybrid_search(query=query, project_id=project_id, top_k=15)
                    if len(expanded) > len(scored_chunks):
                        scored_chunks = expanded

                latency_ms = (time.perf_counter() - t0) * 1000

                docs = [
                    RetrievedDoc(
                        source_file=sc.chunk.source_file,
                        section_title=sc.chunk.section_title,
                        page_number=sc.chunk.page,
                        content=sc.chunk.content,
                        relevance_score=round(sc.score, 4) if sc.score else None,
                    )
                    for sc in scored_chunks
                ]

                # Log retrieval metrics
                avg_score = sum(sc.score for sc in scored_chunks) / len(scored_chunks) if scored_chunks else 0.0
                logger.info(
                    "RAG [hybrid] retrieved %d docs for fault '%s' in %.0fms | avg_rrf_score=%.4f | method=hybrid",
                    len(docs), fault_code, latency_ms, avg_score
                )
                return docs, latency_ms

            except Exception as exc:
                logger.warning("Hybrid search failed, falling back to legacy retriever: %s", exc)

        # ── Fallback: Legacy retriever interface ──────────────────────────────
        try:
            filters: Optional[Dict[str, Any]] = None
            if project_id:
                filters = {"project_id": project_id}

            raw_chunks = self._retriever.retrieve(query=query, top_k=top_k, filters=filters)

            if len(raw_chunks) < 3 and top_k < 15:
                logger.info("RAG [legacy]: Low coverage. Expanding to top_k=15.")
                expanded = self._retriever.retrieve(query=query, top_k=15, filters=filters)
                if len(expanded) > len(raw_chunks):
                    raw_chunks = expanded

        except Exception as exc:
            logger.warning("RAG retrieval failed (non-fatal): %s", exc)
            return [], 0.0

        latency_ms = (time.perf_counter() - t0) * 1000

        docs = [
            RetrievedDoc(
                source_file=chunk.metadata.source_file,
                section_title=chunk.metadata.section_title,
                page_number=chunk.metadata.page_number,
                content=chunk.content,
                relevance_score=None,
            )
            for chunk in raw_chunks
        ]

        logger.info(
            "RAG [legacy] retrieved %d docs for fault '%s' in %.0fms | method=vector_only",
            len(docs), fault_code, latency_ms
        )
        return docs, latency_ms
