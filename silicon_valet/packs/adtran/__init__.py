"""Adtran domain pack — NetVanta, Total Access, AOS runbooks."""

from __future__ import annotations

import logging

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack

logger = logging.getLogger(__name__)


class Pack(BasePack):
    name = "adtran"
    version = "1.0"
    description = "Adtran network devices: NetVanta, Total Access, AOS"

    def detect(self, dna: DNAStore) -> bool:
        import os
        if os.getenv("SV_ENABLE_ADTRAN", "").lower() in ("1", "true", "yes"):
            return True
        try:
            from silicon_valet.tools.netdevice import load_inventory
            inv = load_inventory()
            for entry in inv.values():
                plat = (entry.get("platform") or entry.get("device_type") or "").lower()
                if plat.startswith("adtran"):
                    return True
        except Exception as e:
            logger.debug("adtran pack detect failed: %s", e)
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
                title="Adtran AOS interface down",
                problem_pattern="Adtran NetVanta/TA interface in a down state",
                symptoms=[
                    "show interfaces reports administratively down or line protocol down",
                    "No traffic on customer port",
                ],
                steps=[
                    {"action": "check", "command": "show interfaces", "explanation": "Overview of all interfaces", "risk_tier": "green"},
                    {"action": "check", "command": "show interfaces {interface}", "explanation": "Interface detail", "risk_tier": "green"},
                    {"action": "check", "command": "show logging", "explanation": "Recent events", "risk_tier": "green"},
                    {"action": "fix", "command": "interface {interface}\nno shutdown", "explanation": "Enable the interface", "risk_tier": "yellow"},
                ],
                root_cause="Admin shut, cable/SFP issue, or far-end down",
                verification="show interfaces {interface} reports 'up/up'",
                tags=["adtran", "aos", "interface"],
                pack_source="adtran",
            ),
            RunbookEntry(
                title="Adtran AOS save config after change",
                problem_pattern="Config changes lost after reload on Adtran device",
                symptoms=[
                    "Changes applied in running-config but missing after reboot",
                ],
                steps=[
                    {"action": "check", "command": "show running-config", "explanation": "View current config", "risk_tier": "green"},
                    {"action": "check", "command": "show startup-config", "explanation": "View saved config", "risk_tier": "green"},
                    {"action": "fix", "command": "write", "explanation": "Persist running-config to startup-config", "risk_tier": "yellow"},
                ],
                root_cause="Config not saved before reload",
                verification="show startup-config matches show running-config",
                tags=["adtran", "aos", "config", "save"],
                pack_source="adtran",
            ),
            RunbookEntry(
                title="Adtran DSL/GPON subscriber offline",
                problem_pattern="Customer on an Adtran access device reporting offline",
                symptoms=[
                    "Subscriber session not present on the BNG",
                    "ONT/modem reporting loss-of-signal",
                ],
                steps=[
                    {"action": "check", "command": "show interfaces {interface}", "explanation": "Port layer-1 status", "risk_tier": "green"},
                    {"action": "check", "command": "show gpon onu info all 2>/dev/null", "explanation": "ONU registration state (GPON)", "risk_tier": "green"},
                    {"action": "check", "command": "show pppoe sessions 2>/dev/null", "explanation": "PPPoE sessions if applicable", "risk_tier": "green"},
                    {"action": "check", "command": "show logging | include {subscriber}", "explanation": "Log entries for this subscriber", "risk_tier": "green"},
                ],
                root_cause="Physical fiber/copper issue, ONU not provisioned, or auth failure upstream",
                verification="Subscriber session re-established and traffic flowing",
                tags=["adtran", "gpon", "subscriber", "access"],
                pack_source="adtran",
            ),
            RunbookEntry(
                title="Adtran OSPF neighbor flapping",
                problem_pattern="OSPF neighbor on an Adtran router keeps cycling INIT/FULL",
                symptoms=[
                    "show ip ospf neighbor shows frequent state transitions",
                    "Routing convergence events in syslog",
                ],
                steps=[
                    {"action": "check", "command": "show ip ospf neighbor", "explanation": "Neighbor states", "risk_tier": "green"},
                    {"action": "check", "command": "show ip ospf interface {interface}", "explanation": "Hello/dead timers, MTU", "risk_tier": "green"},
                    {"action": "check", "command": "show ip interface {interface}", "explanation": "Interface IP/MTU", "risk_tier": "green"},
                ],
                root_cause="MTU mismatch, timer mismatch, authentication mismatch",
                verification="show ip ospf neighbor stable at FULL for at least 5 minutes",
                tags=["adtran", "ospf", "routing"],
                pack_source="adtran",
            ),
        ]
