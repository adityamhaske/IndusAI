"""
SystemHealthService — probes each infrastructure component.

Design:
  - All checks have a hard timeout (2 s) and never crash the app.
  - Returns structured dicts so the API endpoint can relay them directly.
  - Checks are independent — a failing LLM does NOT affect the RAG check.
"""
import logging
import time
from typing import Optional

import requests

from app.config.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 2.0          # seconds for every probe
_LLM_PROBE_PATH = "/api/tags"       # Ollama endpoint to test reachability
_QDRANT_PROBE_PATH = "/healthz"     # Qdrant health endpoint


class SystemHealthService:
    """Stateless health-probe helper (no instance state needed)."""

    # ── LLM ──────────────────────────────────────────────────────────────────

    def check_llm(self, base_url: Optional[str] = None) -> dict:
        """
        Probe the local LLM (Ollama by default).

        Returns:
            {"ok": bool, "provider": str, "url": str, "reason": str|None,
             "latency_ms": float|None}
        """
        provider = settings.LLM_PROVIDER
        url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        probe_url = url + _LLM_PROBE_PATH

        if provider in ["mock", "gemini", "openai"]:
            return {
                "ok": True,
                "provider": provider,
                "url": "cloud://api",
                "reason": f"Managed cloud provider ({provider}) active",
                "latency_ms": 0.0,
            }

        t0 = time.perf_counter()
        try:
            resp = requests.get(probe_url, timeout=_TIMEOUT)
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                models = [m.get("name", "") for m in (resp.json().get("models") or [])]
                logger.debug("Ollama reachable at %s. Models: %s", url, models)
                return {
                    "ok": True,
                    "provider": provider,
                    "url": url,
                    "reason": None,
                    "latency_ms": round(latency_ms, 1),
                    "models_available": models,
                }
            else:
                reason = f"Ollama responded with HTTP {resp.status_code}"
                logger.warning("LLM probe failed: %s", reason)
                return {"ok": False, "provider": provider, "url": url, "reason": reason, "latency_ms": None}
        except requests.exceptions.ConnectionError as exc:
            msg = f"Connection refused — is Ollama running? ({exc})"
            logger.warning("LLM probe: %s", msg)
            return {"ok": False, "provider": provider, "url": url, "reason": msg, "latency_ms": None}
        except requests.exceptions.Timeout:
            msg = f"Ollama did not respond within {_TIMEOUT}s"
            logger.warning("LLM probe: %s", msg)
            return {"ok": False, "provider": provider, "url": url, "reason": msg, "latency_ms": None}
        except Exception as exc:
            msg = f"Unexpected error during LLM probe: {exc}"
            logger.exception("LLM probe unexpected error")
            return {"ok": False, "provider": provider, "url": url, "reason": msg, "latency_ms": None}

    # ── Vector store ──────────────────────────────────────────────────────────

    def check_vector_store(self) -> dict:
        """
        Probe the configured vector store.
        Currently supports Qdrant (HTTP probe) and in_memory (always ok).
        """
        vtype = settings.VECTOR_STORE_TYPE
        if vtype in ["in_memory", "cloud"]:
            return {"ok": True, "type": vtype, "reason": f"{vtype} store assumed available"}

        # Qdrant
        host = settings.QDRANT_HOST
        port = settings.QDRANT_PORT
        probe_url = f"http://{host}:{port}{_QDRANT_PROBE_PATH}"
        t0 = time.perf_counter()
        try:
            resp = requests.get(probe_url, timeout=_TIMEOUT)
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "type": "qdrant",
                    "url": f"{host}:{port}",
                    "reason": None,
                    "latency_ms": round(latency_ms, 1),
                }
            else:
                return {
                    "ok": False,
                    "type": "qdrant",
                    "url": f"{host}:{port}",
                    "reason": f"Qdrant responded with HTTP {resp.status_code}",
                    "latency_ms": None,
                }
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "type": "qdrant",
                "url": f"{host}:{port}",
                "reason": "Connection refused — is Qdrant running?",
                "latency_ms": None,
            }
        except requests.exceptions.Timeout:
            return {
                "ok": False,
                "type": "qdrant",
                "url": f"{host}:{port}",
                "reason": f"Qdrant did not respond within {_TIMEOUT}s",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "type": "qdrant",
                "url": f"{host}:{port}",
                "reason": f"Unexpected error: {exc}",
                "latency_ms": None,
            }

    # ── RAG ───────────────────────────────────────────────────────────────────

    def check_rag(self) -> dict:
        """
        Verify the RAG retriever stack is usable.
        A RAG check is considered healthy when:
          - Vector store is reachable (checked above)
          - Embedding model is loaded (import-time check)

        Returns same dict shape as other checks.
        """
        vs = self.check_vector_store()
        if not vs["ok"]:
            return {
                "ok": False,
                "reason": f"Vector store not reachable: {vs['reason']}",
                "vector_store": vs,
            }

        # Check embedding model import (will be fast if already loaded)
        try:
            from app.embeddings.mock_embedder import MockEmbedder  # always importable
            if settings.EMBEDDING_PROVIDER == "sentence_transformers":
                from app.embeddings.sentence_transformer_embedder import SentenceTransformerEmbedder  # noqa
            return {"ok": True, "reason": None, "vector_store": vs}
        except ImportError as exc:
            return {
                "ok": False,
                "reason": f"Embedding module import failed: {exc}",
                "vector_store": vs,
            }

    # ── Full status ───────────────────────────────────────────────────────────

    def full_status(self) -> dict:
        """
        Aggregate probe for all subsystems.
        Safe to call frequently (each check has its own timeout).
        """
        llm = self.check_llm()
        rag = self.check_rag()
        vs = rag.get("vector_store", {})

        all_ok = llm["ok"] and rag["ok"]
        status = "healthy" if all_ok else "degraded"

        return {
            "status": status,
            "llm_connected": llm["ok"],
            "llm_provider": llm.get("provider"),
            "llm_url": llm.get("url"),
            "llm_reason": llm.get("reason"),
            "llm_latency_ms": llm.get("latency_ms"),
            "rag_connected": rag["ok"],
            "rag_reason": rag.get("reason"),
            "vector_store_connected": vs.get("ok", False),
            "vector_store_type": vs.get("type"),
            "vector_store_reason": vs.get("reason"),
        }


# Module-level singleton
_health_service: Optional[SystemHealthService] = None


def get_health_service() -> SystemHealthService:
    global _health_service
    if _health_service is None:
        _health_service = SystemHealthService()
    return _health_service
