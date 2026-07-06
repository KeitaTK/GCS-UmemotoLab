#!/bin/bash
# raspi/install.sh — Raspberry Pi 5 初回セットアップスクリプト
#
# 使用方法:
#   cd ~/GCS-UmemotoLab/raspi
#   bash install.sh
#
# 以下の処理を行います:
#   1. 依存パッケージのインストール
#   2. systemd サービス登録（自動起動）
#   3. mavlink-router 設定確認

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

echo "=== GCS-UmemotoLab Raspberry Pi Setup ==="
echo ""

# --------------------------------------------------
# 1. 依存パッケージのインストール
# --------------------------------------------------
echo "[1/4] Installing Python dependencies..."
if [ ! -d "$REPO_DIR/.venv" ]; then
    python3 -m venv "$REPO_DIR/.venv"
    echo "  Created virtual environment"
fi
source "$REPO_DIR/.venv/bin/activate"
pip install --upgrade pip -q
pip install -r "$SCRIPT_DIR/requirements.txt" -q
echo "  Dependencies installed"

# --------------------------------------------------
# 2. systemd サービスファイルの作成
# --------------------------------------------------
echo "[2/4] Creating systemd service..."
SERVICE_FILE="/etc/systemd/system/gcs-backend.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "  Service file already exists, skipping"
else
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=GCS Backend Server (Raspberry Pi)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=taki
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/.venv/bin/python $SCRIPT_DIR/backend_server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    echo "  Created $SERVICE_FILE"
fi

# --------------------------------------------------
# 3. UART 有効化確認
# --------------------------------------------------
echo "[3/4] Checking UART configuration..."
if grep -q "enable_uart=1" /boot/firmware/config.txt 2>/dev/null; then
    echo "  UART already enabled"
else
    echo "  WARNING: UART may not be enabled."
    echo "  Add 'enable_uart=1' and 'dtoverlay=uart0' to /boot/firmware/config.txt"
fi

# --------------------------------------------------
# 4. mavlink-router 設定確認
# --------------------------------------------------
echo "[4/4] Checking mavlink-router configuration..."
MLR_CONF="/etc/mavlink-router/main.conf"
if [ -f "$MLR_CONF" ]; then
    echo "  mavlink-router config found: $MLR_CONF"
    if systemctl is-active --quiet mavlink-router; then
        echo "  mavlink-router is running"
    else
        echo "  WARNING: mavlink-router is not running"
        echo "  Run: sudo systemctl start mavlink-router"
    fi
else
    echo "  WARNING: mavlink-router config not found."
    echo "  Create $MLR_CONF with:"
    echo "    [General]"
    echo "    [UartEndpoint pixhawk]"
    echo "    Device = /dev/ttyAMA0"
    echo "    Baud = 115200"
    echo "    [UdpEndpoint gcs]"
    echo "    Address = 0.0.0.0"
    echo "    Port = 14550"
    echo "    Mode = Server"
fi

echo ""
echo "=== Setup complete ==="
echo ""
echo "Start manually:  cd ~/GCS-UmemotoLab/raspi && python backend_server.py"
echo "Start via systemd: sudo systemctl start gcs-backend"
echo "Enable autostart:  sudo systemctl enable gcs-backend"
echo "View logs:         sudo journalctl -u gcs-backend -f"