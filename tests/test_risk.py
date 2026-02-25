"""Tests for the risk engine — classifier and engine."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from silicon_valet.config import ValetConfig
from silicon_valet.risk.classifier import ClassifiedAction, RiskClassifier, RiskTier
from silicon_valet.risk.engine import RiskEngine


@pytest.fixture
def classifier():
    return RiskClassifier()


@pytest.fixture
def risk_engine(mock_config):
    classifier = RiskClassifier()
    return RiskEngine(classifier, mock_config)


class TestRiskClassifier:
    """Comprehensive classification tests for 50+ commands."""

    # ── GREEN (read-only) ──

    @pytest.mark.parametrize("command", [
        "cat /etc/nginx/nginx.conf",
        "head -n 20 /var/log/syslog",
        "tail -f /var/log/nginx/error.log",
        "ls -la /etc/",
        "find /var/log -name '*.log' -mtime -1",
        "stat /etc/hosts",
        "grep 'error' /var/log/syslog",
        "ps aux",
        "top -bn1",
        "uptime",
        "free -h",
        "df -h",
        "du -sh /var/log",
        "who",
        "hostname",
        "ss -tlnp",
        "netstat -tulpn",
        "ip addr show",
        "ip -j addr show",
        "dig example.com",
        "nslookup example.com",
        "ping -c 3 10.0.0.1",
        "traceroute 10.0.0.1",
        "curl https://localhost/health",
        "kubectl get pods -n kube-system",
        "kubectl describe pod coredns-abc123",
        "kubectl logs nginx-pod-xyz",
        "kubectl top nodes",
        "systemctl status nginx",
        "systemctl is-active nginx",
        "systemctl list-units --type=service",
        "journalctl -u nginx --since '1 hour ago'",
        "dmesg",
        "docker ps",
        "docker logs container123",
        "docker inspect container123",
    ])
    def test_green_commands(self, classifier, command):
        result = classifier.classify(command)
        assert result.tier == RiskTier.GREEN, f"Expected GREEN for: {command}, got {result.tier}"

    # ── YELLOW (modification) ──

    @pytest.mark.parametrize("command", [
        "systemctl restart nginx",
        "systemctl stop postgresql",
        "systemctl start rabbitmq-server",
        "systemctl enable nginx",
        "systemctl disable cups",
        "kubectl apply -f deploy/",
        "kubectl scale deployment nginx --replicas=3",
        "kubectl rollout restart deployment nginx",
        "kubectl edit configmap my-config",
        "kubectl patch deployment nginx -p '{}'",
        "kubectl delete pod nginx-abc123",
        "cp /etc/nginx/nginx.conf /tmp/backup",
        "mv /tmp/file.txt /var/data/",
        "mkdir -p /opt/newdir",
        "chmod 644 /etc/nginx/nginx.conf",
        "chown www-data:www-data /var/www/html",
        "sed -i 's/old/new/g' /etc/config.conf",
        "tee /tmp/output.txt",
        "echo 'data' >> /var/log/custom.log",
        "docker stop container123",
        "docker restart container123",
        "apt install nginx",
        "pip install requests",
    ])
    def test_yellow_commands(self, classifier, command):
        result = classifier.classify(command)
        assert result.tier == RiskTier.YELLOW, f"Expected YELLOW for: {command}, got {result.tier}"

    # ── RED (destructive) ──

    @pytest.mark.parametrize("command", [
        "rm /tmp/file.txt",
        "rm -rf /var/data/old/",
        "rmdir /opt/empty",
        "kubectl delete deployment nginx",
        "kubectl delete namespace testing",
        "kubectl delete service my-svc",
        "kubectl delete pvc data-volume",
        "kubectl drain worker-01",
        "systemctl mask nginx",
        "systemctl daemon-reload",
        "mkfs.ext4 /dev/sdb1",
        "dd if=/dev/zero of=/dev/sdb bs=1M",
        "iptables -A INPUT -j DROP",
        "reboot",
        "shutdown -h now",
        "poweroff",
        "docker rm container123",
        "docker rmi nginx:latest",
        "docker system prune",
        "docker volume rm data_vol",
        "apt remove nginx",
        "apt purge nginx",
        "pip uninstall requests",
    ])
    def test_red_commands(self, classifier, command):
        result = classifier.classify(command)
        assert result.tier == RiskTier.RED, f"Expected RED for: {command}, got {result.tier}"

    # ── Pipe chains ──

    def test_pipe_green_green(self, classifier):
        result = classifier.classify("ps aux | grep nginx")
        assert result.tier == RiskTier.GREEN

    def test_pipe_green_red(self, classifier):
        """Pipe containing destructive command should be RED."""
        result = classifier.classify("find /tmp -name '*.log' | rm")
        # The rm at the end makes this RED
        assert result.tier == RiskTier.RED

    # ── Unknown commands default to YELLOW ──

    def test_unknown_command_defaults_yellow(self, classifier):
        result = classifier.classify("some-custom-script --flag")
        assert result.tier == RiskTier.YELLOW

    # ── Explanation ──

    def test_explanation_present(self, classifier):
        result = classifier.classify("systemctl restart nginx")
        assert "nginx" in result.explanation.lower() or "restart" in result.explanation.lower()

    def test_rollback_suggestion(self, classifier):
        result = classifier.classify("systemctl stop nginx")
        assert result.rollback_command is not None
        assert "start" in result.rollback_command


class TestRiskEngine:
    @pytest.mark.asyncio
    async def test_green_auto_executes(self, risk_engine):
        result = await risk_engine.execute("echo hello")
        # echo is unknown → YELLOW, but let's test with a known green command
        result = await risk_engine.execute("hostname")
        assert result.return_code == 0
        assert result.approved is True

    @pytest.mark.asyncio
    async def test_yellow_requires_approval(self, risk_engine):
        """YELLOW command without callback returns denied."""
        result = await risk_engine.execute("systemctl restart nginx")
        assert result.approved is False
        assert result.return_code == -1

    @pytest.mark.asyncio
    async def test_yellow_with_approval(self, risk_engine):
        """YELLOW command with approval callback that approves."""
        callback = AsyncMock(return_value=True)
        result = await risk_engine.execute("mkdir -p /tmp/sv_test_dir", approval_callback=callback)
        assert result.approved is True
        callback.assert_called_once()

    @pytest.mark.asyncio
    async def test_yellow_denied(self, risk_engine):
        """YELLOW command with approval callback that denies."""
        callback = AsyncMock(return_value=False)
        result = await risk_engine.execute("systemctl restart nginx", approval_callback=callback)
        assert result.approved is False
        assert "denied" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_red_requires_approval(self, risk_engine):
        """RED command without callback returns denied."""
        result = await risk_engine.execute("rm -rf /tmp/test")
        assert result.approved is False

    @pytest.mark.asyncio
    async def test_execution_log(self, risk_engine):
        await risk_engine.execute("hostname")
        log = risk_engine.get_recent_executions(10)
        assert len(log) >= 1
        assert log[-1].command == "hostname"

    @pytest.mark.asyncio
    async def test_timeout(self, risk_engine):
        callback = AsyncMock(return_value=True)
        result = await risk_engine.execute("sleep 10", approval_callback=callback, timeout=1)
        assert result.return_code == -1
        assert "timed out" in result.stderr.lower()

    @pytest.mark.asyncio
    async def test_duration_tracked(self, risk_engine):
        result = await risk_engine.execute("hostname")
        assert result.duration_ms >= 0
