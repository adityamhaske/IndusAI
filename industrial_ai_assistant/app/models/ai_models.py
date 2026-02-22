from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union

class AIRequest(BaseModel):
    """Normalized payload sent to any AI Provider."""
    prompt: str = Field(description="The primary user prompt or question")
    system_prompt: Optional[str] = Field(default=None, description="Optional system behavior instruction")
    temperature: float = Field(default=0.0, description="Sampling temperature")
    max_tokens: int = Field(default=1024, description="Maximum tokens to generate")
    response_format: str = Field(default="text", description="'text' or 'json'")
    json_schema: Optional[Dict[str, Any]] = Field(default=None, description="Schema definition if response_format is json")
    timeout_ms: int = Field(default=30000, description="Timeout threshold in milliseconds")

class AIResponse(BaseModel):
    """Normalized output returned from any AI Provider."""
    raw_output: str = Field(default="", description="The raw string output from the model")
    parsed_output: Optional[Dict[str, Any]] = Field(default=None, description="Successfully parsed JSON object if requested")
    model_name: str = Field(description="Which exact model fulfilled the request (e.g. 'mistral:latest')")
    provider_name: str = Field(description="Which provider fulfilled the request (e.g. 'local_ollama')")
    prompt_tokens: int = Field(default=0, description="Tokens used in prompt")
    completion_tokens: int = Field(default=0, description="Tokens used in completion")
    latency_ms: int = Field(default=0, description="Milliseconds elapsed entirely within the provider boundary")
    success: bool = Field(default=True, description="False if a timeout, connection error, or parse error occurred")
    error: Optional[str] = Field(default=None, description="Error message if success is False")
    error_type: Optional[str] = Field(default=None, description="'TIMEOUT', 'CONNECTION', 'PARSE', 'UNKNOWN'")
