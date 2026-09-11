"""
MVP embedding function.

For a real deployment this would call an embedding model (e.g. a hosted
API or a local sentence-transformers model). To keep this MVP's dependency
footprint small and fully offline-runnable (no model download, no GPU/CPU
heavy torch install), we use a deterministic hashing-based bag-of-words
vectorizer. It is good enough to demonstrate real retrieval behavior
(semantically-similar-ish text lands closer in cosine space than unrelated
text, for a small curated domain-knowledge set) but it is NOT a production
quality embedding model.

Swap `embed_text` for a real embedding client to move beyond MVP.
"""
import hashlib
import math
import re

VECTOR_SIZE = 256

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def embed_text(text: str) -> list[float]:
    vec = [0.0] * VECTOR_SIZE
    tokens = _tokenize(text)
    if not tokens:
        return vec
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % VECTOR_SIZE
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign

    norm = math.sqrt(sum(v * v for v in vec))
    if norm > 0:
        vec = [v / norm for v in vec]
    return vec
