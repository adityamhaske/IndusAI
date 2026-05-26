"""
SystemHealthService — Subsystem probes for the health endpoint.

Rewritten for cloud-native architecture. Probes Qdrant Cloud and Firestore.
Ollama and SentenceTransformer probes removed.
"""
import logging
import time
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 5  # seconds
_QDRANT_PROBE_PATH = "/collections"


class SystemHealthService:

    # ── Qdrant Cloud ──────────────────────────────────────────────────────────

    def check_vector_store(self) -> dict:
        """Probe the Qdrant Cloud vector store."""
        from app.config.settings import settings

        url = settings.QDRANT_URL
        api_key = settings.QDRANT_API_KEY

        if not url:
            return {"ok": False, "type": "qdrant_cloud", "reason": "QDRANT_URL not configured"}

        probe_url = f"{url.rstrip('/')}{_QDRANT_PROBE_PATH}"
        headers = {}
        if api_key:
            headers["api-key"] = api_key

        t0 = time.perf_counter()
        try:
            resp = requests.get(probe_url, timeout=_TIMEOUT, headers=headers)
            latency_ms = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                return {
                    "ok": True,
                    "type": "qdrant_cloud",
                    "url": url,
                    "reason": None,
                    "latency_ms": round(latency_ms, 1),
                }
            else:
                return {
                    "ok": False,
                    "type": "qdrant_cloud",
                    "url": url,
                    "reason": f"Qdrant responded with HTTP {resp.status_code}",
                    "latency_ms": None,
                }
        except requests.exceptions.ConnectionError:
            return {
                "ok": False,
                "type": "qdrant_cloud",
                "url": url,
                "reason": "Connection refused — check QDRANT_URL",
                "latency_ms": None,
            }
        except requests.exceptions.Timeout:
            return {
                "ok": False,
                "type": "qdrant_cloud",
                "url": url,
                "reason": f"Qdrant did not respond within {_TIMEOUT}s",
                "latency_ms": None,
            }
        except Exception as exc:
            return {
                "ok": False,
                "type": "qdrant_cloud",
                "url": url,
                "reason": f"Unexpected error: {exc}",
                "latency_ms": None,
            }

    # ── Firestore ────────────────────────────────────────────────────────────

    def check_firestore(self) -> dict:
        """Probe Firestore connectivity."""
        t0 = time.perf_counter()
        try:
            from app.core.firebase import get_firestore_client
            db = get_firestore_client()
            # Simple read to verify connectivity
            list(db.collection("_health_check").limit(1).stream())
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "ok": True,
                "type": "firestore",
                "reason": None,
                "latency_ms": round(latency_ms, 1),
            }
        except Exception as exc:
            latency_ms = (time.perf_counter() - t0) * 1000
            return {
                "ok": False,
                "type": "firestore",
                "reason": f"Firestore probe failed: {exc}",
                "latency_ms": round(latency_ms, 1),
            }

    # ── Full status ───────────────────────────────────────────────────────────

    def full_status(self) -> dict:
        """
        Aggregate probe for all subsystems.
        Safe to call frequently (each check has its own timeout).
        """
        vs = self.check_vector_store()
        fs = self.check_firestore()

        all_ok = vs["ok"] and fs["ok"]
        status = "healthy" if all_ok else "degraded"

        return {
            "status": status,
            "vector_store_connected": vs["ok"],
            "vector_store_type": vs.get("type"),
            "vector_store_url": vs.get("url"),
            "vector_store_reason": vs.get("reason"),
            "vector_store_latency_ms": vs.get("latency_ms"),
            "firestore_connected": fs["ok"],
            "firestore_reason": fs.get("reason"),
            "firestore_latency_ms": fs.get("latency_ms"),
        }


# Module-level singleton
_health_service: Optional[SystemHealthService] = None


def get_health_service() -> SystemHealthService:
    global _health_service
    if _health_service is None:
        _health_service = SystemHealthService()
    return _health_service
