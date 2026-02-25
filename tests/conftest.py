"""Shared test fixtures for Silicon Valet tests."""

from __future__ import annotations

import pytest

from silicon_valet.config import ValetConfig
from silicon_valet.dna.store import DNAStore
from silicon_valet.dna.models import Node, Service, Port, ConfigFile, Dependency, NetworkInterface


@pytest.fixture
def mock_config(tmp_path):
    """A ValetConfig pointing at temp directories."""
    return ValetConfig(
        data_dir=tmp_path / "data",
        ollama_orchestrator="http://localhost:11434",
        ollama_coder="http://localhost:11435",
        backup_dir=tmp_path / "backups",
    )


@pytest.fixture
def dna_store():
    """An in-memory DNAStore for testing."""
    store = DNAStore(":memory:")
    yield store
    store.close()


@pytest.fixture
def populated_dna(dna_store):
    """A DNAStore pre-populated with sample infrastructure data."""
    # Nodes
    w1 = dna_store.upsert_node(Node(hostname="worker-01", ip="10.0.0.11", role="worker", ram_total_mb=32768, cpu_cores=8))
    w2 = dna_store.upsert_node(Node(hostname="worker-02", ip="10.0.0.12", role="worker", ram_total_mb=32768, cpu_cores=8))

    # Services
    nginx = dna_store.upsert_service(Service(name="nginx", type="systemd", node_id=w1.id, status="running", pid=1234))
    postgres = dna_store.upsert_service(Service(name="postgresql", type="systemd", node_id=w1.id, status="running", pid=5678))
    zabbix = dna_store.upsert_service(Service(name="zabbix-server", type="systemd", node_id=w2.id, status="running"))
    coredns = dna_store.upsert_service(Service(name="coredns", type="k8s_pod", node_id=w1.id, namespace="kube-system", status="running", image="rancher/mirrored-coredns-coredns:1.10.1"))

    # Ports
    dna_store.upsert_port(Port(service_id=nginx.id, port=80, protocol="tcp"))
    dna_store.upsert_port(Port(service_id=nginx.id, port=443, protocol="tcp"))
    dna_store.upsert_port(Port(service_id=postgres.id, port=5432, protocol="tcp", bind_address="127.0.0.1"))
    dna_store.upsert_port(Port(service_id=zabbix.id, port=10051, protocol="tcp"))

    # Config files
    dna_store.upsert_config_file(ConfigFile(service_id=nginx.id, path="/etc/nginx/nginx.conf", hash_sha256="abc123"))
    dna_store.upsert_config_file(ConfigFile(service_id=postgres.id, path="/etc/postgresql/14/main/postgresql.conf"))
    dna_store.upsert_config_file(ConfigFile(service_id=zabbix.id, path="/etc/zabbix/zabbix_server.conf"))

    # Dependencies
    dna_store.add_dependency(Dependency(source_service_id=zabbix.id, target_service_id=postgres.id, dep_type="network", detail="connects on port 5432"))
    dna_store.add_dependency(Dependency(source_service_id=nginx.id, target_service_id=zabbix.id, dep_type="network", detail="reverse proxy to zabbix web"))

    # Network interfaces
    dna_store.upsert_network_interface(NetworkInterface(node_id=w1.id, name="eth0", ip="10.0.0.11", subnet="10.0.0.0/24", mac="00:11:22:33:44:55"))
    dna_store.upsert_network_interface(NetworkInterface(node_id=w2.id, name="eth0", ip="10.0.0.12", subnet="10.0.0.0/24", mac="00:11:22:33:44:66"))

    return dna_store
