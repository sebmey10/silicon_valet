# Silicon Valet

A self-hosted, agentic infrastructure intelligence system that runs on **any** Linux server. Silicon Valet learns the environment it lives in — services, configs, failure patterns, history — and helps users manage infrastructure through plain English conversation.

It automatically detects whether it's running on a bare-metal server, a VM, Docker, or a k3s Kubernetes cluster, and adapts accordingly.

## Quick Start (Any Linux Server)

```bash
git clone https://github.com/your-org/silicon-valet.git
cd silicon-valet
./setup.sh
```

The setup script detects your environment and walks you through everything — even if you've never used a command line before. After setup:

```bash
valet run
```

That's it. Start chatting. Ask it anything about your server.

## What It Does

- **Talks to you in plain English** — describe problems, ask questions, request changes
- **Learns your infrastructure** — continuously scans services, ports, configs, and dependencies
- **Remembers everything** — past sessions, resolved incidents, and successful fixes carry over
- **Stays safe** — every command goes through a 3-tier risk engine before execution
- **Adapts to your environment** — works on bare metal, VMs, Docker, or Kubernetes

## Deployment Options

### Option 1: Standalone (Recommended)

Runs Ollama + Silicon Valet directly on the machine. Best for single servers, VMs, and bare metal.

```bash
./setup.sh    # Choose option [1]
valet run
```

### Option 2: Docker Compose

Runs everything in containers.

```bash
./setup.sh    # Choose option [2]
# or manually:
docker compose up -d
valet connect localhost
```

### Option 3: Kubernetes (k3s)

For multi-node clusters. Requires 2+ worker nodes with 32GB RAM each.

```bash
./setup.sh    # Choose option [3]
# or manually:
./install.sh
valet connect <node-ip>
```

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI Client                        │
│            valet run  /  valet connect               │
└───────────────────────┬─────────────────────────────┘
                        │ WebSocket :7443
┌───────────────────────┴─────────────────────────────┐
│                   Valet Core                         │
│                                                      │
│  ┌──────────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ Orchestrator  │  │  Risk    │  │  Memory Layer  │ │
│  │ (Planner +   │  │  Engine  │  │  Episodic      │ │
│  │  Coder)      │  │  G/Y/R   │  │  Procedural    │ │
│  └──────────────┘  └──────────┘  │  DNA            │ │
│                                   └────────────────┘ │
│  ┌──────────────┐  ┌────────────────────────────┐   │
│  │  Environment │  │      Domain Packs          │   │
│  │  Detection   │  │  linux, networking, k8s,   │   │
│  │  (auto)      │  │  docker, web, db, firewall │   │
│  └──────────────┘  └────────────────────────────┘   │
└───────────────┬─────────────────────────────────────┘
                │
    ┌───────────┴──────────┐
    │  Ollama (local or    │
    │  multi-node)         │
    │  qwen3:8b            │
    │  qwen2.5-coder:7b    │
    │  nomic-embed-text    │
    └──────────────────────┘
```

## Core Concepts

### Environment Detection

At startup, Silicon Valet probes the system to discover:
- Kubernetes cluster (k3s/k8s)
- Docker containers
- Systemd services
- Network interfaces and ports
- Available Ollama endpoints

It then adapts its scanning, system prompt, and domain packs accordingly.

### Infrastructure DNA

Continuously scans to build a knowledge graph of nodes, services, ports, config files, and dependencies. This "DNA" provides real-time context for every conversation.

### Three-Tier Risk Engine

Every command goes through a risk classifier before execution:

| Tier | Behavior | Examples |
|------|----------|---------|
| **GREEN** | Auto-executes | `cat`, `ls`, `ps`, `ping`, `ss`, `kubectl get` |
| **YELLOW** | Preview + confirm | `systemctl restart`, `kubectl apply`, `sed -i` |
| **RED** | Type-to-confirm | `rm -rf`, `kubectl delete namespace`, `reboot` |

No command bypasses the risk engine. There is no escape hatch.

### Persistent Memory

- **Episodic** — Remembers past troubleshooting sessions (semantic search via ChromaDB)
- **Procedural** — Runbook library that grows from resolved incidents
- **Declarative** — Infrastructure DNA (always-current system state)

Memory persists across sessions. Silicon Valet never forgets what happened on your server.

### Domain Packs

Auto-detecting packs that provide specialized runbooks:

| Pack | Activates When | Covers |
|------|----------------|--------|
| **linux** | Always (on Linux) | Disk, CPU, memory, OOM, systemd, cron, logs |
| **networking** | Always | DNS, routing, connectivity |
| **kubernetes** | k8s cluster detected | Pods, deployments, resources, events |
| **docker** | Docker detected | Containers, images, networks, volumes |
| **webserver** | nginx/Apache detected | 502s, SSL certs, config errors |
| **database** | postgres/mysql/redis detected | Connections, slow queries, disk |
| **firewall** | ufw/fail2ban/sshd detected | SSH lockout, port access, banning |
| **zabbix** | Zabbix detected | Server, agents, triggers |
| **rabbitmq** | RabbitMQ detected | Queues, consumers, nodes |

## CLI Commands

| Command | Description |
|---------|-------------|
| `/status` | Session stats and system health |
| `/dna` | Infrastructure DNA summary |
| `/brief` | Save context, clear history |
| `/history` | Recent command execution log |
| `/runbooks` | List available runbooks |
| `/packs` | List active domain packs |
| `/help` | Show all commands |
| `/quit` | Disconnect |

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SV_OLLAMA_WORKER01` | `auto` | Orchestrator Ollama endpoint |
| `SV_OLLAMA_WORKER02` | `auto` | Coder Ollama endpoint |
| `SV_DATA_DIR` | `~/.silicon_valet/data` | Data directory |
| `SV_ORCHESTRATOR_MODEL` | `qwen3:8b` | Main reasoning model |
| `SV_CODER_MODEL` | `qwen2.5-coder:7b` | Code specialist model |
| `SV_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `SV_NUM_CTX` | `4096` | Context window size |
| `SV_SCAN_INTERVAL` | `600` | DNA scan interval (seconds) |
| `SV_WS_PORT` | `7443` | WebSocket server port |

Set `auto` for Ollama endpoints to let Silicon Valet discover them automatically (localhost, or k8s service names if in a cluster).

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Troubleshooting

**Ollama not found:** Run `curl -fsSL https://ollama.com/install.sh | sh` to install it.

**Models not loaded:** Run `ollama pull qwen3:8b && ollama pull qwen2.5-coder:7b && ollama pull nomic-embed-text`.

**Slow responses:** First inference after cold start loads models into RAM (30-60s). Subsequent responses are faster. Runs on CPU only.

**WebSocket connection refused:** Make sure `valet-server` is running, or use `valet run` which starts both.

## License

MIT
