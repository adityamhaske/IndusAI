from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class LLMInterface(ABC):
    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: The user input or prompt.
            system_prompt: Optional system context.
            
        Returns:
            The raw string response from the LLM.
        """
        pass
    
    @abstractmethod
    def generate_json(self, prompt: str, schema: Any, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate a structured JSON response.
        
        Args:
            prompt: The user input.
            schema: The Pydantic model or JSON schema to enforce.
            system_prompt: Optional system context.
            
        Returns:
            A dictionary matching the schema.
        """
        pass
