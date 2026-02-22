import json
import time
import requests
from typing import Any, Dict, Optional
from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

class LocalOllamaProvider(AIProvider):
    """
    Implements the AIProvider interface for a local Ollama instance.
    """
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "mistral"):
        self.base_url = base_url
        self.model = model

    @property
    def provider_name(self) -> str:
        return "local_ollama"

    @property
    def provider_type(self) -> str:
        return "local"

    def generate(self, request: AIRequest) -> AIResponse:
        start_time = time.perf_counter()
        url = f"{self.base_url}/api/generate"
        
        full_prompt = request.prompt
        if request.system_prompt:
            full_prompt = f"System: {request.system_prompt}\nUser: {request.prompt}"
            
        if request.response_format == "json":
            full_prompt += "\nOutput strict JSON."

        payload = {
            "model": self.model,
            "prompt": full_prompt,
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens
            }
        }
        
        if request.response_format == "json":
            payload["format"] = "json"

        # Ollama timeout translation (timeout is handled by requests wrapper)
        timeout_seconds = request.timeout_ms / 1000.0
        idle_timeout_seconds = 10.0

        try:
            response = requests.post(url, json=payload, stream=True, timeout=(5.0, timeout_seconds))
            response.raise_for_status()
            
            raw_text = ""
            prompt_tokens = 0
            completion_tokens = 0
            last_token_timestamp = time.perf_counter()
            first_token_received = False
            
            for line in response.iter_lines():
                current_time = time.perf_counter()
                
                # Streaming Watchdog: Abort if tokens are stalling wildly during generation
                if first_token_received and (current_time - last_token_timestamp > idle_timeout_seconds):
                    raise TimeoutError(f"Local model generation exceeded configured idle timeout ({idle_timeout_seconds}s stall).")
                
                if line:
                    chunk = json.loads(line)
                    if "response" in chunk:
                        raw_text += chunk["response"]
                        first_token_received = True
                        last_token_timestamp = current_time
                        
                    if chunk.get("done"):
                        prompt_tokens = chunk.get("prompt_eval_count", 0)
                        completion_tokens = chunk.get("eval_count", 0)
                        break
            
            parsed_json = None
            if request.response_format == "json":
                try:
                    parsed_json = json.loads(raw_text)
                except json.JSONDecodeError as decode_err:
                    latency = int((time.perf_counter() - start_time) * 1000)
                    return AIResponse(
                        raw_output=raw_text,
                        model_name=self.model,
                        provider_name=self.provider_name,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        latency_ms=latency,
                        success=False,
                        error=f"Malformed JSON output: {str(decode_err)}",
                        error_type="PARSE"
                    )
            
            latency = int((time.perf_counter() - start_time) * 1000)
            return AIResponse(
                raw_output=raw_text,
                parsed_output=parsed_json,
                model_name=self.model,
                provider_name=self.provider_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency,
                success=True,
                error=None
            )

        except (requests.exceptions.Timeout, TimeoutError) as e:
            latency = int((time.perf_counter() - start_time) * 1000)
            msg = "Local model generation exceeded configured idle timeout."
            return AIResponse(
                raw_output="",
                model_name=self.model,
                provider_name=self.provider_name,
                latency_ms=latency,
                success=False,
                error=msg,
                error_type="TIMEOUT"
            )
        except requests.exceptions.RequestException as e:
            latency = int((time.perf_counter() - start_time) * 1000)
            return AIResponse(
                raw_output="",
                model_name=self.model,
                provider_name=self.provider_name,
                latency_ms=latency,
                success=False,
                error=f"Ollama connection error: {str(e)}",
                error_type="CONNECTION"
            )
        except Exception as e:
            latency = int((time.perf_counter() - start_time) * 1000)
            return AIResponse(
                raw_output="",
                model_name=self.model,
                provider_name=self.provider_name,
                latency_ms=latency,
                success=False,
                error=f"Unexpected Ollama exception: {str(e)}",
                error_type="UNKNOWN"
            )
