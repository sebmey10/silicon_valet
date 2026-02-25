"""Risk engine — the single chokepoint through which all shell execution flows."""

from __future__ import annotations

import asyncio
import logging
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from silicon_valet.config import ValetConfig
from silicon_valet.risk.classifier import ClassifiedAction, RiskClassifier, RiskTier

logger = logging.getLogger(__name__)


@dataclass
class ExecutionResult:
    """Result of a command execution through the risk engine."""

    stdout: str
    stderr: str
    return_code: int
    tier: RiskTier
    command: str
    duration_ms: int
    backup_path: str | None = None
    approved: bool = True  # False if user denied


class RiskEngine:
    """The single chokepoint for all shell execution. Every command must pass through here."""

    def __init__(self, classifier: RiskClassifier, config: ValetConfig) -> None:
        self.classifier = classifier
        self.config = config
        self.execution_log: list[ExecutionResult] = []

    async def execute(
        self,
        command: str,
        approval_callback: Callable | None = None,
        timeout: int = 30,
    ) -> ExecutionResult:
        """Execute a command after risk classification and approval.

        Args:
            command: The shell command to execute.
            approval_callback: Async function that presents the risk prompt to the user
                             and returns True (approved) or False (denied).
                             Required for YELLOW and RED tier commands.
            timeout: Maximum execution time in seconds.

        Returns:
            ExecutionResult with output, return code, and metadata.
        """
        action = self.classifier.classify(command)
        logger.info("Risk: %s — %s — %s", action.tier.value.upper(), command, action.explanation)

        # GREEN: auto-execute
        if action.tier == RiskTier.GREEN and self.config.risk_auto_approve_green:
            return await self._run(action, timeout)

        # YELLOW/RED: require approval
        if approval_callback is None:
            logger.warning("No approval callback for %s command: %s", action.tier.value, command)
            return ExecutionResult(
                stdout="",
                stderr="No approval callback provided for non-GREEN command",
                return_code=-1,
                tier=action.tier,
                command=command,
                duration_ms=0,
                approved=False,
            )

        approved = await approval_callback(action)
        if not approved:
            logger.info("User denied: %s", command)
            return ExecutionResult(
                stdout="",
                stderr="Command denied by user",
                return_code=-1,
                tier=action.tier,
                command=command,
                duration_ms=0,
                approved=False,
            )

        # Create backup if needed
        backup_path = None
        if action.backup_needed:
            backup_path = await self._create_backup(action)

        result = await self._run(action, timeout)
        result.backup_path = backup_path
        return result

    async def _run(self, action: ClassifiedAction, timeout: int) -> ExecutionResult:
        """Execute the command and capture output."""
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_shell(
                action.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            duration_ms = int((time.monotonic() - start) * 1000)

            result = ExecutionResult(
                stdout=stdout_bytes.decode("utf-8", errors="replace"),
                stderr=stderr_bytes.decode("utf-8", errors="replace"),
                return_code=proc.returncode or 0,
                tier=action.tier,
                command=action.command,
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.monotonic() - start) * 1000)
            result = ExecutionResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                return_code=-1,
                tier=action.tier,
                command=action.command,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.monotonic() - start) * 1000)
            result = ExecutionResult(
                stdout="",
                stderr=str(e),
                return_code=-1,
                tier=action.tier,
                command=action.command,
                duration_ms=duration_ms,
            )

        self.execution_log.append(result)
        return result

    async def _create_backup(self, action: ClassifiedAction) -> str | None:
        """Create a backup of files that will be modified."""
        # Extract file paths from the command (basic heuristic)
        parts = action.command.split()
        backup_dir = self.config.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime("%Y%m%d_%H%M%S")

        for part in parts:
            # If a part looks like a file path that exists
            path = Path(part)
            if path.exists() and path.is_file():
                backup_name = f"{path.name}.{timestamp}.bak"
                backup_path = backup_dir / backup_name
                try:
                    shutil.copy2(str(path), str(backup_path))
                    logger.info("Backup created: %s → %s", path, backup_path)
                    return str(backup_path)
                except (PermissionError, OSError) as e:
                    logger.warning("Backup failed for %s: %s", path, e)

        return None

    def get_recent_executions(self, n: int = 10) -> list[ExecutionResult]:
        """Return the most recent command executions."""
        return self.execution_log[-n:]
