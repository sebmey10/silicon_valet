"""Pack loader — discovers, detects, and activates domain packs."""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookLibrary
from silicon_valet.packs.base import BasePack

logger = logging.getLogger(__name__)

# Known pack modules (discovered at import time)
PACK_MODULES = [
    "silicon_valet.packs.linux",
    "silicon_valet.packs.networking",
    "silicon_valet.packs.kubernetes",
    "silicon_valet.packs.docker",
    "silicon_valet.packs.webserver",
    "silicon_valet.packs.database",
    "silicon_valet.packs.firewall",
    "silicon_valet.packs.zabbix",
    "silicon_valet.packs.rabbitmq",
]


class PackLoader:
    """Discovers, activates, and manages domain packs."""

    def __init__(self, dna: DNAStore) -> None:
        self.dna = dna
        self._all_packs: list[BasePack] = []

    def discover_packs(self) -> list[BasePack]:
        """Import and instantiate all known pack modules."""
        packs = []
        for module_path in PACK_MODULES:
            try:
                mod = importlib.import_module(module_path)
                if hasattr(mod, "Pack"):
                    pack = mod.Pack()
                    packs.append(pack)
                    logger.debug("Discovered pack: %s", pack.name)
            except ImportError as e:
                logger.debug("Pack module %s not available: %s", module_path, e)
            except Exception as e:
                logger.warning("Error loading pack %s: %s", module_path, e)
        self._all_packs = packs
        return packs

    def activate_matching(self) -> list[BasePack]:
        """Detect which packs match the current environment and activate them."""
        if not self._all_packs:
            self.discover_packs()

        active = []
        for pack in self._all_packs:
            try:
                if pack.detect(self.dna):
                    active.append(pack)
                    logger.info("Activated pack: %s v%s", pack.name, pack.version)
                else:
                    logger.debug("Pack %s: not detected in environment", pack.name)
            except Exception as e:
                logger.warning("Error detecting pack %s: %s", pack.name, e)
        return active

    def register_tools(self, active_packs: list[BasePack]) -> list[type]:
        """Collect and register tools from active packs."""
        all_tools = []
        for pack in active_packs:
            try:
                tools = pack.get_tools()
                all_tools.extend(tools)
                logger.debug("Registered %d tools from pack %s", len(tools), pack.name)
            except Exception as e:
                logger.warning("Error getting tools from pack %s: %s", pack.name, e)
        return all_tools

    def seed_runbooks(self, active_packs: list[BasePack], runbook_lib: RunbookLibrary) -> None:
        """Seed runbook entries from active packs (async wrapper for sync init)."""
        import asyncio
        for pack in active_packs:
            try:
                seeds = pack.get_runbook_seeds()
                for seed in seeds:
                    # Check if already seeded (by title)
                    existing = runbook_lib.conn.execute(
                        "SELECT id FROM runbooks WHERE title = ? AND pack_source = ?",
                        (seed.title, pack.name),
                    ).fetchone()
                    if existing is None:
                        # We need to run async add in sync context
                        try:
                            loop = asyncio.get_event_loop()
                            if loop.is_running():
                                asyncio.ensure_future(runbook_lib.add(seed))
                            else:
                                loop.run_until_complete(runbook_lib.add(seed))
                        except RuntimeError:
                            asyncio.run(runbook_lib.add(seed))
                        logger.debug("Seeded runbook: %s (from %s)", seed.title, pack.name)
            except Exception as e:
                logger.warning("Error seeding runbooks from pack %s: %s", pack.name, e)
