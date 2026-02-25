"""Memory tools — search episodic memory and runbook library."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging

try:
    from qwen_agent.tools.base import BaseTool, register_tool
except ImportError:
    def register_tool(name):
        def decorator(cls):
            cls._tool_name = name
            return cls
        return decorator
    class BaseTool:
        description = ""
        parameters = []
        def call(self, params, **kwargs): raise NotImplementedError

try:
    import json5
except ImportError:
    import json as json5

from silicon_valet.memory.procedural import RunbookEntry

logger = logging.getLogger(__name__)


def _run_async(coro):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(lambda: asyncio.new_event_loop().run_until_complete(coro)).result()


@register_tool("search_history")
class SearchHistoryTool(BaseTool):
    description = "Search past session episodes for similar problems."
    parameters = [
        {"name": "query", "type": "string", "description": "Problem description to search for.", "required": True},
        {"name": "n", "type": "integer", "description": "Number of results (default 5).", "required": False},
    ]
    _episodic = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        episodes = _run_async(self._episodic.search(parsed["query"], n=parsed.get("n", 5)))
        return json.dumps({
            "episodes": [
                {"id": e.id, "problem": e.problem_description, "outcome": e.outcome,
                 "resolution": e.resolution_summary, "timestamp": e.timestamp}
                for e in episodes
            ]
        }, ensure_ascii=False)


@register_tool("search_runbooks")
class SearchRunbooksTool(BaseTool):
    description = "Search the runbook library for known problem resolutions."
    parameters = [
        {"name": "query", "type": "string", "description": "Problem description to search for.", "required": True},
        {"name": "n", "type": "integer", "description": "Number of results (default 5).", "required": False},
    ]
    _runbook_lib = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        runbooks = _run_async(self._runbook_lib.search(parsed["query"], n=parsed.get("n", 5)))
        return json.dumps({
            "runbooks": [
                {"id": r.id, "title": r.title, "pattern": r.problem_pattern,
                 "root_cause": r.root_cause, "steps": r.steps, "success_count": r.success_count}
                for r in runbooks
            ]
        }, ensure_ascii=False)


@register_tool("save_runbook")
class SaveRunbookTool(BaseTool):
    description = "Save a new runbook entry from a resolved session."
    parameters = [
        {"name": "title", "type": "string", "description": "Runbook title.", "required": True},
        {"name": "problem_pattern", "type": "string", "description": "Problem pattern description.", "required": True},
        {"name": "symptoms", "type": "array", "description": "List of symptom strings.", "required": True},
        {"name": "steps", "type": "array", "description": "List of step objects.", "required": True},
        {"name": "root_cause", "type": "string", "description": "Root cause.", "required": False},
        {"name": "verification", "type": "string", "description": "How to verify resolution.", "required": False},
        {"name": "tags", "type": "array", "description": "Tags for categorization.", "required": False},
    ]
    _runbook_lib = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        entry = RunbookEntry(
            title=parsed["title"],
            problem_pattern=parsed["problem_pattern"],
            symptoms=parsed.get("symptoms", []),
            steps=parsed.get("steps", []),
            root_cause=parsed.get("root_cause"),
            verification=parsed.get("verification"),
            tags=parsed.get("tags", []),
        )
        _run_async(self._runbook_lib.add(entry))
        return json.dumps({"saved": True, "id": entry.id, "title": entry.title}, ensure_ascii=False)
