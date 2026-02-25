"""Kubernetes domain pack — pod health, resource pressure, log tailing, deployment status."""

from __future__ import annotations

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack


class Pack(BasePack):
    name = "kubernetes"
    version = "1.0"
    description = "Kubernetes cluster management, pod health, resource monitoring, deployments"

    def detect(self, dna: DNAStore) -> bool:
        # Check if any k8s services exist in DNA
        services = dna.get_all_services()
        return any(s.type.startswith("k8s_") for s in services)

    def get_tools(self) -> list[type]:
        return []  # Core k8s tools are in tools/kubernetes.py

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Pod stuck in CrashLoopBackOff",
                problem_pattern="Pod keeps crashing and restarting in CrashLoopBackOff state",
                symptoms=[
                    "kubectl get pods shows CrashLoopBackOff status",
                    "Pod restart count increasing",
                    "Application not accessible",
                ],
                steps=[
                    {"action": "check", "command": "kubectl get pods -A | grep -i crash", "explanation": "Find crashing pods", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl describe pod {pod_name} -n {namespace}", "explanation": "Get pod events and details", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl logs {pod_name} -n {namespace} --previous", "explanation": "Check previous container logs", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl get events -n {namespace} --sort-by=.lastTimestamp", "explanation": "Check recent events", "risk_tier": "green"},
                ],
                root_cause="Application crash, missing config/secrets, resource limits, or image pull failure",
                verification="Pod reaches Running state and stays running for >5 minutes",
                tags=["kubernetes", "pods", "crashloop"],
                pack_source="kubernetes",
            ),
            RunbookEntry(
                title="Node resource pressure",
                problem_pattern="Node showing memory or disk pressure, pods being evicted",
                symptoms=[
                    "kubectl describe node shows MemoryPressure or DiskPressure",
                    "Pods being evicted from the node",
                    "New pods stuck in Pending state",
                ],
                steps=[
                    {"action": "check", "command": "kubectl top nodes", "explanation": "Check node resource usage", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl describe node {node_name} | grep -A5 Conditions", "explanation": "Check node conditions", "risk_tier": "green"},
                    {"action": "check", "command": "kubectl top pods -A --sort-by=memory", "explanation": "Find memory-hungry pods", "risk_tier": "green"},
                    {"action": "check", "command": "df -h", "explanation": "Check disk usage", "risk_tier": "green"},
                ],
                root_cause="Insufficient resources on the node for running workloads",
                verification="Node conditions show no pressure warnings",
                tags=["kubernetes", "resources", "pressure", "eviction"],
                pack_source="kubernetes",
            ),
        ]
