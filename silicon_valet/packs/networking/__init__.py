"""Networking domain pack — VLAN analysis, route tracing, DNS debugging, connectivity testing."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "networking"
    version = "1.0"
    description = "Network diagnostics, DNS debugging, route analysis, connectivity testing"

    def detect(self, dna: DNAStore) -> bool:
        # Networking tools are always relevant
        return True

    def get_tools(self) -> list[type]:
        return []  # Core network tools are already in tools/network.py

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="DNS resolution failure",
                problem_pattern="DNS queries failing or returning wrong results",
                symptoms=[
                    "Services cannot resolve hostnames",
                    "dig or nslookup returns SERVFAIL or NXDOMAIN",
                    "Applications report connection timeout to named hosts",
                ],
                steps=[
                    {"action": "check", "command": "dig @127.0.0.1 example.com", "explanation": "Test local DNS resolver", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/resolv.conf", "explanation": "Verify DNS configuration", "risk_tier": "green"},
                    {"action": "check", "command": "systemctl status systemd-resolved", "explanation": "Check DNS service status", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl get pods -n kube-system -l k8s-app=kube-dns", "explanation": "Check CoreDNS pods", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart systemd-resolved", "explanation": "Restart DNS resolver", "risk_tier": "yellow"},
                ],
                root_cause="DNS resolver service is down or misconfigured",
                verification="dig example.com returns correct IP",
                tags=["dns", "networking", "resolution"],
                pack_source="networking",
            ),
            RunbookEntry(
                title="Network connectivity loss between nodes",
                problem_pattern="Nodes cannot reach each other over the network",
                symptoms=[
                    "ping between nodes fails",
                    "kubectl reports NotReady nodes",
                    "Services on remote nodes unreachable",
                ],
                steps=[
                    {"action": "check", "command": "ping -c 3 {target_ip}", "explanation": "Test basic connectivity", "risk_tier": "green"},
                    {"action": "check", "command": "ip route show", "explanation": "Check routing table", "risk_tier": "green"},
                    {"action": "check", "command": "ip link show", "explanation": "Check network interfaces", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp", "explanation": "Check listening ports", "risk_tier": "green"},
                    {"action": "check", "command": "traceroute {target_ip}", "explanation": "Trace network path", "risk_tier": "green"},
                ],
                root_cause="Network interface down, route misconfiguration, or firewall blocking",
                verification="ping between nodes succeeds with <10ms latency",
                tags=["networking", "connectivity", "nodes"],
                pack_source="networking",
            ),
        ]
