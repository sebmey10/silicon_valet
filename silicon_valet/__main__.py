"""Silicon Valet entry point. Starts all subsystems and the WebSocket server."""

from __future__ import annotations

import asyncio
import logging
import signal
import sys

from silicon_valet.config import load_config

logger = logging.getLogger("silicon_valet")


async def startup() -> None:
    """Initialize all subsystems and start the server."""
    config = load_config()

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Silicon Valet v%s starting...", __import__("silicon_valet").__version__)

    # Phase 0: Environment detection
    from silicon_valet.environment import EnvironmentDetector
    detector = EnvironmentDetector()
    capabilities = await detector.detect()
    config.resolve_from_environment(capabilities)
    logger.info(
        "Environment: %s | Ollama: %s (orchestrator), %s (coder)",
        capabilities.env_type.value,
        config.ollama_orchestrator,
        config.ollama_coder,
    )

    # Phase 1: Infrastructure DNA
    from silicon_valet.dna.store import DNAStore
    dna = DNAStore(config.dna_db_path)
    logger.info("DNA store initialized at %s", config.dna_db_path)

    # Phase 2: Embedder
    from silicon_valet.memory.embeddings import OllamaEmbedder
    embedder = OllamaEmbedder(config.ollama_orchestrator, config.embed_model)

    # Phase 3: Memory systems
    from silicon_valet.memory.episodic import EpisodicMemory
    from silicon_valet.memory.procedural import RunbookLibrary
    from silicon_valet.memory.context import MemoryContext
    episodic = EpisodicMemory(config.chromadb_path, embedder)
    runbook_lib = RunbookLibrary(config.runbook_db_path, config.chromadb_path, embedder)
    memory = MemoryContext(dna, episodic, runbook_lib)
    logger.info("Memory systems initialized")

    # Phase 4: Risk engine
    from silicon_valet.risk.classifier import RiskClassifier
    from silicon_valet.risk.engine import RiskEngine
    classifier = RiskClassifier()
    risk_engine = RiskEngine(classifier, config)
    logger.info("Risk engine armed")

    # Phase 5: Domain packs
    from silicon_valet.packs.loader import PackLoader
    pack_loader = PackLoader(dna)
    active_packs = pack_loader.activate_matching()
    pack_loader.seed_runbooks(active_packs, runbook_lib)
    logger.info("Domain packs loaded: %s", [p.name for p in active_packs])

    # Phase 6: Background scanner
    from silicon_valet.dna.scanner import BackgroundScanner
    scanner = BackgroundScanner(dna, config)
    scanner_task = asyncio.create_task(scanner.run_forever(config.scan_interval))
    logger.info("Background scanner started (interval: %ds)", config.scan_interval)

    # Phase 7: Orchestrator
    from silicon_valet.orchestrator.planner import PlannerAgent
    from silicon_valet.orchestrator.coder import CoderAgent
    from silicon_valet.orchestrator.handoff import HandoffManager

    # Collect tool names from active packs + built-in tools
    tool_names = [t.__name__ for p in active_packs for t in p.get_tools()]
    planner = PlannerAgent(config, tool_names, memory)
    coder = CoderAgent(config)
    handoff = HandoffManager(config.data_dir)

    # Phase 8: WebSocket server
    from silicon_valet.server.ws_server import ValetServer
    server = ValetServer(
        config=config,
        dna=dna,
        memory=memory,
        episodic=episodic,
        risk_engine=risk_engine,
        planner=planner,
        coder=coder,
        handoff=handoff,
    )
    logger.info("Silicon Valet ready on ws://%s:%d", config.ws_host, config.ws_port)
    await server.start()


def main() -> None:
    """CLI entry point."""
    loop = asyncio.new_event_loop()

    def _shutdown(sig: signal.Signals) -> None:
        logger.info("Received %s, shutting down...", sig.name)
        for task in asyncio.all_tasks(loop):
            task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig)

    try:
        loop.run_until_complete(startup())
    except (asyncio.CancelledError, KeyboardInterrupt):
        logger.info("Silicon Valet stopped.")
    finally:
        loop.close()


if __name__ == "__main__":
    main()
