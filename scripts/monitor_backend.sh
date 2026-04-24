#!/bin/bash
# Phase 7: Backend 本番環境テスト - 監視・データ収集スクリプト

cd /home/taki/GCS-UmemotoLab

# ステップ 1: 現在のプロセス状態を記録
echo "=== Phase 7 Monitoring - $(date) ===" >> monitoring.log
ps aux | grep -E 'backend_server.*python' | grep -v grep >> monitoring.log 2>&1
echo "PID Count: $(pgrep -f 'python3 app/backend_server' | wc -l)" >> monitoring.log

# ステップ 2: システムリソース監視
echo "--- System Resources ---" >> monitoring.log
free -h >> monitoring.log
echo "--- CPU Usage ---" >> monitoring.log
top -bn1 | head -5 >> monitoring.log

# ステップ 3: Backend ログの最新情報を確認
echo "--- Backend Log (Latest 30 lines) ---" >> monitoring.log
tail -30 backend_production.log >> monitoring.log
echo "" >> monitoring.log

# ステップ 4: Pixhawk 接続状態をチェック
echo "--- Pixhawk Connection Status ---" >> monitoring.log
tail -10 backend_production.log | grep -E 'heartbeat|Active drones' >> monitoring.log || echo "No heartbeat info found" >> monitoring.log
echo "" >> monitoring.log

echo "[OK] Monitoring data recorded at $(date)" >> monitoring.log
