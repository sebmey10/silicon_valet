"""Zabbix domain pack — connector debugging, trigger analysis, host discovery issues."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "zabbix"
    version = "1.0"
    description = "Zabbix monitoring server management, trigger analysis, agent connectivity"

    def detect(self, dna: DNAStore) -> bool:
        services = dna.search_services("zabbix")
        return len(services) > 0

    def get_tools(self) -> list[type]:
        return []

    def get_scan_extensions(self) -> list[str]:
        return ["/etc/zabbix/**/*.conf", "/usr/lib/zabbix/externalscripts/"]

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Zabbix server not starting",
                problem_pattern="Zabbix server service fails to start or crashes immediately",
                symptoms=[
                    "systemctl status zabbix-server shows failed",
                    "Zabbix web UI unreachable",
                    "Port 10051 not listening",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status zabbix-server", "explanation": "Check service status", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl -u zabbix-server --since '10 min ago'", "explanation": "Check recent logs", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/zabbix/zabbix_server.conf | grep -v '^#' | grep -v '^$'", "explanation": "Review active config", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp | grep 10051", "explanation": "Check if port is in use", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart zabbix-server", "explanation": "Restart Zabbix server", "risk_tier": "yellow"},
                ],
                root_cause="Database connection failure, config error, or port conflict",
                verification="systemctl is-active zabbix-server returns active AND port 10051 is listening",
                tags=["zabbix", "server", "startup"],
                pack_source="zabbix",
            ),
            RunbookEntry(
                title="Zabbix agent unreachable",
                problem_pattern="Zabbix server cannot communicate with agent on monitored host",
                symptoms=[
                    "Host shows as unreachable in Zabbix dashboard",
                    "Get value from agent failed: cannot connect",
                    "Port 10050 not responding",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status zabbix-agent2", "explanation": "Check agent status on target", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp | grep 10050", "explanation": "Check if agent port is listening", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/zabbix/zabbix_agent2.conf | grep Server", "explanation": "Verify allowed server IPs", "risk_tier": "green"},
                    {"action": "check", "command": "ping -c 3 {agent_host}", "explanation": "Test network connectivity", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart zabbix-agent2", "explanation": "Restart the agent", "risk_tier": "yellow"},
                ],
                root_cause="Agent not running, firewall blocking port 10050, or Server= config mismatch",
                verification="Zabbix server can query the agent and host shows as available",
                tags=["zabbix", "agent", "connectivity"],
                pack_source="zabbix",
            ),
        ]
