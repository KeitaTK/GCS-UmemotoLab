#!/bin/bash
# RTK Full Pipeline + Monitor
# Usage: bash scripts/rtk_monitor.sh
set -e
cd ~/GCS-UmemotoLab
source .venv/bin/activate

echo "=== RTK Pipeline Startup ==="

# 1. Kill any existing bridge/SSH
pkill -f 'udp_tcp_bridge' 2>/dev/null || true
pkill -f 'ssh.*14551.*raspi' 2>/dev/null || true

# 2. Start RTK Base Station (port 2101)
echo "[1/4] Starting RTK Base Station..."
python3 -c "
import subprocess, sys
p = subprocess.Popen([sys.executable, '-u', 'rtk_tools/rtk_base_station.py',
    '--serial-port', '/dev/tty.usbmodem113301', '--tcp-port', '2101', '--log-level', 'INFO'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, start_new_session=True)
print(f'Base PID={p.pid}')
"
sleep 5

# Verify RTCM
python3 -c "
import socket
s=socket.socket(); s.settimeout(10)
s.connect(('127.0.0.1',2101))
d=s.recv(1024)
assert d[0]==0xD3, f'Bad RTCM header: 0x{d[0]:02X}'
print(f'RTCM OK: {len(d)}b')
s.close()
" || { echo "ERROR: RTCM not flowing"; exit 1; }

# 3. SSH Tunnel
echo "[2/4] SSH Tunnel to Raspi..."
python3 -c "
import subprocess
p = subprocess.Popen(
    ['ssh', '-N', '-L', '14551:localhost:14551',
     '-o', 'ConnectTimeout=15', '-o', 'ServerAliveInterval=30',
     '-o', 'StrictHostKeyChecking=no',
     '-o', 'ProxyCommand=/opt/homebrew/bin/tailscale nc %h %p',
     'raspi'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
print(f'SSH PID={p.pid}')
"
sleep 12

# 4. Bridge
echo "[3/4] UDP-TCP Bridge..."
python3 -c "
import subprocess, sys
p = subprocess.Popen([sys.executable, '-u', 'scripts/udp_tcp_bridge.py', '14552', '14551'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
print(f'Bridge PID={p.pid}')
"
sleep 5

# 5. GCS Connect
echo "[4/4] GCS Backend Connect..."
curl -s -X POST http://localhost:8000/api/disconnect 2>/dev/null || true
sleep 2
curl -s -X POST http://localhost:8000/api/connect \
    -H 'Content-Type: application/json' \
    -d '{"config_path":"config/gcs_local.yml"}'
sleep 10

# Verify MAVLink
STATUS=$(curl -s http://localhost:8000/api/status)
echo "Status: $STATUS" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'MAVLink: connected={d[\"connection\"][\"is_connected\"]} drones={d[\"drones_connected\"]}')"

echo "=== Pipeline Ready ==="
