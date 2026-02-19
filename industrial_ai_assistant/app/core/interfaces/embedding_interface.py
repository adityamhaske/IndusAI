from abc import ABC, abstractmethod
from typing import List

class EmbeddingInterface(ABC):
    @abstractmethod
    def embed_text(self, text: str) -> List[float]:
        """
        Embed a single text string.
        
        Args:
            text: Single string to embed.
            
        Returns:
            A list of floats representing the embedding vector.
        """
        pass

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Embed a batch of texts.
        
        Args:
            texts: List of strings to embed.
            
        Returns:
            A list of embedding vectors.
        """
        pass
