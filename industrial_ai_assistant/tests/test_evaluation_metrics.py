import pytest
from app.evaluation.metrics_calculator import MetricsCalculator
from app.core.schemas import ChatResponse

def test_metrics_calculation():
    calc = MetricsCalculator()
    
    response = ChatResponse(
        summary="Test",
        confidence_score=0.9,
        related_tags=["tag1"],
        source_sections=["Section A"],
        limitations="None"
    )
    
    ground_truth = {
        "required_tags": ["tag1", "tag2"],
        "must_cite_sections": ["Section A"]
    }
    
    metrics = calc.calculate(response, ground_truth)
    
    assert metrics["tag_recall"] == 0.5 # 1 out of 2 tags
    assert metrics["citation_recall"] == 1.0 # Section A found
