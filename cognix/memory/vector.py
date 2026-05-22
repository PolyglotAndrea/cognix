"""Small local text-vector helpers.

This is not a replacement for a real embedding index. It gives Cognix a
dependency-free semantic-ish similarity layer for local-first memory ranking and
HITL answer suggestions. The storage contract can later be backed by sqlite-vec,
pgvector, or an external embedding service.
"""

from __future__ import annotations

import hashlib
import math
import re


VECTOR_DIM = 256


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", text.lower())
    chars = re.findall(r"[\u4e00-\u9fff]", text)
    bigrams = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    return [token for token in [*words, *bigrams] if len(token.strip()) > 1]


def text_vector(text: str, *, dim: int = VECTOR_DIM) -> list[float]:
    vector = [0.0] * dim
    for token in tokenize(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[idx] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[i] * right[i] for i in range(size))
