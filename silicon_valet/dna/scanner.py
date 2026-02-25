"""Background scanner that probes the environment and updates Infrastructure DNA."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from silicon_valet.config import ValetConfig
from silicon_valet.dna.models import ConfigFile, Dependency, NetworkInterface, Node, Port, Service
from silicon_valet.dna.store import DNAStore

logger = logging.getLogger(__name__)

# Common config directories to check for known services
SERVICE_CONFIG_PATHS: dict[str, list[str]] = {
    "nginx": ["/etc/nginx/"],
    "apache2": ["/etc/apache2/", "/etc/httpd/"],
    "postgresql": ["/etc/postgresql/"],
    "mysql": ["/etc/mysql/"],
    "zabbix-server": ["/etc/zabbix/"],
    "zabbix-agent": ["/etc/zabbix/"],
    "zabbix-agent2": ["/etc/zabbix/"],
    "rabbitmq-server": ["/etc/rabbitmq/"],
    "redis-server": ["/etc/redis/"],
    "sshd": ["/etc/ssh/"],
    "docker": ["/etc/docker/"],
    "containerd": ["/etc/containerd/"],
    "k3s": ["/etc/rancher/k3s/"],
}


@dataclass
class ScanResult:
    nodes: list[Node] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    ports: list[Port] = field(default_factory=list)
    config_files: list[ConfigFile] = field(default_factory=list)
    network_interfaces: list[NetworkInterface] = field(default_factory=list)
    dependencies: list[Dependency] = field(default_factory=list)


async def _run_cmd(cmd: list[str], timeout: int = 15) -> str | None:
    """Run a command and return stdout, or None on failure."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()
        logger.debug("Command %s failed (rc=%d): %s", cmd, proc.returncode, stderr.decode(errors="replace")[:200])
        return None
    except (asyncio.TimeoutError, FileNotFoundError, PermissionError) as e:
        logger.debug("Command %s error: %s", cmd, e)
        return None


class BackgroundScanner:
    """Periodically scans the environment and updates the DNA store."""

    def __init__(self, store: DNAStore, config: ValetConfig) -> None:
        self.store = store
        self.config = config

    async def run_forever(self, interval: int = 600) -> None:
        """Run scan_once() in a loop. First scan runs immediately."""
        logger.info("Background scanner starting (interval=%ds)", interval)
        while True:
            try:
                result = await self.scan_once()
                logger.info(
                    "Scan complete: %d nodes, %d services, %d ports",
                    len(result.nodes), len(result.services), len(result.ports),
                )
            except Exception:
                logger.exception("Scanner error")
            await asyncio.sleep(interval)

    async def scan_once(self) -> ScanResult:
        """Run all discovery methods and reconcile with the store."""
        result = ScanResult()

        # Run discovery methods concurrently
        nodes_task = asyncio.create_task(self._scan_nodes())
        k8s_task = asyncio.create_task(self._scan_k8s_services())
        systemd_task = asyncio.create_task(self._scan_systemd_units())
        ports_task = asyncio.create_task(self._scan_ports())
        network_task = asyncio.create_task(self._scan_network_interfaces())

        result.nodes = await nodes_task
        k8s_services = await k8s_task
        systemd_services = await systemd_task
        result.services = k8s_services + systemd_services
        result.ports = await ports_task
        result.network_interfaces = await network_task

        # Persist to store
        node_map: dict[str, int] = {}
        for node in result.nodes:
            stored = self.store.upsert_node(node)
            node_map[stored.hostname] = stored.id

        active_service_ids: set[int] = set()
        service_name_map: dict[str, int] = {}
        for svc in result.services:
            if svc.node_id is None and node_map:
                # Assign to first node if node unknown (best effort)
                svc.node_id = next(iter(node_map.values()))
            stored = self.store.upsert_service(svc)
            active_service_ids.add(stored.id)
            service_name_map[stored.name] = stored.id

        # Associate ports with services by matching PID or port patterns
        for port in result.ports:
            if port.service_id is None:
                # Try to find a matching service by scanning known port assignments
                existing_svc = self.store.get_service_by_port(port.port)
                if existing_svc:
                    port.service_id = existing_svc.id
            if port.service_id is not None:
                self.store.upsert_port(port)

        for iface in result.network_interfaces:
            if iface.node_id or node_map:
                if not iface.node_id and node_map:
                    iface.node_id = next(iter(node_map.values()))
                self.store.upsert_network_interface(iface)

        # Scan config files for known services
        for svc_name, svc_id in service_name_map.items():
            configs = await self._scan_config_files(svc_name, svc_id)
            result.config_files.extend(configs)
            for cf in configs:
                self.store.upsert_config_file(cf)

        # Infer dependencies
        result.dependencies = await self._infer_dependencies(service_name_map)
        for dep in result.dependencies:
            self.store.add_dependency(dep)

        return result

    async def _scan_nodes(self) -> list[Node]:
        """Discover cluster nodes via kubectl."""
        output = await _run_cmd(["kubectl", "get", "nodes", "-o", "json"])
        if not output:
            return []

        nodes = []
        try:
            data = json.loads(output)
            for item in data.get("items", []):
                metadata = item.get("metadata", {})
                status = item.get("status", {})
                addresses = {a["type"]: a["address"] for a in status.get("addresses", [])}
                capacity = status.get("capacity", {})

                # Parse RAM from capacity (e.g., "32874536Ki" -> MB)
                ram_str = capacity.get("memory", "")
                ram_mb = None
                if ram_str.endswith("Ki"):
                    ram_mb = int(ram_str.rstrip("Ki")) // 1024
                elif ram_str.endswith("Mi"):
                    ram_mb = int(ram_str.rstrip("Mi"))

                labels = metadata.get("labels", {})
                role = "control-plane" if "node-role.kubernetes.io/control-plane" in labels else "worker"

                nodes.append(Node(
                    hostname=metadata.get("name", ""),
                    ip=addresses.get("InternalIP"),
                    role=role,
                    os_version=status.get("nodeInfo", {}).get("osImage"),
                    ram_total_mb=ram_mb,
                    cpu_cores=int(capacity.get("cpu", 0)) or None,
                ))
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Failed to parse kubectl nodes output: %s", e)
        return nodes

    async def _scan_k8s_services(self) -> list[Service]:
        """Discover k8s pods and deployments."""
        services = []

        # Pods
        output = await _run_cmd(["kubectl", "get", "pods", "-A", "-o", "json"])
        if output:
            try:
                data = json.loads(output)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    status = item.get("status", {})
                    spec = item.get("spec", {})
                    containers = spec.get("containers", [])
                    image = containers[0]["image"] if containers else None

                    phase = status.get("phase", "Unknown")
                    svc_status = "running" if phase == "Running" else phase.lower()

                    services.append(Service(
                        name=metadata.get("name", ""),
                        type="k8s_pod",
                        namespace=metadata.get("namespace"),
                        status=svc_status,
                        image=image,
                    ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse kubectl pods output: %s", e)

        # Deployments
        output = await _run_cmd(["kubectl", "get", "deployments", "-A", "-o", "json"])
        if output:
            try:
                data = json.loads(output)
                for item in data.get("items", []):
                    metadata = item.get("metadata", {})
                    status = item.get("status", {})
                    ready = status.get("readyReplicas", 0)
                    desired = status.get("replicas", 0)
                    svc_status = "running" if ready == desired and ready > 0 else "degraded"

                    services.append(Service(
                        name=metadata.get("name", ""),
                        type="k8s_deploy",
                        namespace=metadata.get("namespace"),
                        status=svc_status,
                    ))
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning("Failed to parse kubectl deployments output: %s", e)

        return services

    async def _scan_systemd_units(self) -> list[Service]:
        """Discover systemd services."""
        output = await _run_cmd([
            "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--output=json",
        ])
        if not output:
            # Fallback to plain text parsing
            output = await _run_cmd([
                "systemctl", "list-units", "--type=service", "--all", "--no-pager", "--plain",
            ])
            if not output:
                return []
            return self._parse_systemctl_plain(output)

        services = []
        try:
            units = json.loads(output)
            for unit in units:
                name = unit.get("unit", "")
                if name.endswith(".service"):
                    name = name[:-8]  # Strip .service suffix
                active = unit.get("active", "unknown")
                status = "running" if active == "active" else active

                services.append(Service(name=name, type="systemd", status=status))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse systemctl JSON output: %s", e)
        return services

    def _parse_systemctl_plain(self, output: str) -> list[Service]:
        """Parse plain-text systemctl output as fallback."""
        services = []
        for line in output.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 4 and parts[0].endswith(".service"):
                name = parts[0].replace(".service", "")
                active = parts[2]  # loaded/not-found, active/inactive, sub
                status = "running" if active == "active" else active
                services.append(Service(name=name, type="systemd", status=status))
        return services

    async def _scan_ports(self) -> list[Port]:
        """Discover listening ports via ss."""
        ports = []
        for proto in ("tcp", "udp"):
            flag = "-tlnp" if proto == "tcp" else "-ulnp"
            output = await _run_cmd(["ss", flag])
            if not output:
                continue
            for line in output.strip().split("\n")[1:]:  # Skip header
                parts = line.split()
                if len(parts) < 5:
                    continue
                local_addr = parts[3] if len(parts) > 3 else ""
                # Parse address:port
                match = re.match(r"(.+):(\d+)$", local_addr)
                if match:
                    bind = match.group(1).strip("[]")
                    port_num = int(match.group(2))
                    ports.append(Port(
                        port=port_num,
                        protocol=proto,
                        bind_address=bind if bind != "*" else "0.0.0.0",
                        state="LISTEN",
                    ))
        return ports

    async def _scan_network_interfaces(self) -> list[NetworkInterface]:
        """Discover network interfaces via ip command."""
        output = await _run_cmd(["ip", "-j", "addr", "show"])
        if not output:
            return []

        interfaces = []
        try:
            data = json.loads(output)
            for iface in data:
                name = iface.get("ifname", "")
                state = iface.get("operstate", "UNKNOWN")
                mac = iface.get("address", "")
                addr_info = iface.get("addr_info", [])

                ip_addr = None
                subnet = None
                for addr in addr_info:
                    if addr.get("family") == "inet":
                        ip_addr = addr.get("local")
                        prefix = addr.get("prefixlen")
                        if ip_addr and prefix:
                            subnet = f"{ip_addr}/{prefix}"
                        break

                if name not in ("lo",):  # Skip loopback
                    interfaces.append(NetworkInterface(
                        node_id=0,  # Will be assigned during reconciliation
                        name=name,
                        ip=ip_addr,
                        subnet=subnet,
                        mac=mac,
                        state=state,
                    ))
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse ip addr output: %s", e)
        return interfaces

    async def _scan_config_files(self, service_name: str, service_id: int) -> list[ConfigFile]:
        """Discover config files for a known service."""
        configs = []
        search_paths = SERVICE_CONFIG_PATHS.get(service_name, [])

        for base_path in search_paths:
            output = await _run_cmd(["find", base_path, "-type", "f", "-name", "*.conf"])
            if not output:
                continue
            for filepath in output.strip().split("\n"):
                filepath = filepath.strip()
                if not filepath:
                    continue
                # Hash the file for change detection
                hash_output = await _run_cmd(["sha256sum", filepath])
                file_hash = hash_output.split()[0] if hash_output else None

                configs.append(ConfigFile(
                    service_id=service_id,
                    path=filepath,
                    hash_sha256=file_hash,
                ))
        return configs

    async def _infer_dependencies(self, service_name_map: dict[str, int]) -> list[Dependency]:
        """Infer service dependencies from environment variables and known patterns."""
        deps = []

        # Check known dependency patterns
        known_deps = [
            # (source_pattern, target_pattern, dep_type, detail)
            ("zabbix-server", "postgresql", "network", "database backend"),
            ("zabbix-server", "mysql", "network", "database backend"),
            ("rabbitmq-server", "erlang", "config", "runtime dependency"),
        ]

        for src_pattern, tgt_pattern, dep_type, detail in known_deps:
            for svc_name, svc_id in service_name_map.items():
                if src_pattern in svc_name:
                    for tgt_name, tgt_id in service_name_map.items():
                        if tgt_pattern in tgt_name and svc_id != tgt_id:
                            deps.append(Dependency(
                                source_service_id=svc_id,
                                target_service_id=tgt_id,
                                dep_type=dep_type,
                                detail=detail,
                            ))
        return deps
