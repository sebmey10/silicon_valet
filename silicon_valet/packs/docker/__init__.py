"""Docker domain pack — container management, image cleanup, network diagnostics."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "docker"
    version = "1.0"
    description = "Docker container management: lifecycle, images, networks, volumes"

    def detect(self, dna: DNAStore) -> bool:
        # Check for Docker services or container-type services in DNA
        services = dna.get_all_services()
        if any(s.type == "container" for s in services):
            return True
        if any(s.name in ("docker", "dockerd", "containerd") for s in services):
            return True
        return False

    def get_tools(self) -> list[type]:
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Docker container won't start",
                problem_pattern="Docker container fails to start or keeps restarting",
                symptoms=[
                    "docker ps shows container in 'Restarting' or 'Exited' state",
                    "docker logs shows errors on startup",
                    "Application not accessible on expected port",
                ],
                steps=[
                    {"action": "check", "command": "docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'", "explanation": "List all containers with status", "risk_tier": "green"},
                    {"action": "check", "command": "docker logs --tail 50 {container_name}", "explanation": "Check container logs", "risk_tier": "green"},
                    {"action": "check", "command": "docker inspect {container_name} | head -80", "explanation": "Inspect container configuration", "risk_tier": "green"},
                    {"action": "check", "command": "docker events --since 10m --filter container={container_name} 2>/dev/null | tail -20", "explanation": "Check recent Docker events", "risk_tier": "green"},
                    {"action": "fix", "command": "docker restart {container_name}", "explanation": "Restart the container", "risk_tier": "yellow"},
                ],
                root_cause="Missing environment variables, wrong image tag, port conflict, or volume mount issue",
                verification="docker ps shows container in 'Up' state",
                tags=["docker", "container", "startup", "restart"],
                pack_source="docker",
            ),
            RunbookEntry(
                title="Docker disk space from images",
                problem_pattern="Docker images and build cache consuming excessive disk space",
                symptoms=[
                    "df -h shows /var/lib/docker using significant space",
                    "docker pull fails with 'no space left'",
                    "Build cache growing unbounded",
                ],
                steps=[
                    {"action": "check", "command": "docker system df", "explanation": "Show Docker disk usage breakdown", "risk_tier": "green"},
                    {"action": "check", "command": "docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.Size}}' | sort -k3 -rh | head -20", "explanation": "List largest images", "risk_tier": "green"},
                    {"action": "check", "command": "docker volume ls -q | wc -l", "explanation": "Count Docker volumes", "risk_tier": "green"},
                    {"action": "fix", "command": "docker image prune -f", "explanation": "Remove dangling images", "risk_tier": "yellow"},
                    {"action": "fix", "command": "docker system prune -f", "explanation": "Clean up unused containers, networks, and dangling images", "risk_tier": "yellow"},
                ],
                root_cause="Accumulated old images, unused containers, or build cache not cleaned",
                verification="docker system df shows reduced space usage",
                tags=["docker", "disk", "images", "cleanup"],
                pack_source="docker",
            ),
            RunbookEntry(
                title="Docker container networking issue",
                problem_pattern="Containers cannot communicate with each other or the host",
                symptoms=[
                    "Container cannot reach another container by name",
                    "Port forwarding not working",
                    "DNS resolution failing inside container",
                ],
                steps=[
                    {"action": "check", "command": "docker network ls", "explanation": "List Docker networks", "risk_tier": "green"},
                    {"action": "check", "command": "docker network inspect bridge", "explanation": "Inspect default bridge network", "risk_tier": "green"},
                    {"action": "check", "command": "docker exec {container_name} cat /etc/resolv.conf 2>/dev/null", "explanation": "Check DNS config inside container", "risk_tier": "green"},
                    {"action": "check", "command": "iptables -L -n | head -30 2>/dev/null", "explanation": "Check iptables rules affecting Docker", "risk_tier": "green"},
                ],
                root_cause="Containers on different networks, DNS resolver misconfigured, or iptables blocking",
                verification="Containers can resolve and reach each other by name",
                tags=["docker", "networking", "dns", "bridge"],
                pack_source="docker",
            ),
        ]
