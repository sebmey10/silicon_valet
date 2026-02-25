"""Tests for memory systems — embeddings, episodic, procedural."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silicon_valet.memory.embeddings import OllamaEmbedder
from silicon_valet.memory.episodic import Episode, EpisodicMemory
from silicon_valet.memory.procedural import RunbookEntry, RunbookLibrary


@pytest.fixture
def mock_embedder():
    """An OllamaEmbedder that returns deterministic fake embeddings."""
    embedder = OllamaEmbedder("http://fake:11434", "nomic-embed-text")

    # Generate simple but different embeddings based on text content
    call_count = 0

    async def fake_embed(text: str) -> list[float]:
        nonlocal call_count
        call_count += 1
        # Create a simple embedding that varies by text hash
        base = hash(text) % 1000 / 1000.0
        return [base + i * 0.01 for i in range(384)]

    embedder.embed = fake_embed
    return embedder


@pytest.fixture
def episodic_memory(tmp_path, mock_embedder):
    return EpisodicMemory(tmp_path / "chromadb", mock_embedder)


@pytest.fixture
def runbook_library(tmp_path, mock_embedder):
    return RunbookLibrary(
        tmp_path / "runbooks.sqlite3",
        tmp_path / "chromadb",
        mock_embedder,
    )


class TestOllamaEmbedder:
    @pytest.mark.asyncio
    async def test_embed_returns_vector(self, mock_embedder):
        result = await mock_embedder.embed("test text")
        assert isinstance(result, list)
        assert len(result) == 384
        assert all(isinstance(x, float) for x in result)

    @pytest.mark.asyncio
    async def test_embed_batch(self, mock_embedder):
        # Override with batch capability
        embedder = OllamaEmbedder("http://fake:11434")
        embedder.embed = mock_embedder.embed
        results = await embedder.embed_batch(["text 1", "text 2", "text 3"])
        assert len(results) == 3
        assert all(len(r) == 384 for r in results)


class TestEpisodicMemory:
    @pytest.mark.asyncio
    async def test_store_and_count(self, episodic_memory):
        ep = Episode(
            session_id="sess-001",
            problem_description="nginx returning 502 on port 80",
            conversation_summary="Investigated nginx config, found upstream was down",
            outcome="resolved",
            resolution_summary="Restarted the upstream service",
        )
        await episodic_memory.store(ep)
        assert episodic_memory.count() == 1

    @pytest.mark.asyncio
    async def test_search_returns_results(self, episodic_memory):
        ep1 = Episode(
            session_id="sess-001",
            problem_description="nginx returning 502 bad gateway",
            conversation_summary="Investigated nginx, upstream down",
            outcome="resolved",
            resolution_summary="Restarted upstream",
        )
        ep2 = Episode(
            session_id="sess-002",
            problem_description="disk space running low on worker-01",
            conversation_summary="Checked df, found large logs",
            outcome="resolved",
            resolution_summary="Rotated logs",
        )
        await episodic_memory.store(ep1)
        await episodic_memory.store(ep2)

        results = await episodic_memory.search("502 error on nginx", n=2)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_empty_returns_empty(self, episodic_memory):
        results = await episodic_memory.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_session_episodes(self, episodic_memory):
        ep = Episode(
            session_id="sess-001",
            problem_description="test problem",
            conversation_summary="test conversation",
            outcome="resolved",
            resolution_summary="test resolution",
        )
        await episodic_memory.store(ep)

        results = await episodic_memory.get_session_episodes("sess-001")
        assert len(results) == 1
        assert results[0].session_id == "sess-001"


class TestRunbookLibrary:
    @pytest.mark.asyncio
    async def test_add_and_count(self, runbook_library):
        rb = RunbookEntry(
            title="Fix nginx 502",
            problem_pattern="nginx returns 502 bad gateway",
            symptoms=["502 error in browser", "upstream unreachable in error log"],
            steps=[
                {"action": "check", "command": "systemctl status upstream", "explanation": "Verify upstream status", "risk_tier": "green"},
                {"action": "fix", "command": "systemctl restart upstream", "explanation": "Restart the upstream service", "risk_tier": "yellow"},
            ],
            root_cause="Upstream service crashed",
            verification="curl localhost:80 returns 200",
            tags=["nginx", "502", "upstream"],
        )
        await runbook_library.add(rb)
        assert runbook_library.count() == 1

    @pytest.mark.asyncio
    async def test_search_returns_results(self, runbook_library):
        rb = RunbookEntry(
            title="Fix nginx 502",
            problem_pattern="nginx returns 502 bad gateway",
            symptoms=["502 error in browser"],
            steps=[{"action": "restart", "command": "systemctl restart nginx"}],
            tags=["nginx"],
        )
        await runbook_library.add(rb)

        results = await runbook_library.search("nginx 502 error", n=3)
        assert len(results) == 1
        assert results[0].title == "Fix nginx 502"

    @pytest.mark.asyncio
    async def test_record_success(self, runbook_library):
        rb = RunbookEntry(
            title="Fix disk space",
            problem_pattern="disk space low",
            symptoms=["df shows >90%"],
            steps=[{"action": "rotate", "command": "logrotate -f /etc/logrotate.conf"}],
            tags=["disk"],
        )
        await runbook_library.add(rb)
        await runbook_library.record_success(rb.id)

        all_entries = runbook_library.get_all()
        assert all_entries[0].success_count == 1
        assert all_entries[0].last_used is not None

    @pytest.mark.asyncio
    async def test_search_empty_returns_empty(self, runbook_library):
        results = await runbook_library.search("anything")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_all(self, runbook_library):
        for i in range(3):
            rb = RunbookEntry(
                title=f"Runbook {i}",
                problem_pattern=f"Problem {i}",
                symptoms=[f"Symptom {i}"],
                steps=[{"action": f"step {i}"}],
                tags=[f"tag{i}"],
            )
            await runbook_library.add(rb)
        assert len(runbook_library.get_all()) == 3
