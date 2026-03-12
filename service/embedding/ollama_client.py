"""Ollama embedding client with batch support."""

from __future__ import annotations

from typing import Any

import requests


class OllamaEmbeddingClient:
    """Thin wrapper for Ollama ``/api/embed`` endpoint."""

    def __init__(self, endpoint: str, model: str, timeout_seconds: int = 120) -> None:
        self.endpoint = endpoint
        self.model = model
        self.timeout_seconds = timeout_seconds

    def embed(self, text: str) -> list[float]:
        """Compute one embedding vector."""
        vectors = self.embed_batch([text], batch_size=1)
        return vectors[0]

    def embed_batch(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        """Compute embeddings for a batch of texts."""
        if not texts:
            return []
        if batch_size <= 0:
            raise ValueError("batch_size must be greater than 0")

        vectors: list[list[float]] = []
        for offset in range(0, len(texts), batch_size):
            batch = texts[offset : offset + batch_size]
            payload = {"model": self.model, "input": batch}
            response = requests.post(self.endpoint, json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            vectors.extend(_extract_embeddings(response.json()))

        if len(vectors) != len(texts):
            raise RuntimeError(
                "Ollama embedding response count mismatch: "
                f"expected={len(texts)} got={len(vectors)}"
            )
        return vectors


def _extract_embeddings(payload: dict[str, Any]) -> list[list[float]]:
    """Normalize Ollama-compatible payload into ``list[list[float]]``."""
    embeddings = payload.get("embeddings")
    if isinstance(embeddings, list):
        if embeddings and isinstance(embeddings[0], (int, float)):
            return [[float(v) for v in embeddings]]
        return [[float(v) for v in vector] for vector in embeddings]

    one = payload.get("embedding")
    if isinstance(one, list):
        return [[float(v) for v in one]]

    data = payload.get("data")
    if isinstance(data, list):
        parsed: list[list[float]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            vector = item.get("embedding")
            if isinstance(vector, list):
                parsed.append([float(v) for v in vector])
        if parsed:
            return parsed

    raise RuntimeError(f"Unexpected Ollama embedding payload: keys={sorted(payload.keys())}")
