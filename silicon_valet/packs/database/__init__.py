"""Database domain pack — PostgreSQL, MySQL, Redis, MongoDB diagnostics."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "database"
    version = "1.0"
    description = "Database management: PostgreSQL, MySQL, Redis, MongoDB"

    def detect(self, dna: DNAStore) -> bool:
        services = dna.get_all_services()
        db_names = {"postgresql", "postgres", "mysql", "mysqld", "mariadb",
                     "redis", "redis-server", "mongod", "mongodb"}
        return any(s.name in db_names for s in services)

    def get_tools(self) -> list[type]:
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Database connection refused",
                problem_pattern="Applications cannot connect to the database server",
                symptoms=[
                    "Connection refused errors in application logs",
                    "Database port not listening",
                    "Database service not running",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status postgresql 2>/dev/null || systemctl status mysql 2>/dev/null || systemctl status redis", "explanation": "Check database service status", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp | grep -E ':(5432|3306|6379|27017)'", "explanation": "Check if database ports are listening", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl -u postgresql --no-pager -n 30 2>/dev/null || journalctl -u mysql --no-pager -n 30", "explanation": "Check database logs", "risk_tier": "green"},
                    {"action": "check", "command": "cat /var/log/postgresql/postgresql-*-main.log 2>/dev/null | tail -30 || tail -30 /var/log/mysql/error.log 2>/dev/null", "explanation": "Check database log files", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart postgresql 2>/dev/null || systemctl restart mysql 2>/dev/null || systemctl restart redis", "explanation": "Restart database service", "risk_tier": "yellow"},
                ],
                root_cause="Service crashed, configuration error, disk full, or permission issue",
                verification="Database service is running and accepting connections on expected port",
                tags=["database", "connection", "postgresql", "mysql", "redis"],
                pack_source="database",
            ),
            RunbookEntry(
                title="Slow database queries",
                problem_pattern="Database queries taking too long, causing application slowness",
                symptoms=[
                    "Application response times increased",
                    "Database CPU or I/O usage spiking",
                    "Slow query log filling up",
                ],
                steps=[
                    {"action": "check", "command": "cat /var/log/postgresql/postgresql-*-main.log 2>/dev/null | grep -i 'duration:' | tail -20", "explanation": "Check PostgreSQL slow queries", "risk_tier": "green"},
                    {"action": "check", "command": "mysqladmin processlist 2>/dev/null || redis-cli info stats 2>/dev/null", "explanation": "Check active queries/connections", "risk_tier": "green"},
                    {"action": "check", "command": "iostat -x 1 3 2>/dev/null || cat /proc/diskstats", "explanation": "Check disk I/O (database bottleneck)", "risk_tier": "green"},
                    {"action": "check", "command": "free -h", "explanation": "Check available memory for caching", "risk_tier": "green"},
                ],
                root_cause="Missing indexes, insufficient memory for caching, disk I/O bottleneck, or long-running transactions",
                verification="Query response times return to normal levels",
                tags=["database", "performance", "slow", "queries"],
                pack_source="database",
            ),
            RunbookEntry(
                title="Database disk usage growing",
                problem_pattern="Database data directory consuming excessive disk space",
                symptoms=[
                    "df -h shows database partition filling up",
                    "WAL/binlog files accumulating",
                    "Database backups failing due to space",
                ],
                steps=[
                    {"action": "check", "command": "du -sh /var/lib/postgresql/ 2>/dev/null || du -sh /var/lib/mysql/ 2>/dev/null", "explanation": "Check database data directory size", "risk_tier": "green"},
                    {"action": "check", "command": "ls -lah /var/lib/postgresql/*/main/pg_wal/ 2>/dev/null | tail -20", "explanation": "Check PostgreSQL WAL size", "risk_tier": "green"},
                    {"action": "check", "command": "ls -lah /var/log/mysql/ 2>/dev/null", "explanation": "Check MySQL binary logs", "risk_tier": "green"},
                    {"action": "check", "command": "df -h", "explanation": "Overall disk usage", "risk_tier": "green"},
                ],
                root_cause="WAL/binlog retention too long, missing VACUUM, table bloat, or forgotten backups",
                verification="Database disk usage stabilized or reduced",
                tags=["database", "disk", "storage", "wal"],
                pack_source="database",
            ),
        ]
