from typing import List
from sentence_transformers import SentenceTransformer
from app.core.interfaces.embedding_interface import EmbeddingInterface

class SentenceTransformerEmbedder(EmbeddingInterface):
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> List[float]:
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return self.model.encode(texts).tolist()
