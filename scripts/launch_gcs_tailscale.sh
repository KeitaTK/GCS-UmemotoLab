#!/bin/bash
# GCS Launch Script - Tailscale SSH Tunnel Mode
# Run this to connect to the real drone via Tailscale

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== GCS-UmemotoLab: Tailscale SSH Tunnel Mode ==="

# 1. Ensure socat bridge is running on Raspi
echo "[1/4] Setting up Raspi socat bridge..."
ssh raspi 'pkill socat 2>/dev/null; sleep 1
socat TCP-LISTEN:14551,fork,reuseaddr UDP:localhost:14550 &' 2>/dev/null &
sleep 2

# 2. Setup SSH tunnel (Mac:14551 -> Raspi:14551)
echo "[2/4] Establishing SSH tunnel..."
ssh -f -N -L 14551:localhost:14551 -o ConnectTimeout=15 -o ServerAliveInterval=30 raspi
sleep 2

# 3. Start UDP-TCP bridge
echo "[3/4] Starting UDP-TCP bridge..."
pkill -f udp_tcp_bridge 2>/dev/null
cd "$PROJECT_DIR"
python3 /tmp/udp_tcp_bridge.py &
sleep 1

# 4. Launch GCS
echo "[4/4] Starting GCS..."
export GCS_CONFIG_PATH="$PROJECT_DIR/config/gcs_sshtunnel.yml"
export PYTHONPATH="$PROJECT_DIR/app:$PYTHONPATH"

cd "$PROJECT_DIR"
source .venv/bin/activate
python app/main.py
