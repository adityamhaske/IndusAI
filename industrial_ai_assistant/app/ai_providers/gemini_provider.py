import time
from typing import Dict, Any, Optional
from google import genai
from google.genai import types

from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

class GeminiProvider(AIProvider):
    """
    Implements the AIProvider interface for Google Gemini models.
    Uses the new official google-genai SDK.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not api_key:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            
        self.api_key = api_key
        # fallback to gemini-1.5-flash if invalid model string provided
        # 2.5-flash doesn't exist, they are 1.5 or 2.0
        self.model_name = "gemini-2.0-flash" if "2.0" in model else ("gemini-1.5-flash" if "2.5" in model else model)
        
        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def provider_type(self) -> str:
        return "cloud"

    def generate(self, request: AIRequest) -> AIResponse:
        start_time = time.perf_counter()
        
        if not self.client:
            return self._build_error_response("Gemini API key missing from configuration", "CONNECTION", start_time)

        try:
            full_prompt = request.prompt
            if request.system_prompt:
                full_prompt = f"System Instruction: {request.system_prompt}\n\n{request.prompt}"

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=full_prompt,
                config=types.GenerateContentConfig(
                    temperature=request.temperature,
                    max_output_tokens=request.max_tokens,
                    response_mime_type="application/json" if request.response_format == "json" else "text/plain",
                )
            )
            
            raw_text = ""
            try:
                raw_text = response.text or ""
            except ValueError as access_err:
                finish_reason = getattr(response.candidates[0].finish_reason, "name", str(response.candidates[0].finish_reason)) if response.candidates else "UNKNOWN"
                return self._build_error_response(f"Gemini returned no text content (finish_reason: {finish_reason}). Error: {access_err}", "EMPTY_RESPONSE", start_time)

            if not raw_text.strip():
                finish_reason = getattr(response.candidates[0].finish_reason, "name", str(response.candidates[0].finish_reason)) if response.candidates else "UNKNOWN"
                return self._build_error_response(f"Gemini returned empty text (finish_reason: {finish_reason})", "EMPTY_RESPONSE", start_time)

            prompt_tokens = 0
            completion_tokens = 0
            if response.usage_metadata:
                prompt_tokens = response.usage_metadata.prompt_token_count or 0
                completion_tokens = response.usage_metadata.candidates_token_count or 0
            
            parsed_json = None
            if request.response_format == "json":
                import json
                try:
                    cleaned_text = raw_text.strip()
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]
                    if cleaned_text.endswith("```"):
                        cleaned_text = cleaned_text[:-3]
                    parsed_json = json.loads(cleaned_text.strip())
                except json.JSONDecodeError as decode_err:
                    return self._build_error_response(f"Malformed JSON output: {str(decode_err)}", "PARSE", start_time, raw_output=raw_text)

            latency = int((time.perf_counter() - start_time) * 1000)
            return AIResponse(
                raw_output=raw_text,
                parsed_output=parsed_json,
                model_name=self.model_name,
                provider_name=self.provider_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                latency_ms=latency,
                success=True,
                error=None
            )

        except Exception as e:
            return self._build_error_response(f"Unexpected Gemini exception: {str(e)}", "UNKNOWN", start_time)

    def _build_error_response(self, error_msg: str, error_type: str, start_time: float, raw_output: str = "") -> AIResponse:
        latency = int((time.perf_counter() - start_time) * 1000)
        return AIResponse(
            raw_output=raw_output,
            model_name=self.model_name,
            provider_name=self.provider_name,
            latency_ms=latency,
            success=False,
            error=error_msg,
            error_type=error_type
        )
