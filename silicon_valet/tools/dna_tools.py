"""DNA query tools — query the Infrastructure DNA store directly."""

from __future__ import annotations

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


@register_tool("query_dna")
class QueryDNATool(BaseTool):
    description = "Query the Infrastructure DNA for environment information."
    parameters = [
        {"name": "query", "type": "string", "description": "What to look up (e.g., 'services on worker-01', 'port 8080').", "required": True},
    ]
    _dna_store = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        query = parsed.get("query", "").lower()
        store = self._dna_store
        if store is None:
            return json.dumps({"error": "DNA store not initialized."})

        # Simple keyword routing to store methods
        if "port" in query:
            for word in query.split():
                if word.isdigit():
                    svc = store.get_service_by_port(int(word))
                    if svc:
                        return json.dumps({"port": int(word), "service": svc.to_dict()})
                    return json.dumps({"port": int(word), "service": None})
            return json.dumps({"ports": store.get_listening_ports()[:20]})

        if "service" in query or "running" in query:
            services = store.search_services(query.replace("services", "").replace("running", "").strip())
            if not services:
                services = store.get_all_services()
            return json.dumps({"services": [s.to_dict() for s in services[:20]]})

        if "node" in query:
            for word in query.split():
                node = store.get_node(word)
                if node:
                    svcs = store.get_services_on_node(word)
                    return json.dumps({"node": node.to_dict(), "services": [s.to_dict() for s in svcs]})
            return json.dumps({"nodes": [n.to_dict() for n in store.get_all_nodes()]})

        if "change" in query:
            changes = store.get_changes_since(hours=24)
            return json.dumps({"changes": [c.to_dict() for c in changes[:20]]})

        return json.dumps({"summary": store.get_context_summary()})


@register_tool("list_services")
class ListServicesTool(BaseTool):
    description = "List services, optionally filtered by node or status."
    parameters = [
        {"name": "node", "type": "string", "description": "Filter by node hostname.", "required": False},
        {"name": "status", "type": "string", "description": "Filter by status (running, stopped, etc.).", "required": False},
    ]
    _dna_store = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        store = self._dna_store
        if parsed.get("node"):
            services = store.get_services_on_node(parsed["node"])
        else:
            services = store.get_all_services()
        if parsed.get("status"):
            services = [s for s in services if s.status == parsed["status"]]
        return json.dumps({"services": [s.to_dict() for s in services]}, ensure_ascii=False)


@register_tool("show_ports")
class ShowPortsTool(BaseTool):
    description = "Show all listening ports and their associated services."
    parameters = []
    _dna_store = None

    def call(self, params: str = "{}", **kwargs) -> str:
        return json.dumps({"ports": self._dna_store.get_listening_ports()}, ensure_ascii=False)


@register_tool("show_changes")
class ShowChangesTool(BaseTool):
    description = "Show recent infrastructure changes."
    parameters = [
        {"name": "hours", "type": "integer", "description": "Lookback period in hours (default 24).", "required": False},
    ]
    _dna_store = None

    def call(self, params: str = "{}", **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        hours = parsed.get("hours", 24) if isinstance(parsed, dict) else 24
        changes = self._dna_store.get_changes_since(hours=hours)
        return json.dumps({"changes": [c.to_dict() for c in changes]}, ensure_ascii=False)
