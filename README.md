# Silicon Valet

A self-hosted, offline-capable AI server engineer. Plug a USB stick into any
Linux server, run one command, and get a chat UI where you talk to the server
in plain English — "why is nginx 502ing?", "what changed on core-rtr-01 in the
last hour?", "migrate me off this EOL kernel." It detects the environment it
lives in, learns the services it finds, and operates through a 3-tier risk
engine so nothing destructive runs without explicit approval.

```
  ┌───────────────────────────────────┐
  │            You (browser)          │
  └───────────────┬───────────────────┘
                  │  HTTPS / SSH tunnel
  ┌───────────────▼───────────────────┐
  │      OpenWebUI  (port 3000)       │   ← chat UI the human sees
  └───────────────┬───────────────────┘
                  │  OpenAI /v1/chat/completions
  ┌───────────────▼───────────────────┐
  │   Silicon Valet core (port 7444)  │   ← planner, risk engine, packs
  │   ├─ Linux pack                   │
  │   ├─ Cisco / Nokia / Adtran packs │
  │   ├─ Kubernetes / Docker packs    │
  │   └─ DNA scanner + memory (RAG)   │
  └───────────────┬───────────────────┘
                  │
  ┌───────────────▼───────────────────┐
  │       Ollama  (local models)      │
  │   qwen3:8b | qwen2.5-coder:7b     │
  │   nomic-embed-text  |  phi4-mini  │
  └───────────────────────────────────┘
```

---

## ⚡ USB Quick Start — The Easy Path

This is the flow the project is optimized for.

### 1. Build the USB (one time, on your workstation)

```bash
# On your dev box, with docker + ollama installed:
git clone https://github.com/your-org/silicon_valet.git
cd silicon_valet

# Mount a ≥32 GB USB stick (FAT32 or exFAT) and pass its path:
sudo ./usb/prepare_usb.sh /media/$USER/SILICON_VALET
sudo eject /media/$USER/SILICON_VALET
```

The preparer downloads Python wheels, pulls all Ollama models, saves the
Ollama + OpenWebUI docker images, and drops an `AUTORUN.sh` at the USB root.
You now have an offline install medium.

### 2. Plug into the server

```bash
# On the target Linux server:
sudo mkdir -p /mnt/usb && sudo mount /dev/sdb1 /mnt/usb   # find the device via lsblk
cd /mnt/usb
sudo bash AUTORUN.sh
```

`AUTORUN.sh` detects the environment, picks an install mode
(docker-compose / systemd standalone / k3s), imports the offline models and
images, generates a bearer token, and prints:

```
Chat UI  (OpenWebUI):  http://127.0.0.1:3000
API      (OpenAI):     http://127.0.0.1:7444/v1
CLI      (WebSocket):  ws://127.0.0.1:7443
Auth token: 8fD…Hg9
```

### 3. Chat

Loopback-only by default. From your laptop:

```bash
ssh -L 3000:127.0.0.1:3000 <server>
# open http://localhost:3000 — create an admin account — start chatting
```

Full detail: see [usb/README.md](usb/README.md).

---

## What it does differently

| Capability | How |
|---|---|
| **Talks to the server, not at it** | OpenWebUI chat → OpenAI-compat API → Qwen-Agent planner with tools |
| **Knows its environment** | `EnvironmentDetector` at startup (distro, systemd, docker, k8s), continuous DNA scanner afterwards |
| **Safe in prod** | 3-tier risk engine (GREEN/YELLOW/RED). GREEN auto-runs (read-only). YELLOW/RED require explicit approval. No escape hatch. |
| **Speaks network gear** | First-class packs for Cisco IOS/IOS-XE/NX-OS/IOS-XR, Nokia SR OS + SR Linux, Adtran AOS. Powered by netmiko. |
| **Offline** | Wheels, models, and docker images all ship on the USB. Never phones home. |
| **Bounded by default** | Binds to `127.0.0.1`. All APIs gated by a bearer token generated on first boot. |

## Risk tiers

| Tier | Examples | Behavior |
|---|---|---|
| **GREEN** | `cat`, `ls`, `ps`, `show ip int brief`, `kubectl get pods` | Auto-executes |
| **YELLOW** | `systemctl restart`, `sed -i`, `no shutdown`, `kubectl apply` | CLI prompts for approval. Web UI denies by default. |
| **RED** | `rm -rf`, `reload`, `factory-reset`, `kubectl delete namespace` | CLI requires type-to-confirm. Web UI always denies. |

Web-UI approval for YELLOW is off by default because the web chat can't do
true interactive prompts — use the CLI for YELLOW/RED, or explicitly accept
the risk with `SV_HTTP_AUTO_APPROVE_YELLOW=true`.

## Domain packs

Packs are auto-detected and loaded based on what's in the DNA or inventory:

| Pack | Activates when | Covers |
|---|---|---|
| `linux` | always (on Linux) | disk, CPU, memory, OOM, systemd, cron, logs |
| `networking` | always | DNS, routing, connectivity |
| `kubernetes` | k8s/k3s cluster detected | pods, deployments, events |
| `docker` | docker detected | containers, images, networks |
| `webserver` | nginx/Apache detected | 502s, SSL certs, config |
| `database` | postgres/mysql/redis detected | connections, slow queries |
| `firewall` | ufw/fail2ban/sshd | SSH lockout, port access |
| `zabbix` | zabbix detected | server, agents, triggers |
| `rabbitmq` | rabbitmq detected | queues, consumers, nodes |
| **`cisco`** | inventory has a Cisco device, or `SV_ENABLE_CISCO=true` | interfaces, OSPF, BGP, VLANs, CPU |
| **`nokia`** | inventory has a Nokia device, or `SV_ENABLE_NOKIA=true` | SR OS ports, services (VPLS/VPRN), IS-IS, CPM, SR Linux |
| **`adtran`** | inventory has an Adtran device, or `SV_ENABLE_ADTRAN=true` | AOS interfaces, GPON/DSL, OSPF, save-config |

### Configuring network devices

Drop an inventory at `/etc/silicon_valet/devices.yaml` (see
[usb/devices.sample.yaml](usb/devices.sample.yaml)):

```yaml
devices:
  core-rtr-01:
    host: 10.0.0.1
    platform: cisco_xe      # any netmiko device_type
    username: netops
    password_env: SV_DEVICE_PW
```

Then just talk: *"Check interface status on core-rtr-01."* The agent calls the
`netdevice_show` tool, runs `show interfaces`, parses the output.

---

## Deployment modes

`AUTORUN.sh` picks the right one; you can also pick manually.

### Standalone (bare-metal / VM, systemd)

```bash
./setup.sh        # interactive
# or:
python -m venv .venv && source .venv/bin/activate
pip install -e .
valet-server      # starts the agent
valet connect 127.0.0.1 --token $(cat ~/.silicon_valet/data/auth.token)
```

### Docker compose

```bash
cp usb/devices.sample.yaml /etc/silicon_valet/devices.yaml  # optional
docker compose up -d
# UI: http://127.0.0.1:3000   (OpenWebUI)
# API: http://127.0.0.1:7444  (OpenAI-compatible)
```

### Kubernetes (k3s)

```bash
kubectl apply -f deploy/
```

---

## Configuration

Everything is env vars. Safe defaults.

| Variable | Default | Purpose |
|---|---|---|
| `SV_WS_HOST` / `SV_WS_PORT` | `127.0.0.1` / `7443` | WebSocket CLI bind |
| `SV_HTTP_HOST` / `SV_HTTP_PORT` | `127.0.0.1` / `7444` | OpenAI-compat API bind |
| `SV_HTTP_ENABLED` | `true` | Start the HTTP API alongside the WebSocket |
| `SV_AUTH_TOKEN` | auto-generated | Bearer token for WS + HTTP (persisted to `data_dir/auth.token`) |
| `SV_HTTP_AUTO_APPROVE_YELLOW` | `false` | Let web-chat sessions run YELLOW commands |
| `SV_RISK_AUTO_GREEN` | `true` | Auto-run read-only commands (leave on) |
| `SV_ORCHESTRATOR_MODEL` | `qwen3:8b` | Main reasoning model |
| `SV_CODER_MODEL` | `qwen2.5-coder:7b` | Code-generation model |
| `SV_EMBED_MODEL` | `nomic-embed-text` | Embedding model (for RAG) |
| `SV_DATA_DIR` | `~/.silicon_valet/data` | State directory |
| `SV_DEVICE_INVENTORY` | `/etc/silicon_valet/devices.yaml` | Network-device inventory path |
| `SV_ENABLE_CISCO/NOKIA/ADTRAN` | `false` | Force-enable a network-device pack even without inventory |

---

## Development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest -q
ruff check .
```

Adding a new device vendor? Copy `silicon_valet/packs/cisco/` to
`silicon_valet/packs/<vendor>/`, tweak `detect()`, and write runbook seeds.
Add it to `PACK_MODULES` in `silicon_valet/packs/loader.py`.

Adding a new tool? Subclass `qwen_agent.tools.base.BaseTool`, decorate with
`@register_tool("name")`, drop it in `silicon_valet/tools/` or in your pack's
`get_tools()`. Tools get the risk-engine approval callback for free.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `ollama not found` | `curl -fsSL https://ollama.com/install.sh \| sh` (or seed `~/.ollama` from the USB payload) |
| Models not pulled | `ollama pull qwen3:8b qwen2.5-coder:7b nomic-embed-text` |
| WebSocket connection refused | Check `systemctl status silicon-valet` or `docker compose logs silicon-valet` |
| OpenWebUI says "no models" | Token mismatch between `SV_AUTH_TOKEN` and OpenWebUI's `OPENAI_API_KEY` |
| Web-UI tool calls denied | You're hitting the YELLOW guard. Use the CLI, or set `SV_HTTP_AUTO_APPROVE_YELLOW=true`. |
| Slow first response | Cold-start loads models into RAM (30–60s on CPU). Subsequent replies are faster. |
| netmiko timeout | Test the device SSH manually; verify `platform` in inventory matches a netmiko device_type. |

## License

MIT
