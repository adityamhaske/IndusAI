import litellm
import os
from typing import Optional

litellm.drop_params = True

DEFAULT_MODEL = "gemini/gemini-1.5-flash"

def get_api_key():
    return os.environ.get("GEMINI_API_KEY")


async def generate(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 8192,
) -> str:
    messages = []
    if system_prompt:
        messages.append({
            "role": "system", 
            "content": system_prompt
        })
    messages.append({"role": "user", "content": prompt})
    
    response = await litellm.acompletion(
        model=DEFAULT_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
        api_key=get_api_key(),
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content

def generate_sync(
    prompt: str,
    system_prompt: Optional[str] = None,
    max_tokens: int = 8192,
) -> str:
    messages = []
    if system_prompt:
        messages.append({
            "role": "system", 
            "content": system_prompt
        })
    messages.append({"role": "user", "content": prompt})
    
    response = litellm.completion(
        model=DEFAULT_MODEL,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.2,
        api_key=get_api_key(),
        response_format={"type": "json_object"}
    )
    return response.choices[0].message.content

async def embed(text: str) -> list[float]:
    response = await litellm.aembedding(
        model="gemini/text-embedding-004",
        input=text,
        api_key=get_api_key(),
    )
    return getattr(response.data[0], "embedding", response.data[0].get("embedding") if isinstance(response.data[0], dict) else None)

def embed_sync(text: str) -> list[float]:
    response = litellm.embedding(
        model="gemini/text-embedding-004",
        input=text,
        api_key=get_api_key(),
    )
    return getattr(response.data[0], "embedding", response.data[0].get("embedding") if isinstance(response.data[0], dict) else None)

async def embed_batch(texts: list[str]) -> list[list[float]]:
    # LiteLLM aembedding does not officially document list[str] inputs for all providers, 
    # but for Gemini it usually works. We'll use a loop or asyncio.gather to be safe
    # if it doesn't support batch out of the box, but aembedding often takes input: list
    # Let's try passing list directly, as litellm passes input down to provider.
    response = await litellm.aembedding(
        model="gemini/text-embedding-004",
        input=texts,
        api_key=get_api_key(),
    )
    return [getattr(d, "embedding", d.get("embedding") if isinstance(d, dict) else None) for d in response.data]
