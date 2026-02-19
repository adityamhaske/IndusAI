import re

def clean_text(text: str) -> str:
    """Removes extra whitespace and non-printable characters."""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def truncate_text(text: str, max_length: int = 1000) -> str:
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."
