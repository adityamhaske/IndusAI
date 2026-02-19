from typing import List
import random
from app.core.interfaces.embedding_interface import EmbeddingInterface

class MockEmbedder(EmbeddingInterface):
    def embed_text(self, text: str) -> List[float]:
        # Return random vector of size 384
        return [random.random() for _ in range(384)]

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self.embed_text(t) for t in texts]
