"""Unified memory context builder for agent prompt injection."""

from __future__ import annotations

import logging

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.episodic import EpisodicMemory
from silicon_valet.memory.procedural import RunbookLibrary

logger = logging.getLogger(__name__)


class MemoryContext:
    """Builds combined context from DNA, episodic memory, and runbooks for agent injection."""

    def __init__(
        self,
        dna: DNAStore,
        episodic: EpisodicMemory,
        runbook: RunbookLibrary,
    ) -> None:
        self.dna = dna
        self.episodic = episodic
        self.runbook = runbook

    async def build_context(self, user_message: str) -> str:
        """Build a context string combining DNA summary, relevant episodes, and matching runbooks.

        This context is injected into the agent's system prompt before every response.
        """
        sections = []

        # 1. DNA summary (always included)
        dna_summary = self.dna.get_context_summary()
        sections.append(dna_summary)

        # 2. Relevant past episodes (semantic search)
        try:
            episodes = await self.episodic.search(user_message, n=2)
            if episodes:
                lines = ["\n## Relevant Past Sessions"]
                for ep in episodes:
                    lines.append(f"- **{ep.outcome}**: {ep.problem_description[:200]}")
                    if ep.resolution_summary:
                        lines.append(f"  Resolution: {ep.resolution_summary[:200]}")
                sections.append("\n".join(lines))
        except Exception as e:
            logger.debug("Episodic search failed: %s", e)

        # 3. Matching runbooks (semantic search)
        try:
            runbooks = await self.runbook.search(user_message, n=2)
            if runbooks:
                lines = ["\n## Matching Runbooks"]
                for rb in runbooks:
                    lines.append(f"- **{rb.title}** (used {rb.success_count}x)")
                    lines.append(f"  Pattern: {rb.problem_pattern}")
                    if rb.root_cause:
                        lines.append(f"  Root cause: {rb.root_cause}")
                    steps_summary = "; ".join(
                        s.get("explanation", s.get("action", ""))[:60] for s in rb.steps[:3]
                    )
                    lines.append(f"  Steps: {steps_summary}")
                sections.append("\n".join(lines))
        except Exception as e:
            logger.debug("Runbook search failed: %s", e)

        return "\n\n".join(sections)
