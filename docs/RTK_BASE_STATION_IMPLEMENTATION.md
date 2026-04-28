# RTK基地局オールインワン化 - 実装計画と自動化

**更新日**: 2026-04-28  
**ステータス**: Phase A完了、Phase B/C実装中

---

## 現在のシステムアーキテクチャ

```
┌──────────────────────────┐
│   Windows PC (GCS)       │
│  ┌────────────────────┐  │
│  │  rtk_base_station  │  │ ← ublox シリアル受信
│  │  (TCP: port 2101)  │  │
│  └────────────────────┘  │
└──────────────┬───────────┘
               │ TCP/WiFi
        Wi-Fi Router
               │
┌──────────────┴───────────┐
│  Raspberry Pi 5          │
│  ┌────────────────────┐  │
│  │ backend_server.py  │  │ ← TCP で RTCM 受信
│  │ (RTCM inject)      │  │
│  └────────────────────┘  │
└──────────────┬───────────┘
               │ Serial/USB
        ┌──────┴──────┐
        │  Pixhawk6C  │
        │  (ArduPilot)│
        └─────────────┘
```

---

## PHASE A: PC側 RTCM受信・配信機構 (✓ 完了)

### 実装内容

**ファイル**: `rtk_base_station.py`
- ublox からシリアルでRTCM v3フレーム受信
- TCP サーバーで Raspberry Pi への配信
- マルチスレッド実装（SerialReader + TcpServer）
- 統計ログ出力

### テスト結果

| テスト | 結果 | 詳細 |
|--------|------|------|
| ローカルシミュレーション | ✓ PASS | 92フレーム受信、30秒間、106バイト/フレーム |
| フレーム解析 | ✓ PASS | RTCM v3フレーム正常抽出 |
| TCP配信 | ✓ PASS | マルチクライアント対応 |

### 実行方法

```powershell
# ローカルテスト
python tests/test_rtk_base_station_integration.py

# 実運用 (ublox が COM3 接続)
python rtk_base_station.py --serial-port COM3 --baudrate 115200 --tcp-port 2101 --log-level INFO
```

---

## PHASE B: Raspberry Pi側 RTCM受信・ドローン送信 (実装中)

### 実装対象

**ファイル**: `app/backend_server.py` (拡張)
- PC の rtk_base_station から TCP で RTCM 受信
- RtcmInjector でPixhawk へ GPS_RTCM_DATA を送信

### 設定

**ファイル**: `config/gcs_local.yml` (Raspberry Pi版)

```yaml
# RTCM/RTK settings
rtcm_enabled: true
rtcm_host: 192.168.11.x  # PC のLAN IPアドレス
rtcm_tcp_port: 2101       # rtk_base_station.py のポート

connection_type: serial
serial_port: /dev/ttyACM0
baudrate: 115200
```

### 実装手順

```bash
# Raspberry Pi 上で実施

# 1. 設定を更新（PC IP と TCP ポート）
vi ~/GCS-UmemotoLab/config/gcs_local.yml

# 2. backend_server を起動
cd ~/GCS-UmemotoLab
source .venv/bin/activate
python app/backend_server.py 2>&1 | tee backend_rtk.log
```

### テスト

```bash
# ローカルテスト（ublox シミュレータ使用）
python tests/test_rtk_base_station_integration.py
```

---

## PHASE C: 統合テスト・検証 (実装予定)

### テスト項目

#### C-1: 1台ドローンでのRTK検証
- Pixhawk6C へRTCM注入
- RTK Fix 状態の確認
- GPS位置精度の測定

#### C-2: 2台ドローンでの検証
- System ID 1, 2 でのルーティング検証
- 各ドローンへの独立したRTCM送信

#### C-3: u-center でのリアルタイム監視
- RTCM フレーム受信状況
- RTK Fix 状態の可視化
- 位置誤差の監視

### テストスクリプト

**ファイル**: `tests/test_integrated_rtk_system.py` (新規作成)

実装予定の機能：
- Pixhawk ハートビート受信確認
- RTCM フレーム到達確認
- GPS 位置情報取得確認
- 複数ドローン制御確認

---

## 全体フロー図

```
【運用フロー】

1. PC側 起動
   rtk_base_station.py --serial-port COM3

2. Raspberry Pi側 起動
   backend_server.py

3. ublox (基地局) を接続
   - PC に USB/シリアルで接続
   - RTCM v3 フレーム配信開始

4. ドローン (Pixhawk) を接続
   - Raspberry Pi に USB で接続
   - ArduPilot ファームウェア実行

5. 通信確認
   ┌─ ublox RTCM フレーム
   ├─ PC rtk_base_station
   ├─ WiFi/TCP 転送
   ├─ Raspberry Pi backend
   ├─ RtcmInjector
   └─ Pixhawk GPS RTK Fix

6. u-center で監視
   - RTK Fix 状態確認
   - 位置精度測定
   - ドローン制御検証
```

---

## 今後のマイルストーン

| フェーズ | 内容 | 予定日 | ステータス |
|---------|------|--------|----------|
| **A** | PC側RTCM受信・配信 | 2026-04-28 | ✓ 完了 |
| **B** | Raspberry Pi側受信・送信 | 2026-04-28-29 | 🔄 進行中 |
| **C** | 統合テスト・検証 | 2026-04-29-30 | ⏳ 予定 |
| **本番運用** | 実運用開始 | 2026-05-01 | ⏳ 予定 |

---

## トラブルシューティング

| 問題 | 原因 | 対処 |
|------|------|------|
| PC→Raspberry Pi 接続できない | ファイアウォール/WiFi不通 | `ping 192.168.11.19` で確認 |
| ublox からRTCM受信できない | シリアルポート誤り | `python -m serial.tools.list_ports` で確認 |
| ドローンがRTK Fix にならない | ドローン側 RTK設定未設定 | ArduPilot パラメータ確認 |
| TCP タイムアウト | Raspberry Pi 側 backend停止 | ログ確認: `tail -100 backend_rtk.log` |

---

## 参考資料

- [RTCM v3 フレーム仕様](https://docs.rtcm.org/)
- [ArduPilot RTK セットアップ](https://ardupilot.org/copter/docs/rtk-gps.html)
- [Pixhawk6C ハードウェア仕様](https://docs.px4.io/)
- [u-center ユーザーマニュアル](https://www.u-blox.com/)
