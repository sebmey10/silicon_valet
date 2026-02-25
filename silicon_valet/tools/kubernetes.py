"""Kubernetes tools — kubectl wrappers routed through the risk engine."""

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


def _exec(command, engine, callback, timeout=30):
    with concurrent.futures.ThreadPoolExecutor() as pool:
        return pool.submit(
            lambda: asyncio.new_event_loop().run_until_complete(
                engine.execute(command=command, approval_callback=callback, timeout=timeout)
            )
        ).result()


@register_tool("kubectl_get")
class KubectlGetTool(BaseTool):
    description = "Get Kubernetes resources."
    parameters = [
        {"name": "resource", "type": "string", "description": "Resource type (pods, services, deployments, etc.).", "required": True},
        {"name": "namespace", "type": "string", "description": "Namespace (default: all).", "required": False},
        {"name": "name", "type": "string", "description": "Specific resource name.", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        cmd = f"kubectl get {parsed['resource']}"
        if parsed.get("name"):
            cmd += f" {parsed['name']}"
        if parsed.get("namespace"):
            cmd += f" -n {parsed['namespace']}"
        else:
            cmd += " -A"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("kubectl_describe")
class KubectlDescribeTool(BaseTool):
    description = "Describe a Kubernetes resource in detail."
    parameters = [
        {"name": "resource", "type": "string", "description": "Resource type.", "required": True},
        {"name": "name", "type": "string", "description": "Resource name.", "required": True},
        {"name": "namespace", "type": "string", "description": "Namespace.", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        cmd = f"kubectl describe {parsed['resource']} {parsed['name']}"
        if parsed.get("namespace"):
            cmd += f" -n {parsed['namespace']}"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("kubectl_logs")
class KubectlLogsTool(BaseTool):
    description = "Get logs from a Kubernetes pod."
    parameters = [
        {"name": "pod", "type": "string", "description": "Pod name.", "required": True},
        {"name": "namespace", "type": "string", "description": "Namespace.", "required": False},
        {"name": "lines", "type": "integer", "description": "Number of lines (default 100).", "required": False},
        {"name": "container", "type": "string", "description": "Container name.", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        cmd = f"kubectl logs {parsed['pod']} --tail={parsed.get('lines', 100)}"
        if parsed.get("namespace"):
            cmd += f" -n {parsed['namespace']}"
        if parsed.get("container"):
            cmd += f" -c {parsed['container']}"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"logs": result.stdout, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("kubectl_apply")
class KubectlApplyTool(BaseTool):
    description = "Apply a Kubernetes manifest (requires confirmation)."
    parameters = [
        {"name": "path", "type": "string", "description": "Path to manifest file.", "required": True},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        result = _exec(f"kubectl apply -f {parsed['path']}", self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "stderr": result.stderr, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("kubectl_delete")
class KubectlDeleteTool(BaseTool):
    description = "Delete a Kubernetes resource (destructive — requires explicit confirmation)."
    parameters = [
        {"name": "resource", "type": "string", "description": "Resource type.", "required": True},
        {"name": "name", "type": "string", "description": "Resource name.", "required": True},
        {"name": "namespace", "type": "string", "description": "Namespace.", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        cmd = f"kubectl delete {parsed['resource']} {parsed['name']}"
        if parsed.get("namespace"):
            cmd += f" -n {parsed['namespace']}"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "stderr": result.stderr, "return_code": result.return_code}, ensure_ascii=False)


@register_tool("kubectl_scale")
class KubectlScaleTool(BaseTool):
    description = "Scale a Kubernetes deployment (requires confirmation)."
    parameters = [
        {"name": "deployment", "type": "string", "description": "Deployment name.", "required": True},
        {"name": "replicas", "type": "integer", "description": "Target replica count.", "required": True},
        {"name": "namespace", "type": "string", "description": "Namespace.", "required": False},
    ]
    _risk_engine = None
    _approval_callback = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        cmd = f"kubectl scale deployment {parsed['deployment']} --replicas={parsed['replicas']}"
        if parsed.get("namespace"):
            cmd += f" -n {parsed['namespace']}"
        result = _exec(cmd, self._risk_engine, self._approval_callback)
        return json.dumps({"output": result.stdout, "return_code": result.return_code}, ensure_ascii=False)
