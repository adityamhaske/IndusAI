"""
Test retrieval with inline mocks.
MockEmbedder and InMemoryStore were deleted in Phase 1. 
This test now uses inline mocks per user directive (Q1: Option A).
"""
import pytest


class _MockEmbedder:
    """Returns a fixed-dimension zero vector for any text."""
    def embed_text(self, text: str):
        return [0.0] * 768


def test_mock_embedder_returns_vector():
    embedder = _MockEmbedder()
    vec = embedder.embed_text("hello world")
    assert len(vec) == 768
    assert all(v == 0.0 for v in vec)


def test_mock_embedder_deterministic():
    embedder = _MockEmbedder()
    v1 = embedder.embed_text("test")
    v2 = embedder.embed_text("test")
    assert v1 == v2
