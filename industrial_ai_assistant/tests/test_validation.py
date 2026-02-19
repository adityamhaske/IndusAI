import pytest
from app.services.validation_service import ValidationService
from app.core.schemas import ChatResponse
from app.core.exceptions import ValidationError

def test_validation_hallucination_check():
    validator = ValidationService()
    
    # Valid response
    response = ChatResponse(
        summary="Test",
        confidence_score=0.9,
        related_tags=["valid_tag"],
        limitations="None"
    )
    
    # Should pass if tag is known
    assert validator.validate_response(response, known_tags=["valid_tag"]) is True
    
    # Should fail if tag is unknown
    with pytest.raises(ValidationError):
        validator.validate_response(response, known_tags=["other_tag"])
