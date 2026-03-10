"""Web server domain pack — nginx, Apache, SSL, reverse proxy diagnostics."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "webserver"
    version = "1.0"
    description = "Web server management: nginx, Apache, SSL certificates, reverse proxy"

    def detect(self, dna: DNAStore) -> bool:
        services = dna.get_all_services()
        web_names = {"nginx", "apache2", "httpd", "caddy", "lighttpd"}
        return any(s.name in web_names for s in services)

    def get_tools(self) -> list[type]:
        return []

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="502 Bad Gateway",
                problem_pattern="Web server returning 502 Bad Gateway errors",
                symptoms=[
                    "Users see 502 Bad Gateway in browser",
                    "Upstream backend is unreachable from the web server",
                    "Error logs show 'upstream prematurely closed connection'",
                ],
                steps=[
                    {"action": "check", "command": "systemctl status nginx 2>/dev/null || systemctl status apache2", "explanation": "Check web server status", "risk_tier": "green"},
                    {"action": "check", "command": "tail -50 /var/log/nginx/error.log 2>/dev/null || tail -50 /var/log/apache2/error.log", "explanation": "Check web server error logs", "risk_tier": "green"},
                    {"action": "check", "command": "ss -tlnp | grep -E ':(80|443|8080|3000|8000)'", "explanation": "Check if backend ports are listening", "risk_tier": "green"},
                    {"action": "check", "command": "nginx -t 2>&1 || apachectl configtest 2>&1", "explanation": "Test web server configuration", "risk_tier": "green"},
                    {"action": "fix", "command": "systemctl restart nginx 2>/dev/null || systemctl restart apache2", "explanation": "Restart web server", "risk_tier": "yellow"},
                ],
                root_cause="Backend service crashed, port mismatch, or web server misconfiguration",
                verification="curl -I http://localhost returns 200 OK",
                tags=["webserver", "nginx", "apache", "502", "gateway"],
                pack_source="webserver",
            ),
            RunbookEntry(
                title="SSL certificate expiring or expired",
                problem_pattern="HTTPS not working due to expired or about-to-expire SSL certificate",
                symptoms=[
                    "Browser shows certificate warning or error",
                    "curl reports SSL certificate problem",
                    "Certbot renewal failed",
                ],
                steps=[
                    {"action": "check", "command": "echo | openssl s_client -connect localhost:443 2>/dev/null | openssl x509 -noout -dates", "explanation": "Check certificate expiry dates", "risk_tier": "green"},
                    {"action": "check", "command": "ls -la /etc/letsencrypt/live/ 2>/dev/null", "explanation": "List Let's Encrypt certificates", "risk_tier": "green"},
                    {"action": "check", "command": "certbot certificates 2>/dev/null", "explanation": "Check certbot certificate status", "risk_tier": "green"},
                    {"action": "check", "command": "systemctl status certbot.timer 2>/dev/null", "explanation": "Check auto-renewal timer", "risk_tier": "green"},
                    {"action": "fix", "command": "certbot renew --dry-run", "explanation": "Test certificate renewal", "risk_tier": "yellow"},
                ],
                root_cause="Auto-renewal failed, certbot misconfigured, or DNS validation issue",
                verification="openssl shows valid certificate with future expiry date",
                tags=["ssl", "tls", "certificate", "https", "certbot"],
                pack_source="webserver",
            ),
            RunbookEntry(
                title="Web server config test failure",
                problem_pattern="Web server refuses to start or reload due to configuration error",
                symptoms=[
                    "nginx -t or apachectl configtest reports errors",
                    "Web server won't start after config change",
                    "systemctl status shows 'failed'",
                ],
                steps=[
                    {"action": "check", "command": "nginx -t 2>&1 || apachectl configtest 2>&1", "explanation": "Run config test to see exact error", "risk_tier": "green"},
                    {"action": "check", "command": "ls -la /etc/nginx/sites-enabled/ 2>/dev/null || ls -la /etc/apache2/sites-enabled/", "explanation": "List enabled sites", "risk_tier": "green"},
                    {"action": "check", "command": "journalctl -u nginx --no-pager -n 30 2>/dev/null || journalctl -u apache2 --no-pager -n 30", "explanation": "Check recent logs", "risk_tier": "green"},
                ],
                root_cause="Syntax error in config file, missing included file, or duplicate server_name",
                verification="nginx -t returns 'syntax is ok' and 'test is successful'",
                tags=["webserver", "nginx", "apache", "config"],
                pack_source="webserver",
            ),
        ]
