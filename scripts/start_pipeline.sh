#!/bin/bash
cd ~/GCS-UmemotoLab
source .venv/bin/activate
export PYTHONPATH=$PWD/app
echo "SSH tunnel..."
ssh -f -L 14551:localhost:14551 -o ConnectTimeout=15 -o ServerAliveInterval=30 -o StrictHostKeyChecking=no -o 'ProxyCommand=/opt/homebrew/bin/tailscale nc %h %p' raspi 'sleep 99999'
sleep 6
echo "Bridge..."
python scripts/udp_tcp_bridge.py 14552 14551 &
sleep 3
echo "Backend connect..."
curl -s -X POST http://localhost:8000/api/disconnect 2>/dev/null
sleep 1
curl -s -X POST http://localhost:8000/api/connect -H 'Content-Type: application/json' -d '{"config_path":"config/gcs_local.yml"}'
echo "Done! http://localhost:8000/"
