"""OllamaEmbedder — generates embeddings via Ollama's nomic-embed-text model."""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class OllamaEmbedder:
    """Generate text embeddings using Ollama's embedding API."""

    def __init__(self, ollama_url: str, model: str = "nomic-embed-text") -> None:
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string."""
        client = await self._get_client()
        response = await client.post(
            f"{self.ollama_url}/api/embeddings",
            json={"model": self.model, "prompt": text},
        )
        response.raise_for_status()
        data = response.json()
        return data["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts. Processes sequentially to avoid overloading CPU."""
        results = []
        for text in texts:
            embedding = await self.embed(text)
            results.append(embedding)
        return results

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
