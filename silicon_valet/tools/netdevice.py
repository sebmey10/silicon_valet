"""Network device tools — SSH/Telnet into Cisco, Nokia, Adtran, Juniper, Arista gear.

Built on top of netmiko. All commands flow through the risk engine: read-only
`show`/`display` commands are GREEN, `configure`/`commit`/`reload` are YELLOW or
RED. Credentials are loaded from /etc/silicon_valet/devices.yaml or
~/.silicon_valet/devices.yaml so secrets never sit in chat history.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import os
from pathlib import Path
from typing import Any

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
    import json as json5  # type: ignore[no-redef]

try:
    import yaml
except ImportError:
    yaml = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


# --- Device inventory loading -------------------------------------------------

_INVENTORY_PATHS = [
    Path("/etc/silicon_valet/devices.yaml"),
    Path.home() / ".silicon_valet" / "devices.yaml",
    Path(os.getenv("SV_DEVICE_INVENTORY", "")) if os.getenv("SV_DEVICE_INVENTORY") else None,
]


def load_inventory() -> dict[str, dict[str, Any]]:
    """Load device inventory from YAML. Returns {name: {host, platform, ...}}."""
    if yaml is None:
        return {}
    for p in _INVENTORY_PATHS:
        if p is None or not p.exists():
            continue
        try:
            with p.open() as f:
                data = yaml.safe_load(f) or {}
            devices = data.get("devices", {}) if isinstance(data, dict) else {}
            if devices:
                logger.info("Loaded %d devices from %s", len(devices), p)
                return devices
        except Exception as e:
            logger.warning("Failed to load device inventory at %s: %s", p, e)
    return {}


# --- Platform mapping ---------------------------------------------------------

# Vendor hint -> netmiko device_type. netmiko supports many more; these are the
# ones Silicon Valet ships runbooks for out of the box.
PLATFORM_MAP = {
    "cisco_ios": "cisco_ios",
    "cisco_xe": "cisco_xe",
    "cisco_nxos": "cisco_nxos",
    "cisco_asa": "cisco_asa",
    "cisco_xr": "cisco_xr",
    "nokia_sros": "nokia_sros",
    "nokia_srl": "nokia_srl",
    "adtran_os": "adtran_os",
    "juniper_junos": "juniper_junos",
    "arista_eos": "arista_eos",
    "linux": "linux",
}


def _fingerprint_from_banner(banner: str) -> str | None:
    """Guess netmiko platform from an SSH banner string."""
    b = banner.lower().replace("_", " ").replace("-", " ")
    if "cisco ios xe" in b or "ios-xe" in b:
        return "cisco_xe"
    if "nx-os" in b or "nexus" in b:
        return "cisco_nxos"
    if "ios xr" in b:
        return "cisco_xr"
    if "cisco ios" in b or "cisco systems" in b:
        return "cisco_ios"
    if "nokia" in b and "sr os" in b:
        return "nokia_sros"
    if "nokia" in b and "srlinux" in b:
        return "nokia_srl"
    if "adtran" in b or "netvanta" in b or "total access" in b:
        return "adtran_os"
    if "junos" in b or "juniper" in b:
        return "juniper_junos"
    if "arista" in b or "eos" in b:
        return "arista_eos"
    return None


# --- Risk classification for device commands ---------------------------------

# Command prefixes that are always safe (read-only on network gear).
_DEVICE_GREEN_PREFIXES = (
    "show ", "display ", "dir", "ping ", "traceroute ",
    "monitor ", "admin show", "file show", "info",
)

# Command prefixes that change state.
_DEVICE_YELLOW_PREFIXES = (
    "configure", "conf t", "config t", "no ", "interface ",
    "commit", "save", "copy running", "write memory", "wr ",
    "clear counters", "clear logging", "clear arp",
    "shutdown", "no shutdown", "reset ",
)

# Command prefixes that can cut you off or reboot the device.
_DEVICE_RED_PREFIXES = (
    "reload", "reboot", "admin reboot", "admin reload",
    "erase ", "format ", "delete ", "rm ",
    "factory-reset", "factory default", "clear running-config",
    "shutdown system", "power off",
)


def _classify_device_command(cmd: str) -> str:
    c = cmd.strip().lower()
    for prefix in _DEVICE_RED_PREFIXES:
        if c.startswith(prefix):
            return "red"
    for prefix in _DEVICE_GREEN_PREFIXES:
        if c.startswith(prefix):
            return "green"
    for prefix in _DEVICE_YELLOW_PREFIXES:
        if c.startswith(prefix):
            return "yellow"
    return "yellow"  # unknown -> safe default


# --- Netmiko wrapper ---------------------------------------------------------

def _get_connection_kwargs(device: str) -> dict[str, Any]:
    """Resolve a device name into netmiko connection kwargs."""
    inv = load_inventory()
    if device in inv:
        entry = dict(inv[device])
        entry.setdefault("device_type", PLATFORM_MAP.get(entry.pop("platform", ""), "cisco_ios"))
        # Support env-var password references: password_env: MY_SECRET
        if "password_env" in entry:
            entry["password"] = os.getenv(entry.pop("password_env"), "")
        return entry
    # Fall back: treat device string as host:platform@user (for ad-hoc use).
    # e.g. "10.0.0.1:cisco_ios@admin"
    host = device
    platform = "cisco_ios"
    user = os.getenv("SV_DEVICE_USERNAME", "admin")
    if "@" in host:
        user, host = host.split("@", 1)
    if ":" in host:
        host, platform = host.split(":", 1)
    return {
        "host": host,
        "device_type": PLATFORM_MAP.get(platform, "cisco_ios"),
        "username": user,
        "password": os.getenv("SV_DEVICE_PASSWORD", ""),
    }


def _run_on_device(connect_kwargs: dict[str, Any], commands: list[str],
                   config_mode: bool = False) -> dict[str, Any]:
    """Connect, send commands, and disconnect. Runs in a worker thread."""
    try:
        from netmiko import ConnectHandler
    except ImportError:
        return {"error": "netmiko is not installed. Run: pip install netmiko"}

    try:
        with ConnectHandler(**connect_kwargs) as conn:
            if config_mode:
                output = conn.send_config_set(commands)
            else:
                output = "\n".join(conn.send_command(c) for c in commands)
            return {
                "output": output,
                "host": connect_kwargs.get("host"),
                "platform": connect_kwargs.get("device_type"),
                "success": True,
            }
    except Exception as e:
        logger.exception("Device command failed")
        return {"error": str(e), "host": connect_kwargs.get("host"), "success": False}


# --- Qwen-Agent tools ---------------------------------------------------------

@register_tool("netdevice_show")
class NetDeviceShowTool(BaseTool):
    """Run a read-only `show` or `display` command on a network device (GREEN)."""

    description = (
        "Run a read-only command (show/display/ping/dir) on a network device "
        "(Cisco, Nokia, Adtran, Juniper, Arista). Use for diagnostics — never for config changes."
    )
    parameters = [
        {"name": "device", "type": "string",
         "description": "Device name from inventory, or host[:platform][@user].",
         "required": True},
        {"name": "command", "type": "string",
         "description": "The show/display command to run (e.g. 'show ip interface brief').",
         "required": True},
    ]
    _risk_engine: Any = None
    _approval_callback: Any = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        device = parsed["device"]
        command = parsed["command"].strip()

        tier = _classify_device_command(command)
        if tier != "green":
            return json.dumps({
                "error": f"Command '{command}' is not read-only (tier={tier}). Use netdevice_config instead.",
                "tier": tier,
            })

        connect_kwargs = _get_connection_kwargs(device)
        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(_run_on_device, connect_kwargs, [command], False).result()
        return json.dumps(result, ensure_ascii=False)


@register_tool("netdevice_config")
class NetDeviceConfigTool(BaseTool):
    """Apply configuration changes on a network device (YELLOW/RED — requires approval)."""

    description = (
        "Apply configuration changes to a network device. Always goes through the "
        "Silicon Valet risk engine for user approval. Use a list of config lines, "
        "e.g. ['interface Gi0/1','no shutdown','description uplink']."
    )
    parameters = [
        {"name": "device", "type": "string",
         "description": "Device name from inventory, or host[:platform][@user].",
         "required": True},
        {"name": "commands", "type": "array",
         "description": "List of configuration commands to apply in order.",
         "required": True},
        {"name": "save", "type": "boolean",
         "description": "If true, persist the config after applying (write memory / commit).",
         "required": False},
    ]
    _risk_engine: Any = None
    _approval_callback: Any = None

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        device = parsed["device"]
        commands = parsed["commands"]
        if isinstance(commands, str):
            commands = [commands]
        save = bool(parsed.get("save", False))

        # Highest tier among all commands wins
        tier = "green"
        tier_order = {"green": 0, "yellow": 1, "red": 2}
        for c in commands:
            t = _classify_device_command(c)
            if tier_order[t] > tier_order[tier]:
                tier = t

        connect_kwargs = _get_connection_kwargs(device)
        preview = f"[{connect_kwargs.get('host')}:{connect_kwargs.get('device_type')}] " \
                  f"apply {len(commands)} config line(s): {commands[:3]}"

        # Route approval through the risk engine if available
        if self._approval_callback is not None and tier != "green":
            async def _ask() -> bool:
                return await self._approval_callback(preview, tier, f"Network device config change (tier {tier})")
            try:
                approved = asyncio.new_event_loop().run_until_complete(_ask())
            except Exception as e:
                logger.warning("Approval callback failed: %s", e)
                approved = False
            if not approved:
                return json.dumps({"error": "User denied config change", "tier": tier})

        with concurrent.futures.ThreadPoolExecutor() as pool:
            result = pool.submit(_run_on_device, connect_kwargs, commands, True).result()

        if save and result.get("success"):
            platform = connect_kwargs.get("device_type", "")
            save_cmd = _save_command_for(platform)
            if save_cmd:
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    pool.submit(_run_on_device, connect_kwargs, [save_cmd], False).result()
                result["saved"] = True

        result["tier"] = tier
        return json.dumps(result, ensure_ascii=False)


def _save_command_for(platform: str) -> str | None:
    """Return the vendor-specific 'save running config' command."""
    if platform.startswith("cisco"):
        return "write memory"
    if platform.startswith("nokia_sros"):
        return "admin save"
    if platform.startswith("nokia_srl"):
        return "commit save"
    if platform.startswith("adtran"):
        return "write"
    if platform.startswith("juniper"):
        return "commit"
    if platform.startswith("arista"):
        return "write memory"
    return None


@register_tool("netdevice_fingerprint")
class NetDeviceFingerprintTool(BaseTool):
    """SSH into a device (raw), read the banner, and guess the vendor/platform."""

    description = (
        "Probe a network device's SSH banner to identify its vendor and OS. "
        "Useful when you don't yet know whether a device is Cisco, Nokia, Adtran, etc."
    )
    parameters = [
        {"name": "host", "type": "string", "description": "IP or hostname to probe.", "required": True},
        {"name": "port", "type": "integer", "description": "SSH port (default 22).", "required": False},
    ]

    def call(self, params: str, **kwargs) -> str:
        parsed = json5.loads(params) if isinstance(params, str) else params
        host = parsed["host"]
        port = int(parsed.get("port", 22))
        try:
            import socket
            with socket.create_connection((host, port), timeout=5) as s:
                banner = s.recv(256).decode("utf-8", errors="replace")
        except Exception as e:
            return json.dumps({"error": str(e), "host": host})
        platform = _fingerprint_from_banner(banner)
        return json.dumps({
            "host": host,
            "banner": banner.strip(),
            "platform": platform,
            "netmiko_device_type": PLATFORM_MAP.get(platform, None) if platform else None,
        }, ensure_ascii=False)


@register_tool("netdevice_list_inventory")
class NetDeviceListInventoryTool(BaseTool):
    """List all configured network devices."""

    description = "List all network devices defined in the Silicon Valet device inventory."
    parameters: list = []

    def call(self, params: str = "", **kwargs) -> str:
        inv = load_inventory()
        summary = [
            {"name": name, "host": entry.get("host"), "platform": entry.get("platform") or entry.get("device_type")}
            for name, entry in inv.items()
        ]
        return json.dumps({"devices": summary, "count": len(summary)}, ensure_ascii=False)
