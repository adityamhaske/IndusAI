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

    @property
    def provider_type(self) -> str:
        return "cloud"

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
            "stream": True,
            "stream_options": {"include_usage": True}
        }
        
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # No timeout — let OpenAI take as long as needed
        try:
            with self._sync_client.stream(
                "POST",
                "/v1/chat/completions",
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(None)
            ) as response:
                response.raise_for_status()
                
                raw_text = ""
                prompt_tokens = 0
                completion_tokens = 0
                last_token_timestamp = time.perf_counter()
                first_token_received = False
                
                import json
                for line in response.iter_lines():
                        
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                if "content" in delta and delta["content"]:
                                    raw_text += delta["content"]
                                    first_token_received = True
                                    last_token_timestamp = current_time
                            
                            if "usage" in chunk and chunk["usage"]:
                                prompt_tokens = chunk["usage"].get("prompt_tokens", 0)
                                completion_tokens = chunk["usage"].get("completion_tokens", 0)
                        except json.JSONDecodeError:
                            continue
            
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
