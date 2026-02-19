from typing import List, Optional
from app.core.schemas import ChatResponse
from app.core.exceptions import ValidationError

class ValidationService:
    def validate_response(self, response: ChatResponse, known_tags: List[str] = []) -> bool:
        """
        Validates the LLM response against constraints.
        
        Args:
            response: The structured response from the LLM.
            known_tags: A list of valid tags from the system.
            
        Raises:
            ValidationError: If the response fails any check.
            
        Returns:
            True if valid.
        """
        # 1. Check for empty source sections
        if not response.source_sections:
            # It's okay if confidence is low, but ideally we want sources.
            # For strictness:
            if response.confidence_score > 0.5:
                 pass # Warning?
        
        # 2. Hallucination Check: Verify tags
        # If the LLM returns tags, they must exist in our known_tags list (if provided)
        if known_tags:
            for tag in response.related_tags:
                if tag not in known_tags:
                    raise ValidationError(f"Hallucinated tag detected: {tag}")

        # 3. Schema Logic Checks
        if response.confidence_score < 0.0 or response.confidence_score > 1.0:
            raise ValidationError("Confidence score must be between 0 and 1.")

        return True
