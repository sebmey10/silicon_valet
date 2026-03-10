"""Environment detection layer — discovers what kind of server Silicon Valet is running on."""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import socket
from dataclasses import dataclass, field
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class EnvironmentType(Enum):
    KUBERNETES = "kubernetes"
    DOCKER = "docker"
    BARE_METAL = "bare_metal"
    UNKNOWN = "unknown"


@dataclass
class EnvironmentCapabilities:
    """Describes the detected runtime environment and available infrastructure."""

    env_type: EnvironmentType = EnvironmentType.UNKNOWN
    has_kubectl: bool = False
    has_docker: bool = False
    has_systemd: bool = False
    has_ollama_local: bool = False
    ollama_endpoints: list[str] = field(default_factory=list)
    hostname: str = ""
    os_info: str = ""
    available_ram_mb: int | None = None
    cpu_cores: int | None = None
    available_models: dict[str, list[str]] = field(default_factory=dict)

    @property
    def environment_description(self) -> str:
        """Human-readable environment description for the AI system prompt."""
        if self.env_type == EnvironmentType.KUBERNETES:
            return f"Kubernetes (k3s) cluster on {self.hostname}"
        elif self.env_type == EnvironmentType.DOCKER:
            return f"Docker environment on {self.hostname} ({self.os_info})"
        elif self.env_type == EnvironmentType.BARE_METAL:
            return f"Linux server ({self.hostname}, {self.os_info})"
        return f"server ({self.hostname})"


async def _run_cmd(cmd: list[str], timeout: int = 10) -> str | None:
    """Run a command and return stdout, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()
        return None
    except (asyncio.TimeoutError, FileNotFoundError, PermissionError, OSError):
        return None


async def _probe_ollama(url: str) -> list[str] | None:
    """Probe an Ollama endpoint. Returns model names or None if unreachable."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                return [m.get("name", "") for m in data.get("models", [])]
    except Exception:
        pass
    return None


class EnvironmentDetector:
    """Detects the runtime environment and available capabilities."""

    async def detect(self) -> EnvironmentCapabilities:
        """Run all detection probes and return capabilities."""
        caps = EnvironmentCapabilities()

        # Basic system info
        caps.hostname = socket.gethostname()
        caps.os_info = platform.platform()

        # Run all probes concurrently
        results = await asyncio.gather(
            self._check_kubectl(),
            self._check_docker(),
            self._check_systemd(),
            self._check_ram(),
            self._check_cpu(),
            self._probe_all_ollama_endpoints(),
            return_exceptions=True,
        )

        caps.has_kubectl = results[0] is True if not isinstance(results[0], Exception) else False
        caps.has_docker = results[1] is True if not isinstance(results[1], Exception) else False
        caps.has_systemd = results[2] is True if not isinstance(results[2], Exception) else False
        caps.available_ram_mb = results[3] if not isinstance(results[3], Exception) else None
        caps.cpu_cores = results[4] if not isinstance(results[4], Exception) else None

        if not isinstance(results[5], Exception):
            ollama_results = results[5]
            for endpoint, models in ollama_results.items():
                if models is not None:
                    caps.ollama_endpoints.append(endpoint)
                    caps.available_models[endpoint] = models
            caps.has_ollama_local = "http://localhost:11434" in caps.ollama_endpoints

        # Determine environment type (priority: k8s > docker > bare_metal)
        if caps.has_kubectl:
            caps.env_type = EnvironmentType.KUBERNETES
        elif caps.has_docker and not caps.has_systemd:
            # Pure Docker (e.g., running inside a container)
            caps.env_type = EnvironmentType.DOCKER
        else:
            caps.env_type = EnvironmentType.BARE_METAL

        logger.info(
            "Environment detected: %s | kubectl=%s docker=%s systemd=%s ollama_endpoints=%d",
            caps.env_type.value,
            caps.has_kubectl,
            caps.has_docker,
            caps.has_systemd,
            len(caps.ollama_endpoints),
        )

        return caps

    async def _check_kubectl(self) -> bool:
        """Check if kubectl is available and connected to a cluster."""
        which = await _run_cmd(["which", "kubectl"])
        if not which:
            return False
        info = await _run_cmd(["kubectl", "cluster-info"], timeout=5)
        return info is not None

    async def _check_docker(self) -> bool:
        """Check if Docker is available and running."""
        which = await _run_cmd(["which", "docker"])
        if not which:
            return False
        info = await _run_cmd(["docker", "info"], timeout=5)
        return info is not None

    async def _check_systemd(self) -> bool:
        """Check if systemd is available."""
        result = await _run_cmd(["which", "systemctl"])
        return result is not None

    async def _check_ram(self) -> int | None:
        """Get total RAM in MB."""
        # Try /proc/meminfo (Linux)
        try:
            import pathlib
            meminfo = pathlib.Path("/proc/meminfo")
            if meminfo.exists():
                text = meminfo.read_text()
                for line in text.splitlines():
                    if line.startswith("MemTotal:"):
                        kb = int(line.split()[1])
                        return kb // 1024
        except Exception:
            pass

        # Fallback: free -m
        output = await _run_cmd(["free", "-m"])
        if output:
            for line in output.splitlines():
                if line.startswith("Mem:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        return int(parts[1])

        # macOS fallback
        output = await _run_cmd(["sysctl", "-n", "hw.memsize"])
        if output:
            try:
                return int(output) // (1024 * 1024)
            except ValueError:
                pass

        return None

    async def _check_cpu(self) -> int | None:
        """Get CPU core count."""
        output = await _run_cmd(["nproc"])
        if output:
            try:
                return int(output)
            except ValueError:
                pass

        # macOS fallback
        output = await _run_cmd(["sysctl", "-n", "hw.ncpu"])
        if output:
            try:
                return int(output)
            except ValueError:
                pass

        return None

    async def _probe_all_ollama_endpoints(self) -> dict[str, list[str] | None]:
        """Probe all potential Ollama endpoints concurrently."""
        endpoints_to_probe = {"http://localhost:11434"}

        # Add env-var-specified endpoints
        for var in ("SV_OLLAMA_WORKER01", "SV_OLLAMA_WORKER02"):
            val = os.getenv(var)
            if val and val != "auto":
                endpoints_to_probe.add(val.rstrip("/"))

        endpoints = sorted(endpoints_to_probe)
        probe_results = await asyncio.gather(
            *(_probe_ollama(ep) for ep in endpoints),
            return_exceptions=True,
        )

        results: dict[str, list[str] | None] = {}
        for ep, result in zip(endpoints, probe_results):
            results[ep] = result if not isinstance(result, Exception) else None

        return results
