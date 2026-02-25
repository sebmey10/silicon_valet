"""Risk classifier — categorizes commands into GREEN, YELLOW, or RED tiers."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum

from silicon_valet.risk.patterns import GREEN_PATTERNS, RED_PATTERNS, YELLOW_PATTERNS


class RiskTier(Enum):
    GREEN = "green"    # Auto-execute (read-only)
    YELLOW = "yellow"  # Preview + confirm (modification)
    RED = "red"        # Explicit type-to-confirm (destructive)


@dataclass
class ClassifiedAction:
    """A command with its risk classification and metadata."""

    command: str
    tier: RiskTier
    explanation: str
    rollback_command: str | None = None
    backup_needed: bool = False


# Rollback command templates for common operations
_ROLLBACK_TEMPLATES: dict[str, str] = {
    "systemctl start": "systemctl stop {service}",
    "systemctl stop": "systemctl start {service}",
    "systemctl restart": "systemctl restart {service}",
    "systemctl enable": "systemctl disable {service}",
    "systemctl disable": "systemctl enable {service}",
    "kubectl apply": "kubectl delete -f {target}",
    "kubectl scale": "kubectl scale {target} --replicas={original}",
}


class RiskClassifier:
    """Classifies shell commands into risk tiers based on pattern matching."""

    def classify(self, command: str) -> ClassifiedAction:
        """Classify a command and return its risk tier with metadata."""
        command = command.strip()

        # For pipe chains, classify by the highest-risk component
        if "|" in command:
            return self._classify_pipe_chain(command)

        tier = self._match_tier(command)
        explanation = self._explain(command, tier)
        rollback = self._suggest_rollback(command)
        backup_needed = tier == RiskTier.YELLOW  # YELLOW ops should back up

        return ClassifiedAction(
            command=command,
            tier=tier,
            explanation=explanation,
            rollback_command=rollback,
            backup_needed=backup_needed,
        )

    def _match_tier(self, command: str) -> RiskTier:
        """Match a single command against patterns. Unknown defaults to YELLOW."""
        # Check RED first (most dangerous)
        for pattern in RED_PATTERNS:
            if pattern.search(command):
                return RiskTier.RED

        # Check GREEN (safe read-only)
        for pattern in GREEN_PATTERNS:
            if pattern.search(command):
                return RiskTier.GREEN

        # Check YELLOW (modifications)
        for pattern in YELLOW_PATTERNS:
            if pattern.search(command):
                return RiskTier.YELLOW

        # Unknown commands default to YELLOW (safe default)
        return RiskTier.YELLOW

    def _classify_pipe_chain(self, command: str) -> ClassifiedAction:
        """For pipe chains, use the highest risk tier among all components."""
        parts = [p.strip() for p in command.split("|")]
        highest_tier = RiskTier.GREEN
        tier_order = {RiskTier.GREEN: 0, RiskTier.YELLOW: 1, RiskTier.RED: 2}

        for part in parts:
            tier = self._match_tier(part)
            if tier_order[tier] > tier_order[highest_tier]:
                highest_tier = tier

        explanation = self._explain(command, highest_tier)
        if highest_tier == RiskTier.RED:
            explanation += " (pipe chain contains destructive command)"

        return ClassifiedAction(
            command=command,
            tier=highest_tier,
            explanation=explanation,
            backup_needed=highest_tier == RiskTier.YELLOW,
        )

    def _explain(self, command: str, tier: RiskTier) -> str:
        """Generate a plain English explanation of what the command does."""
        cmd_parts = command.split()
        if not cmd_parts:
            return "Empty command"

        base_cmd = cmd_parts[0]

        # Common explanations
        explanations = {
            "cat": "Read file contents",
            "ls": "List directory contents",
            "ps": "Show running processes",
            "df": "Show disk space usage",
            "du": "Show directory size",
            "free": "Show memory usage",
            "uptime": "Show system uptime",
            "ping": f"Test network connectivity to {cmd_parts[1] if len(cmd_parts) > 1 else 'host'}",
            "dig": f"DNS lookup for {cmd_parts[1] if len(cmd_parts) > 1 else 'domain'}",
            "curl": "Make HTTP request",
            "rm": f"Delete {'files/directories' if '-r' in command else 'files'}",
            "cp": "Copy files",
            "mv": "Move/rename files",
            "mkdir": "Create directory",
            "chmod": "Change file permissions",
            "chown": "Change file ownership",
            "reboot": "Reboot the system",
            "shutdown": "Shut down the system",
            "dd": "Low-level data copy (can overwrite entire disks)",
        }

        if base_cmd in explanations:
            return explanations[base_cmd]

        if base_cmd == "systemctl" and len(cmd_parts) >= 3:
            action = cmd_parts[1]
            service = cmd_parts[2]
            return f"{action.capitalize()} the {service} service"

        if base_cmd == "kubectl" and len(cmd_parts) >= 3:
            action = cmd_parts[1]
            resource = cmd_parts[2] if len(cmd_parts) > 2 else ""
            return f"Kubernetes: {action} {resource}"

        if base_cmd == "journalctl":
            return "Read system logs"

        if base_cmd == "sed" and "-i" in command:
            return "Edit file in-place"

        tier_label = {
            RiskTier.GREEN: "Read-only operation",
            RiskTier.YELLOW: "Modification operation",
            RiskTier.RED: "Destructive operation",
        }
        return f"{tier_label[tier]}: {base_cmd}"

    def _suggest_rollback(self, command: str) -> str | None:
        """Suggest a rollback command if one is known."""
        for prefix, template in _ROLLBACK_TEMPLATES.items():
            if command.startswith(prefix):
                parts = command.split()
                if len(parts) >= 3:
                    return template.format(service=parts[2], target=parts[2], original="?")
        return None
