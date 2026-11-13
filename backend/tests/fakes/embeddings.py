"""
Deterministic fake for Chroma's DefaultEmbeddingFunction.

The real one downloads an ~80MB ONNX model on first use. Tests only need
stable vectors with the right shape, so this hashes each document into a
384-dim unit vector (same dimension as all-MiniLM-L6-v2). Identical text gives
identical vectors, so exact-match retrieval still works.
"""
from __future__ import annotations

import hashlib

import numpy as np

DIM = 384


def fake_embed(texts):
    vectors = []
    for text in texts:
        seed = int.from_bytes(hashlib.sha256(str(text).encode("utf-8")).digest()[:8], "little")
        vec = np.random.default_rng(seed).standard_normal(DIM).astype(np.float32)
        vectors.append(vec / np.linalg.norm(vec))
    return vectors


def install(monkeypatch) -> None:
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def __call__(self, input):  # noqa: N807 - matches chroma's signature
        return fake_embed(input)

    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", __call__)


# ---------------------------------------------------------------------------
# Bag-of-words embedding (the memory battery)
# ---------------------------------------------------------------------------
# fake_embed only matches identical text, so it can't test recall by
# reference ("remember the lighthouse?"). bow_embed hashes each word into a
# dimension: texts that share words get nearby vectors, deterministically,
# with no model download. Crude, but it ranks the way a battery needs.

_STOP = {"the", "and", "for", "with", "that", "this", "you", "your", "was", "are",
         "but", "not", "have", "about", "what", "remember", "cass", "user"}


def bow_embed(texts):
    import re
    vectors = []
    for text in texts:
        vec = np.zeros(DIM, dtype=np.float32)
        for word in re.findall(r"[a-z0-9]+", str(text).lower()):
            if len(word) < 3 or word in _STOP:
                continue
            h = int.from_bytes(hashlib.sha256(word.encode("utf-8")).digest()[:8], "little")
            vec[h % DIM] += 1.0
        norm = np.linalg.norm(vec)
        vectors.append(vec / norm if norm else np.full(DIM, 1 / np.sqrt(DIM), dtype=np.float32))
    return vectors


def install_bow(monkeypatch) -> None:
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    def __call__(self, input):  # noqa: N807
        return bow_embed(input)

    monkeypatch.setattr(DefaultEmbeddingFunction, "__call__", __call__)
