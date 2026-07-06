# RTCM → EKF Injection Test Report

**日付**: 2026-07-07 01:11 JST  
**ブランチ**: current (worktree 1346d)  
**テストスクリプト**: `tests/test_rtcm_ekf_injection.py`  
**テスト環境**: Linux (ダミーF9Pシミュレータ使用)

---

## テスト概要

RTKパイプライン（F9P → TCP:2101 → RtcmReader → RtcmInjector → GPS_RTCM_DATA → Pixhawk EKF）の全段階を検証するエンドツーエンドテストを実施した。

実機F9Pが接続されていない環境のため、`DummyF9PBaseStation` を使用してF9P基地局の動作をシミュレートしている。

---

## テスト結果: 4/4 PASS ✅

| # | テスト | 結果 | 詳細 |
|---|--------|------|------|
| 1 | RTK単独測位 (Standalone) | ✅ PASS | NMEA fix=1, TCP:2101 リッスン確認 OK |
| 2 | RTCM TCP配信 | ✅ PASS | 18 frames, 6 msg types, 573 B/s |
| 3 | GPS_RTCM_DATA注入 | ✅ PASS | 29 MAVLink frames, CRC-16 valid=20/20 |
| 4 | Full Pipeline E2E | ✅ PASS | byte_loss=0.0%, 完全なデータ到達 |

### 1. RTK単独測位 (Standalone Positioning) — PASS

- F9P基地局シミュレータが `127.0.0.1:2101` で起動
- NMEA `$GNGGA` センテンスが正しく生成されることを確認:
  - `fix=1` (GPS単独測位)
  - `satellites=18`, `HDOP=0.8`
  - 基準局座標: `35.6812367, 139.7671250, 42.0m`
- TCP:2101 ポートでリッスン状態を確認

### 2. RTCM TCP配信 (RTCM Distribution) — PASS

- TCP:2101 に接続し、5秒間で18個のRTCM v3フレームを受信
- 全フレームが有効な `0xD3` preamble を持つ
- 6種類のRTCMメッセージタイプを確認:
  | メッセージタイプ | 名称 | フレーム数 |
  |---|---|---|
  | 1005 | StationXYZ | 3 |
  | 1074 | GPS_MSM4 | 3 |
  | 1084 | GLO_MSM4 | 3 |
  | 1094 | GAL_MSM4 | 3 |
  | 1124 | BDS_MSM4 | 3 |
  | 1230 | GLO_Bias | 3 |
- 帯域: 573 bytes/sec (~3.3 fps)

### 3. GPS_RTCM_DATA注入 (MAVLink Injection) — PASS

- `RtcmReader` がTCP:2101からRTCMフレームを受信
- `RtcmInjector` がRTCM → `GPS_RTCM_DATA` (MAVLink msgid=233) に変換
- 5秒間のデータフロー:
  - RTCM受信: **16 messages**, 2,493 bytes
  - GPS_RTCM_DATA送信: **16 messages** → **29 MAVLink frames** (180byte分割)
- **MAVLink v2フレーム検証**: 20/20 フレームが正しい msgid=233
- **CRC-16 CCITT検証**: 20/20 チェックサム一致

### 4. Full Pipeline E2E — PASS

```
F9P (Dummy) → TCP:2101 → RtcmReader → RtcmInjector → GPS_RTCM_DATA
```

- 全コンポーネントが協調動作することを確認
- **byte_loss = 0.0%** — データロスなしで完全なパイプラインスループット
- 5秒間で16 RTCM messages → 30 MAVLink frames の変換を確認

---

## パイプラインアーキテクチャ

```
┌─────────────────────────────────────────────────────────────────────┐
│ PC/Mac (GCS-UmemotoLab)                                             │
│                                                                     │
│  DummyF9PBaseStation (本番: rtk_base_station_v2.py)                 │
│  ├── RtcmSerialReader: USBシリアルからRTCM受信 (0xD3 フレーム境界)    │
│  ├── TcpServer: TCP :2101 で全クライアントにブロードキャスト           │
│  └── UdpBroadcaster: UDPブロードキャスト (オプション)                 │
│                                                                     │
│  RtcmReader (app/rtk_tools/rtcm_reader.py)                          │
│  ├── TCP:2101 クライアント接続                                       │
│  ├── RTCM v3 フレーム解析 (0xD3 preamble + 長さ抽出)                 │
│  ├── CRC-24Q 検証                                                   │
│  └── コールバックベースのデータ配信                                   │
│       │                                                             │
│  RtcmInjector (app/rtk_tools/rtcm_injector.py)                      │
│  ├── RTCM → GPS_RTCM_DATA (MAVLink msgid=233) 変換                  │
│  ├── 180バイト分割 (max_payload_size=180)                            │
│  ├── フラグ (fragmented, fragment_id)                               │
│  ├── CRC-16 CCITT チェックサム付与                                   │
│  └── MAVLink v2 フレーム構築                                        │
│       │                                                             │
│       ↓                                                             │
└───────┼─────────────────────────────────────────────────────────────┘
        │
   MAVLink v2 (UART /dev/ttyACM0 または UDP)
        │
        ↓
┌──────────────────────────────────────────────────────────────────────┐
│ Pixhawk (ArduPilot)                                                  │
│  ├── GPS_RTCM_DATA 受信                                             │
│  ├── EKF (Extended Kalman Filter) にRTCM補正注入                     │
│  └── RTK Float → RTK Fixed への収束                                  │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 実機テスト手順（参考）

F9P実機 + Pixhawk 実機がある場合のテスト手順:

### Step 1: F9P基地局起動
```bash
cd ~/GCS-UmemotoLab && source .venv/bin/activate
python rtk_tools/rtk_base_station_v2.py --tcp-port 2101 --log-level INFO
```
- F9PをPCにUSB接続
- `hardware.yml` でシリアルポート・基準局座標を設定済みであること
- 起動時にF9Pが自動設定される（TMODE3 Fixed Mode + RTCM3出力有効化）

### Step 2: RTCM配信確認
```bash
# 別ターミナルで
nc -v 127.0.0.1 2101 | xxd | head -20
# 0xD3 で始まるRTCMフレームが流れていればOK
```

### Step 3: GCS起動（RTCM注入）
```bash
python app/main.py
# 設定ファイルで rtcm.enabled=true, rtcm.host=127.0.0.1, rtcm.port=2101
# ログに "RTCM data injected: X bytes in Y frame(s)" が表示されれば成功
```

### Step 4: Pixhawk GPSステータス確認
- QGroundControl または GCS Web UI で GPS fix type を監視
- fix=4 (DGPS) → fix=5 (RTK Float) → fix=6 (RTK Fixed) への遷移を確認

---

## コード品質指標

| 指標 | 値 |
|------|-----|
| テスト数 | 4 |
| 合格 | 4 |
| 不合格 | 0 |
| データロス率 | 0.0% |
| MAVLinkフレーム妥当性 | 100% (20/20) |
| CRC-16一致率 | 100% (20/20) |
| RTCMメッセージタイプ | 6種類 |
| スループット | ~573 B/s |

---

## 結論

RTKパイプラインの全段階（F9P基地局 → TCP:2101配信 → RtcmReader → RtcmInjector → GPS_RTCM_DATA）が正常に動作することを確認した。

実機F9P + Pixhawk 環境での確認は別途必要だが、ソフトウェアスタックのパイプライン完全性は検証済みである。
