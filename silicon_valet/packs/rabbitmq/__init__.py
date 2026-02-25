"""RabbitMQ domain pack — queue depth, consumer health, dead letter queues."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "rabbitmq"
    version = "1.0"
    description = "RabbitMQ message broker management, queue monitoring, consumer health"

    def detect(self, dna: DNAStore) -> bool:
        services = dna.search_services("rabbitmq")
        if services:
            return True
        # Also check for AMQP port
        svc = dna.get_service_by_port(5672)
        return svc is not None

    def get_tools(self) -> list[type]:
        return []

    def get_scan_extensions(self) -> list[str]:
        return ["/etc/rabbitmq/**/*.conf"]

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="RabbitMQ queue backlog growing",
                problem_pattern="Messages accumulating in queue faster than consumers process them",
                symptoms=[
                    "Queue depth increasing over time",
                    "Consumer processing latency increasing",
                    "Memory usage on RabbitMQ node rising",
                ],
                steps=[
                    {"action": "check", "command": "rabbitmqctl list_queues name messages consumers", "explanation": "List queues with message count and consumer count", "risk_tier": "green"},
                    {"action": "check", "command": "rabbitmqctl list_connections", "explanation": "Check active connections", "risk_tier": "green"},
                    {"action": "check", "command": "rabbitmqctl status", "explanation": "Check RabbitMQ node health", "risk_tier": "green"},
                    {"action": "check", "command": "free -h", "explanation": "Check available memory", "risk_tier": "green"},
                ],
                root_cause="Consumer is down, slow, or disconnected; or producer rate exceeds consumer capacity",
                verification="Queue depth is stable or decreasing",
                tags=["rabbitmq", "queues", "backlog"],
                pack_source="rabbitmq",
            ),
            RunbookEntry(
                title="RabbitMQ node not starting",
                problem_pattern="RabbitMQ server fails to start",
                symptoms=[
                    "systemctl status rabbitmq-server shows failed",
                    "Port 5672 not listening",
                    "AMQP connections refused",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status rabbitmq-server", "explanation": "Check service status", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl -u rabbitmq-server --since '10 min ago'", "explanation": "Check recent logs", "risk_tier": "green"},
                    {"action": "check", "command": "cat /etc/rabbitmq/rabbitmq.conf 2>/dev/null || echo 'No config file'", "explanation": "Check configuration", "risk_tier": "green"},
                    {"action": "check", "command": "ls -la /var/lib/rabbitmq/mnesia/", "explanation": "Check database directory", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart rabbitmq-server", "explanation": "Restart RabbitMQ", "risk_tier": "yellow"},
                ],
                root_cause="Erlang cookie mismatch, Mnesia database corruption, or config error",
                verification="rabbitmqctl status returns healthy node status",
                tags=["rabbitmq", "startup", "server"],
                pack_source="rabbitmq",
            ),
        ]
