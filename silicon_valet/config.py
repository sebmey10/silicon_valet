"""Central configuration for Silicon Valet. All modules import from here."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from silicon_valet.environment import EnvironmentCapabilities, EnvironmentType

logger = logging.getLogger(__name__)

# Default data directory: ~/.silicon_valet/data for standalone, /data/valet for k8s
_DEFAULT_DATA_DIR = os.getenv(
    "SV_DATA_DIR",
    str(Path.home() / ".silicon_valet" / "data"),
)

_DEFAULT_BACKUP_DIR = os.getenv(
    "SV_BACKUP_DIR",
    str(Path.home() / ".silicon_valet" / "backups"),
)


@dataclass
class ValetConfig:
    """Configuration loaded from environment variables with sensible defaults.

    Ollama endpoints default to "auto", which means Silicon Valet will probe
    for reachable Ollama instances at startup (localhost:11434, or env-specified
    endpoints). Set SV_OLLAMA_WORKER01 / SV_OLLAMA_WORKER02 explicitly to
    override auto-detection.
    """

    data_dir: Path = field(default_factory=lambda: Path(_DEFAULT_DATA_DIR))
    ollama_orchestrator: str = os.getenv("SV_OLLAMA_WORKER01", "auto")
    ollama_coder: str = os.getenv("SV_OLLAMA_WORKER02", "auto")
    orchestrator_model: str = os.getenv("SV_ORCHESTRATOR_MODEL", "qwen3:8b")
    coder_model: str = os.getenv("SV_CODER_MODEL", "qwen2.5-coder:7b")
    embed_model: str = os.getenv("SV_EMBED_MODEL", "nomic-embed-text")
    num_ctx: int = int(os.getenv("SV_NUM_CTX", "4096"))
    scan_interval: int = int(os.getenv("SV_SCAN_INTERVAL", "600"))
    ws_host: str = os.getenv("SV_WS_HOST", "0.0.0.0")
    ws_port: int = int(os.getenv("SV_WS_PORT", "7443"))
    risk_auto_approve_green: bool = os.getenv("SV_RISK_AUTO_GREEN", "true").lower() == "true"
    backup_dir: Path = field(default_factory=lambda: Path(_DEFAULT_BACKUP_DIR))
    log_level: str = os.getenv("SV_LOG_LEVEL", "INFO")

    # Set after environment detection runs
    capabilities: EnvironmentCapabilities | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.backup_dir = Path(self.backup_dir)

    # --- Convenience properties for environment type ---

    @property
    def is_kubernetes(self) -> bool:
        from silicon_valet.environment import EnvironmentType
        return self.capabilities is not None and self.capabilities.env_type == EnvironmentType.KUBERNETES

    @property
    def is_docker(self) -> bool:
        from silicon_valet.environment import EnvironmentType
        return self.capabilities is not None and self.capabilities.env_type == EnvironmentType.DOCKER

    @property
    def is_standalone(self) -> bool:
        from silicon_valet.environment import EnvironmentType
        return self.capabilities is not None and self.capabilities.env_type == EnvironmentType.BARE_METAL

    # --- Path properties ---

    @property
    def dna_db_path(self) -> Path:
        return self.data_dir / "dna.sqlite3"

    @property
    def runbook_db_path(self) -> Path:
        return self.data_dir / "runbooks.sqlite3"

    @property
    def chromadb_path(self) -> Path:
        return self.data_dir / "chromadb_data"

    @property
    def briefs_dir(self) -> Path:
        return self.data_dir / "briefs"

    @property
    def session_log_dir(self) -> Path:
        return self.data_dir / "session_logs"

    def ensure_dirs(self) -> None:
        """Create all required data directories."""
        for d in [self.data_dir, self.backup_dir, self.chromadb_path,
                  self.briefs_dir, self.session_log_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def resolve_from_environment(self, caps: EnvironmentCapabilities) -> None:
        """Resolve 'auto' settings using detected environment capabilities.

        Called once at startup after EnvironmentDetector.detect() completes.
        """
        self.capabilities = caps

        # Resolve Ollama endpoints
        if self.ollama_orchestrator == "auto":
            if caps.ollama_endpoints:
                self.ollama_orchestrator = caps.ollama_endpoints[0]
                logger.info("Ollama orchestrator resolved to: %s", self.ollama_orchestrator)
            else:
                # Fallback: assume localhost (Ollama may start later)
                self.ollama_orchestrator = "http://localhost:11434"
                logger.warning("No Ollama endpoints found; defaulting to localhost:11434")

        if self.ollama_coder == "auto":
            if len(caps.ollama_endpoints) >= 2:
                # Use second endpoint for coder (multi-node setup)
                self.ollama_coder = caps.ollama_endpoints[1]
                logger.info("Ollama coder resolved to: %s (separate endpoint)", self.ollama_coder)
            else:
                # Single-node: share the orchestrator endpoint
                self.ollama_coder = self.ollama_orchestrator
                logger.info("Ollama coder shares orchestrator endpoint: %s", self.ollama_coder)


def load_config() -> ValetConfig:
    """Load configuration from environment variables."""
    config = ValetConfig()
    config.ensure_dirs()
    return config
