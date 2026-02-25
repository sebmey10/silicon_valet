"""Tests for slash commands."""

import pytest
from unittest.mock import AsyncMock, MagicMock, PropertyMock

from silicon_valet.cli.commands import handle_command, COMMANDS


@pytest.fixture
def mock_session():
    session = MagicMock()
    session.session_id = "test-1234"
    session.history = [
        {"role": "user", "content": "What services are running?"},
        {"role": "assistant", "content": "Here are the services..."},
    ]
    # DNA store
    session.dna = MagicMock()
    session.dna.get_all_nodes.return_value = [MagicMock(), MagicMock()]
    session.dna.get_all_services.return_value = [
        MagicMock(status="running"),
        MagicMock(status="running"),
        MagicMock(status="stopped"),
    ]
    session.dna.get_context_summary.return_value = "2 nodes, 3 services"
    # Risk engine
    session.risk_engine = MagicMock()
    session.risk_engine.execution_log = []
    # Handoff
    session.handoff = MagicMock()
    session.handoff.write_brief.return_value = "/tmp/brief.json"
    return session


class TestCommands:
    @pytest.mark.asyncio
    async def test_help(self, mock_session):
        result = await handle_command("/help", mock_session)
        assert "Available commands" in result
        for cmd in COMMANDS:
            assert cmd in result

    @pytest.mark.asyncio
    async def test_status(self, mock_session):
        result = await handle_command("/status", mock_session)
        assert "test-1234" in result
        assert "Nodes: 2" in result
        assert "Services: 3" in result

    @pytest.mark.asyncio
    async def test_dna(self, mock_session):
        result = await handle_command("/dna", mock_session)
        assert "2 nodes, 3 services" in result

    @pytest.mark.asyncio
    async def test_brief(self, mock_session):
        result = await handle_command("/brief Investigating nginx", mock_session)
        assert "Mission brief saved" in result

    @pytest.mark.asyncio
    async def test_history_empty(self, mock_session):
        result = await handle_command("/history", mock_session)
        assert "No commands" in result

    @pytest.mark.asyncio
    async def test_history_with_entries(self, mock_session):
        entry = MagicMock()
        entry.tier = "GREEN"
        entry.command = "ls -la"
        entry.return_code = 0
        mock_session.risk_engine.execution_log = [entry]
        result = await handle_command("/history", mock_session)
        assert "ls -la" in result
        assert "GREEN" in result

    @pytest.mark.asyncio
    async def test_unknown_command(self, mock_session):
        result = await handle_command("/foobar", mock_session)
        assert "Unknown command" in result

    @pytest.mark.asyncio
    async def test_quit(self, mock_session):
        result = await handle_command("/quit", mock_session)
        assert result == "QUIT"
