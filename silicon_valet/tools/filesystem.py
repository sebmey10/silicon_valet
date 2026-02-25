"""Filesystem tools — read, write, search, diff files."""

from __future__ import annotations

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

logger = logging.getLogger(__name__)


def _exec_via_risk(command, risk_engine, approval_callback):
    import asyncio, concurrent.futures
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(
            lambda: asyncio.new_event_loop().run_until_complete(
                risk_engine.execute(command=command, approval_callback=approval_callback, timeout=30)
            )
        ).result()


@register_tool("read_file")
class ReadFileTool(BaseTool):
    description = "Read the contents of a file."
    parameters = [
        {"name": "path", "type": "string", "description": "File path to read.", "required": True},
        {"name": "lines", "type": "integer", "description": "Number of lines (default 100).", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        path = parsed.get("path", "")
        lines = parsed.get("lines", 100)
        result = _exec_via_risk(f"head -n {lines} {path}", self._risk_engine, self._approval_callback)
        return json.dumps({"content": result.stdout, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("write_file")
class WriteFileTool(BaseTool):
    description = "Write content to a file (requires confirmation)."
    parameters = [
        {"name": "path", "type": "string", "description": "File path to write.", "required": True},
        {"name": "content", "type": "string", "description": "Content to write.", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        path = parsed.get("path", "")
        content = parsed.get("content", "")
        # Use tee to write (YELLOW tier)
        import shlex
        escaped = content.replace("'", "'\\''")
        cmd = f"echo '{escaped}' | tee {shlex.quote(path)}"
        result = _exec_via_risk(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"success": result.return_code == 0, "stderr": result.stderr}, ensure_ascii=False)


@register_tool("search_files")
class SearchFilesTool(BaseTool):
    description = "Search for files by pattern or content."
    parameters = [
        {"name": "pattern", "type": "string", "description": "Search pattern (grep or filename glob).", "required": True},
        {"name": "directory", "type": "string", "description": "Directory to search (default '.').", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        pattern = parsed.get("pattern", "")
        directory = parsed.get("directory", ".")
        result = _exec_via_risk(f"grep -r --include='*' -l '{pattern}' {directory} 2>/dev/null | head -20", self._risk_engine, self._approval_callback)
        return json.dumps({"files": result.stdout.strip().split("\n") if result.stdout.strip() else []}, ensure_ascii=False)


@register_tool("file_diff")
class FileDiffTool(BaseTool):
    description = "Show differences between two files."
    parameters = [
        {"name": "path1", "type": "string", "description": "First file.", "required": True},
        {"name": "path2", "type": "string", "description": "Second file.", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        result = _exec_via_risk(f"diff {parsed['path1']} {parsed['path2']}", self._risk_engine, self._approval_callback)
        return json.dumps({"diff": result.stdout, "return_code": result.return_code}, ensure_ascii=False)
