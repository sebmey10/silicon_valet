"""Firewall and security domain pack — ufw, iptables, firewalld, fail2ban."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "firewall"
    version = "1.0"
    description = "Firewall and security: ufw, iptables, firewalld, fail2ban, SSH hardening"

    def detect(self, dna: DNAStore) -> bool:
        services = dna.get_all_services()
        fw_names = {"ufw", "firewalld", "iptables", "nftables", "fail2ban"}
        # Also activate if SSH is running (always relevant for security)
        if any(s.name == "sshd" and s.status == "running" for s in services):
            return True
        return any(s.name in fw_names for s in services)

    def get_tools(self) -> list[type]:
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Locked out of SSH",
                problem_pattern="Cannot SSH into server due to firewall or fail2ban",
                symptoms=[
                    "SSH connection timeout or refused",
                    "fail2ban has banned your IP",
                    "Firewall rule blocking port 22",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status sshd", "explanation": "Check SSH service status", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp | grep :22", "explanation": "Check if SSH is listening", "risk_tier": "green"},
                    {"action": "check", "command": "fail2ban-client status sshd 2>/dev/null", "explanation": "Check fail2ban SSH jail status", "risk_tier": "green"},
                    {"action": "check", "command": "ufw status 2>/dev/null || firewall-cmd --list-all 2>/dev/null || iptables -L -n | head -30", "explanation": "Check firewall rules", "risk_tier": "green"},
                    {"action": "fix", "command": "fail2ban-client set sshd unbanip {ip_address}", "explanation": "Unban IP from fail2ban", "risk_tier": "yellow"},
                    {"action": "fix", "command": "ufw allow 22/tcp 2>/dev/null || firewall-cmd --add-service=ssh --permanent 2>/dev/null", "explanation": "Allow SSH through firewall", "risk_tier": "yellow"},
                ],
                root_cause="IP banned by fail2ban, firewall misconfigured, or SSH service down",
                verification="SSH connection succeeds from the affected IP",
                tags=["ssh", "firewall", "fail2ban", "lockout", "security"],
                pack_source="firewall",
            ),
            RunbookEntry(
                title="Port unreachable despite service running",
                problem_pattern="Service is running and listening but clients cannot connect from outside",
                symptoms=[
                    "Service shows as running in systemctl",
                    "ss shows service listening on the port",
                    "External clients get 'connection refused' or timeout",
                ],
                steps=[
                    {"action": "check", "command": "ss -tlnp | grep {port}", "explanation": "Verify service is listening on the port", "risk_tier": "green"},
                    {"action": "check", "command": "ufw status verbose 2>/dev/null || firewall-cmd --list-all 2>/dev/null", "explanation": "Check firewall rules for the port", "risk_tier": "green"},
                    {"action": "check", "command": "iptables -L -n -v | grep {port} 2>/dev/null", "explanation": "Check iptables for the port", "risk_tier": "green"},
                    {"action": "check", "command": "curl -v localhost:{port} 2>&1 | head -10", "explanation": "Test local connectivity", "risk_tier": "green"},
                    {"action": "fix", "command": "ufw allow {port}/tcp 2>/dev/null || firewall-cmd --add-port={port}/tcp --permanent && firewall-cmd --reload 2>/dev/null", "explanation": "Allow port through firewall", "risk_tier": "yellow"},
                ],
                root_cause="Firewall blocking the port, service bound to localhost only, or cloud security group",
                verification="External client can connect to the service",
                tags=["firewall", "port", "networking", "access"],
                pack_source="firewall",
            ),
            RunbookEntry(
                title="Fail2ban blocking legitimate users",
                problem_pattern="Fail2ban banning legitimate IPs due to aggressive rules",
                symptoms=[
                    "Users reporting intermittent connection failures",
                    "fail2ban-client status shows many banned IPs",
                    "Legitimate login attempts being counted as failures",
                ],
                steps=[
                    {"action": "check", "command": "fail2ban-client status", "explanation": "List all fail2ban jails", "risk_tier": "green"},
                    {"action": "check", "command": "fail2ban-client status sshd 2>/dev/null", "explanation": "Check SSH jail details and banned IPs", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/fail2ban/jail.local 2>/dev/null || cat /etc/fail2ban/jail.conf | grep -A5 '\\[sshd\\]'", "explanation": "Check fail2ban configuration", "risk_tier": "green"},
                    {"action": "check", "command": "tail -50 /var/log/fail2ban.log", "explanation": "Check recent fail2ban actions", "risk_tier": "green"},
                ],
                root_cause="Ban threshold too low, ban time too long, or ignoreip not configured for known IPs",
                verification="Legitimate users can connect without being banned",
                tags=["fail2ban", "security", "banning", "ssh"],
                pack_source="firewall",
            ),
        ]
