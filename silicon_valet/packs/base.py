"""Base class for Domain Packs — the community extension mechanism."""

from __future__ import annotations

from abc import ABC, abstractmethod

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry


class BasePack(ABC):
    """Abstract base class for all domain packs.

    A domain pack provides service-specific intelligence:
    - Detection rules to auto-activate when the service is present
    - MCP tools specific to the service domain
    - Runbook seeds for common problems
    - DNA scan extensions for additional discovery
    """

    name: str = ""
    version: str = "1.0"
    description: str = ""

    @abstractmethod
    def detect(self, dna: DNAStore) -> bool:
        """Check if this pack is relevant to the current environment.

        Returns True if the pack should be activated.
        """
        ...

    @abstractmethod
    def get_tools(self) -> list[type]:
        """Return tool classes to register with the agent."""
        ...

    @abstractmethod
    def get_runbook_seeds(self) -> list[RunbookEntry]:
        """Return pre-written runbook entries for common problems."""
        ...

    def get_scan_extensions(self) -> list[str]:
        """Return additional glob patterns for the scanner to check.

        Override to add service-specific config paths.
        """
        return []
