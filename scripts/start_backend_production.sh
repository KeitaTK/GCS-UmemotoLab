#!/bin/bash
# Phase 7: Backend 本番環境テスト起動スクリプト

cd /home/taki/GCS-UmemotoLab

# 既存プロセスを停止
pkill -f 'python3 app/backend_server' 2>/dev/null || true
sleep 2

# 仮想環境を有効化してバックグラウンド実行
source .venv/bin/activate
nohup python3 -u app/backend_server.py >> backend_production.log 2>&1 &

# 起動確認
sleep 3
if pgrep -f 'python3 app/backend_server' > /dev/null; then
    echo "[OK] Backend started successfully (PID: $(pgrep -f 'python3 app/backend_server'))"
    tail -10 backend_production.log
else
    echo "[ERROR] Backend failed to start"
    tail -20 backend_production.log
fi
