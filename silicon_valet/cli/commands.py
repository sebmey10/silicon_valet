"""Slash commands — in-session commands for status, history, and control."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silicon_valet.server.session import SessionManager

logger = logging.getLogger(__name__)

COMMANDS = {
    "/status": "Show session statistics and cluster health",
    "/dna": "Show infrastructure DNA summary",
    "/brief": "Create a mission brief and start fresh context",
    "/history": "Show recent command execution history",
    "/runbooks": "List available runbook entries",
    "/explain": "Show detailed reasoning for last response",
    "/packs": "List active domain packs",
    "/help": "Show available commands",
    "/quit": "Disconnect from Silicon Valet",
}


async def handle_command(text: str, session: "SessionManager") -> str | None:
    """Parse and execute a slash command. Returns response text or None."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    handler = _HANDLERS.get(cmd)
    if handler:
        return await handler(session, args)
    return f"Unknown command: {cmd}\nType /help for available commands."


async def _cmd_help(session: "SessionManager", args: str) -> str:
    lines = ["Available commands:", ""]
    for cmd, desc in COMMANDS.items():
        lines.append(f"  {cmd:12s}  {desc}")
    return "\n".join(lines)


async def _cmd_status(session: "SessionManager", args: str) -> str:
    nodes = session.dna.get_all_nodes()
    services = session.dna.get_all_services()
    running = [s for s in services if s.status == "running"]
    exec_log = session.risk_engine.execution_log

    lines = [
        f"Session: {session.session_id}",
        f"Messages: {len(session.history)}",
        f"Nodes: {len(nodes)}",
        f"Services: {len(services)} ({len(running)} running)",
        f"Commands executed: {len(exec_log)}",
    ]
    return "\n".join(lines)


async def _cmd_dna(session: "SessionManager", args: str) -> str:
    return session.dna.get_context_summary()


async def _cmd_brief(session: "SessionManager", args: str) -> str:
    from silicon_valet.orchestrator.handoff import MissionBrief

    brief = MissionBrief(
        objective=args or "Continued investigation",
        completed_steps=[
            m["content"][:80]
            for m in session.history
            if m["role"] == "user"
        ],
        discoveries=[],
        next_step="Continue from mission brief",
    )
    path = session.handoff.write_brief(brief)
    session.history.clear()
    return f"Mission brief saved: {brief.task_id}\nContext cleared. Resume with /resume {brief.task_id}"


async def _cmd_history(session: "SessionManager", args: str) -> str:
    log = session.risk_engine.execution_log
    if not log:
        return "No commands executed in this session."
    lines = ["Recent commands:", ""]
    for entry in log[-10:]:
        tier = entry.tier
        cmd = entry.command[:60]
        rc = entry.return_code
        lines.append(f"  [{tier}] {cmd} → rc={rc}")
    return "\n".join(lines)


async def _cmd_runbooks(session: "SessionManager", args: str) -> str:
    try:
        from silicon_valet.memory.procedural import RunbookLibrary
        # Access runbook library through memory context
        runbooks = session.memory.runbook.get_all_sync()
        if not runbooks:
            return "No runbooks available yet."
        lines = ["Available runbooks:", ""]
        for rb in runbooks[:20]:
            lines.append(f"  [{rb.id[:8]}] {rb.title} (used {rb.success_count}x)")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listing runbooks: {e}"


async def _cmd_packs(session: "SessionManager", args: str) -> str:
    return "Domain packs: use /status for active pack information."


async def _cmd_explain(session: "SessionManager", args: str) -> str:
    return "Explanation mode: ask your question again with 'explain why' for detailed reasoning."


async def _cmd_quit(session: "SessionManager", args: str) -> str:
    return "QUIT"


_HANDLERS = {
    "/help": _cmd_help,
    "/status": _cmd_status,
    "/dna": _cmd_dna,
    "/brief": _cmd_brief,
    "/history": _cmd_history,
    "/runbooks": _cmd_runbooks,
    "/packs": _cmd_packs,
    "/explain": _cmd_explain,
    "/quit": _cmd_quit,
}
