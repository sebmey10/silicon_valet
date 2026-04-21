#!/usr/bin/env bash
# prepare_usb.sh — Run this ONCE on your workstation to build the USB image.
#
# It takes a mounted USB stick and fills it with everything Silicon Valet needs
# to run on an air-gapped server:
#   - the repo itself (this directory)
#   - a pinned Python wheel cache (no pip downloads at install time)
#   - Ollama install script + pre-pulled GGUF model blobs
#   - the OpenWebUI docker image saved as a tarball
#   - the autorun.sh entrypoint the server operator runs
#
# Usage:
#   sudo ./usb/prepare_usb.sh /media/<you>/SILICON_VALET
#
# The USB must be formatted FAT32 or exFAT and have ≥ 32GB free (models are
# the bulk of it: qwen3:8b ~5GB, qwen2.5-coder:7b ~4.5GB, nomic-embed ~300MB).
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <usb_mount_path>" >&2
  echo "  e.g. $0 /media/you/SILICON_VALET" >&2
  exit 1
fi

USB_ROOT="$1"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ! -d "$USB_ROOT" ]]; then
  echo "error: $USB_ROOT is not a directory. Plug the USB in and pass the mount path." >&2
  exit 1
fi

echo "==> Preparing Silicon Valet USB at $USB_ROOT"
echo "    Source repo: $REPO_ROOT"

# 1) Copy the repo (without caches)
echo "==> [1/5] Copying repo..."
mkdir -p "$USB_ROOT/silicon_valet"
rsync -a --delete \
  --exclude '.git/' --exclude '.venv/' --exclude '__pycache__/' \
  --exclude '.pytest_cache/' --exclude 'usb/payload/' \
  --exclude '*.pyc' --exclude 'node_modules/' \
  "$REPO_ROOT/" "$USB_ROOT/silicon_valet/"

# 2) Download Python wheels for offline install
echo "==> [2/5] Downloading Python wheels (this takes a few minutes)..."
mkdir -p "$USB_ROOT/silicon_valet/usb/payload/wheels"
python3 -m pip download \
  -r "$REPO_ROOT/requirements.txt" \
  -d "$USB_ROOT/silicon_valet/usb/payload/wheels" \
  --platform manylinux2014_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --python-version 311 \
  --only-binary=:all: || {
    echo "    (cross-platform wheel download failed; falling back to native wheels)"
    python3 -m pip download \
      -r "$REPO_ROOT/requirements.txt" \
      -d "$USB_ROOT/silicon_valet/usb/payload/wheels"
  }

# 3) Pre-pull Ollama models if ollama is installed locally
echo "==> [3/5] Pre-pulling Ollama models..."
MODELS=("qwen3:8b" "qwen2.5-coder:7b" "nomic-embed-text")
if command -v ollama >/dev/null 2>&1; then
  for m in "${MODELS[@]}"; do
    echo "    pulling $m..."
    ollama pull "$m" || echo "    (failed to pull $m; will be pulled on the server instead)"
  done
  # Export Ollama's blob cache onto the USB
  OLLAMA_HOME="${OLLAMA_MODELS:-$HOME/.ollama}"
  if [[ -d "$OLLAMA_HOME" ]]; then
    mkdir -p "$USB_ROOT/silicon_valet/usb/payload/ollama"
    echo "    copying ollama blob cache (may take a while)..."
    rsync -a "$OLLAMA_HOME/" "$USB_ROOT/silicon_valet/usb/payload/ollama/"
  fi
else
  echo "    ollama not installed locally; skipping. The server will pull on first run."
fi

# 4) Save the Ollama + OpenWebUI docker images
echo "==> [4/5] Saving docker images (optional — for air-gapped docker hosts)..."
mkdir -p "$USB_ROOT/silicon_valet/usb/payload/images"
if command -v docker >/dev/null 2>&1; then
  docker pull ollama/ollama:latest >/dev/null && \
    docker save ollama/ollama:latest | gzip > "$USB_ROOT/silicon_valet/usb/payload/images/ollama.tar.gz"
  docker pull ghcr.io/open-webui/open-webui:main >/dev/null && \
    docker save ghcr.io/open-webui/open-webui:main | gzip > "$USB_ROOT/silicon_valet/usb/payload/images/openwebui.tar.gz"
else
  echo "    docker not installed; skipping image snapshot."
fi

# 5) Drop a top-level AUTORUN.sh at the USB root so the operator has one obvious file
echo "==> [5/5] Writing top-level AUTORUN.sh..."
cat > "$USB_ROOT/AUTORUN.sh" <<'EOF'
#!/usr/bin/env bash
# Plug this USB into the server, then run:
#   sudo bash AUTORUN.sh
# from the USB's mount point.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
exec bash "$HERE/silicon_valet/usb/autorun.sh" "$@"
EOF
chmod +x "$USB_ROOT/AUTORUN.sh"

# Also a friendly README at the root
cat > "$USB_ROOT/README.txt" <<EOF
Silicon Valet — Server Engineer Agent
======================================

1) Plug this USB into any Linux server.
2) Mount it if not auto-mounted:
     sudo mkdir -p /mnt/silicon_valet
     sudo mount /dev/sdXX /mnt/silicon_valet
3) Run:
     cd /mnt/silicon_valet
     sudo bash AUTORUN.sh
4) Wait 2–5 minutes. It will print a URL and a one-time token.
5) Open that URL in a browser (SSH tunnel is fine) and chat.

See silicon_valet/usb/README.md for full details and troubleshooting.
EOF

echo
echo "✅ USB prepared at $USB_ROOT"
echo "   Plug it into the target server and run:  sudo bash AUTORUN.sh"
du -sh "$USB_ROOT" 2>/dev/null || true
