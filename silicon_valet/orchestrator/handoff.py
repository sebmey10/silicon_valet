"""Mission briefs — context handoff when approaching token limits."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

from silicon_valet.dna.store import DNAStore

logger = logging.getLogger(__name__)


@dataclass
class MissionBrief:
    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    objective: str = ""
    completed_steps: list[str] = field(default_factory=list)
    discoveries: list[str] = field(default_factory=list)
    next_step: str = ""
    ruled_out: list[str] = field(default_factory=list)
    dna_context_ids: list[int] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> MissionBrief:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class HandoffManager:
    """Manages mission briefs for context handoff."""

    def __init__(self, data_dir: Path):
        self.briefs_dir = data_dir / "briefs"
        self.briefs_dir.mkdir(parents=True, exist_ok=True)

    def needs_handoff(self, token_count: int, max_ctx: int) -> bool:
        """Returns True if token usage exceeds 80% of context window."""
        return token_count > (max_ctx * 0.8)

    def write_brief(self, brief: MissionBrief) -> Path:
        """Write a mission brief to disk."""
        path = self.briefs_dir / f"{brief.task_id}.json"
        path.write_text(json.dumps(brief.to_dict(), indent=2, ensure_ascii=False))
        logger.info("Wrote mission brief: %s", path)
        return path

    def read_brief(self, task_id: str) -> MissionBrief | None:
        """Read a mission brief from disk."""
        path = self.briefs_dir / f"{task_id}.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text())
        return MissionBrief.from_dict(data)

    def list_briefs(self) -> list[MissionBrief]:
        """List all mission briefs, sorted by timestamp descending."""
        briefs = []
        for path in self.briefs_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                briefs.append(MissionBrief.from_dict(data))
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed brief: %s", path)
        briefs.sort(key=lambda b: b.timestamp, reverse=True)
        return briefs

    def brief_to_prompt(self, brief: MissionBrief, dna: DNAStore) -> str:
        """Convert a mission brief into a context prompt for the next session."""
        lines = [
            "=== MISSION BRIEF (Continued Investigation) ===",
            f"Task ID: {brief.task_id}",
            f"Objective: {brief.objective}",
            "",
        ]

        if brief.completed_steps:
            lines.append("Completed steps:")
            for i, step in enumerate(brief.completed_steps, 1):
                lines.append(f"  {i}. {step}")
            lines.append("")

        if brief.discoveries:
            lines.append("Key discoveries:")
            for d in brief.discoveries:
                lines.append(f"  - {d}")
            lines.append("")

        if brief.ruled_out:
            lines.append("Ruled out:")
            for r in brief.ruled_out:
                lines.append(f"  - {r}")
            lines.append("")

        if brief.next_step:
            lines.append(f"Next step: {brief.next_step}")
            lines.append("")

        # Inject targeted DNA context for referenced services
        if brief.dna_context_ids:
            lines.append("Relevant infrastructure context:")
            for svc_id in brief.dna_context_ids:
                svc = dna.get_service(svc_id)
                if svc:
                    lines.append(f"  - {svc.name} ({svc.type}) on {svc.node_id}: {svc.status}")
                    configs = dna.get_configs_for_service(svc_id)
                    for cfg in configs:
                        lines.append(f"    Config: {cfg.path}")
            lines.append("")

        lines.append("=== END BRIEF ===")
        return "\n".join(lines)
