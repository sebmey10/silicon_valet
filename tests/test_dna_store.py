"""Tests for the DNAStore — CRUD operations and graph-like queries."""

from __future__ import annotations

import pytest

from silicon_valet.dna.models import (
    ConfigFile,
    Dependency,
    NetworkInterface,
    Node,
    Port,
    Service,
)
from silicon_valet.dna.store import DNAStore


class TestNodeOperations:
    def test_upsert_new_node(self, dna_store):
        node = dna_store.upsert_node(Node(hostname="test-node", ip="10.0.0.1", role="worker"))
        assert node.id is not None
        assert node.hostname == "test-node"

    def test_upsert_existing_node_updates(self, dna_store):
        n1 = dna_store.upsert_node(Node(hostname="test-node", ip="10.0.0.1", role="worker"))
        n2 = dna_store.upsert_node(Node(hostname="test-node", ip="10.0.0.2"))
        assert n1.id == n2.id  # Same row
        fetched = dna_store.get_node("test-node")
        assert fetched.ip == "10.0.0.2"

    def test_get_node_missing(self, dna_store):
        assert dna_store.get_node("nonexistent") is None

    def test_get_all_nodes(self, populated_dna):
        nodes = populated_dna.get_all_nodes()
        assert len(nodes) == 2
        hostnames = {n.hostname for n in nodes}
        assert hostnames == {"worker-01", "worker-02"}

    def test_node_upsert_records_change(self, dna_store):
        node = dna_store.upsert_node(Node(hostname="n1", ip="10.0.0.1"))
        changes = dna_store.get_changes_since(hours=1)
        assert any(c.entity_type == "node" and c.change_type == "added" for c in changes)

    def test_node_modification_records_change(self, dna_store):
        dna_store.upsert_node(Node(hostname="n1", ip="10.0.0.1"))
        dna_store.upsert_node(Node(hostname="n1", ip="10.0.0.2"))
        changes = dna_store.get_changes_since(hours=1)
        mod_changes = [c for c in changes if c.change_type == "modified"]
        assert len(mod_changes) >= 1
        assert any(c.field == "ip" for c in mod_changes)


class TestServiceOperations:
    def test_upsert_new_service(self, populated_dna):
        svc = populated_dna.upsert_service(
            Service(name="rabbitmq", type="systemd", node_id=1, status="running")
        )
        assert svc.id is not None

    def test_get_services_on_node(self, populated_dna):
        services = populated_dna.get_services_on_node("worker-01")
        names = {s.name for s in services}
        assert "nginx" in names
        assert "postgresql" in names

    def test_get_service_by_name(self, populated_dna):
        svc = populated_dna.get_service_by_name("nginx")
        assert svc is not None
        assert svc.name == "nginx"

    def test_get_service_by_port(self, populated_dna):
        svc = populated_dna.get_service_by_port(80)
        assert svc is not None
        assert svc.name == "nginx"

    def test_get_service_by_port_missing(self, populated_dna):
        assert populated_dna.get_service_by_port(9999) is None

    def test_search_services(self, populated_dna):
        results = populated_dna.search_services("zabbix")
        assert len(results) == 1
        assert results[0].name == "zabbix-server"

    def test_search_services_by_image(self, populated_dna):
        results = populated_dna.search_services("coredns")
        assert len(results) >= 1

    def test_get_all_services(self, populated_dna):
        services = populated_dna.get_all_services()
        assert len(services) == 4


class TestPortOperations:
    def test_upsert_port(self, populated_dna):
        svc = populated_dna.get_service_by_name("nginx")
        port = populated_dna.upsert_port(Port(service_id=svc.id, port=8080, protocol="tcp"))
        assert port.id is not None

    def test_get_listening_ports(self, populated_dna):
        ports = populated_dna.get_listening_ports()
        assert len(ports) == 4
        port_numbers = {p["port"] for p in ports}
        assert port_numbers == {80, 443, 5432, 10051}

    def test_port_includes_service_name(self, populated_dna):
        ports = populated_dna.get_listening_ports()
        port_80 = next(p for p in ports if p["port"] == 80)
        assert port_80["service_name"] == "nginx"


class TestConfigFileOperations:
    def test_get_configs_for_service(self, populated_dna):
        svc = populated_dna.get_service_by_name("nginx")
        configs = populated_dna.get_configs_for_service(svc.id)
        assert len(configs) == 1
        assert configs[0].path == "/etc/nginx/nginx.conf"

    def test_config_file_hash_change_tracked(self, populated_dna):
        svc = populated_dna.get_service_by_name("nginx")
        populated_dna.upsert_config_file(
            ConfigFile(service_id=svc.id, path="/etc/nginx/nginx.conf", hash_sha256="new_hash")
        )
        changes = populated_dna.get_changes_since(hours=1)
        hash_changes = [c for c in changes if c.field == "hash_sha256"]
        assert len(hash_changes) >= 1


class TestDependencies:
    def test_add_dependency(self, populated_dna):
        deps = populated_dna.get_dependencies(
            populated_dna.get_service_by_name("zabbix-server").id, direction="outgoing"
        )
        assert len(deps) == 1
        assert deps[0]["target_name"] == "postgresql"

    def test_get_dependencies_both_directions(self, populated_dna):
        pg = populated_dna.get_service_by_name("postgresql")
        deps = populated_dna.get_dependencies(pg.id, direction="both")
        # postgresql has one incoming dep (from zabbix)
        incoming = [d for d in deps if d["direction"] == "incoming"]
        assert len(incoming) == 1

    def test_get_dependents_bfs(self, populated_dna):
        """BFS: nginx → zabbix → postgresql. Dependents of postgresql should include zabbix and nginx."""
        pg = populated_dna.get_service_by_name("postgresql")
        dependents = populated_dna.get_dependents(pg.id)
        names = {s.name for s in dependents}
        assert "zabbix-server" in names
        # nginx depends on zabbix which depends on postgresql
        assert "nginx" in names

    def test_duplicate_dependency_idempotent(self, populated_dna):
        zabbix = populated_dna.get_service_by_name("zabbix-server")
        pg = populated_dna.get_service_by_name("postgresql")
        dep = populated_dna.add_dependency(
            Dependency(source_service_id=zabbix.id, target_service_id=pg.id, dep_type="network")
        )
        # Should return existing, not create duplicate
        assert dep.id is not None


class TestNetworkInterfaces:
    def test_upsert_network_interface(self, dna_store):
        node = dna_store.upsert_node(Node(hostname="n1", ip="10.0.0.1"))
        iface = dna_store.upsert_network_interface(
            NetworkInterface(node_id=node.id, name="eth0", ip="10.0.0.1", mac="aa:bb:cc:dd:ee:ff")
        )
        assert iface.id is not None


class TestChangesLog:
    def test_changes_since(self, populated_dna):
        changes = populated_dna.get_changes_since(hours=1)
        # Should have changes from all the initial data population
        assert len(changes) > 0

    def test_mark_services_removed(self, populated_dna):
        services = populated_dna.get_all_services()
        keep_ids = {services[0].id}  # Keep only the first service
        populated_dna.mark_services_removed(keep_ids)
        remaining = populated_dna.get_all_services()
        assert len(remaining) == 1
        changes = populated_dna.get_changes_since(hours=1)
        removed = [c for c in changes if c.change_type == "removed" and c.entity_type == "service"]
        assert len(removed) == 3


class TestContextSummary:
    def test_context_summary_not_empty(self, populated_dna):
        summary = populated_dna.get_context_summary()
        assert "Current Environment" in summary
        assert "worker-01" in summary
        assert "nginx" in summary

    def test_context_summary_empty_store(self, dna_store):
        summary = dna_store.get_context_summary()
        assert "Current Environment" in summary
