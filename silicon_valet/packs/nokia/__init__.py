"""Nokia domain pack — SR OS (7x50), SR Linux, and ISAM DSLAM runbooks."""

from __future__ import annotations

import logging

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack

logger = logging.getLogger(__name__)


class Pack(BasePack):
    name = "nokia"
    version = "1.0"
    description = "Nokia network devices: SR OS, SR Linux, ISAM DSLAM"

    def detect(self, dna: DNAStore) -> bool:
        import os
        if os.getenv("SV_ENABLE_NOKIA", "").lower() in ("1", "true", "yes"):
            return True
        try:
            from silicon_valet.tools.netdevice import load_inventory
            inv = load_inventory()
            for entry in inv.values():
                plat = (entry.get("platform") or entry.get("device_type") or "").lower()
                if plat.startswith("nokia"):
                    return True
        except Exception as e:
            logger.debug("nokia pack detect failed: %s", e)
        return False

    def get_tools(self) -> list[type]:
        from silicon_valet.tools.netdevice import (
            NetDeviceShowTool,
            NetDeviceConfigTool,
            NetDeviceFingerprintTool,
            NetDeviceListInventoryTool,
        )
        return [
            NetDeviceShowTool,
            NetDeviceConfigTool,
            NetDeviceFingerprintTool,
            NetDeviceListInventoryTool,
        ]

    def get_runbook_seeds(self) -> list[RunbookEntry]:
        return [
            RunbookEntry(
                title="Nokia SR OS port admin-down",
                problem_pattern="Nokia SR OS port appears down; subscribers on that port offline",
                symptoms=[
                    "show port reports 'down/down'",
                    "No LLDP neighbor",
                    "Subscriber sessions dropping",
                ],
                steps=[
                    {"action": "check", "command": "show port", "explanation": "Summary of every port", "risk_tier": "green"},
                    {"action": "check", "command": "show port {port} detail", "explanation": "Full status + counters for the port", "risk_tier": "green"},
                    {"action": "check", "command": "show log log-id 99", "explanation": "Check system event log for link events", "risk_tier": "green"},
                    {"action": "fix", "command": "configure port {port} no shutdown", "explanation": "Bring the port up administratively", "risk_tier": "yellow"},
                ],
                root_cause="Port administratively shut, SFP fault, or peer-side down",
                verification="show port {port} shows 'up/up'",
                tags=["nokia", "sros", "port", "layer1"],
                pack_source="nokia",
            ),
            RunbookEntry(
                title="Nokia SR OS service (VPLS/VPRN) not forwarding",
                problem_pattern="L2 or L3 VPN service built but customer traffic not passing",
                symptoms=[
                    "SAP shows oper-state down",
                    "MAC table empty on VPLS",
                    "VPRN route-table missing expected prefixes",
                ],
                steps=[
                    {"action": "check", "command": "show service service-using", "explanation": "List services on this node", "risk_tier": "green"},
                    {"action": "check", "command": "show service id {svc_id} base", "explanation": "Base service state", "risk_tier": "green"},
                    {"action": "check", "command": "show service id {svc_id} sap", "explanation": "SAP admin/oper state", "risk_tier": "green"},
                    {"action": "check", "command": "show service id {svc_id} sdp", "explanation": "SDP bindings (for mesh services)", "risk_tier": "green"},
                    {"action": "check", "command": "show service id {svc_id} fdb detail", "explanation": "VPLS MAC table", "risk_tier": "green"},
                ],
                root_cause="SAP admin-down, SDP down, MTU mismatch, or encap-value mismatch",
                verification="show service id {svc_id} base reports oper-state up and traffic counters incrementing",
                tags=["nokia", "sros", "vpls", "vprn", "service"],
                pack_source="nokia",
            ),
            RunbookEntry(
                title="Nokia SR OS IS-IS adjacency down",
                problem_pattern="IS-IS neighbor not forming or stuck in INIT",
                symptoms=[
                    "show router isis adjacency reports neighbor missing or in INIT",
                    "LSDB incomplete",
                ],
                steps=[
                    {"action": "check", "command": "show router isis adjacency", "explanation": "Neighbor states", "risk_tier": "green"},
                    {"action": "check", "command": "show router isis interface", "explanation": "Interface level/authentication", "risk_tier": "green"},
                    {"action": "check", "command": "show router interface", "explanation": "Verify IP + system IP reachability", "risk_tier": "green"},
                ],
                root_cause="MTU mismatch, area/level mismatch, authentication mismatch, or interface passive",
                verification="show router isis adjacency reports 'Up' for the neighbor",
                tags=["nokia", "sros", "isis", "routing"],
                pack_source="nokia",
            ),
            RunbookEntry(
                title="Nokia SR OS high CPU / control-plane",
                problem_pattern="SR OS CPM / control-plane reporting high CPU utilization",
                symptoms=[
                    "show system cpu reports elevated values",
                    "Slow CLI response",
                    "BGP or IS-IS flaps without clear L1 cause",
                ],
                steps=[
                    {"action": "check", "command": "show system cpu", "explanation": "CPU summary", "risk_tier": "green"},
                    {"action": "check", "command": "show system memory-pools", "explanation": "Memory health", "risk_tier": "green"},
                    {"action": "check", "command": "show system cpu-usage", "explanation": "Per-process breakdown", "risk_tier": "green"},
                    {"action": "check", "command": "show log log-id 99 | match CRITICAL", "explanation": "Critical events in syslog", "risk_tier": "green"},
                ],
                root_cause="Control-plane flood, CPM filter missing, or route churn",
                verification="show system cpu drops back to baseline; BGP/IS-IS stable for 10 minutes",
                tags=["nokia", "sros", "cpu", "performance"],
                pack_source="nokia",
            ),
            RunbookEntry(
                title="Nokia SR Linux interface diagnostic",
                problem_pattern="SR Linux interface not forwarding expected traffic",
                symptoms=[
                    "info from state interface {name} shows admin-state enable but oper-state down",
                    "Peers unreachable via that interface",
                ],
                steps=[
                    {"action": "check", "command": "info from state interface {name}", "explanation": "Full interface state (YANG)", "risk_tier": "green"},
                    {"action": "check", "command": "info from state interface {name} statistics", "explanation": "Counter deltas", "risk_tier": "green"},
                    {"action": "check", "command": "show network-instance default route-table ipv4-unicast", "explanation": "Route table for default NI", "risk_tier": "green"},
                ],
                root_cause="Admin disable on subinterface, wrong encapsulation, MTU mismatch",
                verification="oper-state reports 'up' and counters increment",
                tags=["nokia", "srlinux", "interface"],
                pack_source="nokia",
            ),
        ]
