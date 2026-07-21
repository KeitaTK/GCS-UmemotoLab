#!/usr/bin/env bash
# ============================================================================
# operation_full.sh — 正しいシステム構成でRTCM注入とGPS誤差データ収集を行う
# ============================================================================
#
# システム構成:
#   Mac (u-blox F9P) ──TCP:2101──> Raspi (rtk_forwarder) ──/dev/ttyAMA4──> F9P Rover (CAN2→Pixhawk)
#                                        │                        UART2: RTCM注入専用
#   Mac (GCS) <──SSH Tunnel── Raspi (mavlink-router) ──/dev/ttyAMA0──> Pixhawk (MAVLink)
#                                        │
#   Fix監視: MAVLink GPS_RAW_INT.fix_type (GCS REST API)  ← gcs_fix_monitor.py (新)
#   ⛔ f9p_fix_monitor.py (UBX経由) は非推奨
#
# キー情報:
#   Raspi IP      : 100.69.75.96  (Tailscale)
#   Mac u-blox    : /dev/tty.usbmodem*
#   Raspi MAVLink : /dev/ttyAMA0   (GPIO8,10,11 → Pixhawk TELEM1)
#   Raspi RTCM    : /dev/ttyAMA4   (GPIO12,13 → F9P Rover)
#   Pixhawk→F9P   : CAN2
#
# Usage:
#   chmod +x scripts/operation_full.sh
#   ./scripts/operation_full.sh
#   ./scripts/operation_full.sh --samples 30 --output logs/gps_error.csv
# ============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_DIR="${PROJECT_DIR}/config"
LOG_DIR="${PROJECT_DIR}/logs"

RASPI_HOST="100.69.75.96"
MAVLINK_TCP_PORT="5760"
BRIDGE_UDP_PORT="14552"
GCS_API_PORT="8000"
RTCM_TCP_PORT="2101"
SAMPLE_COUNT="30"
OUTPUT_CSV=""
SKIP_UBLOX_CHECK=false
SKIP_RASPI_SETUP=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --raspi-host) RASPI_HOST="$2"; shift 2 ;;
        --samples) SAMPLE_COUNT="$2"; shift 2 ;;
        --output) OUTPUT_CSV="$2"; shift 2 ;;
        --skip-ublox-check) SKIP_UBLOX_CHECK=true; shift ;;
        --skip-raspi-setup) SKIP_RASPI_SETUP=true; shift ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo "  --raspi-host HOST    Raspi Tailscale IP (default: 100.69.75.96)"
            echo "  --samples N          サンプル数 (default: 30)"
            echo "  --output PATH        CSV出力パス"
            echo "  --skip-ublox-check   u-blox確認をスキップ"
            echo "  --skip-raspi-setup   Raspi側セットアップをスキップ"
            exit 0 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

cd "$PROJECT_DIR"
[ -f .venv/bin/activate ] && source .venv/bin/activate
mkdir -p "$LOG_DIR"

if [ -z "$OUTPUT_CSV" ]; then
    TIMESTAMP=$(date +%Y%m%d_%H%M%S)
    OUTPUT_CSV="${LOG_DIR}/gps_error_${TIMESTAMP}.csv"
fi

echo ""
echo "============================================================"
echo "  GPS誤差データ収集 オペレーション"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo "  Raspi        : ${RASPI_HOST}"
echo "  RTCM TCP     : ${RTCM_TCP_PORT}"
echo "  MAVLink TCP  : ${MAVLINK_TCP_PORT}"
echo "  サンプル数   : ${SAMPLE_COUNT}"
echo "  出力CSV      : ${OUTPUT_CSV}"
echo "============================================================"
echo ""
# ===================================================================
# STEP 1: u-blox 確認
# ===================================================================
echo "━━━ [1/7] u-blox 確認 ━━━"
UBLOX_PORT=""

if [ "$SKIP_UBLOX_CHECK" = true ]; then
    echo "  SKIP (--skip-ublox-check)"
else
    UBLOX_CANDIDATES=$(ls /dev/tty.usbmodem* 2>/dev/null || true)
    if [ -z "$UBLOX_CANDIDATES" ]; then
        echo "  ✗ /dev/tty.usbmodem* が見つかりません"
        echo "    → u-blox F9PのUSB接続を確認"
        echo "    → スキップするには --skip-ublox-check"
        exit 1
    fi
    UBLOX_PORT=$(echo "$UBLOX_CANDIDATES" | head -1)
    echo "  ✓ 検出: ${UBLOX_PORT}"

    echo "  NMEA受信テスト中 (3秒)..."
    stty -f "$UBLOX_PORT" 38400 2>/dev/null || true
    NMEA_DATA=$(timeout 3 cat "$UBLOX_PORT" 2>/dev/null | head -5 || true)
    if echo "$NMEA_DATA" | grep -q '\$G[NP]GGA'; then
        echo "  ✓ GGA sentence received — u-blox OK"
    else
        echo "  ⚠ GGA未受信（基地局起動時にF9P設定が実行されます）"
    fi
fi

if [ -n "$UBLOX_PORT" ]; then
    echo "  base_station.json serial_port → ${UBLOX_PORT}"
    sed -i '' "s|\"serial_port\": \".*\"|\"serial_port\": \"${UBLOX_PORT}\"|" "${CONFIG_DIR}/base_station.json"
fi

# ===================================================================
# STEP 2: RTK基地局起動（TCP:2101）
# ===================================================================
echo "━━━ [2/7] RTK基地局起動（TCP:${RTCM_TCP_PORT}） ━━━"

pkill -f rtk_base_station_v2.py 2>/dev/null || true
sleep 1

nohup python rtk_tools/rtk_base_station_v2.py \
    --config "${CONFIG_DIR}/base_station.json" \
    --tcp-port "$RTCM_TCP_PORT" \
    > "${LOG_DIR}/rtk_base_station.log" 2>&1 &

BASE_PID=$!
echo "  ✓ 基地局起動 (PID: ${BASE_PID})"
echo "  Log: ${LOG_DIR}/rtk_base_station.log"

echo "  基地局の準備を待っています（F9P設定 + RTCM出力開始）..."
for i in $(seq 1 20); do
    sleep 1
    if grep -q "RTK Base Station v2 started successfully" "${LOG_DIR}/rtk_base_station.log" 2>/dev/null; then
        echo "  ✓ 基地局準備完了"
        break
    fi
    if [ $i -eq 20 ]; then
        echo "  ⚠ 基地局の準備完了メッセージ未検出"
        echo "    → tail -f ${LOG_DIR}/rtk_base_station.log で確認"
    fi
done

sleep 2
if lsof -i "TCP:${RTCM_TCP_PORT}" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    echo "  ✓ TCP:${RTCM_TCP_PORT} LISTEN 確認"
else
    echo "  ⚠ TCP:${RTCM_TCP_PORT} がLISTENしていません"
fi
echo ""

# ===================================================================
# STEP 3: SSHトンネル + Bridge起動
# ===================================================================
echo "━━━ [3/7] SSHトンネル確立 + Bridge起動 ━━━"

pkill -f "ssh.*-L.*45760" 2>/dev/null || true
pkill -f udp_tcp_bridge.py 2>/dev/null || true
sleep 1

# Raspi側socat確認
echo "  Raspi socat: TCP:${MAVLINK_TCP_PORT} → UDP:14550"
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no \
    "taki@${RASPI_HOST}" \
    "ss -tlnp 2>/dev/null | grep -q ':${MAVLINK_TCP_PORT}' || \
     (nohup socat TCP-LISTEN:${MAVLINK_TCP_PORT},fork,reuseaddr UDP:localhost:14550 > /dev/null 2>&1 &)" \
    2>/dev/null || echo "  ⚠ Raspi socat起動失敗（既に稼働中かも）"

sleep 1

# SSHトンネル: Mac:45760 → Raspi:5760
echo "  SSHトンネル: localhost:45760 → ${RASPI_HOST}:${MAVLINK_TCP_PORT}"
ssh -f -N -L "45760:localhost:${MAVLINK_TCP_PORT}" \
    -o ConnectTimeout=15 \
    -o ServerAliveInterval=30 \
    -o StrictHostKeyChecking=no \
    "taki@${RASPI_HOST}" 2>/dev/null

if [ $? -eq 0 ]; then
    echo "  ✓ SSHトンネル確立"
else
    echo "  ✗ SSHトンネル確立失敗"
    echo "    → Tailscale接続と ssh taki@${RASPI_HOST} を確認"
    exit 1
fi

sleep 2

# Bridge: UDP:14552 ↔ TCP:45760
echo "  ブリッジ起動: UDP:${BRIDGE_UDP_PORT} ↔ TCP:45760"
python scripts/udp_tcp_bridge.py "$BRIDGE_UDP_PORT" 45760 \
    > "${LOG_DIR}/bridge.log" 2>&1 &

BRIDGE_PID=$!
echo "  ✓ ブリッジ起動 (PID: ${BRIDGE_PID})"
sleep 1
echo ""
echo ""

# ===================================================================
# STEP 4: GCSバックエンド接続
# ===================================================================
echo "━━━ [4/7] GCSバックエンド接続 ━━━"

# GCSサーバー起動確認
if curl -s "http://localhost:${GCS_API_PORT}/api/health" > /dev/null 2>&1; then
    echo "  ✓ GCSサーバー稼働中 (port ${GCS_API_PORT})"
else
    echo "  GCSサーバー起動中..."
    export PYTHONPATH="${PROJECT_DIR}/app:$PYTHONPATH"
    nohup python app/main.py --host 0.0.0.0 --port "$GCS_API_PORT" \
        > "${LOG_DIR}/gcs_server.log" 2>&1 &
    GCS_PID=$!
    echo "  GCSサーバー起動 (PID: ${GCS_PID})"
    for i in $(seq 1 10); do
        sleep 1
        if curl -s "http://localhost:${GCS_API_PORT}/api/health" > /dev/null 2>&1; then
            echo "  ✓ GCSサーバー起動完了"
            break
        fi
        [ $i -eq 10 ] && echo "  ⚠ GCSサーバー起動タイムアウト"
    done
fi

# 再接続
curl -s -X POST "http://localhost:${GCS_API_PORT}/api/disconnect" > /dev/null 2>&1 || true
sleep 1

echo "  GCS接続中 (UDP:${BRIDGE_UDP_PORT})..."
curl -s -X POST "http://localhost:${GCS_API_PORT}/api/connect" \
    -H 'Content-Type: application/json' \
    -d "{\"endpoint\": \"127.0.0.1:${BRIDGE_UDP_PORT}\", \"connection_type\": \"udp\"}" \
    > /dev/null 2>&1

# テレメトリ確認
echo "  テレメトリ確認中..."
for i in $(seq 1 10); do
    sleep 2
    DRONE_DATA=$(curl -s "http://localhost:${GCS_API_PORT}/api/drones" 2>/dev/null || true)
    if echo "$DRONE_DATA" | grep -q '"system_id"'; then
        echo "  ✓ MAVLinkテレメトリ受信中"
        FIX_TYPE=$(echo "$DRONE_DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); drones=d.get('drones',[]); print(drones[0].get('gps_fix','N/A') if drones else 'N/A')" 2>/dev/null || echo "N/A")
        echo "  Pixhawk fix_type: ${FIX_TYPE}"
        break
    fi
    [ $i -eq 10 ] && echo "  ⚠ テレメトリ未受信（継続します）"
done
echo ""

# ===================================================================
# STEP 5: RTCM注入状況 + MAVLink fix_type監視 (MAVLink GPS_RAW_INT)
# ===================================================================
echo "━━━ [5/7] RTCM注入状況 + fix_type監視 (MAVLink) ━━━"
echo "  Fix監視方式: MAVLink GPS_RAW_INT.fix_type (GCS REST API経由)"
echo "  UART2: RTCM注入専用 (UBX出力=無効)"

if [ "$SKIP_RASPI_SETUP" = false ]; then
    echo "  Raspi rtk_forwarder 状態確認..."
    FORWARDER_STATUS=$(ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
        "taki@${RASPI_HOST}" \
        "pgrep -f rtk_forwarder_service.py > /dev/null && echo 'RUNNING' || echo 'NOT_RUNNING'" \
        2>/dev/null || echo "SSH_FAILED")

    if [ "$FORWARDER_STATUS" = "RUNNING" ]; then
        echo "  ✓ rtk_forwarder: RUNNING"
        ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no \
            "taki@${RASPI_HOST}" \
            "tail -5 ~/GCS-UmemotoLab/logs/rtcm_injection.log 2>/dev/null || echo '(no log yet)'" \
            2>/dev/null
    elif [ "$FORWARDER_STATUS" = "NOT_RUNNING" ]; then
        echo "  ✗ rtk_forwarder: NOT RUNNING"
        echo "    → Raspiで実行: cd ~/GCS-UmemotoLab && bash deploy/start_raspi_services.sh"
    else
        echo "  ⚠ SSH接続失敗 — Raspi状態不明"
    fi
fi

echo ""
echo "  最新GPS fix_type (MAVLink GPS_RAW_INT):"
DRONE_DATA=$(curl -s "http://localhost:${GCS_API_PORT}/api/drones" 2>/dev/null || true)
if [ -n "$DRONE_DATA" ]; then
    echo "$DRONE_DATA" | python3 -c "
import sys, json
FIX_NAMES = {0:'NO_GPS',1:'NO_FIX',2:'2D_FIX',3:'3D_FIX',4:'DGPS',5:'RTK_FLOAT',6:'RTK_FIXED'}
d = json.load(sys.stdin)
for drone in d.get('drones', []):
    ft = drone.get('gps_fix', -1)
    sats = drone.get('gps_sats', 0)
    fn = FIX_NAMES.get(ft, f'UNK({ft})')
    lat = drone.get('lat', 0)
    lon = drone.get('lon', 0)
    alt = drone.get('alt', 0)
    print(f'    SYSID={drone.get(\"system_id\",\"?\")}: fix={ft}({fn}) sats={sats}')
    print(f'    lat={lat:.7f} lon={lon:.7f} alt={alt:.1f}m')
" 2>/dev/null || echo "    (parse error)"
fi

echo ""
echo "  💡 MAVLink Fix監視スクリプト (gcs_fix_monitor.py):"
echo "      python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:${GCS_API_PORT} --timeout 120"
echo "  ⛔ f9p_fix_monitor.py (UBX経由) は非推奨 (UART2=RTCM注入専用)"
echo ""

# ===================================================================
# STEP 6: GPS誤差データ ${SAMPLE_COUNT} サンプル収集
# ===================================================================
echo "━━━ [6/7] GPS誤差データ ${SAMPLE_COUNT} サンプル収集 ━━━"
echo ""

if [ -z "$UBLOX_PORT" ]; then
    echo "  u-bloxポート未指定 — Pixhawk GPSデータのみ収集"
    python scripts/collect_with_fixed_base.py \
        --gcs-url "http://localhost:${GCS_API_PORT}" \
        --count "$SAMPLE_COUNT" \
        --interval 2.0 \
        --output "$OUTPUT_CSV" \
        --max-duration 120
else
    python scripts/gps_compare_collect.py \
        --ublox "$UBLOX_PORT" \
        --ublox-baud 38400 \
        --gcs-url "http://localhost:${GCS_API_PORT}" \
        --count "$SAMPLE_COUNT" \
        --interval 2.0 \
        --output "$OUTPUT_CSV" \
        --max-duration 120
fi

COLLECT_EXIT=$?
if [ $COLLECT_EXIT -ne 0 ]; then
    echo "  ⚠ データ収集が不完全です（終了コード: ${COLLECT_EXIT}）"
fi

# ===================================================================
# STEP 7: 誤差分析
# ===================================================================
echo "━━━ [7/7] 誤差分析 ━━━"

if [ -f "$OUTPUT_CSV" ]; then
    ROW_COUNT=$(tail -n +2 "$OUTPUT_CSV" 2>/dev/null | wc -l | tr -d ' ')
    echo "  収集データ: ${ROW_COUNT} サンプル (${OUTPUT_CSV})"
    echo ""
    echo "  ─── 誤差分析結果 ───"

    python3 - << PYEOF
import csv, math, sys

csv_path = "${OUTPUT_CSV}"
try:
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        rows = list(reader)
except Exception as e:
    print(f"  CSV読み込みエラー: {e}")
    sys.exit(0)

if not rows:
    print("  データなし")
    sys.exit(0)

FIX_NAMES = {0:"NO_GPS",1:"NO_FIX",2:"2D_FIX",3:"3D_FIX",4:"DGPS",5:"RTK_FLOAT",6:"RTK_FIXED"}

# fix_type 分布
fix_dist = {}
for r in rows:
    ft = r.get('fix_p', r.get('fix_type', 'N/A'))
    try: ft = int(ft)
    except (ValueError, TypeError): pass
    fix_dist[ft] = fix_dist.get(ft, 0) + 1

print(f"  総サンプル数: {len(rows)}")
print(f"  Fix Type 分布:")
for ft in sorted(fix_dist.keys(), key=lambda x: x if isinstance(x,int) else 99):
    name = FIX_NAMES.get(ft, f"UNK({ft})")
    pct = fix_dist[ft] / max(len(rows), 1) * 100
    bar = '#' * max(1, int(pct/2))
    print(f"    {name:<15s}  {fix_dist[ft]:4d}  ({pct:5.1f}%)  {bar}")

# 水平誤差
h_vals = []
v_vals = []
for r in rows:
    for key in ['horizontal_error_m', 'h_err', 'h_error']:
        if key in r and r[key]:
            try: h_vals.append(float(r[key])); break
            except (ValueError, TypeError): pass
    for key in ['vertical_error_m', 'v_err', 'delta_alt_m']:
        if key in r and r[key]:
            try: v_vals.append(float(r[key])); break
            except (ValueError, TypeError): pass

if h_vals:
    n = len(h_vals)
    mean_h = sum(h_vals) / n
    var_h = sum((x-mean_h)**2 for x in h_vals) / (n-1) if n>1 else 0
    std_h = math.sqrt(var_h)
    rms_h = math.sqrt(sum(x**2 for x in h_vals) / n)
    print(f"\n  水平誤差: mean={mean_h*100:.1f}cm  std={std_h*100:.1f}cm  rms={rms_h*100:.1f}cm")
    print(f"             min={min(h_vals)*100:.1f}cm  max={max(h_vals)*100:.1f}cm")
    if mean_h < 0.03:
        print(f"  ✅ 公称精度内 (<3cm)！")

if v_vals:
    n = len(v_vals)
    mean_v = sum(v_vals) / n
    var_v = sum((x-mean_v)**2 for x in v_vals) / (n-1) if n>1 else 0
    std_v = math.sqrt(var_v)
    print(f"  垂直誤差: mean={mean_v*100:.1f}cm  std={std_v*100:.1f}cm  min={min(v_vals)*100:.1f}cm  max={max(v_vals)*100:.1f}cm")

# RTK Fixedのみ
rtk_rows = [r for r in rows if str(r.get('fix_p', r.get('fix_type', ''))) == '6']
if rtk_rows:
    rtk_h = []
    for r in rtk_rows:
        for key in ['horizontal_error_m', 'h_err', 'h_error']:
            if key in r and r[key]:
                try: rtk_h.append(float(r[key])); break
                except (ValueError, TypeError): pass
    if rtk_h:
        mean_rtk = sum(rtk_h) / len(rtk_h)
        print(f"\n  ★ RTK FIXED 水平誤差 ({len(rtk_h)}サンプル):")
        print(f"    mean={mean_rtk*100:.1f}cm  max={max(rtk_h)*100:.1f}cm")
        if mean_rtk < 0.03:
            print(f"    ✅ RTK FIXED 公称精度内 (<3cm)！")
        else:
            print(f"    ⚠ RTK FIXED 公称精度超過 (>3cm)")

print(f"\n  詳細CSV: ${OUTPUT_CSV}")
PYEOF
else
    echo "  ✗ データファイルなし: ${OUTPUT_CSV}"
fi

# ===================================================================
# クリーンアップ情報
# ===================================================================
echo ""
echo "============================================================"
echo "  オペレーション完了"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================================"
echo ""
echo "  実行中のプロセス:"
echo "    基地局:       PID ${BASE_PID:-N/A}"
echo "    ブリッジ:     PID ${BRIDGE_PID:-N/A}"
echo "    GCSサーバー:  PID ${GCS_PID:-N/A}"
echo ""
echo "  出力: ${OUTPUT_CSV}"
echo ""
echo "  停止:"
echo "    pkill -f rtk_base_station_v2.py"
echo "    pkill -f udp_tcp_bridge.py"
echo "    pkill -f 'app/main.py'"
echo "============================================================"
echo ""