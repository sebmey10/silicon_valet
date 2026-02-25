# Silicon Valet

A self-hosted, air-gapped, agentic infrastructure intelligence system that runs on k3s. Silicon Valet learns the environment it lives in — services, configs, failure patterns, history — and helps users manage infrastructure through plain English conversation.

<!-- demo.gif -->

## Prerequisites

- **k3s** cluster with kubectl access
- **2 worker nodes** (32GB RAM each recommended), CPU-only
- **Git** for cloning
- Pre-downloaded **Ollama models** (see below)

## Install

```bash
git clone https://github.com/your-org/silicon-valet.git
cd silicon-valet
./install.sh
valet connect <node-ip>
```

### Model Preparation (Internet-Connected Machine)

Silicon Valet runs fully air-gapped. Download models beforehand:

```bash
ollama pull qwen3:8b
ollama pull qwen2.5-coder:7b
ollama pull nomic-embed-text
cp -r ~/.ollama/models/ /path/to/usb/models/
```

Copy the `models/` directory into the repo root before running `install.sh`.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLI Client                        │
│              valet connect <ip>                      │
└───────────────────────┬─────────────────────────────┘
                        │ WebSocket :7443
┌───────────────────────┴─────────────────────────────┐
│                   Valet Core                         │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │Orchestrator│ │Risk Engine│ │  Memory Layer       │ │
│  │(Planner + │ │ GREEN     │ │  Episodic (ChromaDB) │ │
│  │ Coder)    │ │ YELLOW    │ │  Procedural (SQLite) │ │
│  │           │ │ RED       │ │  DNA (SQLite)        │ │
│  └──────────┘ └──────────┘ └──────────────────────┘ │
│  ┌──────────────────┐  ┌───────────────────────────┐ │
│  │   MCP Tools      │  │    Domain Packs           │ │
│  │ shell, k8s, net  │  │ networking, k8s, zabbix,  │ │
│  │ filesystem, dna  │  │ rabbitmq                  │ │
│  └──────────────────┘  └───────────────────────────┘ │
└───────────────┬──────────────────┬──────────────────┘
                │                  │
    ┌───────────┴──────┐  ┌───────┴──────────┐
    │  Ollama worker-01│  │  Ollama worker-02│
    │  qwen3:8b        │  │  qwen2.5-coder:7b│
    │  nomic-embed-text│  │                  │
    └──────────────────┘  └──────────────────┘
```

## Core Concepts

### Infrastructure DNA

Silicon Valet continuously scans the cluster to build a knowledge graph of nodes, services, ports, config files, and dependencies. This "DNA" provides real-time context for every conversation.

### Three-Tier Risk Engine

Every command goes through a risk classifier before execution:

| Tier | Behavior | Examples |
|------|----------|---------|
| **GREEN** | Auto-executes | `kubectl get pods`, `cat`, `ping`, `ss` |
| **YELLOW** | Preview + confirm | `systemctl restart`, `kubectl apply`, `sed -i` |
| **RED** | Type-to-confirm | `rm -rf`, `kubectl delete namespace`, `reboot` |

No command bypasses the risk engine. There is no escape hatch.

### Memory Systems

- **Episodic** — Remembers past troubleshooting sessions (semantic search via ChromaDB)
- **Procedural** — Runbook library that grows from resolved incidents
- **Declarative** — Infrastructure DNA (always-current cluster state)

### Domain Packs

Extensible packs that auto-detect services and provide specialized runbooks:

- **networking** — DNS, routing, connectivity (always active)
- **kubernetes** — Pod health, resource pressure, deployments
- **zabbix** — Server management, agent connectivity, triggers
- **rabbitmq** — Queue monitoring, consumer health, node management

## CLI Commands

| Command | Description |
|---------|-------------|
| `/status` | Session stats and cluster health |
| `/dna` | Infrastructure DNA summary |
| `/brief` | Save mission brief, clear context |
| `/history` | Recent command execution log |
| `/runbooks` | List available runbooks |
| `/packs` | List active domain packs |
| `/help` | Show all commands |
| `/quit` | Disconnect |

## Configuration

All settings via environment variables (or ConfigMap):

| Variable | Default | Description |
|----------|---------|-------------|
| `SV_DATA_DIR` | `/data/valet` | Data directory (PVC mount) |
| `SV_OLLAMA_WORKER01` | `http://ollama-worker01:11434` | Orchestrator Ollama endpoint |
| `SV_OLLAMA_WORKER02` | `http://ollama-worker02:11434` | Coder Ollama endpoint |
| `SV_ORCHESTRATOR_MODEL` | `qwen3:8b` | Main reasoning model |
| `SV_CODER_MODEL` | `qwen2.5-coder:7b` | Code specialist model |
| `SV_EMBED_MODEL` | `nomic-embed-text` | Embedding model |
| `SV_NUM_CTX` | `4096` | Context window size |
| `SV_SCAN_INTERVAL` | `600` | DNA scan interval (seconds) |
| `SV_WS_PORT` | `7443` | WebSocket server port |

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/ -v
```

## Troubleshooting

**Pods not starting:** Check node resources with `kubectl top nodes`. Each Ollama instance needs 6-10GB RAM.

**Models not loading:** Verify models were copied correctly: `kubectl exec -n silicon-valet <ollama-pod> -- ollama list`

**WebSocket connection refused:** Ensure the NodePort service is running: `kubectl get svc -n silicon-valet`

**Slow responses:** This runs on CPU only. First inference after cold start loads the model into RAM (30-60s). Subsequent responses are faster.

## License

MIT
