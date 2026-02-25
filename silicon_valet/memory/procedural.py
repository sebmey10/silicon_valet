"""Procedural memory — runbook library for learned and seeded problem resolutions."""

from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chromadb

from silicon_valet.memory.embeddings import OllamaEmbedder

logger = logging.getLogger(__name__)

RUNBOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS runbooks (
    id              TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    problem_pattern TEXT NOT NULL,
    symptoms        TEXT NOT NULL,  -- JSON array
    root_cause      TEXT,
    steps           TEXT NOT NULL,  -- JSON array of {action, command, explanation, risk_tier}
    verification    TEXT,
    tags            TEXT NOT NULL,  -- JSON array
    pack_source     TEXT,  -- NULL = learned from session, otherwise pack name
    success_count   INTEGER DEFAULT 0,
    created_at      TEXT NOT NULL,
    last_used       TEXT
);
"""


@dataclass
class RunbookEntry:
    title: str
    problem_pattern: str
    symptoms: list[str]
    steps: list[dict]
    root_cause: str | None = None
    verification: str | None = None
    tags: list[str] = field(default_factory=list)
    pack_source: str | None = None
    success_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_used: str | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_search_text(self) -> str:
        parts = [self.title, self.problem_pattern]
        parts.extend(self.symptoms)
        if self.root_cause:
            parts.append(self.root_cause)
        return " ".join(parts)

    def to_row(self) -> tuple:
        return (
            self.id, self.title, self.problem_pattern,
            json.dumps(self.symptoms), self.root_cause,
            json.dumps(self.steps), self.verification,
            json.dumps(self.tags), self.pack_source,
            self.success_count, self.created_at, self.last_used,
        )

    @classmethod
    def from_row(cls, row: dict) -> RunbookEntry:
        return cls(
            id=row["id"],
            title=row["title"],
            problem_pattern=row["problem_pattern"],
            symptoms=json.loads(row["symptoms"]),
            root_cause=row["root_cause"],
            steps=json.loads(row["steps"]),
            verification=row["verification"],
            tags=json.loads(row["tags"]),
            pack_source=row["pack_source"],
            success_count=row["success_count"],
            created_at=row["created_at"],
            last_used=row["last_used"],
        )


class RunbookLibrary:
    """Stored procedures for known problem patterns with semantic search."""

    def __init__(self, db_path: Path, chromadb_path: Path, embedder: OllamaEmbedder) -> None:
        self.embedder = embedder
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(RUNBOOK_SCHEMA)
        self.conn.commit()

        self.chroma_client = chromadb.PersistentClient(path=str(chromadb_path))
        self.collection = self.chroma_client.get_or_create_collection(
            name="runbooks",
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("Runbook library initialized (%d entries)", self.count())

    async def add(self, entry: RunbookEntry) -> None:
        """Add a runbook entry to both SQLite and ChromaDB."""
        self.conn.execute(
            "INSERT OR REPLACE INTO runbooks "
            "(id, title, problem_pattern, symptoms, root_cause, steps, verification, "
            "tags, pack_source, success_count, created_at, last_used) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            entry.to_row(),
        )
        self.conn.commit()

        embedding = await self.embedder.embed(entry.to_search_text())
        self.collection.upsert(
            ids=[entry.id],
            embeddings=[embedding],
            metadatas=[{"title": entry.title, "pack_source": entry.pack_source or "learned"}],
            documents=[entry.to_search_text()],
        )
        logger.debug("Added runbook: %s", entry.title)

    async def search(self, query: str, n: int = 5) -> list[RunbookEntry]:
        """Search runbooks by semantic similarity."""
        if self.collection.count() == 0:
            return []

        query_embedding = await self.embedder.embed(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=min(n, self.collection.count()),
        )

        entries = []
        for rb_id in results["ids"][0]:
            row = self.conn.execute("SELECT * FROM runbooks WHERE id = ?", (rb_id,)).fetchone()
            if row:
                entries.append(RunbookEntry.from_row(row))
        return entries

    async def record_success(self, runbook_id: str) -> None:
        """Increment success count and update last_used timestamp."""
        now = datetime.now(timezone.utc).isoformat()
        self.conn.execute(
            "UPDATE runbooks SET success_count = success_count + 1, last_used = ? WHERE id = ?",
            (now, runbook_id),
        )
        self.conn.commit()

    def get_all(self) -> list[RunbookEntry]:
        """Get all runbook entries."""
        rows = self.conn.execute("SELECT * FROM runbooks ORDER BY success_count DESC").fetchall()
        return [RunbookEntry.from_row(r) for r in rows]

    def count(self) -> int:
        row = self.conn.execute("SELECT COUNT(*) as cnt FROM runbooks").fetchone()
        return row["cnt"]

    def close(self) -> None:
        self.conn.close()
