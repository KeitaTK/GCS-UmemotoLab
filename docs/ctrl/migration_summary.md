# UART2 Fix監視 移行サマリ

## 移行概要

| 項目 | 旧方式 (Before) | 新方式 (After) |
|------|----------------|----------------|
| **Fix監視ソース** | UBX-NAV-PVT (UART2 TX2 直接読取) | MAVLink GPS_RAW_INT.fix_type (GCS REST API) |
| **監視スクリプト** | `rtk_tools/f9p_fix_monitor.py` | `rtk_tools/gcs_fix_monitor.py` |
| **UART2 用途** | RTCM3入力 + UBX出力 (双方向) | RTCM3入力専用 (UBX出力=無効) |
| **必要なHW変更** | — | なし（ゼロ） |
| **ログフォーマット** | `rtcm_fix_transition.log` (CSV) | 同左（互換性維持） |

## 変更ファイル一覧

### 新規作成

| ファイル | 説明 |
|----------|------|
| `rtk_tools/gcs_fix_monitor.py` | MAVLink GPS_RAW_INT.fix_type を GCS REST API 経由で監視する新スクリプト |

### 変更

| ファイル | 変更内容 |
|----------|---------|
| `rtk_tools/f9p_fix_monitor.py` | `[DEPRECATED]` マーク追加。モジュール本体は残置 |
| `rtk_tools/f9p_rover_config.py` | `CFG-UART2OUTPROT-UBX`: 1→0, `CFG-MSGOUT-UBX-NAV-PVT-UART2`: 1→0 |
| `scripts/operation_full.sh` | STEP5: Fix監視を MAVLink ベースに変更 |
| `README.md` | アーキテクチャ図・データフロー図・手順書を更新 |

### 新規ドキュメント

| ファイル | 説明 |
|----------|------|
| `docs/ctrl/migration_summary.md` | 本ファイル |

## アーキテクチャ変更点

### 旧: UART2双方向
```
Raspi TX → F9P UART2 RX2 (RTCM3注入)
F9P UART2 TX2 → Raspi RX (UBX-NAV-PVT監視)
```

### 新: UART2 RTCM注入専用 + MAVLink Fix監視
```
Raspi TX → F9P UART2 RX2 (RTCM3注入専用)
F9P → DroneCAN → Pixhawk → MAVLink GPS_RAW_INT → GCS REST API → gcs_fix_monitor.py
```

## fix_type マッピング（ログ互換性）

`rtcm_fix_transition.log` の `carrSoln` 列には以下のマッピング値を書き込む：

| MAVLink fix_type | 名称 | carrSoln (ログ互換値) |
|-----------------|------|----------------------|
| 0〜4 | NO_GPS 〜 DGPS | 0 (NONE) |
| 5 | RTK_FLOAT | 1 (FLOAT) |
| 6 | RTK_FIXED | 2 (FIXED) |
| 7〜8 | STATIC / PPP | 0 (NONE) |

## F9P UART2 設定変更

`f9p_rover_config.py` の設定キー変更：

```python
# 旧
('CFG-UART2OUTPROT-UBX',      1),   # UBX 出力を有効化
('CFG-MSGOUT-UBX-NAV-PVT-UART2', 1), # NAV-PVT 出力

# 新
('CFG-UART2OUTPROT-UBX',      0),   # UBX 出力を無効化 (UART2=RTCM注入専用)
('CFG-MSGOUT-UBX-NAV-PVT-UART2', 0), # NAV-PVT 出力 無効
```

Verify期待値: `CFG-UART2OUTPROT-UBX` expected=1→0

## 使用方法

### Fix監視（新方式）
```bash
# GCS起動済みの状態で
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --timeout 120
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --once
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --monitor
```

### F9P Rover 再設定（UBX出力無効化）
```bash
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4 --verify-only
```

### 旧方式（非推奨・参照用）
```bash
# ⛔ 非推奨。UART2 UBX出力=無効のため機能しない
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --once
```

## ハードウェア変更

**なし（ゼロ）**

- F9P UART2 の物理配線変更不要
- UART2 TX2 (Pin 3) は未使用となるが、接続したままでも問題なし
- DroneCAN バス (F9P→Pixhawk) は変更なし

## 移行日

2026-07-21

---

## 初回実機テスト結果 (2026-07-21 21:15)

### テスト環境

| 項目 | 状態 |
|------|------|
| 日時 | 2026-07-21 21:15 |
| Mac (GCS/基地局) | Tailscale IP: 100.80.225.4, macOS |
| Raspi5-1 (Rover側) | Tailscale IP: 100.69.75.96, hostname: raspi5 |
| u-blox基地局 | /dev/tty.usbmodem114301, 38400bps |
| Pixhawk drone | system_id=1, mode=STABILIZE, armed=false |

### Step 1: 環境確認 ✅

| 確認項目 | 結果 |
|----------|------|
| u-blox USB認識 | ✅ `/dev/tty.usbmodem114301` (38400bps) |
| Tailscale接続 | ✅ `raspi5-1` active, direct connection |
| GCSサーバー | ✅ port 8000, `status: ok` |
| MAVLink受信 | ✅ system_id=1, fix=3(3D_FIX), sats=9→12 |

### Step 2: パイプライン起動 ⚠️ (一部課題あり)

| 項目 | 状態 | 詳細 |
|------|------|------|
| rtk_base_station.py | ✅ | PID 18413, u-blox→TCP:2101, 653k+ RTCM frames |
| SSHトンネル | ✅ | `14553→raspi5:5760` (既存トンネル流用) |
| MAVLink Bridge | ✅ | PID 28724, TCP:14553→UDP:14551 |
| GCS接続 (/api/connect) | ✅ | connected=True, 21,452 packets |
| RTCM注入 (Raspi→F9P) | ⚠️ | 手動スクリプトで確立 (後述) |

#### RTCM注入経路の課題

新アーキテクチャでは Raspi 上の `rtk_forwarder_service.py` がRTCMをF9P UART2へ注入するが、
以下の問題が発生した：

1. **NTRIPプロトコル不一致**: `rtk_forwarder` は NTRIP caster として接続を試みるが、
   Mac側 `rtk_base_station.py` は生TCPストリームを提供しており、NTRIPハンドシェイクに失敗
2. **一時対応**: `/tmp/direct_inject.py` (生TCP→シリアル変換スクリプト) をRaspiに配置し、
   `100.80.225.4:2101` → `/dev/ttyAMA4:115200` の直接注入を確立

```
【暫定パイプライン】
u-blox → Mac TCP:2101 → Tailscale → Raspi TCP → /dev/ttyAMA4 → F9P UART2
```

### Step 3: Fix監視 ❌ (未達)

| 時刻 | fix_type | sats | eph | epv | 備考 |
|------|----------|------|-----|-----|------|
| 21:07 | 3 (3D_FIX) | 11 | 148cm | 219cm | RTCM注入開始前 |
| 21:09 | 3 (3D_FIX) | 12 | 140cm | 216cm | NTRIP caster試行中 |
| 21:12 | 3 (3D_FIX) | 11 | 148cm | 219cm | Raspi直接注入確立 |
| 21:13 | 3 (3D_FIX) | 11 | 148cm | 219cm | +60s経過 |
| 21:15 | 3 (3D_FIX) | 11 | 148cm | 218cm | +180s経過 |

**RTK FLOAT/FIXED に遷移せず**。3D_FIXのままeph/epvに改善なし。

### Step 4: データ収集 ❌ (スキップ)

RTK Fix未達のため `gps_compare_collect.py` による比較データ収集は未実施。
FLOAT/FIXED到達後に再試行が必要。

### Step 5: 考察と次のアクション

#### 確認済みの動作項目
- ✅ u-blox基地局: RTCMフレーム活発に生成 (653,804 frames)
- ✅ Mac→Raspi TCP接続: Tailscale経由でRTCM到達確認
- ✅ /dev/ttyAMA4: 115200bps, PL011 AXI, 正常アクセス可能
- ✅ MAVLinkテレメトリ: GPS_RAW_INT受信中、fix_type監視可能
- ✅ GCS REST API: `/api/drones`, `/api/telemetry`, `/api/status` 正常
- ✅ `gcs_fix_monitor.py`: ポーリング動作確認済み

#### 推定される未達原因
1. **F9P Rover未設定**: `f9p_rover_config.py` による UART2 RTCM3入力有効化 (`CFG-UART2INPROT-RTCM3X=1`) が未実行の可能性
2. **基地局Survey-In未完了**: u-blox基地局がSurvey-In完了前で有効なRTCM補正データを生成できていない可能性
3. **物理結線**: /dev/ttyAMA4 → F9P UART2 RX2 の配線確認が必要

#### 推奨アクション
1. Raspi上で `f9p_rover_config.py --port /dev/ttyAMA4 --verify-only` 実行し設定確認
2. 未設定の場合は `f9p_rover_config.py --port /dev/ttyAMA4` で設定実行
3. 基地局のSurvey-In状態を確認（`base_station.json` mode=survey_in, auto_obs_duration=60s）
4. `rtk_forwarder_service.py` に生TCPソースタイプ (`source_type: tcp`) を追加するコード修正
5. FLOAT到達後、`gps_compare_collect.py` で30サンプル収集し水平/垂直誤差を評価

### 接続情報 (次回テスト用)

```bash
# Mac側 基地局起動
python3 legacy/rtk_base_station.py --serial-port /dev/tty.usbmodem114301 --baudrate 38400 --tcp-port 2101

# Raspi側 直接注入 (暫定)
ssh taki@100.69.75.96 'cd ~/GCS-UmemotoLab && source .venv/bin/activate && python3 /tmp/direct_inject.py'

# MAVLink Bridge
python3 -c "..." # TCP:14553→UDP:14551

# GCS接続
curl -X POST http://localhost:8000/api/connect -H 'Content-Type: application/json' -d '{"config_path":"config/gcs_local.yml"}'

# Fix監視
python3 rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --timeout 300
```
