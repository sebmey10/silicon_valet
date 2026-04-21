#!/usr/bin/env bash
# autorun.sh — run this ON THE SERVER after plugging in the USB.
#
# What it does, in order:
#   1. Detects the server environment (distro, init, docker/k8s, CPU/RAM).
#   2. Picks the best install mode (docker-compose if docker is present,
#      otherwise a systemd service).
#   3. Copies payload (wheels, models, images) off the USB onto the server.
#   4. Installs Silicon Valet in offline mode.
#   5. Generates a fresh bearer token for OpenWebUI + the CLI.
#   6. Brings the stack up, bound to 127.0.0.1 only.
#   7. Prints the URL and token for the operator.
#
# Safe to re-run: every step is idempotent.
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
PAYLOAD="$HERE/payload"
INSTALL_DIR="${SV_INSTALL_DIR:-/opt/silicon_valet}"
DATA_DIR="${SV_DATA_DIR:-/var/lib/silicon_valet}"
LOG_FILE="/var/log/silicon_valet_install.log"

if [[ $EUID -ne 0 ]]; then
  echo "Please run as root:  sudo bash $0"
  exit 1
fi

mkdir -p "$DATA_DIR"
touch "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
note() { printf '   %s\n' "$*"; }
die() { printf '\n\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "Silicon Valet bootstrap starting"
note "Install dir: $INSTALL_DIR"
note "Data dir:    $DATA_DIR"
note "Log file:    $LOG_FILE"

# ---------- 1. Detect environment --------------------------------------------
say "Step 1/6 — Detecting environment"

OS_ID="unknown"; OS_PRETTY="unknown"
if [[ -r /etc/os-release ]]; then
  . /etc/os-release
  OS_ID="${ID:-unknown}"
  OS_PRETTY="${PRETTY_NAME:-$OS_ID}"
fi
note "OS:     $OS_PRETTY"

KERNEL=$(uname -r)
ARCH=$(uname -m)
note "Kernel: $KERNEL ($ARCH)"

HAS_SYSTEMD=0; command -v systemctl >/dev/null 2>&1 && HAS_SYSTEMD=1
HAS_DOCKER=0;  command -v docker    >/dev/null 2>&1 && HAS_DOCKER=1
HAS_PODMAN=0;  command -v podman    >/dev/null 2>&1 && HAS_PODMAN=1
HAS_K3S=0;     command -v k3s       >/dev/null 2>&1 && HAS_K3S=1
HAS_PYTHON=0;  command -v python3   >/dev/null 2>&1 && HAS_PYTHON=1

note "systemd=$HAS_SYSTEMD docker=$HAS_DOCKER podman=$HAS_PODMAN k3s=$HAS_K3S python3=$HAS_PYTHON"

RAM_MB=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo 2>/dev/null || echo 0)
CPU_CORES=$(nproc 2>/dev/null || echo 1)
note "Resources: ${RAM_MB} MB RAM, ${CPU_CORES} cores"

if (( RAM_MB < 8000 )); then
  echo "⚠️  Warning: qwen3:8b needs ≥ 8 GB RAM. Will fall back to qwen2.5-coder:7b or phi4-mini."
  ORCHESTRATOR_MODEL="qwen2.5-coder:7b"
  (( RAM_MB < 6000 )) && ORCHESTRATOR_MODEL="phi4-mini"
else
  ORCHESTRATOR_MODEL="qwen3:8b"
fi
note "Selected orchestrator model: $ORCHESTRATOR_MODEL"

# Decide install mode
MODE="standalone"
if [[ $HAS_DOCKER -eq 1 ]] && docker info >/dev/null 2>&1; then
  MODE="docker"
fi
if [[ $HAS_K3S -eq 1 ]] && k3s kubectl get nodes >/dev/null 2>&1; then
  MODE="k3s"
fi
if [[ "${SV_FORCE_MODE:-}" != "" ]]; then
  MODE="$SV_FORCE_MODE"
fi
note "Install mode: $MODE"

# ---------- 2. Copy payload to disk -------------------------------------------
say "Step 2/6 — Copying Silicon Valet to $INSTALL_DIR"

mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude 'usb/payload/' \
  "$REPO_ROOT/" "$INSTALL_DIR/"

if [[ -d "$PAYLOAD/wheels" ]]; then
  mkdir -p "$INSTALL_DIR/wheels"
  rsync -a "$PAYLOAD/wheels/" "$INSTALL_DIR/wheels/"
  note "Wheel cache: $(ls "$INSTALL_DIR/wheels" | wc -l) files"
fi

# ---------- 3. Offline model + image import -----------------------------------
say "Step 3/6 — Importing offline artifacts (models + docker images)"

if [[ -d "$PAYLOAD/ollama" ]]; then
  # Seed /root/.ollama so docker-compose's ollama container has models on first run.
  mkdir -p /var/lib/silicon_valet/ollama_data
  rsync -a "$PAYLOAD/ollama/" /var/lib/silicon_valet/ollama_data/
  note "Seeded Ollama model cache from USB."
fi

if [[ $HAS_DOCKER -eq 1 ]] && [[ -d "$PAYLOAD/images" ]]; then
  for img in "$PAYLOAD/images/"*.tar.gz; do
    [[ -f "$img" ]] || continue
    note "Loading $(basename "$img")..."
    gunzip -c "$img" | docker load
  done
fi

# ---------- 4. Install + start ------------------------------------------------
say "Step 4/6 — Installing Silicon Valet ($MODE mode)"

AUTH_TOKEN_FILE="$DATA_DIR/auth.token"
if [[ ! -s "$AUTH_TOKEN_FILE" ]]; then
  python3 -c "import secrets; print(secrets.token_urlsafe(32))" > "$AUTH_TOKEN_FILE"
  chmod 600 "$AUTH_TOKEN_FILE"
fi
AUTH_TOKEN=$(cat "$AUTH_TOKEN_FILE")

case "$MODE" in
  docker)
    cd "$INSTALL_DIR"
    cat > "$INSTALL_DIR/.env" <<EOF
SV_BIND=127.0.0.1
SV_AUTH_TOKEN=$AUTH_TOKEN
SV_ORCHESTRATOR_MODEL=$ORCHESTRATOR_MODEL
WEBUI_AUTH=true
EOF
    docker compose up -d --build
    ;;

  standalone)
    if [[ $HAS_PYTHON -eq 0 ]]; then
      case "$OS_ID" in
        ubuntu|debian) apt-get update && apt-get install -y python3 python3-venv python3-pip ;;
        rhel|centos|rocky|almalinux|fedora) dnf install -y python3 python3-pip || yum install -y python3 python3-pip ;;
        arch|manjaro) pacman -Sy --noconfirm python python-pip ;;
        *) die "Can't auto-install python3 on $OS_ID — please install it and re-run." ;;
      esac
    fi

    # Install Ollama natively if missing and we have internet — otherwise warn.
    if ! command -v ollama >/dev/null 2>&1; then
      if curl -fsS --max-time 5 https://ollama.com >/dev/null 2>&1; then
        note "Installing Ollama (needs internet)..."
        curl -fsSL https://ollama.com/install.sh | sh
      else
        note "⚠️  Ollama not installed and no internet. Copy ollama binary manually before continuing."
      fi
    fi

    # Seed ~/.ollama/models if we have it on the USB
    if [[ -d "$PAYLOAD/ollama" ]]; then
      mkdir -p /usr/share/ollama/.ollama /root/.ollama
      rsync -a "$PAYLOAD/ollama/" /usr/share/ollama/.ollama/ || true
      rsync -a "$PAYLOAD/ollama/" /root/.ollama/ || true
    fi

    # Enable ollama service if systemd
    if [[ $HAS_SYSTEMD -eq 1 ]] && systemctl list-unit-files | grep -q '^ollama.service'; then
      systemctl enable --now ollama || true
    fi

    # Create venv + install offline
    python3 -m venv "$INSTALL_DIR/.venv"
    "$INSTALL_DIR/.venv/bin/pip" install --upgrade pip
    if [[ -d "$INSTALL_DIR/wheels" ]] && [[ -n "$(ls -A "$INSTALL_DIR/wheels" 2>/dev/null)" ]]; then
      "$INSTALL_DIR/.venv/bin/pip" install --no-index --find-links="$INSTALL_DIR/wheels" -r "$INSTALL_DIR/requirements.txt"
    else
      "$INSTALL_DIR/.venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt"
    fi
    "$INSTALL_DIR/.venv/bin/pip" install -e "$INSTALL_DIR"

    # systemd unit for valet-server
    if [[ $HAS_SYSTEMD -eq 1 ]]; then
      cat > /etc/systemd/system/silicon-valet.service <<EOF
[Unit]
Description=Silicon Valet server-engineer agent
After=network-online.target ollama.service
Wants=network-online.target

[Service]
Type=simple
Environment="SV_DATA_DIR=$DATA_DIR"
Environment="SV_WS_HOST=127.0.0.1"
Environment="SV_HTTP_HOST=127.0.0.1"
Environment="SV_AUTH_TOKEN=$AUTH_TOKEN"
Environment="SV_ORCHESTRATOR_MODEL=$ORCHESTRATOR_MODEL"
ExecStart=$INSTALL_DIR/.venv/bin/valet-server
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
      systemctl daemon-reload
      systemctl enable --now silicon-valet.service
    fi

    # Install OpenWebUI via docker if we can, otherwise skip (user can reach via CLI)
    if [[ $HAS_DOCKER -eq 1 ]]; then
      docker rm -f sv-openwebui 2>/dev/null || true
      docker run -d \
        --name sv-openwebui \
        --restart unless-stopped \
        -p 127.0.0.1:3000:8080 \
        -e OPENAI_API_BASE_URL="http://host.docker.internal:7444/v1" \
        -e OPENAI_API_KEY="$AUTH_TOKEN" \
        -e ENABLE_OLLAMA_API=false \
        -e WEBUI_AUTH=true \
        -e WEBUI_NAME="Silicon Valet" \
        -e DEFAULT_MODELS=silicon-valet \
        --add-host host.docker.internal:host-gateway \
        -v sv_openwebui_data:/app/backend/data \
        ghcr.io/open-webui/open-webui:main
    else
      note "⚠️  No docker; OpenWebUI skipped. Use the CLI: $INSTALL_DIR/.venv/bin/valet"
    fi
    ;;

  k3s)
    note "k3s mode: applying manifests."
    k3s kubectl apply -f "$INSTALL_DIR/deploy/"
    ;;

  *) die "unknown install mode $MODE" ;;
esac

# ---------- 5. Wait for readiness ---------------------------------------------
say "Step 5/6 — Waiting for services to come up"
for i in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:7444/health >/dev/null 2>&1; then
    note "Silicon Valet HTTP API ready."
    break
  fi
  sleep 2
done

# ---------- 6. Print connection info ------------------------------------------
say "Step 6/6 — Done"
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
cat <<EOF

┌──────────────────────────────────────────────────────────────────┐
│  Silicon Valet is running.                                       │
│                                                                  │
│  Chat UI  (OpenWebUI):  http://127.0.0.1:3000                    │
│  API      (OpenAI):     http://127.0.0.1:7444/v1                 │
│  CLI      (WebSocket):  ws://127.0.0.1:7443                      │
│                                                                  │
│  Auth token (share with OpenWebUI + CLI):                        │
│  $AUTH_TOKEN │
│                                                                  │
│  Loopback-only by default. To reach from your laptop, tunnel:    │
│    ssh -L 3000:127.0.0.1:3000 <this-server>                      │
│  Then open http://localhost:3000 in your browser.                │
│                                                                  │
│  Logs:   journalctl -u silicon-valet -f                          │
│  Stop:   docker compose down   (or)  systemctl stop silicon-valet│
└──────────────────────────────────────────────────────────────────┘
EOF
