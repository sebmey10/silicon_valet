# Silicon Valet — USB Edition

Plug a USB stick into any Linux server. Run one command. Two to five minutes
later the server has a local AI engineer running on it, reachable through a
web chat UI on loopback. Everything is offline-capable.

## What's on the USB

```
USB_ROOT/
├── AUTORUN.sh                 # one-liner wrapper the operator runs
├── README.txt                 # short plain-text steps
└── silicon_valet/             # full repo
    └── usb/
        ├── autorun.sh         # real bootstrap (called by AUTORUN.sh)
        ├── prepare_usb.sh     # you run this on your workstation
        └── payload/
            ├── wheels/        # pre-downloaded Python wheels
            ├── ollama/        # pre-pulled Ollama model blobs
            └── images/        # docker image tarballs
```

## Workflow

### On your workstation (once, to build the USB)

```bash
# 1. Mount an empty USB stick formatted FAT32/exFAT (≥ 32 GB).
lsblk               # find the device, e.g. /dev/sdb1
sudo mkdir -p /mnt/silicon_valet_usb
sudo mount /dev/sdb1 /mnt/silicon_valet_usb

# 2. Clone the repo and prepare the USB.
git clone https://github.com/your-org/silicon_valet.git
cd silicon_valet
sudo ./usb/prepare_usb.sh /mnt/silicon_valet_usb

# 3. Eject.
sudo umount /mnt/silicon_valet_usb
```

`prepare_usb.sh` will:

1. Copy the repo onto the stick.
2. Download all Python wheels (`pip download -r requirements.txt`).
3. Pull `qwen3:8b`, `qwen2.5-coder:7b`, and `nomic-embed-text` into your
   local Ollama and copy the blob cache onto the stick.
4. Save the `ollama/ollama` and `ghcr.io/open-webui/open-webui` docker
   images as `.tar.gz` files.
5. Drop `AUTORUN.sh` at the USB root.

> Note: Linux doesn't support Windows-style USB auto-run — the operator
> still has to type one command. That's intentional: nothing executes
> without explicit consent on a production box.

### On the target server (every time you want to use it)

```bash
# 1. Plug the USB in.
# 2. Mount it (some distros auto-mount, most servers do not).
sudo mkdir -p /mnt/usb
sudo mount /dev/sdb1 /mnt/usb     # replace /dev/sdb1 with your stick

# 3. Run the bootstrap.
cd /mnt/usb
sudo bash AUTORUN.sh
```

That's the entire server-side flow. `autorun.sh` figures out the rest.

## What autorun.sh does

1. **Environment detection** — distro, systemd vs. other init, docker/podman
   presence, k3s cluster detection, RAM & CPU. Picks the smallest model that
   will fit (qwen3:8b → qwen2.5-coder:7b → phi4-mini).
2. **Install mode selection**:
   - `k3s` if a k3s cluster is reachable → applies `deploy/`.
   - `docker` if docker is installed and running → brings up
     `docker-compose.yml` (Ollama + Silicon Valet + OpenWebUI).
   - `standalone` otherwise → creates a Python venv, installs offline from
     `wheels/`, registers a `silicon-valet` systemd unit, and starts OpenWebUI
     as a single docker container if possible.
3. **Offline import** — seeds `/var/lib/silicon_valet/ollama_data/` with the
   model blobs from the USB so the Ollama container never has to reach the
   internet. Loads docker image tarballs with `docker load`.
4. **Auth** — generates a bearer token on first run, persists it at
   `/var/lib/silicon_valet/auth.token` (mode 600). The token gates both the
   WebSocket CLI and the OpenWebUI → OpenAI-compat API path.
5. **Binding** — everything binds to `127.0.0.1` by default. Nothing goes on
   the LAN without an explicit action. Reach the UI by SSH-tunnelling:
   `ssh -L 3000:127.0.0.1:3000 <server>`.
6. **Print** — the UI URL and the auth token.

## Connecting

### Browser (recommended)

```bash
ssh -L 3000:127.0.0.1:3000 <server>
# open http://localhost:3000 in your browser
# create the first admin account, done — chat is live
```

### CLI

```bash
# from the same box:
sudo /opt/silicon_valet/.venv/bin/valet connect 127.0.0.1 \
  --token $(sudo cat /var/lib/silicon_valet/auth.token)
```

## Network device support (Cisco, Nokia, Adtran)

Drop a YAML inventory file at `/etc/silicon_valet/devices.yaml`:

```yaml
devices:
  core-rtr-01:
    host: 10.0.0.1
    platform: cisco_ios
    username: netops
    password_env: SV_DEVICE_PW      # read from env var, not stored here
  dslam-42:
    host: 10.0.5.42
    platform: nokia_sros
    username: admin
    password_env: SV_DEVICE_PW
  cpe-site-7:
    host: 10.10.7.1
    platform: adtran_os
    username: admin
    password_env: SV_DEVICE_PW
```

Then just talk to the agent: *"Check interface status on core-rtr-01"*,
*"Why is OSPF not forming with dslam-42?"*, *"Save config on cpe-site-7."*
The Cisco / Nokia / Adtran packs light up whenever devices of that platform
appear in the inventory.

**Read-only `show` / `display` commands are GREEN (auto-execute).**
**Config changes are YELLOW — the CLI prompts; the web UI denies by default
unless you set `SV_HTTP_AUTO_APPROVE_YELLOW=true`.**
**Reboots / erase / factory-reset are RED — always require explicit
approval at the CLI.**

## Making it LAN-accessible (with explicit consent)

If you want colleagues on the same network to reach the UI without SSH:

```bash
# Edit /opt/silicon_valet/.env on the server
SV_BIND=0.0.0.0
# Then restart
docker compose -f /opt/silicon_valet/docker-compose.yml up -d
```

Because every connection still needs the bearer token, this is safe on a
trusted LAN. For untrusted networks, keep it on loopback and use
`ssh -L` or WireGuard.

## Uninstall

```bash
sudo docker compose -f /opt/silicon_valet/docker-compose.yml down -v
sudo systemctl disable --now silicon-valet.service 2>/dev/null || true
sudo rm -f /etc/systemd/system/silicon-valet.service
sudo rm -rf /opt/silicon_valet /var/lib/silicon_valet
```

## Troubleshooting

| Problem | What to do |
|---|---|
| `AUTORUN.sh: command not found` | You're not at the USB root. `cd` to the mount point. |
| Models pull-timeout on bare metal | The USB's `payload/ollama/` didn't make it — copy it to `~/.ollama` manually and re-run. |
| OpenWebUI shows "no models available" | `SV_AUTH_TOKEN` mismatch. Check `/var/lib/silicon_valet/auth.token` and the `OPENAI_API_KEY` env on the openwebui container. |
| "Command denied by user" when chatting | YELLOW/RED changes over OpenWebUI are denied by default. Use the CLI for approval, or set `SV_HTTP_AUTO_APPROVE_YELLOW=true` if you accept the risk. |
| netmiko can't reach a device | Test manually: `ssh netops@<host>`. Check the inventory `platform` key — it must match a [netmiko device_type](https://ktbyers.github.io/netmiko/PLATFORMS.html). |
