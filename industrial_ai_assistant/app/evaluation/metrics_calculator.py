from typing import Dict, Any, List
from app.core.schemas import ChatResponse

class MetricsCalculator:
    def calculate(self, response: ChatResponse, ground_truth: Dict[str, Any]) -> Dict[str, float]:
        metrics = {}
        
        # 1. Hallucination / Fact Check (Mock logic)
        # Check if required tags are present
        required_tags = set(ground_truth.get("required_tags", []))
        provided_tags = set(response.related_tags)
        
        if required_tags:
            overlap = required_tags.intersection(provided_tags)
            metrics["tag_recall"] = len(overlap) / len(required_tags)
        else:
            metrics["tag_recall"] = 1.0

        # 2. Source Citation Check
        must_cite = set(ground_truth.get("must_cite_sections", []))
        cited = set(response.source_sections)
        
        if must_cite:
            # Fuzzy check or exact match? doing simple check for now
            # check if any cited string contains the required string
            hits = 0
            for req in must_cite:
                for c in cited:
                    if req in c:
                        hits += 1
                        break
            metrics["citation_recall"] = hits / len(must_cite)
        else:
            metrics["citation_recall"] = 1.0
            
        metrics["confidence_alignment"] = 1.0 if response.confidence_score > 0.7 else 0.5

        return metrics
