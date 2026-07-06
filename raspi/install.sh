#!/bin/bash
# raspi/install.sh — Raspberry Pi 5 初回セットアップスクリプト
#
# 使用方法:
#   cd ~/GCS-UmemotoLab/raspi
#   bash install.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"
VENV_DIR="$REPO_DIR/.venv"
CURRENT_USER="$USER"  # 実行ユーザーを動的に取得

echo "=== GCS-UmemotoLab Raspberry Pi Setup ==="
echo ""

# --------------------------------------------------
# 1. 依存パッケージのインストール（仮想環境）
# --------------------------------------------------
echo "[1/5] Installing Python dependencies into virtual environment..."
if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
    echo "  Created virtual environment at $VENV_DIR"
fi

# source を使わず、仮想環境内の pip を直接指定して安全にインストール
"$VENV_DIR/bin/pip" install --upgrade pip -q
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt" -q
echo "  Dependencies installed"

# --------------------------------------------------
# 2. systemd サービスファイルの作成
# --------------------------------------------------
echo "[2/5] Creating systemd service..."
SERVICE_FILE="/etc/systemd/system/gcs-backend.service"
if [ -f "$SERVICE_FILE" ]; then
    echo "  Service file already exists, skipping"
else
    # Userを動的に設定し、ExecStartに仮想環境のPythonをフルパスで指定
    sudo tee "$SERVICE_FILE" > /dev/null << EOF
[Unit]
Description=GCS Backend Server (Raspberry Pi)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$REPO_DIR
ExecStart=$VENV_DIR/bin/python $SCRIPT_DIR/backend_server.py
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF
    echo "  Created $SERVICE_FILE"
    
    # システムに新しいサービスファイルを認識させる
    sudo systemctl daemon-reload
    echo "  Reloaded systemd daemon"
fi

# --------------------------------------------------
# 3. UART 有効化確認
# --------------------------------------------------
echo "[3/5] Checking UART configuration..."
if grep -q "enable_uart=1" /boot/firmware/config.txt 2>/dev/null; then
    echo "  UART already enabled"
else
    echo "  WARNING: UART may not be enabled."
    echo "  Add 'enable_uart=1' and 'dtoverlay=uart0' to /boot/firmware/config.txt"
fi

# --------------------------------------------------
# 4. mavlink-router ソースビルドとインストール
# --------------------------------------------------
echo "[4/5] Building mavlink-router from source..."
MAVLINK_BUILD_DIR="/tmp/mavlink-router-build"

if command -v mavlink-routerd &>/dev/null; then
    echo "  mavlink-router already installed"
else
    # ビルドに必要なパッケージをインストール
    sudo apt update -qq
    sudo apt install -y -qq git meson ninja-build pkg-config python3-pip 2>&1 | tail -1

    # ソースをクローン（--depth 1 で高速化）
    if [ ! -d "$MAVLINK_BUILD_DIR" ]; then
        git clone --depth 1 https://github.com/mavlink-router/mavlink-router.git "$MAVLINK_BUILD_DIR"
    fi

    cd "$MAVLINK_BUILD_DIR"
    git submodule update --init --recursive

    # Meson ビルド & インストール
    meson setup build .
    ninja -C build
    sudo ninja -C build install

    cd "$REPO_DIR"
    echo "  mavlink-router built and installed"
fi

MLR_CONF="/etc/mavlink-router/main.conf"
if [ -f "$MLR_CONF" ]; then
    echo "  mavlink-router config already exists, skipping"
else
    sudo mkdir -p /etc/mavlink-router
    sudo tee "$MLR_CONF" > /dev/null << 'EOF'
[General]
ReportStats=true

[UartEndpoint pixhawk]
Device = /dev/ttyAMA0
Baud = 115200

[UdpEndpoint gcs]
Address = 0.0.0.0
Port = 14550
Mode = Server
EOF
    echo "  Created $MLR_CONF"
fi

sudo systemctl enable mavlink-router
sudo systemctl restart mavlink-router
echo "  mavlink-router enabled and started"

# --------------------------------------------------
# 5. gcs-backend サービス起動
# --------------------------------------------------
echo "[5/5] Starting gcs-backend service..."
sudo systemctl enable gcs-backend
sudo systemctl restart gcs-backend
echo "  gcs-backend enabled and started"

echo ""
echo "=== Setup complete ==="
echo ""
echo "View logs:  sudo journalctl -u gcs-backend -f"
echo "View mavlink-router logs:  sudo journalctl -u mavlink-router -f"
echo ""
echo "Pixhawk と Raspi が UART 接続されていれば、すぐにテレメトリが流れ始めます。"
echo "PC側からは Raspi の IP:14550 で UDP 受信可能です。"
