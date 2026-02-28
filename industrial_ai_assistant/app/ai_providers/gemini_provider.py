import time
import httpx
from typing import Dict, Any, Optional
from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

class GeminiProvider(AIProvider):
    """
    Implements the AIProvider interface for Google Gemini models (gemini-1.5-pro, gemini-1.5-flash).
    Uses a shared async client to prevent connection leaks under heavy load.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-1.5-flash"):
        if not api_key:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            
        self.api_key = api_key
        self.model = model
        self.base_url = "https://generativelanguage.googleapis.com"
        self._sync_client = httpx.Client(
            base_url=self.base_url,
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=100),
            timeout=None
        )

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, request: AIRequest) -> AIResponse:
        start_time = time.perf_counter()
        
        if not self.api_key:
            return self._build_error_response("Gemini API key missing from configuration", "CONNECTION", start_time)

        # Gemini expects a specific JSON body mapping
        contents = []
        if request.system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"System Instruction: {request.system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Acknowledged."}]})
             
        contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            }
        }
        
        if request.response_format == "json":
            payload["generationConfig"]["responseMimeType"] = "application/json"

        headers = {
            "Content-Type": "application/json"
        }
        
        # No timeout — let Gemini take as long as needed
        try:
            url = f"/v1beta/models/{self.model}:streamGenerateContent?key={self.api_key}&alt=sse"
            
            with self._sync_client.stream(
                "POST",
                url,
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
                        try:
                            chunk = json.loads(data_str)
                            candidates = chunk.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                if parts and "text" in parts[0]:
                                    raw_text += parts[0]["text"]
                                    first_token_received = True
                                    last_token_timestamp = current_time
                                    
                            usage = chunk.get("usageMetadata", {})
                            if usage:
                                prompt_tokens = usage.get("promptTokenCount", prompt_tokens)
                                completion_tokens = usage.get("candidatesTokenCount", completion_tokens)
                        except json.JSONDecodeError:
                            continue
            
            parsed_json = None
            if request.response_format == "json":
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
            return self._build_error_response(f"Gemini HTTP error: {e.response.status_code} - {e.response.text[:100]}", "CONNECTION", start_time)
        except httpx.RequestError as e:
            return self._build_error_response(f"Gemini connection error: {str(e)}", "CONNECTION", start_time)
        except Exception as e:
            return self._build_error_response(f"Unexpected Gemini exception: {str(e)}", "UNKNOWN", start_time)

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
