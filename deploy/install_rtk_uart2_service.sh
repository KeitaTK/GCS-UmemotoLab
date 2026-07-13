#!/usr/bin/env bash
# install_rtk_uart2_service.sh
# Copy the RTK UART2 injection systemd service and enable it.
set -euo pipefail

SERVICE_NAME="rtk-uart2-inject.service"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_FILE="${SCRIPT_DIR}/${SERVICE_NAME}"
TARGET="/etc/systemd/system/${SERVICE_NAME}"

if [ ! -f "${SERVICE_FILE}" ]; then
    echo "ERROR: ${SERVICE_FILE} not found. Run this script from the deploy/ directory."
    exit 1
fi

echo "Installing ${SERVICE_NAME} ..."
sudo cp "${SERVICE_FILE}" "${TARGET}"
sudo chmod 644 "${TARGET}"

sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"

echo ""
echo "Done. Service installed and enabled."
echo ""
echo "  Start now:       sudo systemctl start ${SERVICE_NAME}"
echo "  Check status:    systemctl status ${SERVICE_NAME}"
echo "  Follow logs:     journalctl -u ${SERVICE_NAME} -f"
