"""Cisco domain pack — IOS, IOS-XE, NX-OS, IOS-XR, ASA runbooks and device tools."""

from __future__ import annotations

import logging
from pathlib import Path

from silicon_valet.dna.store import DNAStore
from silicon_valet.memory.procedural import RunbookEntry
from silicon_valet.packs.base import BasePack

logger = logging.getLogger(__name__)


class Pack(BasePack):
    name = "cisco"
    version = "1.0"
    description = "Cisco network devices: IOS, IOS-XE, NX-OS, IOS-XR, ASA"

    def detect(self, dna: DNAStore) -> bool:
        # Activate whenever there's an inventory file with any Cisco device,
        # or when an env var explicitly enables it.
        import os
        if os.getenv("SV_ENABLE_CISCO", "").lower() in ("1", "true", "yes"):
            return True
        try:
            from silicon_valet.tools.netdevice import load_inventory
            inv = load_inventory()
            for entry in inv.values():
                plat = (entry.get("platform") or entry.get("device_type") or "").lower()
                if plat.startswith("cisco"):
                    return True
        except Exception as e:
            logger.debug("cisco pack detect failed: %s", e)
        return False

    def get_tools(self) -> list[type]:
        # netdevice tools are shared across all net-device packs; importing
        # here ensures they get registered when any pack activates.
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
                title="Cisco interface down",
                problem_pattern="A Cisco switch/router interface is reported down or not passing traffic",
                symptoms=[
                    "show interface status shows 'notconnect' or 'disabled'",
                    "show interface <if> line protocol is down",
                    "Neighbors not appearing in CDP/LLDP",
                ],
                steps=[
                    {"action": "check", "command": "show interface status", "explanation": "List all interface states", "risk_tier": "green"},
                    {"action": "check", "command": "show interface {interface}", "explanation": "Detailed status for the specific interface", "risk_tier": "green"},
                    {"action": "check", "command": "show interface {interface} counters errors", "explanation": "Check for CRC / input errors", "risk_tier": "green"},
                    {"action": "check", "command": "show logging | include {interface}", "explanation": "Look for link-flap log entries", "risk_tier": "green"},
                    {"action": "fix", "command": "interface {interface}\nno shutdown", "explanation": "Bring the interface up", "risk_tier": "yellow"},
                ],
                root_cause="Interface administratively down, cable/SFP issue, duplex mismatch, or err-disable",
                verification="show interface {interface} reports 'up/up' and CDP neighbor reappears",
                tags=["cisco", "ios", "interface", "layer1"],
                pack_source="cisco",
            ),
            RunbookEntry(
                title="Cisco OSPF neighbor not forming",
                problem_pattern="OSPF neighbor stuck in INIT/EXSTART/2WAY, not reaching FULL",
                symptoms=[
                    "show ip ospf neighbor shows state < FULL",
                    "LSAs not propagating",
                    "Adjacency flaps repeatedly",
                ],
                steps=[
                    {"action": "check", "command": "show ip ospf neighbor", "explanation": "Current OSPF neighbor states", "risk_tier": "green"},
                    {"action": "check", "command": "show ip ospf interface {interface}", "explanation": "Verify timers, area, network type, MTU", "risk_tier": "green"},
                    {"action": "check", "command": "show ip interface {interface}", "explanation": "Check IP, MTU, secondary addresses", "risk_tier": "green"},
                    {"action": "check", "command": "debug ip ospf adj", "explanation": "Watch adjacency negotiation (noisy — remember to 'undebug all')", "risk_tier": "yellow"},
                ],
                root_cause="MTU mismatch, area mismatch, timer mismatch, authentication mismatch, or network-type mismatch",
                verification="show ip ospf neighbor reports FULL on both ends",
                tags=["cisco", "ios", "ospf", "routing"],
                pack_source="cisco",
            ),
            RunbookEntry(
                title="Cisco high CPU",
                problem_pattern="Cisco device reporting sustained high CPU",
                symptoms=[
                    "show processes cpu shows >80% sustained",
                    "Control plane packets dropped",
                    "SSH sessions sluggish",
                ],
                steps=[
                    {"action": "check", "command": "show processes cpu sorted | exclude 0.00", "explanation": "Top CPU-consuming processes", "risk_tier": "green"},
                    {"action": "check", "command": "show processes cpu history", "explanation": "CPU trend over the last hour", "risk_tier": "green"},
                    {"action": "check", "command": "show ip traffic", "explanation": "Punt traffic volume", "risk_tier": "green"},
                    {"action": "check", "command": "show platform punt-policer 2>/dev/null || show platform software infrastructure punt", "explanation": "Punt policer stats (IOS-XE)", "risk_tier": "green"},
                ],
                root_cause="Control-plane flood (ARP, BPDU, routing), process-switching instead of CEF, or buggy feature",
                verification="show processes cpu returns to baseline (<30%)",
                tags=["cisco", "cpu", "performance"],
                pack_source="cisco",
            ),
            RunbookEntry(
                title="Cisco VLAN / trunk mismatch",
                problem_pattern="Devices on same VLAN cannot reach each other across switches",
                symptoms=[
                    "Hosts in VLAN X reachable on one switch but not another",
                    "show interface trunk missing the VLAN",
                    "Spanning tree blocking unexpectedly",
                ],
                steps=[
                    {"action": "check", "command": "show vlan brief", "explanation": "List VLANs on this switch", "risk_tier": "green"},
                    {"action": "check", "command": "show interface trunk", "explanation": "VLANs allowed on each trunk", "risk_tier": "green"},
                    {"action": "check", "command": "show spanning-tree vlan {vlan}", "explanation": "STP state for the VLAN", "risk_tier": "green"},
                    {"action": "check", "command": "show mac address-table vlan {vlan}", "explanation": "MAC table for the VLAN", "risk_tier": "green"},
                    {"action": "fix", "command": "interface {trunk}\nswitchport trunk allowed vlan add {vlan}", "explanation": "Add VLAN to the trunk's allowed list", "risk_tier": "yellow"},
                ],
                root_cause="VLAN pruned on a trunk, VTP mismatch, or STP blocking",
                verification="show interface trunk shows the VLAN as allowed and forwarding",
                tags=["cisco", "vlan", "trunk", "l2"],
                pack_source="cisco",
            ),
            RunbookEntry(
                title="Cisco BGP neighbor not established",
                problem_pattern="BGP session not reaching Established state",
                symptoms=[
                    "show bgp summary shows Idle/Active/OpenSent",
                    "No routes received from neighbor",
                ],
                steps=[
                    {"action": "check", "command": "show bgp summary", "explanation": "BGP session states", "risk_tier": "green"},
                    {"action": "check", "command": "show bgp neighbors {neighbor}", "explanation": "Detailed neighbor state and capabilities", "risk_tier": "green"},
                    {"action": "check", "command": "show ip route {neighbor}", "explanation": "Make sure the neighbor is reachable", "risk_tier": "green"},
                    {"action": "check", "command": "ping {neighbor} source {loopback}", "explanation": "TCP 179 reachability check via source", "risk_tier": "green"},
                ],
                root_cause="TCP unreachable, AS mismatch, wrong update-source, MD5 auth mismatch, or eBGP multihop",
                verification="show bgp summary reports Established with non-zero prefixes",
                tags=["cisco", "bgp", "routing"],
                pack_source="cisco",
            ),
        ]
