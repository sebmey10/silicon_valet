"""Network tools — ping, port check, DNS, curl, traceroute."""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging

try:
    from qwen_agent.tools.base import BaseTool, register_tool
except ImportError:
    def register_tool(name):
        def decorator(cls):
            cls._tool_name = name
            return cls
        return decorator
    class BaseTool:
        description = ""
        parameters = []
        def call(self, params, **kwargs): raise NotImplementedError

try:
    import json5
except ImportError:
    import json as json5

logger = logging.getLogger(__name__)


def _exec(command, engine, callback):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(
            lambda: asyncio.new_event_loop().run_until_complete(
                engine.execute(command=command, approval_callback=callback, timeout=30)
            )
        ).result()


@register_tool("ping_host")
class PingHostTool(BaseTool):
    description = "Ping a host to check connectivity."
    parameters = [
        {"name": "host", "type": "string", "description": "Host to ping.", "required": True},
        {"name": "count", "type": "integer", "description": "Number of pings (default 3).", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        count = parsed.get("count", 3)
        result = _exec(f"ping -c {count} {parsed['host']}", self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "success": result.return_code == 0}, ensure_ascii=False)


@register_tool("check_port")
class CheckPortTool(BaseTool):
    description = "Check if a port is open on a host."
    parameters = [
        {"name": "host", "type": "string", "description": "Host to check.", "required": True},
        {"name": "port", "type": "integer", "description": "Port number.", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        result = _exec(f"ss -tlnp | grep :{parsed['port']}", self._risk_engine, self._approval_callback)
        is_open = result.return_code == 0 and result.stdout.strip() != ""
        return json.dumps({"port": parsed["port"], "open": is_open, "detail": result.stdout.strip()}, ensure_ascii=False)


@register_tool("dns_lookup")
class DnsLookupTool(BaseTool):
    description = "Perform a DNS lookup."
    parameters = [
        {"name": "domain", "type": "string", "description": "Domain to look up.", "required": True},
        {"name": "record_type", "type": "string", "description": "Record type (default A).", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        rtype = parsed.get("record_type", "A")
        result = _exec(f"dig {parsed['domain']} {rtype} +short", self._risk_engine, self._approval_callback)
        return json.dumps({"domain": parsed["domain"], "type": rtype, "result": result.stdout.strip()}, ensure_ascii=False)


@register_tool("curl_request")
class CurlRequestTool(BaseTool):
    description = "Make an HTTP request."
    parameters = [
        {"name": "url", "type": "string", "description": "URL to request.", "required": True},
        {"name": "method", "type": "string", "description": "HTTP method (default GET).", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        method = parsed.get("method", "GET").upper()
        cmd = f"curl -s -o /dev/null -w '%{{http_code}}' -X {method} {parsed['url']}"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"url": parsed["url"], "method": method, "status_code": result.stdout.strip(), "success": result.return_code == 0}, ensure_ascii=False)


@register_tool("trace_route")
class TraceRouteTool(BaseTool):
    description = "Trace the network route to a host."
    parameters = [
        {"name": "host", "type": "string", "description": "Host to trace.", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        result = _exec(f"traceroute -m 15 {parsed['host']}", self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "success": result.return_code == 0}, ensure_ascii=False)
