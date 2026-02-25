"""Tests for the handoff / mission brief system."""

import json
import pytest
from pathlib import Path

from silicon_valet.orchestrator.handoff import HandoffManager, MissionBrief


@pytest.fixture
def handoff(tmp_path):
    return HandoffManager(tmp_path)


class TestMissionBrief:
    def test_create_brief(self):
        brief = MissionBrief(
            objective="Diagnose nginx 502 errors",
            completed_steps=["Checked nginx status", "Read error logs"],
            discoveries=["Upstream timeout in logs"],
            next_step="Check backend service health",
        )
        assert brief.task_id
        assert brief.objective == "Diagnose nginx 502 errors"
        assert len(brief.completed_steps) == 2

    def test_brief_serialization(self):
        brief = MissionBrief(
            objective="Test",
            completed_steps=["step1"],
            discoveries=["finding1"],
            next_step="next",
            ruled_out=["not this"],
            dna_context_ids=[1, 2, 3],
        )
        data = brief.to_dict()
        restored = MissionBrief.from_dict(data)
        assert restored.objective == brief.objective
        assert restored.completed_steps == brief.completed_steps
        assert restored.discoveries == brief.discoveries
        assert restored.ruled_out == brief.ruled_out
        assert restored.dna_context_ids == brief.dna_context_ids


class TestHandoffManager:
    def test_write_and_read_brief(self, handoff):
        brief = MissionBrief(objective="Test task", next_step="Do something")
        path = handoff.write_brief(brief)
        assert path.exists()

        loaded = handoff.read_brief(brief.task_id)
        assert loaded is not None
        assert loaded.objective == "Test task"
        assert loaded.next_step == "Do something"

    def test_read_nonexistent_brief(self, handoff):
        assert handoff.read_brief("nonexistent") is None

    def test_list_briefs(self, handoff):
        for i in range(3):
            brief = MissionBrief(objective=f"Task {i}")
            handoff.write_brief(brief)

        briefs = handoff.list_briefs()
        assert len(briefs) == 3

    def test_needs_handoff(self, handoff):
        assert handoff.needs_handoff(3500, 4096) is True
        assert handoff.needs_handoff(3000, 4096) is False
        assert handoff.needs_handoff(2000, 4096) is False

    def test_brief_to_prompt(self, handoff):
        from unittest.mock import MagicMock
        mock_dna = MagicMock()
        mock_dna.get_service.return_value = None

        brief = MissionBrief(
            objective="Fix nginx",
            completed_steps=["Checked status"],
            discoveries=["Upstream error"],
            next_step="Restart backend",
            ruled_out=["DNS issue"],
        )

        prompt = handoff.brief_to_prompt(brief, mock_dna)
        assert "MISSION BRIEF" in prompt
        assert "Fix nginx" in prompt
        assert "Checked status" in prompt
        assert "Upstream error" in prompt
        assert "Restart backend" in prompt
        assert "DNS issue" in prompt
