"""Tests for domain pack loading and detection."""

import pytest
from unittest.mock import MagicMock

from silicon_valet.packs.base import BasePack
from silicon_valet.packs.loader import PackLoader


@pytest.fixture
def mock_dna():
    dna = MagicMock()
    dna.get_all_services.return_value = []
    dna.get_listening_ports.return_value = []
    dna.search_services.return_value = []
    dna.get_service_by_port.return_value = None
    return dna


class TestPackLoader:
    def test_discover_packs(self, mock_dna):
        loader = PackLoader(mock_dna)
        packs = loader.discover_packs()
        # Should find at least the 4 built-in packs
        assert len(packs) >= 4
        names = [p.name for p in packs]
        assert "networking" in names
        assert "kubernetes" in names
        assert "zabbix" in names
        assert "rabbitmq" in names

    def test_networking_always_active(self, mock_dna):
        loader = PackLoader(mock_dna)
        packs = loader.discover_packs()
        active = loader.activate_matching()
        active_names = [p.name for p in active]
        assert "networking" in active_names

    def test_kubernetes_detects_services(self, mock_dna):
        svc = MagicMock()
        svc.name = "kube-apiserver"
        svc.type = "k8s_pod"
        mock_dna.get_all_services.return_value = [svc]

        loader = PackLoader(mock_dna)
        loader.discover_packs()
        active = loader.activate_matching()
        active_names = [p.name for p in active]
        assert "kubernetes" in active_names

    def test_zabbix_detects_services(self, mock_dna):
        svc = MagicMock()
        svc.name = "zabbix-server"
        mock_dna.search_services.return_value = [svc]

        loader = PackLoader(mock_dna)
        loader.discover_packs()
        active = loader.activate_matching()
        active_names = [p.name for p in active]
        assert "zabbix" in active_names

    def test_rabbitmq_detects_port(self, mock_dna):
        svc = MagicMock()
        svc.name = "rabbitmq-server"
        mock_dna.get_service_by_port.return_value = svc

        loader = PackLoader(mock_dna)
        loader.discover_packs()
        active = loader.activate_matching()
        active_names = [p.name for p in active]
        assert "rabbitmq" in active_names

    def test_runbook_seeds(self, mock_dna):
        loader = PackLoader(mock_dna)
        loader.discover_packs()
        active = loader.activate_matching()
        # Networking pack always active and has runbook seeds
        net_pack = [p for p in active if p.name == "networking"][0]
        seeds = net_pack.get_runbook_seeds()
        assert len(seeds) > 0
        assert all(hasattr(s, "title") for s in seeds)
