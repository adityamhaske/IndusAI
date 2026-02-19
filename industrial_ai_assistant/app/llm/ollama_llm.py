import json
from typing import Optional, Dict, Any
import requests
from app.core.interfaces.llm_interface import LLMInterface
from app.core.exceptions import LLMGenerationError

class OllamaLLM(LLMInterface):
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        url = f"{self.base_url}/api/generate"
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": False
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return response.json().get("response", "")
        except requests.RequestException as e:
            raise LLMGenerationError(f"Ollama generation failed: {str(e)}")

    def generate_json(self, prompt: str, schema: Any, system_prompt: Optional[str] = None) -> Dict[str, Any]:
        # For Ollama, we enforce JSON mode
        url = f"{self.base_url}/api/generate"
        
        full_prompt = prompt
        if system_prompt:
            full_prompt = f"System: {system_prompt}\nUser: {prompt}"
            
        full_prompt += "\nOutput strict JSON."

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "format": "json",
            "stream": False
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            json_str = response.json().get("response", "{}")
            return json.loads(json_str)
        except (requests.RequestException, json.JSONDecodeError) as e:
            raise LLMGenerationError(f"Ollama JSON generation failed: {str(e)}")
