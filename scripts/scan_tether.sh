#!/bin/bash
# =============================================================================
# scan_tether.sh - テザリングネットワーク内の Raspberry Pi を検出して SSH 接続
# =============================================================================
#
# 使い方:
#   ./scan_tether.sh              # スキャンして接続
#   ./scan_tether.sh --scan-only  # スキャンのみ（接続しない）
#   ./scan_tether.sh --cmd "ls"   # スキャン後、見つかったRaspiでコマンド実行
#
# 前提:
#   - Mac がスマホのテザリングに接続済みであること
#   - Raspberry Pi も同じテザリングネットワークに接続済みであること
#   - SSH 公開鍵が Raspberry Pi に登録済みであること
# =============================================================================
set -euo pipefail

SSH_USER="taki"
SSH_KEY="$HOME/.ssh/id_ed25519"
SSH_OPTS="-o ConnectTimeout=3 -o StrictHostKeyChecking=accept-new -o BatchMode=yes -i $SSH_KEY"

# テザリングでよく使われるサブネット
TETHER_SUBNETS=("192.168.43" "192.168.42" "172.20.10" "192.168.137" "192.168.44")

SCAN_ONLY=false
REMOTE_CMD=""

# 引数解析
while [[ $# -gt 0 ]]; do
    case "$1" in
        --scan-only) SCAN_ONLY=true; shift ;;
        --cmd) REMOTE_CMD="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--scan-only] [--cmd 'command']"
            echo ""
            echo "Examples:"
            echo "  $0                  # スキャンして対話的SSH接続"
            echo "  $0 --scan-only      # 検出のみ"
            echo "  $0 --cmd 'hostname -I'"
            exit 0 ;;
        *) echo "不明なオプション: $1"; exit 1 ;;
    esac
done

echo "============================================"
echo " Raspberry Pi テザリング接続スキャナー"
echo "============================================"
echo ""

# 現在接続中のネットワークを確認
echo "[INFO] 現在のネットワーク接続を確認中..."
ACTIVE_IFACE=$(route -n get default 2>/dev/null | grep interface | awk '{print $2}')
if [ -z "$ACTIVE_IFACE" ]; then
    echo "[ERROR] デフォルトルートが見つかりません。テザリングに接続されていますか？"
    exit 1
fi

MY_IP=$(ifconfig "$ACTIVE_IFACE" 2>/dev/null | grep "inet " | awk '{print $2}')
if [ -z "$MY_IP" ]; then
    echo "[ERROR] IPアドレスが取得できません。インターフェース: $ACTIVE_IFACE"
    exit 1
fi

echo "[INFO] 接続中インターフェース: $ACTIVE_IFACE"
echo "[INFO] あなたのIPアドレス: $MY_IP"
echo ""

# アクティブなサブネットを特定
FOUND_SUBNET=""
for subnet in "${TETHER_SUBNETS[@]}"; do
    if [[ "$MY_IP" == ${subnet}.* ]]; then
        FOUND_SUBNET="$subnet"
        break
    fi
done

if [ -z "$FOUND_SUBNET" ]; then
    echo "[WARN] IPが標準的なテザリングサブネットではありません ($MY_IP)"
    echo "[INFO] 現在のサブネット全体をスキャンします..."
    FOUND_SUBNET=$(echo "$MY_IP" | sed 's/\.[0-9]*$//')
fi

echo "[INFO] スキャン対象サブネット: ${FOUND_SUBNET}.0/24"
echo ""

FOUND_HOSTS=()

# --- mDNS チェック（最速・NAT64環境でも使える） ---
echo "[SCAN] mDNS (raspi5.local) をチェック..."
mdns_result=$(ssh $SSH_OPTS ${SSH_USER}@raspi5.local "echo 'OK' && hostname" 2>/dev/null || true)
if echo "$mdns_result" | grep -q "OK"; then
    mdns_host=$(echo "$mdns_result" | tail -1)
    echo "  OK 発見！ ${SSH_USER}@raspi5.local (hostname: $mdns_host)"
    FOUND_HOSTS+=("raspi5.local")
fi

# --- スキャン実行 ---
echo "[SCAN] IPで Raspberry Pi を検索中..."
echo ""

PRIORITY_IPS=("${FOUND_SUBNET}.19" "${FOUND_SUBNET}.11" "${FOUND_SUBNET}.100" "${FOUND_SUBNET}.101" "${FOUND_SUBNET}.10")

echo "[SCAN] 優先IPをチェック中..."
for ip in "${PRIORITY_IPS[@]}"; do
    if [ "$ip" = "$MY_IP" ]; then continue; fi
    result=$(ssh $SSH_OPTS ${SSH_USER}@${ip} "echo 'OK' && hostname" 2>/dev/null || true)
    if echo "$result" | grep -q "OK"; then
        host=$(echo "$result" | tail -1)
        echo "  OK 発見！ ${SSH_USER}@${ip} (hostname: $host)"
        FOUND_HOSTS+=("$ip")
    fi
done

if [ ${#FOUND_HOSTS[@]} -eq 0 ]; then
    echo "[SCAN] 優先IPでは見つかりませんでした。フルスキャンを実行..."
    for i in $(seq 1 254); do
        ip="${FOUND_SUBNET}.${i}"
        if [ "$ip" = "$MY_IP" ]; then continue; fi
        skip=false
        for pip in "${PRIORITY_IPS[@]}"; do
            if [ "$ip" = "$pip" ]; then skip=true; break; fi
        done
        if $skip; then continue; fi
        (
            result=$(ssh $SSH_OPTS ${SSH_USER}@${ip} "echo 'OK'" 2>/dev/null || true)
            if [ "$result" = "OK" ]; then echo "FOUND $ip"; fi
        ) &
        if [ $((i % 50)) -eq 0 ]; then wait; fi
    done
    wait
    echo ""
fi

if [ ${#FOUND_HOSTS[@]} -eq 0 ]; then
    echo "============================================"
    echo " Raspberry Pi が見つかりませんでした"
    echo "============================================"
    echo ""
    echo "考えられる原因:"
    echo "  1. Raspberry Pi が同じテザリングネットワークに未接続"
    echo "  2. Raspberry Pi の SSH サーバーが未起動"
    echo "  3. SSH 公開鍵が Raspberry Pi に未登録"
    echo ""
    echo "対処:"
    echo "  Raspi側で 'sudo systemctl status ssh' を確認"
    echo "  Raspi側で 'ip a' を実行してIPを確認"
    echo "  手動接続: ssh taki@${FOUND_SUBNET}.xxx"
    exit 1
fi

echo "============================================"
echo " 検出された Raspberry Pi: ${#FOUND_HOSTS[@]} 台"
echo "============================================"

if [ ${#FOUND_HOSTS[@]} -eq 1 ]; then
    TARGET_IP="${FOUND_HOSTS[0]}"
    echo "接続先: ${SSH_USER}@${TARGET_IP}"
    if $SCAN_ONLY; then
        echo "[DONE] スキャン完了。IP: $TARGET_IP"
        exit 0
    fi
    if [ -n "$REMOTE_CMD" ]; then
        ssh $SSH_OPTS ${SSH_USER}@${TARGET_IP} "$REMOTE_CMD"
    else
        ssh $SSH_OPTS ${SSH_USER}@${TARGET_IP}
    fi
else
    for i in "${!FOUND_HOSTS[@]}"; do
        echo "  [$((i+1))] ${SSH_USER}@${FOUND_HOSTS[$i]}"
    done
    read -rp "接続先の番号を入力: " choice
    TARGET_IP="${FOUND_HOSTS[$((choice-1))]}"
    if $SCAN_ONLY; then exit 0; fi
    if [ -n "$REMOTE_CMD" ]; then
        ssh $SSH_OPTS ${SSH_USER}@${TARGET_IP} "$REMOTE_CMD"
    else
        ssh $SSH_OPTS ${SSH_USER}@${TARGET_IP}
    fi
fi
