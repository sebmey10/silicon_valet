"""Tests for the task router."""

import pytest

from silicon_valet.orchestrator.router import TaskRouter, AgentType


@pytest.fixture
def router():
    return TaskRouter()


class TestTaskRouter:
    def test_default_routes_to_planner(self, router):
        assert router.route("What services are running?") == AgentType.PLANNER

    def test_routes_infra_to_planner(self, router):
        assert router.route("Check if nginx is running") == AgentType.PLANNER
        assert router.route("Restart the web server") == AgentType.PLANNER
        assert router.route("Why is port 8080 not responding?") == AgentType.PLANNER

    def test_routes_code_to_coder(self, router):
        assert router.route("Write me a bash script to monitor disk usage") == AgentType.CODER
        assert router.route("Generate a config for nginx") == AgentType.CODER
        assert router.route("Analyze this code for bugs") == AgentType.CODER
        assert router.route("Write a Python function to parse logs") == AgentType.CODER

    def test_thinking_mode_complex(self, router):
        assert router.needs_thinking("Why is the service crashing?") is True
        assert router.needs_thinking("Diagnose the connection timeout") is True
        assert router.needs_thinking("What's the root cause of the 502 errors?") is True
        assert router.needs_thinking("Investigate the intermittent failures") is True

    def test_thinking_mode_simple(self, router):
        assert router.needs_thinking("Show me the running services") is False
        assert router.needs_thinking("List all pods") is False
        assert router.needs_thinking("What port is nginx on?") is False
