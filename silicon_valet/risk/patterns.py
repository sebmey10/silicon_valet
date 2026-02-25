"""Risk classification patterns for command categorization."""

from __future__ import annotations

import re

# GREEN — Read-only commands that observe without changing state.
# These auto-execute silently.
GREEN_PATTERNS: list[re.Pattern] = [
    # File reading
    re.compile(r"^(cat|head|tail|less|more|bat)\s"),
    re.compile(r"^(ls|ll|dir)\b"),
    re.compile(r"^(find|locate)\s"),
    re.compile(r"^(stat|file|wc|md5sum|sha256sum)\s"),
    re.compile(r"^(diff|cmp)\s"),
    re.compile(r"^(grep|egrep|fgrep|rg|ag)\s"),

    # System info
    re.compile(r"^(ps|top|htop|uptime|free|vmstat|iostat)\b"),
    re.compile(r"^(df|du)\s"),
    re.compile(r"^(who|w|id|whoami|hostname|uname)\b"),
    re.compile(r"^(lscpu|lsblk|lspci|lsusb|lsmod)\b"),
    re.compile(r"^(env|printenv|set)\b"),
    re.compile(r"^date\b"),

    # Network read
    re.compile(r"^(ss|netstat)\s"),
    re.compile(r"^(ip\s+(addr|route|link|neigh)\s+show|ip\s+a)\b"),
    re.compile(r"^(ip\s+-j\s+addr)\b"),
    re.compile(r"^(dig|nslookup|host)\s"),
    re.compile(r"^ping\s"),
    re.compile(r"^(traceroute|tracepath|mtr)\s"),
    re.compile(r"^curl\s+(-s\s+)?(-o\s+/dev/null\s+)?(-w\s+)?.*(-X\s+GET\s+|--request\s+GET\s+)?https?://"),
    re.compile(r"^curl\s+(?!.*(-X\s+(POST|PUT|DELETE|PATCH)|--data|--upload|-d\s))"),
    re.compile(r"^wget\s+--spider\s"),

    # Kubernetes read
    re.compile(r"^kubectl\s+get\s"),
    re.compile(r"^kubectl\s+describe\s"),
    re.compile(r"^kubectl\s+logs?\s"),
    re.compile(r"^kubectl\s+top\s"),
    re.compile(r"^kubectl\s+api-resources\b"),
    re.compile(r"^kubectl\s+cluster-info\b"),
    re.compile(r"^kubectl\s+config\s+(view|get|current)\b"),
    re.compile(r"^kubectl\s+explain\s"),
    re.compile(r"^kubectl\s+version\b"),
    re.compile(r"^k9s\b"),

    # Systemd read
    re.compile(r"^systemctl\s+(status|is-active|is-enabled|is-failed|show|list-units|list-unit-files)\b"),

    # Logs
    re.compile(r"^journalctl\s"),
    re.compile(r"^dmesg\b"),

    # Container read
    re.compile(r"^(docker|podman|crictl)\s+(ps|images|inspect|logs|stats|info|version)\b"),
    re.compile(r"^(docker|podman)\s+network\s+(ls|inspect)\b"),
    re.compile(r"^(docker|podman)\s+volume\s+(ls|inspect)\b"),

    # Package info
    re.compile(r"^(dpkg\s+-l|apt\s+list|rpm\s+-qa)\b"),
    re.compile(r"^pip\s+(list|show|freeze)\b"),
]

# YELLOW — Commands that modify state. Require preview and confirmation.
YELLOW_PATTERNS: list[re.Pattern] = [
    # Service management
    re.compile(r"^systemctl\s+(start|stop|restart|reload|enable|disable)\s"),

    # Kubernetes modify
    re.compile(r"^kubectl\s+apply\s"),
    re.compile(r"^kubectl\s+scale\s"),
    re.compile(r"^kubectl\s+rollout\s"),
    re.compile(r"^kubectl\s+edit\s"),
    re.compile(r"^kubectl\s+patch\s"),
    re.compile(r"^kubectl\s+label\s"),
    re.compile(r"^kubectl\s+annotate\s"),
    re.compile(r"^kubectl\s+cordon\s"),
    re.compile(r"^kubectl\s+uncordon\s"),
    re.compile(r"^kubectl\s+taint\s"),
    re.compile(r"^kubectl\s+delete\s+pod\s"),  # Single pod delete is yellow

    # File modification
    re.compile(r"^(cp|mv|install)\s"),
    re.compile(r"^mkdir\s"),
    re.compile(r"^(touch|truncate)\s"),
    re.compile(r"^(chmod|chown|chgrp)\s"),
    re.compile(r"^(sed\s+-i|perl\s+-i)\s"),
    re.compile(r"^(tee|tee\s+-a)\s"),
    re.compile(r".*>>"),  # Append redirect

    # Network modify
    re.compile(r"^curl\s+.*(-X\s+(POST|PUT|PATCH)|--data|-d\s)"),

    # Container modify
    re.compile(r"^(docker|podman)\s+(start|stop|restart|pause|unpause|exec)\s"),
    re.compile(r"^(docker|podman)\s+network\s+(create|connect|disconnect)\s"),

    # Package management
    re.compile(r"^(apt|apt-get|yum|dnf)\s+(install|update|upgrade)\s"),
    re.compile(r"^pip\s+install\s"),
]

# RED — Destructive commands. Require explicit type-to-confirm.
RED_PATTERNS: list[re.Pattern] = [
    # File destruction
    re.compile(r"^rm(\s|$)"),
    re.compile(r"^rmdir(\s|$)"),
    re.compile(r"^shred(\s|$)"),

    # Kubernetes destroy
    re.compile(r"^kubectl\s+delete\s+(namespace|ns|deployment|deploy|service|svc|pvc|pv|node|ingress|configmap|secret|daemonset|statefulset|job|cronjob)\s"),
    re.compile(r"^kubectl\s+drain\s"),

    # Systemd destructive
    re.compile(r"^systemctl\s+(mask|unmask)\s"),
    re.compile(r"^systemctl\s+daemon-reload\b"),

    # Disk/filesystem destructive
    re.compile(r"^(mkfs\S*|fdisk|parted|gdisk)\s"),
    re.compile(r"^dd\s"),
    re.compile(r"^(wipefs|blkdiscard)\s"),

    # Network destructive
    re.compile(r"^(iptables|ip6tables|nft|nftables)\s"),
    re.compile(r"^ip\s+(addr|route|link)\s+(add|del|set|flush)\s"),

    # System control
    re.compile(r"^(reboot|shutdown|halt|poweroff|init\s+[06])\b"),

    # Container destructive
    re.compile(r"^(docker|podman)\s+(rm|rmi)\s"),
    re.compile(r"^(docker|podman)\s+volume\s+(rm|prune)\s"),
    re.compile(r"^(docker|podman)\s+system\s+prune\b"),
    re.compile(r"^(docker|podman)\s+network\s+rm\s"),

    # Package removal
    re.compile(r"^(apt|apt-get|yum|dnf)\s+(remove|purge|autoremove)\s"),
    re.compile(r"^pip\s+uninstall\s"),

    # Dangerous pipes
    re.compile(r"\|\s*(rm|dd|mkfs\S*|shred)\b"),
    re.compile(r">\s*/dev/sd"),
]
