#!/usr/bin/env bash
# uninstall_rtk_uart2_service.sh
# Stop, disable, and remove the RTK UART2 injection systemd service.
set -euo pipefail

SERVICE_NAME="rtk-uart2-inject.service"
TARGET="/etc/systemd/system/${SERVICE_NAME}"

if [ ! -f "${TARGET}" ]; then
    echo "Service file ${TARGET} does not exist. Nothing to uninstall."
    exit 0
fi

echo "Stopping and disabling ${SERVICE_NAME} ..."
sudo systemctl stop "${SERVICE_NAME}" || true
sudo systemctl disable "${SERVICE_NAME}" || true

echo "Removing ${TARGET} ..."
sudo rm -f "${TARGET}"

sudo systemctl daemon-reload

echo ""
echo "Done. Service stopped, disabled, and removed."
