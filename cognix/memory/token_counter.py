"""Token counting utilities for context budget enforcement."""

from __future__ import annotations

import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# Model -> encoding name mapping. tiktoken uses cl100k_base for GPT-4/3.5-turbo.
_MODEL_ENCODING: dict[str, str] = {
    "gpt-4o": "cl100k_base",
    "gpt-4o-mini": "cl100k_base",
    "gpt-4-turbo": "cl100k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5-turbo": "cl100k_base",
    "claude-3-opus": "cl100k_base",
    "claude-3-sonnet": "cl100k_base",
    "claude-3-haiku": "cl100k_base",
}

_DEFAULT_ENCODING = "cl100k_base"


@lru_cache(maxsize=8)
def _get_encoding(model: str):
    """Lazy-load and cache tiktoken encoding for a model."""
    try:
        import tiktoken
    except ImportError:
        return None

    # Try model-specific encoding first, fall back to default
    encoding_name = _DEFAULT_ENCODING
    for prefix, name in _MODEL_ENCODING.items():
        if model.startswith(prefix):
            encoding_name = name
            break

    try:
        return tiktoken.get_encoding(encoding_name)
    except Exception:
        logger.debug("Failed to get tiktoken encoding '%s', using default", encoding_name)
        try:
            return tiktoken.get_encoding(_DEFAULT_ENCODING)
        except Exception:
            return None


def count_tokens(text: str, model: str = "gpt-4o") -> int:
    """Count tokens in text using tiktoken. Falls back to len//4 if tiktoken unavailable."""
    if not text:
        return 0
    encoding = _get_encoding(model)
    if encoding is None:
        # Rough fallback: ~4 chars per token for English
        return len(text) // 4
    return len(encoding.encode(text))


def truncate_to_budget(text: str, max_tokens: int, model: str = "gpt-4o") -> str:
    """Truncate text to fit within max_tokens. Keeps the end (most recent content)."""
    if not text or max_tokens <= 0:
        return ""
    encoding = _get_encoding(model)
    if encoding is None:
        # Rough fallback
        max_chars = max_tokens * 4
        return text[-max_chars:] if len(text) > max_chars else text

    tokens = encoding.encode(text)
    if len(tokens) <= max_tokens:
        return text
    # Keep the last max_tokens tokens (most recent content)
    truncated_tokens = tokens[-max_tokens:]
    return encoding.decode(truncated_tokens)


def count_message_tokens(messages: list[dict], model: str = "gpt-4o") -> int:
    """Count total tokens in a list of LLM messages (OpenAI format)."""
    if not messages:
        return 0
    total = 0
    for msg in messages:
        # Each message has overhead (~4 tokens for role/formatting)
        total += 4
        content = msg.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += count_tokens(part.get("text", ""), model)
    return total
