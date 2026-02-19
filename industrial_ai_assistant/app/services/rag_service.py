"""
RAGService — thin, focused wrapper around the project retriever.
Responsibilities:
  - Build a retrieval query from fault context + optional user question
  - Call retriever.retrieve()
  - Apply relevance threshold filter
  - Return list of RetrievedDoc
"""
import logging
import time
from typing import List, Optional, Dict, Any

from app.core.interfaces.retriever_interface import RetrieverInterface
from app.models.fault_analysis_models import RetrievedDoc

logger = logging.getLogger(__name__)

RELEVANCE_THRESHOLD = 0.0   # accept all results from retriever (no score available from interface)
DEFAULT_TOP_K = 5


class RAGService:
    """Clean retrieval wrapper. Stateless — no data stored."""

    def __init__(self, retriever: RetrieverInterface):
        self._retriever = retriever

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
        Build a semantically rich query, retrieve docs, filter by threshold.

        Returns:
            (docs, latency_ms)
        """
        # Query construction
        if user_question:
            # Custom question — user question drives the search, fault code anchors scope
            query = f"{user_question} related to fault code {fault_code}"
        else:
            # Default analysis query
            query = (
                f"Fault code {fault_code} explanation, root cause, and troubleshooting steps. "
                f"Device: {device}. Description: {fault_message}"
            )

        filters: Optional[Dict[str, Any]] = None
        if project_id:
            filters = {"project_id": project_id}

        t0 = time.perf_counter()
        try:
            raw_chunks = self._retriever.retrieve(query=query, top_k=top_k, filters=filters)
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
            "RAG retrieved %d docs for fault '%s' in %.0fms",
            len(docs), fault_code, latency_ms
        )
        return docs, latency_ms
