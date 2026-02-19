from typing import List

class HallucinationChecker:
    def check(self, response_text: str, context_chunks: List[str]) -> float:
        """
        Returns a score from 0.0 (hallucinated) to 1.0 (grounded).
        For now, returns a mock score.
        """
        # TODO: Implement LLM-as-a-judge or NLI model here
        return 0.9
