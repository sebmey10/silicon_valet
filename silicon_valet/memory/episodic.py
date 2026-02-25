"""Episodic memory — semantic search over past sessions and outcomes via ChromaDB."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from silicon_valet.memory.embeddings import OllamaEmbedder

logger = logging.getLogger(__name__)


@dataclass
class Episode:
    """A record of a past session interaction and its outcome."""

    session_id: str
    problem_description: str
    conversation_summary: str
    outcome: str  # 'resolved', 'escalated', 'abandoned'
    resolution_summary: str
    tags: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_search_text(self) -> str:
        """Combine fields into a single searchable string."""
        parts = [self.problem_description, self.conversation_summary, self.resolution_summary]
        return " ".join(parts)

    def to_metadata(self) -> dict:
        return {
            "session_id": self.session_id,
            "outcome": self.outcome,
            "tags": json.dumps(self.tags),
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_chroma_result(cls, id: str, metadata: dict, document: str) -> Episode:
        return cls(
            id=id,
            session_id=metadata.get("session_id", ""),
            problem_description=document,
            conversation_summary="",
            outcome=metadata.get("outcome", ""),
            resolution_summary="",
            tags=json.loads(metadata.get("tags", "[]")),
            timestamp=metadata.get("timestamp", ""),
        )


class EpisodicMemory:
    """Semantic memory over past sessions using ChromaDB with pre-computed embeddings."""

    def __init__(self, chromadb_path: Path, embedder: OllamaEmbedder) -> None:
        self.embedder = embedder
        self.client = chromadb.PersistentClient(path=str(chromadb_path))
        self.collection = self.client.get_or_create_collection(
            name="episodes",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Episodic memory initialized (%d episodes stored)", self.collection.count())

    async def store(self, episode: Episode) -> None:
        """Store an episode with its pre-computed embedding."""
        search_text = episode.to_search_text()
        embedding = await self.embedder.embed(search_text)
        self.collection.add(
            ids=[episode.id],
            embeddings=[embedding],
            metadatas=[episode.to_metadata()],
            documents=[search_text],
        )
        logger.debug("Stored episode %s", episode.id)

    async def search(self, query: str, n: int = 5) -> list[Episode]:
        """Search for similar past episodes using semantic similarity."""
        if self.collection.count() == 0:
            return []

        query_embedding = await self.embedder.embed(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n, self.collection.count()),
        )

        episodes = []
        for i in range(len(results["ids"][0])):
            ep = Episode.from_chroma_result(
                id=results["ids"][0][i],
                metadata=results["metadatas"][0][i],
                document=results["documents"][0][i],
            )
            episodes.append(ep)
        return episodes

    async def get_session_episodes(self, session_id: str) -> list[Episode]:
        """Retrieve all episodes from a specific session."""
        results = self.collection.get(
            where={"session_id": session_id},
        )
        episodes = []
        for i in range(len(results["ids"])):
            ep = Episode.from_chroma_result(
                id=results["ids"][i],
                metadata=results["metadatas"][i],
                document=results["documents"][i],
            )
            episodes.append(ep)
        return episodes

    def count(self) -> int:
        return self.collection.count()
