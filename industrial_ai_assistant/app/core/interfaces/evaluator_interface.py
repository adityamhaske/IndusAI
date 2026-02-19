from abc import ABC, abstractmethod
from typing import Dict, Any, List
from app.core.schemas import ChatResponse

class EvaluatorInterface(ABC):
    @abstractmethod
    def evaluate_response(self, query: str, response: ChatResponse, ground_truth: Optional[Dict[str, Any]] = None) -> Dict[str, float]:
        """
        Evaluate a single response.
        
        Args:
            query: The input query.
            response: The generated ChatResponse.
            ground_truth: Optional ground truth data.
            
        Returns:
            Dictionary of metric names and scores.
        """
        pass
