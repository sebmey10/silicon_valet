"""Central configuration for Silicon Valet. All modules import from here."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ValetConfig:
    """Configuration loaded from environment variables with sensible defaults."""

    data_dir: Path = field(default_factory=lambda: Path(os.getenv("SV_DATA_DIR", "/data/valet")))
    ollama_orchestrator: str = os.getenv("SV_OLLAMA_WORKER01", "http://ollama-worker01:11434")
    ollama_coder: str = os.getenv("SV_OLLAMA_WORKER02", "http://ollama-worker02:11434")
    orchestrator_model: str = os.getenv("SV_ORCHESTRATOR_MODEL", "qwen3:8b")
    coder_model: str = os.getenv("SV_CODER_MODEL", "qwen2.5-coder:7b")
    embed_model: str = os.getenv("SV_EMBED_MODEL", "nomic-embed-text")
    num_ctx: int = int(os.getenv("SV_NUM_CTX", "4096"))
    scan_interval: int = int(os.getenv("SV_SCAN_INTERVAL", "600"))
    ws_host: str = os.getenv("SV_WS_HOST", "0.0.0.0")
    ws_port: int = int(os.getenv("SV_WS_PORT", "7443"))
    risk_auto_approve_green: bool = os.getenv("SV_RISK_AUTO_GREEN", "true").lower() == "true"
    backup_dir: Path = field(default_factory=lambda: Path(os.getenv("SV_BACKUP_DIR", "/data/backups")))
    log_level: str = os.getenv("SV_LOG_LEVEL", "INFO")

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.backup_dir = Path(self.backup_dir)

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


def load_config() -> ValetConfig:
    """Load configuration from environment variables."""
    config = ValetConfig()
    config.ensure_dirs()
    return config
