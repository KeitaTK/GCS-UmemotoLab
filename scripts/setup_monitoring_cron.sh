#!/bin/bash
# Phase 7: monitoring.log を 5 分間隔で更新する cron 設定

set -euo pipefail

ROOT_DIR="/home/taki/GCS-UmemotoLab"
MONITOR_SCRIPT="$ROOT_DIR/scripts/monitor_backend.sh"
CRON_LINE="*/5 * * * * bash $MONITOR_SCRIPT"

if [ ! -f "$MONITOR_SCRIPT" ]; then
  echo "[ERROR] monitor script not found: $MONITOR_SCRIPT"
  exit 1
fi

TMP_CRON=$(mktemp)
crontab -l 2>/dev/null | grep -v "monitor_backend.sh" > "$TMP_CRON" || true
echo "$CRON_LINE" >> "$TMP_CRON"
crontab "$TMP_CRON"
rm -f "$TMP_CRON"

echo "[OK] Installed monitoring cron job: $CRON_LINE"
crontab -l | grep "monitor_backend.sh" || true
