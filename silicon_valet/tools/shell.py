"""ShellExecTool — primary command execution tool routed through the RiskEngine."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable

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
        def call(self, params, **kwargs):
            raise NotImplementedError

try:
    import json5
except ImportError:
    import json as json5  # type: ignore[no-redef]

logger = logging.getLogger(__name__)


@register_tool("shell_exec")
class ShellExecTool(BaseTool):
    """Execute a shell command through the Silicon Valet Risk Engine."""

    description = (
        "Execute a shell command on the managed infrastructure. "
        "All commands are risk-classified and may require user approval."
    )
    parameters = [
        {"name": "command", "type": "string", "description": "The shell command to execute.", "required": True},
        {"name": "timeout", "type": "integer", "description": "Max execution time in seconds (default 30).", "required": False},
    ]

    _risk_engine: Any = None
    _approval_callback: Callable | None = None

    def call(self, params: str, **kwargs) -> str:
        try:
            parsed = json5.loads(params) if isinstance(params, str) else params
        except Exception as e:
            return json.dumps({"error": f"Failed to parse parameters: {e}"}, ensure_ascii=False)

        command = parsed.get("command", "").strip()
        if not command:
            return json.dumps({"error": "No command provided."}, ensure_ascii=False)

        timeout = parsed.get("timeout", 30)
        if self._risk_engine is None:
            return json.dumps({"error": "Risk engine not initialized."}, ensure_ascii=False)

        try:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                result = pool.submit(
                    lambda: asyncio.new_event_loop().run_until_complete(
                        self._risk_engine.execute(command=command, approval_callback=self._approval_callback, timeout=timeout)
                    )
                ).result()
        except Exception as e:
            logger.exception("Shell execution failed: %s", command)
            return json.dumps({"error": f"Execution failed: {e}", "command": command}, ensure_ascii=False)

        return json.dumps({
            "stdout": result.stdout, "stderr": result.stderr, "return_code": result.return_code,
            "tier": result.tier.value, "command": result.command, "duration_ms": result.duration_ms,
            "approved": result.approved, "backup_path": result.backup_path,
        }, ensure_ascii=False)
