"""Linux basics domain pack — disk, CPU, memory, systemd, cron, log rotation, user management."""

from __future__ import annotations

import platform

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "linux"
    version = "1.0"
    description = "Linux server fundamentals: disk, CPU, memory, systemd, cron, logs, users"

    def detect(self, dna: DNAStore) -> bool:
        # Always active on Linux systems
        return platform.system() == "Linux"

    def get_tools(self) -> list[type]:
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Disk space full",
                problem_pattern="Root filesystem or data partition running out of disk space",
                symptoms=[
                    "df -h shows 90%+ usage on a partition",
                    "Applications failing with 'No space left on device'",
                    "System becoming unresponsive",
                ],
                steps=[
                    {"action": "check", "command": "df -h", "explanation": "Check disk usage on all partitions", "risk_tier": "green"},
                    {"action": "check", "command": "du -sh /var/log/* | sort -rh | head -20", "explanation": "Find largest items in /var/log", "risk_tier": "green"},
                    {"action": "check", "command": "du -sh /tmp/* 2>/dev/null | sort -rh | head -10", "explanation": "Check /tmp for large files", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl --disk-usage", "explanation": "Check systemd journal size", "risk_tier": "green"},
                    {"action": "fix", "command": "journalctl --vacuum-size=500M", "explanation": "Trim journal to 500MB", "risk_tier": "yellow"},
                    {"action": "fix", "command": "apt-get autoremove -y", "explanation": "Remove unused packages (Debian/Ubuntu)", "risk_tier": "yellow"},
                ],
                root_cause="Log accumulation, old packages, temporary files, or undersized partition",
                verification="df -h shows usage below 85% on all partitions",
                tags=["disk", "storage", "space", "linux"],
                pack_source="linux",
            ),
            RunbookEntry(
                title="High CPU usage",
                problem_pattern="System running slow due to high CPU utilization",
                symptoms=[
                    "top/htop shows CPU near 100%",
                    "System feels sluggish or unresponsive",
                    "Load average exceeds CPU core count",
                ],
                steps=[
                    {"action": "check", "command": "uptime", "explanation": "Check load averages", "risk_tier": "green"},
                    {"action": "check", "command": "ps aux --sort=-%cpu | head -15", "explanation": "Find top CPU consumers", "risk_tier": "green"},
                    {"action": "check", "command": "top -bn1 | head -20", "explanation": "Snapshot of current resource usage", "risk_tier": "green"},
                    {"action": "check", "command": "dmesg | tail -30", "explanation": "Check for kernel-level issues", "risk_tier": "green"},
                ],
                root_cause="Runaway process, insufficient resources, or misconfigured service",
                verification="Load average drops below CPU core count",
                tags=["cpu", "performance", "load", "linux"],
                pack_source="linux",
            ),
            RunbookEntry(
                title="OOM killer triggered",
                problem_pattern="Linux OOM killer terminates processes due to memory exhaustion",
                symptoms=[
                    "Processes disappearing without explanation",
                    "dmesg shows 'Out of memory: Killed process'",
                    "Application restarts unexpectedly",
                ],
                steps=[
                    {"action": "check", "command": "dmesg | grep -i 'oom\\|out of memory' | tail -20", "explanation": "Check for OOM events", "risk_tier": "green"},
                    {"action": "check", "command": "free -h", "explanation": "Check current memory usage", "risk_tier": "green"},
                    {"action": "check", "command": "ps aux --sort=-%mem | head -15", "explanation": "Find top memory consumers", "risk_tier": "green"},
                    {"action": "check", "command": "cat /proc/sys/vm/overcommit_memory", "explanation": "Check memory overcommit setting", "risk_tier": "green"},
                    {"action": "check", "command": "swapon --show", "explanation": "Check swap space", "risk_tier": "green"},
                ],
                root_cause="Memory leak, insufficient RAM, or no swap configured",
                verification="free -h shows adequate available memory, no new OOM events in dmesg",
                tags=["memory", "oom", "ram", "linux"],
                pack_source="linux",
            ),
            RunbookEntry(
                title="Systemd service won't start",
                problem_pattern="A systemd service fails to start or keeps failing",
                symptoms=[
                    "systemctl status shows 'failed' or 'activating'",
                    "Service not responding on expected port",
                    "journalctl shows repeated start/fail cycles",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status {service_name}", "explanation": "Check service status and recent logs", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl -u {service_name} --no-pager -n 50", "explanation": "View service logs", "risk_tier": "green"},
                    {"action": "check", "command": "systemctl cat {service_name}", "explanation": "View service unit file", "risk_tier": "green"},
                    {"action": "check", "command": "systemctl list-dependencies {service_name}", "explanation": "Check service dependencies", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart {service_name}", "explanation": "Attempt service restart", "risk_tier": "yellow"},
                ],
                root_cause="Configuration error, missing dependency, permission issue, or port conflict",
                verification="systemctl status shows 'active (running)'",
                tags=["systemd", "service", "startup", "linux"],
                pack_source="linux",
            ),
            RunbookEntry(
                title="Cron job not running",
                problem_pattern="Scheduled cron job is not executing as expected",
                symptoms=[
                    "Expected output or side effects not occurring",
                    "No log entries from the cron job",
                    "crontab -l shows the job is configured",
                ],
                steps=[
                    {"action": "check", "command": "crontab -l", "explanation": "List current user's cron jobs", "risk_tier": "green"},
                    {"action": "check", "command": "ls -la /etc/cron.d/ /etc/cron.daily/ /etc/cron.hourly/", "explanation": "Check system cron directories", "risk_tier": "green"},
                    {"action": "check", "command": "grep -i cron /var/log/syslog 2>/dev/null | tail -20 || journalctl -u cron --no-pager -n 20", "explanation": "Check cron execution logs", "risk_tier": "green"},
                    {"action": "check", "command": "systemctl status cron 2>/dev/null || systemctl status crond", "explanation": "Verify cron service is running", "risk_tier": "green"},
                ],
                root_cause="Wrong cron syntax, PATH issues, permission denied, or cron service not running",
                verification="Cron job appears in execution logs at expected time",
                tags=["cron", "scheduling", "automation", "linux"],
                pack_source="linux",
            ),
            RunbookEntry(
                title="Log rotation not working",
                problem_pattern="Log files growing unbounded, logrotate not functioning",
                symptoms=[
                    "Log files in /var/log growing very large",
                    "Disk space filling up from log accumulation",
                    "No rotated log files (.1, .gz) present",
                ],
                steps=[
                    {"action": "check", "command": "ls -lh /var/log/*.log | sort -k5 -rh | head -10", "explanation": "Find largest log files", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/logrotate.conf", "explanation": "Check main logrotate config", "risk_tier": "green"},
                    {"action": "check", "command": "ls /etc/logrotate.d/", "explanation": "List per-service logrotate configs", "risk_tier": "green"},
                    {"action": "check", "command": "logrotate -d /etc/logrotate.conf 2>&1 | tail -30", "explanation": "Dry-run logrotate to find errors", "risk_tier": "green"},
                    {"action": "fix", "command": "logrotate -f /etc/logrotate.conf", "explanation": "Force logrotate run", "risk_tier": "yellow"},
                ],
                root_cause="Missing logrotate config, permission issue, or logrotate not installed",
                verification="Rotated log files (.1, .gz) appear, large log files shrink",
                tags=["logs", "logrotate", "disk", "linux"],
                pack_source="linux",
            ),
        ]
