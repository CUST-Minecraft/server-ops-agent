"""Embedding providers: Ollama for runtime, deterministic hash vectors for tests."""

from __future__ import annotations

import hashlib
import math
from typing import Protocol

import requests


class EmbeddingProvider(Protocol):
    model_id: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbeddingProvider:
    model_id = "hash-test"

    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for text in texts:
            vector = [0.0] * self.dimensions
            for token in text.lower().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:4], "big") % self.dimensions
                vector[index] += 1.0
            norm = math.sqrt(sum(value * value for value in vector)) or 1.0
            vectors.append([value / norm for value in vector])
        return vectors


class OllamaEmbeddingProvider:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen3-embedding:0.6b",
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model_id = model
        self.timeout = timeout

    def embed(self, texts: list[str]) -> list[list[float]]:
        response = requests.post(
            f"{self.base_url}/api/embed",
            json={"model": self.model_id, "input": texts},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise RuntimeError("Ollama embedding response has invalid shape")
        return embeddings


def build_embedding_provider(settings) -> EmbeddingProvider:
    if settings.recovery_embedding_provider == "ollama":
        return OllamaEmbeddingProvider(
            base_url=settings.ollama_base_url,
            model=settings.recovery_embedding_model,
            timeout=settings.recovery_embedding_timeout_seconds,
        )
    if settings.recovery_embedding_provider == "hash":
        return HashEmbeddingProvider()
    raise ValueError(
        f"不支持的 recovery embedding provider: {settings.recovery_embedding_provider}"
    )
