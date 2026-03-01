"""
IntelligentCache — Deterministic response cache with LRU eviction (Phase 21).

Caches LLM responses keyed by hash of (query + retrieved context IDs + stats snapshot).
Eliminates redundant LLM calls for identical analytical scenarios.
"""
import hashlib
import logging
import time
from collections import OrderedDict
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 300  # 5 minutes
MAX_CACHE_SIZE = 200


class CachedResponse:
    __slots__ = ("response", "created_at", "ttl", "hit_count")

    def __init__(self, response: Any, ttl: int = DEFAULT_TTL_SECONDS):
        self.response = response
        self.created_at = time.time()
        self.ttl = ttl
        self.hit_count = 0

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > self.ttl


class IntelligentCache:
    """
    LRU cache for deterministic LLM responses.
    Thread-safe via GIL for single-process deployments.
    """

    def __init__(self, max_size: int = MAX_CACHE_SIZE, default_ttl: int = DEFAULT_TTL_SECONDS):
        self._cache: OrderedDict[str, CachedResponse] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._hits = 0
        self._misses = 0

    @staticmethod
    def build_key(query: str, context_ids: list[str], stats_snapshot: dict) -> str:
        """Build deterministic cache key from query + context + stats."""
        payload = f"{query}|{'|'.join(sorted(context_ids))}|{sorted(stats_snapshot.items())}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached response. Returns None on miss or expiry."""
        entry = self._cache.get(key)
        if entry is None:
            self._misses += 1
            return None

        if entry.is_expired():
            del self._cache[key]
            self._misses += 1
            logger.debug("Cache EXPIRED for key=%s", key[:12])
            return None

        # Move to end (most recently used)
        self._cache.move_to_end(key)
        entry.hit_count += 1
        self._hits += 1
        logger.info("Cache HIT for key=%s (hit_count=%d, latency=<1ms)", key[:12], entry.hit_count)
        return entry.response

    def put(self, key: str, response: Any, ttl: Optional[int] = None) -> None:
        """Store response in cache with optional custom TTL."""
        if key in self._cache:
            self._cache.move_to_end(key)
            self._cache[key] = CachedResponse(response, ttl or self._default_ttl)
        else:
            # Evict oldest if at capacity
            while len(self._cache) >= self._max_size:
                evicted_key, _ = self._cache.popitem(last=False)
                logger.debug("Cache EVICTED key=%s (LRU)", evicted_key[:12])
            self._cache[key] = CachedResponse(response, ttl or self._default_ttl)
        logger.debug("Cache STORED key=%s (size=%d/%d)", key[:12], len(self._cache), self._max_size)

    def invalidate(self, key: str) -> bool:
        """Remove specific entry. Returns True if found."""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self) -> int:
        """Clear entire cache. Returns number of entries cleared."""
        count = len(self._cache)
        self._cache.clear()
        return count

    @property
    def stats(self) -> dict:
        """Return cache performance statistics."""
        total = self._hits + self._misses
        return {
            "size": len(self._cache),
            "max_size": self._max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": round(self._hits / total, 3) if total > 0 else 0.0,
            "total_requests": total,
        }


# ── Singleton ──────────────────────────────────────────────────────────────────

_instance: IntelligentCache | None = None


def get_intelligent_cache() -> IntelligentCache:
    global _instance
    if _instance is None:
        _instance = IntelligentCache()
    return _instance
