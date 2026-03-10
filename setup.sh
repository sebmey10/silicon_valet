#!/bin/bash
# Silicon Valet — Universal Setup Script
# =======================================
#
# Works on any Linux server, Docker, or k3s cluster.
# Guides you through the entire setup process.
#
# USAGE:
#   git clone <repo-url>
#   cd silicon-valet
#   ./setup.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')]${NC} $*"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')]${NC} $*"; }

# -------------------------------------------------------
# Banner
# -------------------------------------------------------
echo ""
echo -e "${BOLD}${CYAN}"
echo "  _____ _ _ _                   __     __    _      _   "
echo " / ____(_) (_)                  \\ \\   / /   | |    | |  "
echo "| (___  _| |_  ___ ___  _ __    \\ \\_/ /_ _ | | ___| |_ "
echo " \\___ \\| | | |/ __/ _ \\| '_ \\    \\   / _\` || |/ _ \\ __|"
echo " ____) | | | | (_| (_) | | | |    | | (_| || |  __/ |_ "
echo "|_____/|_|_|_|\\___\\___/|_| |_|    |_|\\__,_||_|\\___|\\__|"
echo ""
echo -e "  Infrastructure Intelligence for Any Server${NC}"
echo ""
echo "  This script will set up Silicon Valet on your system."
echo "  It will detect your environment and guide you through each step."
echo ""

# -------------------------------------------------------
# Step 1: OS Detection
# -------------------------------------------------------
log "Step 1: Detecting your system..."

OS="unknown"
PKG_MGR=""
ARCH=$(uname -m)

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS="$ID"
    case "$ID" in
        ubuntu|debian|raspbian)
            PKG_MGR="apt"
            ;;
        centos|rhel|rocky|almalinux|fedora)
            if command -v dnf &>/dev/null; then
                PKG_MGR="dnf"
            else
                PKG_MGR="yum"
            fi
            ;;
        arch|manjaro)
            PKG_MGR="pacman"
            ;;
        opensuse*|sles)
            PKG_MGR="zypper"
            ;;
    esac
    ok "OS: ${PRETTY_NAME:-$OS} ($ARCH)"
elif [[ "$(uname)" == "Darwin" ]]; then
    OS="macos"
    PKG_MGR="brew"
    ok "OS: macOS ($ARCH) — development mode"
else
    warn "Could not detect OS. Continuing anyway..."
fi

# -------------------------------------------------------
# Step 2: Python Check
# -------------------------------------------------------
log "Step 2: Checking Python..."

PYTHON_CMD=""
for cmd in python3.12 python3.11 python3; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
        PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
        PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
            PYTHON_CMD="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON_CMD" ]; then
    warn "Python 3.11+ not found."
    echo ""
    echo "  Silicon Valet requires Python 3.11 or higher."
    echo ""
    case "$PKG_MGR" in
        apt)
            echo "  Install it with:"
            echo -e "    ${CYAN}sudo apt update && sudo apt install -y python3.11 python3.11-venv python3-pip${NC}"
            ;;
        dnf|yum)
            echo "  Install it with:"
            echo -e "    ${CYAN}sudo $PKG_MGR install -y python3.11${NC}"
            ;;
        pacman)
            echo "  Install it with:"
            echo -e "    ${CYAN}sudo pacman -S python${NC}"
            ;;
        brew)
            echo "  Install it with:"
            echo -e "    ${CYAN}brew install python@3.11${NC}"
            ;;
        *)
            echo "  Please install Python 3.11+ for your OS."
            ;;
    esac
    echo ""
    read -p "  Press Enter after installing Python, or Ctrl+C to exit... "
    # Re-check
    for cmd in python3.12 python3.11 python3; do
        if command -v "$cmd" &>/dev/null; then
            PY_VER=$($cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "0.0")
            PY_MAJOR=$(echo "$PY_VER" | cut -d. -f1)
            PY_MINOR=$(echo "$PY_VER" | cut -d. -f2)
            if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 11 ]; then
                PYTHON_CMD="$cmd"
                break
            fi
        fi
    done
    if [ -z "$PYTHON_CMD" ]; then
        err "Python 3.11+ still not found. Exiting."
        exit 1
    fi
fi

ok "Python: $($PYTHON_CMD --version)"

# -------------------------------------------------------
# Step 3: Environment Detection + Mode Selection
# -------------------------------------------------------
log "Step 3: Detecting your environment..."

HAS_KUBECTL=false
HAS_DOCKER=false
HAS_OLLAMA=false

if command -v kubectl &>/dev/null && kubectl cluster-info &>/dev/null 2>&1; then
    HAS_KUBECTL=true
    NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l | tr -d ' ')
    ok "  Kubernetes cluster detected ($NODE_COUNT nodes)"
fi

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    HAS_DOCKER=true
    ok "  Docker detected and running"
fi

if command -v ollama &>/dev/null; then
    HAS_OLLAMA=true
    ok "  Ollama already installed"
fi

echo ""
echo -e "${BOLD}  How would you like to deploy Silicon Valet?${NC}"
echo ""
echo "  [1] Standalone (recommended)"
echo "      Runs Ollama + Valet directly on this machine."
echo "      Best for: single servers, VMs, bare metal."
echo ""
echo "  [2] Docker Compose"
echo "      Runs Ollama + Valet in containers."
echo "      Best for: Docker-based environments."
echo ""
if [ "$HAS_KUBECTL" = true ]; then
echo "  [3] Kubernetes"
echo "      Deploys to your existing k3s/k8s cluster."
echo "      Best for: multi-node clusters."
echo ""
fi

while true; do
    read -p "  Choose [1/2/3]: " MODE
    case "$MODE" in
        1) DEPLOY_MODE="standalone"; break ;;
        2) DEPLOY_MODE="docker"; break ;;
        3)
            if [ "$HAS_KUBECTL" = true ]; then
                DEPLOY_MODE="kubernetes"; break
            else
                echo "  Kubernetes not detected. Choose 1 or 2."
            fi
            ;;
        *) echo "  Please enter 1, 2, or 3." ;;
    esac
done

echo ""
ok "Deployment mode: $DEPLOY_MODE"

# -------------------------------------------------------
# Step 4: Ollama Setup
# -------------------------------------------------------
if [ "$DEPLOY_MODE" = "kubernetes" ]; then
    log "Step 4: Delegating to Kubernetes installer..."
    echo ""
    if [ -f "$SCRIPT_DIR/install.sh" ]; then
        exec "$SCRIPT_DIR/install.sh"
    else
        err "install.sh not found. Please run the Kubernetes install script manually."
        exit 1
    fi
fi

if [ "$DEPLOY_MODE" = "standalone" ]; then
    log "Step 4: Setting up Ollama..."

    if [ "$HAS_OLLAMA" = false ]; then
        echo ""
        echo "  Ollama is the AI model runtime. It needs to be installed."
        echo "  This will download and install Ollama from ollama.com."
        echo ""
        read -p "  Install Ollama now? [Y/n]: " INSTALL_OLLAMA
        INSTALL_OLLAMA=${INSTALL_OLLAMA:-Y}

        if [[ "$INSTALL_OLLAMA" =~ ^[Yy] ]]; then
            log "  Installing Ollama..."
            curl -fsSL https://ollama.com/install.sh | sh
            ok "  Ollama installed"
        else
            err "Ollama is required for standalone mode. Exiting."
            exit 1
        fi
    fi

    # Start Ollama if not running
    if ! curl -sf http://localhost:11434/api/tags &>/dev/null; then
        log "  Starting Ollama service..."
        if command -v systemctl &>/dev/null; then
            sudo systemctl start ollama 2>/dev/null || ollama serve &>/dev/null &
        else
            ollama serve &>/dev/null &
        fi
        sleep 3
    fi
    ok "  Ollama is running"

    # Pull models
    log "  Pulling AI models (this may take a while on first run)..."
    echo ""

    MODELS=("qwen3:8b" "qwen2.5-coder:7b" "nomic-embed-text")
    for model in "${MODELS[@]}"; do
        echo -e "  ${CYAN}Pulling ${model}...${NC}"
        ollama pull "$model"
        ok "  $model ready"
    done

    echo ""
    ok "  All models downloaded"
fi

if [ "$DEPLOY_MODE" = "docker" ]; then
    log "Step 4: Setting up Docker Compose..."

    if [ "$HAS_DOCKER" = false ]; then
        err "Docker is required for Docker Compose mode but not found."
        echo "  Install Docker first: https://docs.docker.com/engine/install/"
        exit 1
    fi

    if ! command -v docker compose &>/dev/null && ! command -v docker-compose &>/dev/null; then
        err "Docker Compose not found. Install it first."
        echo "  See: https://docs.docker.com/compose/install/"
        exit 1
    fi

    ok "  Docker Compose available"
fi

# -------------------------------------------------------
# Step 5: Install Silicon Valet
# -------------------------------------------------------
log "Step 5: Installing Silicon Valet..."

cd "$SCRIPT_DIR"

if [ "$DEPLOY_MODE" = "standalone" ]; then
    # Create virtual environment
    if [ ! -d ".venv" ]; then
        log "  Creating Python virtual environment..."
        $PYTHON_CMD -m venv .venv
    fi

    # Activate and install
    source .venv/bin/activate
    log "  Installing dependencies..."
    pip install --upgrade pip -q
    pip install -e . -q

    ok "  Silicon Valet installed"

    # Create data directories
    mkdir -p "$HOME/.silicon_valet/data"
    mkdir -p "$HOME/.silicon_valet/backups"
    ok "  Data directories created at ~/.silicon_valet/"
fi

if [ "$DEPLOY_MODE" = "docker" ]; then
    log "  Building and starting containers..."

    COMPOSE_CMD="docker compose"
    if ! docker compose version &>/dev/null 2>&1; then
        COMPOSE_CMD="docker-compose"
    fi

    $COMPOSE_CMD up -d --build

    echo ""
    log "  Waiting for services to start..."
    sleep 10

    # Pull models into the Ollama container
    log "  Pulling AI models into Ollama container..."
    OLLAMA_CONTAINER=$($COMPOSE_CMD ps -q ollama 2>/dev/null | head -1)
    if [ -n "$OLLAMA_CONTAINER" ]; then
        for model in "qwen3:8b" "qwen2.5-coder:7b" "nomic-embed-text"; do
            echo -e "  ${CYAN}Pulling ${model}...${NC}"
            docker exec "$OLLAMA_CONTAINER" ollama pull "$model"
            ok "  $model ready"
        done
    else
        warn "  Could not find Ollama container. You may need to pull models manually."
    fi

    ok "  Docker Compose deployment complete"
fi

# -------------------------------------------------------
# Step 6: Launch + Verify
# -------------------------------------------------------
log "Step 6: Verifying setup..."

if [ "$DEPLOY_MODE" = "standalone" ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Silicon Valet is ready!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "  To start Silicon Valet:"
    echo ""
    echo -e "    ${CYAN}cd $SCRIPT_DIR${NC}"
    echo -e "    ${CYAN}source .venv/bin/activate${NC}"
    echo -e "    ${CYAN}valet run${NC}"
    echo ""
    echo "  Or start the server in the background:"
    echo ""
    echo -e "    ${CYAN}valet-server &${NC}"
    echo -e "    ${CYAN}valet connect localhost${NC}"
    echo ""
    echo "  Silicon Valet will automatically detect your environment"
    echo "  and adapt to whatever is running on this server."
    echo ""
fi

if [ "$DEPLOY_MODE" = "docker" ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  Silicon Valet is ready!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "  The server is running in Docker."
    echo ""
    echo "  To connect:"
    echo ""
    echo -e "    ${CYAN}pip install -e .${NC}  (if not already installed)"
    echo -e "    ${CYAN}valet connect localhost${NC}"
    echo ""
    echo "  Or view logs:"
    echo ""
    echo -e "    ${CYAN}docker compose logs -f silicon-valet${NC}"
    echo ""
fi
