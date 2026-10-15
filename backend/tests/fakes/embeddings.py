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
