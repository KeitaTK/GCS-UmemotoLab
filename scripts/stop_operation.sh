#!/usr/bin/env bash
# ============================================================================
# stop_operation.sh — RTCM注入・GPSデータ収集 全プロセス停止
# ============================================================================
#
# Usage:
#   bash scripts/stop_operation.sh
# ============================================================================

RASPI_HOST="${1:-100.69.75.96}"

echo "=== オペレーション停止 ==="

echo "[1/4] Mac側 基地局停止..."
pkill -f rtk_base_station_v2.py 2>/dev/null && echo "  ✓" || echo "  (not running)"

echo "[2/4] Mac側 ブリッジ停止..."
pkill -f udp_tcp_bridge.py 2>/dev/null && echo "  ✓" || echo "  (not running)"

echo "[3/4] Mac側 GCSサーバー停止..."
pkill -f "app/main.py" 2>/dev/null && echo "  ✓" || echo "  (not running)"

echo "[4/4] Raspi側 rtk_forwarder停止..."
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
    "taki@${RASPI_HOST}" \
    "pkill -f rtk_forwarder_service.py" 2>/dev/null && echo "  ✓" || echo "  (not running or SSH failed)"

# SSHトンネルクリーンアップ
pkill -f "ssh.*-L.*45760" 2>/dev/null && echo "  SSH tunnel: cleaned" || true

echo ""
echo "=== 停止完了 ==="
