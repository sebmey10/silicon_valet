#!/bin/bash
# Silicon Valet — Fully Offline Installer
# ========================================
#
# PREREQUISITES:
#   - k3s cluster running with kubectl access
#   - At least 2 worker nodes (32GB RAM each recommended)
#   - Docker or nerdctl available for building images
#   - models/ directory with pre-downloaded Ollama models
#
# MODEL PREPARATION (on an internet-connected machine):
#   ollama pull qwen3:8b
#   ollama pull qwen2.5-coder:7b
#   ollama pull nomic-embed-text
#   cp -r ~/.ollama/models/ /path/to/usb/models/
#
# USAGE:
#   ./install.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="silicon-valet"
MODELS_DIR="${SCRIPT_DIR}/models"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${CYAN}[$(date '+%H:%M:%S')]${NC} $*"; }
ok()   { echo -e "${GREEN}[$(date '+%H:%M:%S')] ✓${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date '+%H:%M:%S')] !${NC} $*"; }
err()  { echo -e "${RED}[$(date '+%H:%M:%S')] ✗${NC} $*"; }

# -------------------------------------------------------
# 1. Prerequisites check
# -------------------------------------------------------
log "Checking prerequisites..."

if ! command -v kubectl &>/dev/null; then
    err "kubectl not found. Install k3s first."
    exit 1
fi

if ! kubectl cluster-info &>/dev/null; then
    err "Cannot connect to Kubernetes cluster. Is k3s running?"
    exit 1
fi

NODE_COUNT=$(kubectl get nodes --no-headers 2>/dev/null | wc -l)
if [ "$NODE_COUNT" -lt 2 ]; then
    warn "Found ${NODE_COUNT} node(s). Silicon Valet is designed for 2+ worker nodes."
    warn "Continuing anyway — Ollama instances may share a node."
fi

ok "kubectl connected, ${NODE_COUNT} node(s) detected"

# -------------------------------------------------------
# 2. Check models directory
# -------------------------------------------------------
log "Checking models directory..."

if [ ! -d "$MODELS_DIR" ]; then
    err "Models directory not found: ${MODELS_DIR}"
    echo ""
    echo "  Silicon Valet requires pre-downloaded Ollama models."
    echo "  On an internet-connected machine, run:"
    echo ""
    echo "    ollama pull qwen3:8b"
    echo "    ollama pull qwen2.5-coder:7b"
    echo "    ollama pull nomic-embed-text"
    echo ""
    echo "  Then copy the models directory:"
    echo "    cp -r ~/.ollama/models/ ${SCRIPT_DIR}/models/"
    echo ""
    exit 1
fi

# Check for model blobs (Ollama stores models as blobs)
BLOB_COUNT=$(find "$MODELS_DIR" -type f 2>/dev/null | wc -l)
if [ "$BLOB_COUNT" -lt 1 ]; then
    err "Models directory appears empty. See instructions above."
    exit 1
fi

ok "Models directory found with ${BLOB_COUNT} files"

# -------------------------------------------------------
# 3. Build Silicon Valet Docker image
# -------------------------------------------------------
log "Building Silicon Valet Docker image..."

if command -v docker &>/dev/null; then
    BUILD_CMD="docker"
elif command -v nerdctl &>/dev/null; then
    BUILD_CMD="nerdctl"
else
    err "Neither docker nor nerdctl found. Cannot build image."
    exit 1
fi

cd "$SCRIPT_DIR"
$BUILD_CMD build -t silicon-valet:latest .

# Import into k3s containerd
log "Importing image into k3s..."
if command -v docker &>/dev/null; then
    docker save silicon-valet:latest | sudo k3s ctr images import -
else
    nerdctl save silicon-valet:latest | sudo k3s ctr images import -
fi

ok "Image built and imported"

# -------------------------------------------------------
# 4. Apply Kubernetes manifests
# -------------------------------------------------------
log "Applying Kubernetes manifests..."

kubectl apply -f deploy/

ok "Manifests applied"

# -------------------------------------------------------
# 5. Wait for pods to be ready
# -------------------------------------------------------
log "Waiting for pods to start (this may take a few minutes)..."

MAX_WAIT=300
ELAPSED=0
while [ $ELAPSED -lt $MAX_WAIT ]; do
    READY=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | grep -c "Running" || true)
    TOTAL=$(kubectl get pods -n "$NAMESPACE" --no-headers 2>/dev/null | wc -l || echo 0)

    log "  Pods: ${READY}/${TOTAL} running (${ELAPSED}s elapsed)"

    if [ "$READY" -eq "$TOTAL" ] && [ "$TOTAL" -gt 0 ]; then
        break
    fi

    sleep 10
    ELAPSED=$((ELAPSED + 10))
done

if [ "$READY" -ne "$TOTAL" ] || [ "$TOTAL" -eq 0 ]; then
    warn "Not all pods are running after ${MAX_WAIT}s. Checking status..."
    kubectl get pods -n "$NAMESPACE"
    echo ""
    warn "You may need to wait longer or check pod logs:"
    warn "  kubectl logs -n ${NAMESPACE} <pod-name>"
else
    ok "All ${TOTAL} pods running"
fi

# -------------------------------------------------------
# 6. Copy models into Ollama pods
# -------------------------------------------------------
log "Copying models into Ollama pods..."

WORKER01_POD=$(kubectl get pods -n "$NAMESPACE" -l node-role=worker01 --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)
WORKER02_POD=$(kubectl get pods -n "$NAMESPACE" -l node-role=worker02 --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)

if [ -n "$WORKER01_POD" ]; then
    log "  Copying models to ${WORKER01_POD} (worker-01)..."
    kubectl cp "$MODELS_DIR" "${NAMESPACE}/${WORKER01_POD}:/root/.ollama/models" 2>/dev/null || \
        warn "Failed to copy models to worker-01. You may need to copy manually."
    ok "  Models copied to worker-01"
else
    warn "Worker-01 Ollama pod not found"
fi

if [ -n "$WORKER02_POD" ]; then
    log "  Copying models to ${WORKER02_POD} (worker-02)..."
    kubectl cp "$MODELS_DIR" "${NAMESPACE}/${WORKER02_POD}:/root/.ollama/models" 2>/dev/null || \
        warn "Failed to copy models to worker-02. You may need to copy manually."
    ok "  Models copied to worker-02"
else
    warn "Worker-02 Ollama pod not found"
fi

# -------------------------------------------------------
# 7. Verify models loaded
# -------------------------------------------------------
log "Verifying models..."

if [ -n "$WORKER01_POD" ]; then
    log "  Models on worker-01:"
    kubectl exec -n "$NAMESPACE" "$WORKER01_POD" -- ollama list 2>/dev/null || \
        warn "Could not list models on worker-01"
fi

if [ -n "$WORKER02_POD" ]; then
    log "  Models on worker-02:"
    kubectl exec -n "$NAMESPACE" "$WORKER02_POD" -- ollama list 2>/dev/null || \
        warn "Could not list models on worker-02"
fi

# -------------------------------------------------------
# 8. Health check
# -------------------------------------------------------
log "Running health check..."

VALET_POD=$(kubectl get pods -n "$NAMESPACE" -l app=valet-core --no-headers -o custom-columns=":metadata.name" 2>/dev/null | head -1)
if [ -n "$VALET_POD" ]; then
    VALET_STATUS=$(kubectl get pod -n "$NAMESPACE" "$VALET_POD" -o jsonpath='{.status.phase}' 2>/dev/null)
    if [ "$VALET_STATUS" = "Running" ]; then
        ok "Valet core pod is running"
    else
        warn "Valet core pod status: ${VALET_STATUS}"
    fi
else
    warn "Valet core pod not found"
fi

# Get a node IP for connection
NODE_IP=$(kubectl get nodes -o jsonpath='{.items[0].status.addresses[?(@.type=="InternalIP")].address}' 2>/dev/null)
NODE_PORT=$(kubectl get svc -n "$NAMESPACE" valet -o jsonpath='{.spec.ports[0].nodePort}' 2>/dev/null || echo "30743")

# -------------------------------------------------------
# 9. Done!
# -------------------------------------------------------
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Silicon Valet installed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  Connect with:"
echo -e "    ${CYAN}valet connect ${NODE_IP:-<node-ip>}${NC} --port ${NODE_PORT}"
echo ""
echo "  Or install the CLI client first:"
echo -e "    ${CYAN}pip install .${NC}"
echo -e "    ${CYAN}valet connect ${NODE_IP:-<node-ip>}${NC}"
echo ""
echo "  Monitor pods:"
echo -e "    ${CYAN}kubectl get pods -n ${NAMESPACE} -w${NC}"
echo ""
echo "  View logs:"
echo -e "    ${CYAN}kubectl logs -n ${NAMESPACE} -l app=valet-core -f${NC}"
echo ""
