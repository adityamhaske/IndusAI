import time
import google.generativeai as genai
from typing import Dict, Any, Optional
from app.core.interfaces.ai_provider import AIProvider
from app.models.ai_models import AIRequest, AIResponse

class GeminiProvider(AIProvider):
    """
    Implements the AIProvider interface for Google Gemini models (gemini-1.5-pro, gemini-1.5-flash).
    Uses the official google-generativeai SDK.
    """
    
    def __init__(self, api_key: str, model: str = "gemini-2.5-flash"):
        if not api_key:
            import os
            api_key = os.environ.get("GEMINI_API_KEY", "")
            
        self.api_key = api_key
        self.model_name = model
        
        if self.api_key:
            genai.configure(api_key=self.api_key)

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

        try:
            model = genai.GenerativeModel(
                model_name=self.model_name,
                generation_config={
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_tokens,
                }
            )

            full_prompt = request.prompt
            if request.system_prompt:
                full_prompt = f"System Instruction: {request.system_prompt}\n\n{request.prompt}"

            response = model.generate_content(full_prompt)
            
            try:
                raw_text = response.text
            except Exception as access_err:
                # Fallback: check if candidates and parts exist to construct the text
                if response.candidates and response.candidates[0].content.parts:
                    raw_text = "".join(part.text for part in response.candidates[0].content.parts if hasattr(part, 'text'))
                else:
                    finish_reason = response.candidates[0].finish_reason.name if response.candidates else "UNKNOWN"
                    raise ValueError(f"Gemini returned no text content (finish_reason: {finish_reason}). Error: {access_err}")
            
            # Note: google.generativeai doesn't easily expose exact token counts in the text response 
            # without additional API calls, so we mock or estimate them if needed.
            prompt_tokens = 0
            completion_tokens = 0
            
            parsed_json = None
            if request.response_format == "json":
                import json
                try:
                    # Clean up markdown code blocks if gemini returns them
                    cleaned_text = raw_text
                    if cleaned_text.startswith("```json"):
                        cleaned_text = cleaned_text[7:]
                        if cleaned_text.endswith("```"):
                            cleaned_text = cleaned_text[:-3]
                    parsed_json = json.loads(cleaned_text)
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
