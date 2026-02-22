import time
import httpx
from typing import Dict, Any, Optional
from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

class OpenAIProvider(AIProvider):
    """
    Implements the AIProvider interface for OpenAI models (GPT-4o, GPT-3.5-Turbo).
    Uses a shared async client to prevent connection leaks under heavy load.
    """
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        if not api_key:
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
            
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.openai.com/v1/chat/completions"
        self._sync_client = httpx.Client(
            base_url="https://api.openai.com",
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=30.0
        )

    @property
    def provider_name(self) -> str:
        return "openai"

    def generate(self, request: AIRequest) -> AIResponse:
        start_time = time.perf_counter()
        
        if not self.api_key:
            return self._build_error_response("OpenAI API key missing from configuration", "CONNECTION", start_time)

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        timeout_seconds = request.timeout_ms / 1000.0

        try:
            response = self._sync_client.post(
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=timeout_seconds
            )
            response.raise_for_status()
            res_data = response.json()
            
            choices = res_data.get("choices", [])
            if not choices:
                return self._build_error_response("OpenAI returned an empty choices array.", "PARSE", start_time)
                
            raw_text = choices[0].get("message", {}).get("content", "")
            usage = res_data.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            
            parsed_json = None
            if request.response_format == "json":
                import json
                try:
                    parsed_json = json.loads(raw_text)
                except json.JSONDecodeError as decode_err:
                    return self._build_error_response(f"Malformed JSON output: {str(decode_err)}", "PARSE", start_time, raw_output=raw_text)

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

        except httpx.TimeoutException:
            return self._build_error_response(f"OpenAI generation timed out after {timeout_seconds}s", "TIMEOUT", start_time)
        except httpx.HTTPStatusError as e:
            return self._build_error_response(f"OpenAI HTTP error: {e.response.status_code} - {e.response.text[:100]}", "CONNECTION", start_time)
        except httpx.RequestError as e:
            return self._build_error_response(f"OpenAI connection error: {str(e)}", "CONNECTION", start_time)
        except Exception as e:
            return self._build_error_response(f"Unexpected OpenAI exception: {str(e)}", "UNKNOWN", start_time)

    def _build_error_response(self, error_msg: str, error_type: str, start_time: float, raw_output: str = "") -> AIResponse:
        latency = int((time.perf_counter() - start_time) * 1000)
        return AIResponse(
            raw_output=raw_output,
            model_name=self.model,
            provider_name=self.provider_name,
            latency_ms=latency,
            success=False,
            error=error_msg,
            error_type=error_type
        )
