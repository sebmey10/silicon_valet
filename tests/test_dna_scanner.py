"""Tests for the BackgroundScanner — mocked subprocess calls."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from silicon_valet.config import ValetConfig
from silicon_valet.dna.scanner import BackgroundScanner, _run_cmd
from silicon_valet.dna.store import DNAStore


MOCK_KUBECTL_NODES = json.dumps({
    "items": [
        {
            "metadata": {
                "name": "worker-01",
                "labels": {"node-role.kubernetes.io/worker": ""}
            },
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": "10.0.0.11"},
                    {"type": "Hostname", "address": "worker-01"}
                ],
                "capacity": {"cpu": "8", "memory": "32874536Ki"},
                "nodeInfo": {"osImage": "Ubuntu 22.04.3 LTS"}
            }
        },
        {
            "metadata": {
                "name": "worker-02",
                "labels": {"node-role.kubernetes.io/worker": ""}
            },
            "status": {
                "addresses": [
                    {"type": "InternalIP", "address": "10.0.0.12"},
                    {"type": "Hostname", "address": "worker-02"}
                ],
                "capacity": {"cpu": "8", "memory": "32874536Ki"},
                "nodeInfo": {"osImage": "Ubuntu 22.04.3 LTS"}
            }
        }
    ]
})

MOCK_KUBECTL_PODS = json.dumps({
    "items": [
        {
            "metadata": {"name": "coredns-abc123", "namespace": "kube-system"},
            "spec": {"containers": [{"image": "rancher/mirrored-coredns-coredns:1.10.1"}]},
            "status": {"phase": "Running"}
        },
        {
            "metadata": {"name": "nginx-pod-xyz", "namespace": "default"},
            "spec": {"containers": [{"image": "nginx:1.25"}]},
            "status": {"phase": "Running"}
        }
    ]
})

MOCK_KUBECTL_DEPLOYMENTS = json.dumps({
    "items": [
        {
            "metadata": {"name": "nginx", "namespace": "default"},
            "status": {"replicas": 2, "readyReplicas": 2}
        }
    ]
})

MOCK_SYSTEMCTL_JSON = json.dumps([
    {"unit": "nginx.service", "active": "active"},
    {"unit": "sshd.service", "active": "active"},
    {"unit": "postgresql.service", "active": "inactive"},
])

MOCK_SS_TCP = """State   Recv-Q  Send-Q  Local Address:Port  Peer Address:Port
LISTEN  0       128     0.0.0.0:80          0.0.0.0:*
LISTEN  0       128     0.0.0.0:443         0.0.0.0:*
LISTEN  0       128     127.0.0.1:5432      0.0.0.0:*
"""

MOCK_IP_ADDR = json.dumps([
    {
        "ifname": "eth0",
        "operstate": "UP",
        "address": "00:11:22:33:44:55",
        "addr_info": [
            {"family": "inet", "local": "10.0.0.11", "prefixlen": 24}
        ]
    },
    {
        "ifname": "lo",
        "operstate": "UNKNOWN",
        "address": "00:00:00:00:00:00",
        "addr_info": [
            {"family": "inet", "local": "127.0.0.1", "prefixlen": 8}
        ]
    }
])


@pytest.fixture
def scanner(dna_store, mock_config):
    return BackgroundScanner(dna_store, mock_config)


def _mock_run_cmd(responses: dict):
    """Create a side_effect function that returns different output based on command."""
    async def _side_effect(cmd, timeout=15):
        cmd_str = " ".join(cmd)
        for key, value in responses.items():
            if key in cmd_str:
                return value
        return None
    return _side_effect


class TestNodeScanning:
    @pytest.mark.asyncio
    async def test_scan_nodes_parses_kubectl(self, scanner):
        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=_mock_run_cmd({
            "kubectl get nodes": MOCK_KUBECTL_NODES,
        })):
            nodes = await scanner._scan_nodes()
            assert len(nodes) == 2
            assert nodes[0].hostname == "worker-01"
            assert nodes[0].ip == "10.0.0.11"
            assert nodes[0].role == "worker"
            assert nodes[0].ram_total_mb == 32874536 // 1024
            assert nodes[0].cpu_cores == 8

    @pytest.mark.asyncio
    async def test_scan_nodes_returns_empty_on_failure(self, scanner):
        with patch("silicon_valet.dna.scanner._run_cmd", return_value=None):
            nodes = await scanner._scan_nodes()
            assert nodes == []


class TestServiceScanning:
    @pytest.mark.asyncio
    async def test_scan_k8s_services(self, scanner):
        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=_mock_run_cmd({
            "kubectl get pods": MOCK_KUBECTL_PODS,
            "kubectl get deployments": MOCK_KUBECTL_DEPLOYMENTS,
        })):
            services = await scanner._scan_k8s_services()
            pods = [s for s in services if s.type == "k8s_pod"]
            deploys = [s for s in services if s.type == "k8s_deploy"]
            assert len(pods) == 2
            assert len(deploys) == 1
            assert pods[0].status == "running"
            assert deploys[0].name == "nginx"

    @pytest.mark.asyncio
    async def test_scan_systemd_units_json(self, scanner):
        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=_mock_run_cmd({
            "systemctl list-units": MOCK_SYSTEMCTL_JSON,
        })):
            services = await scanner._scan_systemd_units()
            assert len(services) == 3
            nginx = next(s for s in services if s.name == "nginx")
            assert nginx.status == "running"
            pg = next(s for s in services if s.name == "postgresql")
            assert pg.status == "inactive"


class TestPortScanning:
    @pytest.mark.asyncio
    async def test_scan_ports(self, scanner):
        async def mock_cmd(cmd, timeout=15):
            if "-tlnp" in cmd:
                return MOCK_SS_TCP
            return None

        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=mock_cmd):
            ports = await scanner._scan_ports()
            assert len(ports) == 3
            port_numbers = {p.port for p in ports}
            assert port_numbers == {80, 443, 5432}
            pg_port = next(p for p in ports if p.port == 5432)
            assert pg_port.bind_address == "127.0.0.1"


class TestNetworkScanning:
    @pytest.mark.asyncio
    async def test_scan_network_interfaces(self, scanner):
        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=_mock_run_cmd({
            "ip -j addr": MOCK_IP_ADDR,
        })):
            ifaces = await scanner._scan_network_interfaces()
            assert len(ifaces) == 1  # lo is filtered out
            assert ifaces[0].name == "eth0"
            assert ifaces[0].ip == "10.0.0.11"


class TestFullScan:
    @pytest.mark.asyncio
    async def test_scan_once_populates_store(self, scanner):
        """Full integration: scan_once should populate the DNA store."""
        responses = {
            "kubectl get nodes": MOCK_KUBECTL_NODES,
            "kubectl get pods": MOCK_KUBECTL_PODS,
            "kubectl get deployments": MOCK_KUBECTL_DEPLOYMENTS,
            "systemctl list-units": MOCK_SYSTEMCTL_JSON,
            "ip -j addr": MOCK_IP_ADDR,
        }

        async def mock_cmd(cmd, timeout=15):
            cmd_str = " ".join(cmd)
            for key, value in responses.items():
                if key in cmd_str:
                    return value
            return None

        with patch("silicon_valet.dna.scanner._run_cmd", side_effect=mock_cmd):
            result = await scanner.scan_once()
            assert len(result.nodes) == 2
            assert len(result.services) >= 5  # 2 pods + 1 deploy + 3 systemd

            # Verify data persisted in store
            stored_nodes = scanner.store.get_all_nodes()
            assert len(stored_nodes) == 2
            stored_services = scanner.store.get_all_services()
            assert len(stored_services) >= 5
