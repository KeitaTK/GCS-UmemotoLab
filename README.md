# GCS UmemotoLab — ArduPilot GCS with RTK UART2 Direct Injection

macOS/Windows/Linux 上で ArduPilot ドローンを制御・監視する**
マルチドローン対応の地上管制局（GCS）システム**です。
RTK補正データを**UART2経由でF9P GNSSモジュールへ直接注入**する新アーキテクチャを採用し、
RTK FIXED 到達の高速化と信頼性向上を実現しています。

## 概要

| 項目 | 内容 |
|------|------|
| **通信方式** | MAVLink v2 over UDP/Serial |
| **RTK方式** | UART2 Direct Injection（RTCM3→F9P GNSS） |
| **ハードウェア** | PC + Raspberry Pi 5（通信・RTKブリッジ）+ Pixhawk + Holybro H-RTK F9P Helical |
| **言語** | Python 3.10+ |
| **UI** | PySide6 (Qt 6) |
| **特徴** | マルチドローン、RTK UART2直接注入、UBX-NAV-PVT監視、プリフライトチェック |

### 主な機能

| 機能 | 説明 |
|------|------|
| **テレメトリ受信** | HEARTBEAT, SYS_STATUS, GPS, バッテリー |
| **機体制御** | アーム/ディスアーム、離陸/着陸、Guided制御 |
| **強制アーム** | ARMING_CHECK 等を無効化してアーム（屋内テスト用） |
| **RTK UART2 Injection** | MAVLink非依存のRTCM3直接注入。フラグメント分割不要、低レイテンシ |
| **UBX-NAV-PVT 監視** | F9P UART2から直接 Fix状態（carrSoln）をポーリング、RTK FIXEDを確実に検出 |
| **Preflight Check** | GPS/EKF/バッテリー/モーター/RTK UART2 自動総合チェック |
| **systemd サービス** | Raspi起動時にRTK注入を自動開始（`rtk-uart2-inject.service`） |
| **F9P 設定ツール** | Rover/基地局F9Pの自動設定（Survey-In, RTCM3入出力, UBX出力） |
| **マルチドローン** | System ID による複数機の識別・同時制御 |
| **ロギング** | 全MAVLinkメッセージの記録 |

---

## システムアーキテクチャ

2つの独立した通信アーキテクチャが共存します：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         GCS UmemotoLab 全体アーキテクチャ                    │
│                                                                          │
│  ▼ パスA: MAVLink制御（従来から継続）                                      │
│  ┌──────────┐   SSH Tunnel    ┌──────────────┐  UART(GPIO)  ┌──────────┐ │
│  │  PC/Mac  │────────────────→│ Raspberry Pi 5│────────────→│ Pixhawk  │ │
│  │ (GCS UI) │   MAVLink UDP   │ mavlink-router │  TELEM1     │(ArduPilot)│ │
│  └──────────┘                 └──────────────┘             └──────────┘ │
│                                                                          │
│  ▼ パスB: RTK UART2直接注入（新アーキテクチャ）                              │
│  ┌──────────┐   NTRIP/TCP     ┌──────────────┐  USB-Serial   ┌──────────┐ │
│  │ 基地局F9P │────────────────→│ Raspberry Pi 5│─────────────→│F9P Rover │ │
│  │(Survey-In)│  RTCM3 stream  │rtk_forwarder  │  UART2 RX2   │UART2直結 │ │
│  └──────────┘                 │               │←─────────────│UBX-NAV-PVT│ │
│                               │               │  UART2 TX2   │(Fix監視) │ │
│                               └──────────────┘             └─────┬─────┘ │
│                                                                  │       │
│                                                           DroneCAN BUS  │
│                                                                  │       │
│                                                          ┌───────▼─────┐ │
│                                                          │  Pixhawk    │ │
│                                                          │CAN1 (位置受信)│ │
│                                                          └─────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

| パス | 用途 | プロトコル | 経路 |
|------|------|-----------|------|
| **A** | 機体制御・テレメトリ | MAVLink v2 | PC → Raspi(mavlink-router) → Pixhawk TELEM1 |
| **B** | RTK補正データ注入 | RTCM3 (raw) | Base F9P → Raspi(rtk_forwarder) → Rover F9P UART2 |

**ポイント**: RTCM3データはMAVLink GPS_RTCM_DATAを使わず、F9P UART2へ直接注入。フラグメント分割やDroneCAN経由の不透明さを解消。

### Raspi 配線（MAVLink制御パス）

| Pixhawk TELEM1 | Raspi GPIO | 物理Pin |
|----------------|------------|---------|
| TX → | GPIO 15 (RX) | Pin 10 |
| RX → | GPIO 14 (TX) | Pin 8 |
| RTS → | GPIO 17 | Pin 11 |
| CTS → | GPIO 16 | Pin 36 |
| GND → | GND | Pin 6 |

### Raspi 配線（RTK UART2 注入パス）

| F9P UART2 Pin | 信号 | Raspi側 | 用途 |
|---------------|------|---------|------|
| Pin 2 (RX2) | 3.3V TTL | USB-Serial TX | RTCM3データ注入 |
| Pin 3 (TX2) | 3.3V TTL | USB-Serial RX | UBX-NAV-PVT受信 |
| Pin 6 (GND) | GND | USB-Serial GND | 共通グラウンド |

> **注意**: F9PはCANコネクタ経由でPixhawkから5V給電済み。UART2のVCC接続不要。

---

## RTCM注入 全体システム構成図

2つの独立した通信経路（MAVLinkテレメトリ + RTCM注入）を1つの図に統合した全体構成図です。

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                         RTCM注入 全体システム構成図                                     │
│                                                                                      │
│  ┌──────────────────────────┐              ┌──────────────────────────────────────┐  │
│  │         Mac              │              │         Raspberry Pi 5               │  │
│  │                          │              │                                      │  │
│  │  ┌──────────────────┐    │  TCP:2101    │  ┌──────────────────────────────┐    │  │
│  │  │ u-blox F9P(基準局)│────┼────────────→│  │ rtk_forwarder               │    │  │
│  │  │ Survey-In / TIME │    │ RTCM3 Stream │  │ (rtk_forwarder_service.py)  │    │  │
│  │  │ /dev/tty.usbmodem*│   │              │  │                              │    │  │
│  │  └──────────────────┘    │              │  │ NTRIP受信 → Serial転送        │    │  │
│  │                          │              │  └──────────────┬───────────────┘    │  │
│  │  ┌──────────────────┐    │ MAVLink UDP  │                 │                    │  │
│  │  │ GCS UI (PySide6) │←───┼──────────────│                 │ /dev/ttyAMA10      │  │
│  │  │ app/main.py      │    │ SSH Tunnel   │                 │ (GPIO32,33,34)     │  │
│  │  │                  │    │127.0.0.1:14550│ ┌───────────────▼───────────────┐    │  │
│  │  │ テレメトリ表示     │    │              │ │ mavlink-router               │    │  │
│  │  │ 機体制御          │    │              │ │ /etc/mavlink-router/         │    │  │
│  │  └──────────────────┘    │              │ │   main.conf                  │    │  │
│  │                          │              │ │                              │    │  │
│  └──────────────────────────┘              │ │ UART↔UDPブリッジ              │    │  │
│                                             │ └──────────────┬───────────────┘    │  │
│                                             │                 │                    │  │
│                                             │                 │ /dev/ttyAMA0       │  │
│                                             │                 │ (GPIO8,10,11)      │  │
│                                             └─────────────────┼────────────────────┘  │
│                                                               │                       │
│       ┌───────────────────────────────────────────────────────┼───────────────┐       │
│       │                    機体側                              │               │       │
│       │                                                       │               │       │
│       │  ┌──────────────────────────┐     ┌───────────────────▼──────────────┐│       │
│       │  │ F9P Rover                │     │   Pixhawk 6C (ArduPilot)        ││       │
│       │  │ (H-RTK F9P Helical)      │     │                                  ││       │
│       │  │                          │     │ TELEM1 ← MAVLink通信             ││       │
│       │  │ UART2 RX2 ← RTCM3注入    │     │   (GPIO14/15 → Raspi)           ││       │
│       │  │ UART2 TX2 → UBX-NAV-PVT  │     │                                  ││       │
│       │  │                          │     │ CAN2 ──────────┐                 ││       │
│       │  │ RTCM3補正 → RTK測位演算   │     │   位置情報受信   │                 ││       │
│       │  └────────────┬─────────────┘     └────────────────┼─────────────────┘│       │
│       │               │ CAN H/L                              │                  │       │
│       │               └─────────────────────────────────────→│                  │       │
│       │                          DroneCAN BUS (1Mbit/s)      │                  │       │
│       └───────────────────────────────────────────────────────────────────────┘       │
│                                                                                      │
│  【経路凡例】                                                                          │
│  ──→  RTCM注入(パスB): Mac u-blox → TCP:2101 → rtk_forwarder → /dev/ttyAMA10 → F9P   │
│  ←──  MAVLink(パスA): Pixhawk TELEM1 → /dev/ttyAMA0 → mavlink-router → Mac GCS       │
│  ──→  位置情報: F9P Rover → CAN2 → Pixhawk CAN1 (DroneCAN, 既存維持)                   │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### 経路A: MAVLinkテレメトリ（機体制御・監視）

```
Pixhawk TELEM1 → GPIO8(TX),10(RX),11(RTS) → /dev/ttyAMA0 → mavlink-router → Mac GCS
```

| 区間 | デバイス/プロトコル | 詳細 |
|------|-------------------|------|
| Pixhawk → Raspi | GPIO8(TX), GPIO10(RX), GPIO11(RTS) | TELEM1 6pin → Raspi GPIO Header |
| Raspi 受信 | `/dev/ttyAMA0` @ 115200bps | Pi 5 BCM2712 PL011 AXI UART |
| Raspi 中継 | `mavlink-router` (systemd) | UART↔UDP 透過ブリッジ |
| Raspi → Mac | UDP:14550 → SSH Tunnel | Tailscale経由 TCP転送 |
| Mac 受信 | `127.0.0.1:14550` | GCS MavlinkConnection |

### 経路B: RTCM注入（RTK補正データ）

```
Mac u-blox → TCP:2101(RTCM3) → Raspi rtk_forwarder → /dev/ttyAMA10 → F9P UART2 → CAN2 → Pixhawk CAN1
```

| 区間 | デバイス/プロトコル | 詳細 |
|------|-------------------|------|
| u-blox → Raspi | TCP:2101 (Tailscale IP) | RTCM3バイナリストリーム |
| Raspi 受信 | `rtk_forwarder_service.py` | NTRIPクライアント / TCP Socket |
| Raspi 転送 | `/dev/ttyAMA10` @ 115200bps | GPIO32(TX), GPIO33(RX), GPIO34(CTS) |
| F9P 受信 | UART2 RX2 (Pin 2) | RTCM3 → RTK測位演算 |
| F9P → Pixhawk | CAN2 → CAN1 (DroneCAN) | 位置情報供給（既存維持） |

### 各コンポーネントの役割

| コンポーネント | 役割 |
|--------------|------|
| **u-blox F9P (Mac)** | RTK基準局。Survey-Inモードで基準位置を確定し、RTCM3補正データをTCP:2101で配信。`/dev/tty.usbmodem*`経由でMacにUSB接続。 |
| **Raspberry Pi 5** | 機体搭載の通信ブリッジ。`mavlink-router` でMAVLinkをUART↔UDP中継。`rtk_forwarder` でRTCM3をTCP→シリアル変換。2系統の通信を1台で処理。 |
| **F9P Rover (H-RTK F9P Helical)** | 機体搭載のRTK対応GNSSモジュール。UART2でRTCM3補正データを受信しRTK測位演算を実行。UBX-NAV-PVTでFix状態（carrSoln）を出力。CAN経由でPixhawkに位置情報を供給。 |
| **Pixhawk 6C (ArduPilot)** | フライトコントローラ。TELEM1でMAVLink通信、CAN1でF9PからRTK位置情報を受信。ArduPilotがGPS_AUTO_SWITCHで最適GPSソースを自動選択。 |

### デバイス名とGPIOピン対応表

| デバイス名 | GPIOピン | 物理Pin | 信号 | 接続先 | 用途 |
|-----------|----------|---------|------|--------|------|
| `/dev/ttyAMA0` | GPIO8 | Pin 8 | TX | Pixhawk TELEM1 RX | MAVLink送信 |
| `/dev/ttyAMA0` | GPIO10 | Pin 10 | RX | Pixhawk TELEM1 TX | MAVLink受信 |
| `/dev/ttyAMA0` | GPIO11 | Pin 11 | RTS | Pixhawk TELEM1 CTS | フロー制御 |
| `/dev/ttyAMA10` | GPIO32 | Pin 32 | TX | F9P Rover UART2 RX2 | RTCM3データ注入 |
| `/dev/ttyAMA10` | GPIO33 | Pin 33 | RX | F9P Rover UART2 TX2 | UBX-NAV-PVT受信 |
| `/dev/ttyAMA10` | GPIO34 | Pin 34 | CTS | F9P Rover (予備) | フロー制御 |

> **Pi 5 注意**:
> - `/dev/ttyAMA0` は BCM2712 の PL011 AXI UART。`enable_uart=1` + `dtoverlay=uart0` で有効化。
> - `/dev/ttyAMA10` は RP1 チップの追加 UART。`dtoverlay=uart4` 等で有効化。
> - Pixhawk TELEM1 接続では `/dev/ttyAMA0` を直接指定する方が安定する。

---

## RTK クイックスタート

RTK UART2 直接注入の最小セットアップ手順です。詳細は [rtk_direct_uart2_injection_plan.md](docs/05-implementation/rtk_direct_uart2_injection_plan.md) を参照。

### 0. 前提

- Rover側 F9P の UART2 (JST-GH 6pin) が USB-Serial アダプタ経由で Raspi に接続済み
- 基地局 F9P が Survey-In 完了済み（`scripts/ublox_survey_in.py` で確認）
- 基地局が RTCM3 ストリームを配信中

### 1. Rover F9P 設定（初回のみ）

```bash
# Raspi上で実行
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# F9P RoverのUART2をRTCM3入力 + UBX出力に設定
python rtk_tools/f9p_rover_config.py --port /dev/ttyUSB0
```

### 2. RTCM注入開始

```bash
# 方法A: systemd サービスで永続起動
sudo bash deploy/install_rtk_uart2_service.sh
sudo systemctl start rtk-uart2-inject
systemctl status rtk-uart2-inject   # 確認
journalctl -u rtk-uart2-inject -f   # ログ追跡

# 方法B: 手動ワンショット（テスト用）
python rtk_tools/rtk_direct_inject.py \
  --uart-port /dev/ttyUSB0 \
  --base-host 192.168.11.100 \
  --timeout 120
```

### 3. RTK FIXED 確認

```bash
# UBX-NAV-PVT を直接ポーリング
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyUSB0

# プリフライトチェック（GPS/EKF/RTK UART2 総合確認）
python tools/preflight_check.py --rtk-uart-port /dev/ttyUSB0
```

### 4. 飛行準備完了 → GCS起動

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python app/main.py
```

---

## RTCMデータフロー検証手順

RTK UART2（UART4）直接注入の動作確認を、実機を用いて体系的に検証する手順です。
新規ユーザーでもこの手順に従うことで、RTCM注入からRTK FIXED到達までの正常動作を確認できます。

### RTCMデータフロー詳細

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     RTCMデータフロー（RTK UART2 直接注入）                        │
│                                                                              │
│  ┌──────────────┐     NTRIP/TCP        ┌──────────────────┐                  │
│  │  基地局 F9P   │─────────────────────→│  Raspberry Pi 5   │                  │
│  │  (Survey-In)  │   RTCM3 stream      │                  │                  │
│  │              │   port 2101          │ rtk_forwarder_   │                  │
│  │  RTCM3 0xD3  │                     │ service.py       │                  │
│  │  preamble    │                     │                  │                  │
│  └──────────────┘                     │ ① NTRIP接続      │                  │
│                                       │   (TCP Socket)   │                  │
│                                       │                  │                  │
│                                       │ ② RTCM3受信      │                  │
│                                       │   recv(4096)     │                  │
│                                       │                  │                  │
│                                       │ ③ シリアル転送    │                  │
│                                       │   UART4 TX       │                  │
│                                       │   /dev/ttyAMA4   │                  │
│                                       │   @115200bps     │                  │
│                                       └───────┬──────────┘                  │
│                                               │ USB-Serial                  │
│                                               │ (3.3V TTL)                  │
│                                               ▼                             │
│                                       ┌──────────────────┐                  │
│                                       │  Rover F9P       │                  │
│                                       │  (UART2 RX2)     │                  │
│                                       │                  │                  │
│                                       │ ④ RTCM3処理      │                  │
│                                       │   → RTK測位演算   │                  │
│                                       │                  │                  │
│                                       │ ⑤ UBX-NAV-PVT    │                  │
│                                       │   出力 (UART2 TX2)│                  │
│                                       │   carrSoln:      │                  │
│                                       │   0=NONE        │                  │
│                                       │   1=FLOAT       │                  │
│                                       │   2=FIXED  ←目標 │                  │
│                                       └───────┬──────────┘                  │
│                                               │ USB-Serial                  │
│                                               ▼                             │
│                                       ┌──────────────────┐                  │
│                                       │  Raspberry Pi 5   │                  │
│                                       │                  │                  │
│                                       │ ⑥ UBX-NAV-PVT    │                  │
│                                       │   受信・監視      │                  │
│                                       │   f9p_fix_monitor │                  │
│                                       │   .py             │                  │
│                                       │                  │                  │
│                                       │ ⑦ ログ記録        │                  │
│                                       │   rtcm_injection  │                  │
│                                       │   .log            │                  │
│                                       │   rtcm_fix_       │                  │
│                                       │   transition.log  │                  │
│                                       └──────────────────┘                  │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  F9P (DroneCAN) ──→ Pixhawk CAN1 (位置情報供給)                      │    │
│  │  ※ 既存CAN接続は変更なし。UART2注入と並行動作                           │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

| ステップ | 説明 | 担当コンポーネント | 確認方法 |
|----------|------|-------------------|---------|
| ① | NTRIP Caster にTCP接続しRTCM3ストリームを取得 | `rtk_forwarder_service.py` | NTRIP応答 `ICY 200 OK` |
| ② | RTCM3バイナリデータを4096バイト単位で受信 | `rtk_forwarder_service.py` `_run_ntrip_once()` | ログ: `Forward stats:` |
| ③ | 受信データをUSB-Serial経由でF9P UART2 RX2へ送信 | `rtk_forwarder_service.py` `_forward_chunk()` | シリアルポート `/dev/ttyAMA4` |
| ④ | F9PがRTCM3補正データを処理しRTK測位演算を実行 | F9P ファームウェア | carrSoln 遷移観測 |
| ⑤ | F9PがUBX-NAV-PVTメッセージをUART2 TX2から出力 | F9P ファームウェア | UBXメッセージ (0x01 0x07) |
| ⑥ | RaspiがUBX-NAV-PVTを受信しcarrSolnを監視 | `f9p_fix_monitor.py` `poll_nav_pvt()` | carrSoln=2 検出 |
| ⑦ | 注入統計とFix遷移をCSVログに記録 | `RtcmForwarderService` / `F9pFixMonitor` | `logs/` 以下のCSVファイル |

### 検証の前提条件

検証を開始する前に、以下が完了していることを確認してください：

- [ ] Raspi に USB-Serial アダプタが接続され、`/dev/ttyAMA4`（または `/dev/ttyUSB*`）として認識されている
- [ ] F9P Rover の UART2 (JST-GH 6pin) が USB-Serial アダプタ経由で Raspi に接続済み
- [ ] 基地局 F9P が Survey-In 完了済み（`python scripts/ublox_survey_in.py --status` で確認）
- [ ] 基地局が NTRIP Caster として RTCM3 ストリームを配信中
- [ ] Rover F9P の UART2 が設定済み（初回のみ `f9p_rover_config.py` を実行）

### 検証手順（ステップバイステップ）

#### STEP 1: Rover F9P UART2 設定確認

F9P Rover の UART2 が RTCM3 入力 + UBX-NAV-PVT 出力に設定されていることを確認します。

```bash
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# 初回設定（未設定の場合のみ）
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4

# 設定確認（既設定済みの場合）
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4 --verify-only
```

**期待される出力:**
```
UART2 Config Verification Results
  CFG-UART2-BAUDRATE           : expected=115200, actual=115200, OK
  CFG-UART2INPROT-RTCM3X       : expected=     1, actual=1, OK
  CFG-UART2OUTPROT-UBX         : expected=     1, actual=1, OK
  All verified: YES
```

#### STEP 2: 基地局 RTCM3 ストリーム確認

基地局の NTRIP Caster が RTCM3 データを配信していることを確認します。

```bash
# 自動チェック（NTRIPハンドシェイク + RTCM3プリアンブル確認）
python rtk_tools/rtk_direct_inject.py \
  --uart-port /dev/ttyAMA4 \
  --base-host 192.168.11.100 \
  --timeout 10

# 出力の STEP 2 部分を確認:
#   STEP 2: Verify Base Station RTCM3 Stream
#   NTRIP caster response: ICY 200 OK
#   RTCM3 stream verified: preamble=0xD3, received 512 bytes
```

**確認ポイント:**
- NTRIP Caster が `ICY 200 OK` を返すこと
- 受信データの先頭バイトが `0xD3`（RTCM3 プリアンブル）であること

#### STEP 3: RTCM 注入サービス起動

`rtk_forwarder_service.py` を起動し、基地局からのRTCM3データを F9P UART2 に転送します。

```bash
# 方法A: systemd サービスとして永続起動（推奨）
sudo bash deploy/install_rtk_uart4_service.sh
sudo systemctl start rtk-uart4-inject
systemctl status rtk-uart4-inject

# 方法B: 手動起動（テスト・デバッグ用）
python rtk_tools/rtk_forwarder_service.py --config config/rtk_forwarder.yml
```

> **注意:** `config/rtk_forwarder.yml` の `forward.type` が `serial`、`forward.serial_port` が `/dev/ttyAMA4` に設定されていることを確認してください。

**期待されるログ出力（journalctl / コンソール）:**
```
RTK forwarder start: source=ntrip, forward.type=serial, destination=/dev/ttyAMA4@115200bps
Connected to NTRIP caster: 192.168.11.100:2101 / UBLOX_EVK_F9P
NTRIP response: ICY 200 OK
Forward stats: packets=120, bytes=51200
Forward stats: packets=240, bytes=102400
```

#### STEP 4: RTK FIXED 到達確認

F9P の UBX-NAV-PVT 出力を監視し、`carrSoln=2`（RTK FIXED）への遷移を確認します。

```bash
# RTK Fixed 待機（最大120秒）
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --timeout 120

# 単発ポーリング（現在の状態を一度だけ確認）
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --once

# 連続モニタリング（手動監視用）
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --monitor
```

**carrSoln 遷移の期待シーケンス:**
```
  t=  0.0s  carrSoln=0(NONE)     fixType=0  numSV=0   hAcc=99.999m
  t=  5.0s  carrSoln=0(NONE)     fixType=3  numSV=12  hAcc=5.000m
  t= 15.0s  carrSoln=1(FLOAT)    fixType=5  numSV=18  hAcc=1.500m   ← FLOAT到達
  >>> RTK FLOAT reached at t=15.0s <<<
  t= 25.0s  carrSoln=1(FLOAT)    fixType=5  numSV=20  hAcc=0.800m
  t= 35.0s  carrSoln=2(FIXED)    fixType=6  numSV=22  hAcc=0.020m   ← FIXED到達!
  >>> RTK FIXED (1→2) <<<
  ============================================================
    RTK FIXED ACHIEVED!
    Position: lat=35.XXXXXXX lon=139.XXXXXXX hMSL=XX.XXm
    Accuracy: hAcc=0.020m vAcc=0.030m
    Time to fix: 35.0s
  ============================================================
```

| carrSoln | 状態 | 意味 | 水平精度目安 |
|----------|------|------|-------------|
| 0 | NONE | RTK補正なし | >1m |
| 1 | FLOAT | フロート解（搬送波位相の整数値バイアス未確定） | 0.5〜1.5m |
| **2** | **FIXED** | **RTK FIX解（搬送波位相確定、cm級精度）** | **<0.05m** |

#### STEP 5: プリフライトチェック（総合確認）

全システムの状態を総合的にチェックします。

```bash
# GCS API経由（GCS起動中の場合）
python tools/preflight_check.py --rtk-uart-port /dev/ttyAMA4

# 直接 MAVLink 接続（GCS未起動の場合）
python tools/preflight_check.py --direct --rtk-uart-port /dev/ttyAMA4

# UART2チェックのみスキップする場合
python tools/preflight_check.py --skip-rtk-uart2
```

**期待されるチェック項目:**
```
[OK] [RTK_UART2] F9P Rover Config    → Module available
[OK] [RTK_UART2] Fix Monitor          → Module available
[OK] [RTK_UART2] rtk_forwarder config → forward.type=serial → /dev/ttyAMA4 @ 115200 bps
[OK] [RTK_UART2] UART2 Device         → /dev/ttyAMA4 exists
...
FINAL: READY FOR FLIGHT
```

### 確認ポイント一覧

#### ログファイル

| ログファイル | 生成元 | 内容 |
|-------------|--------|------|
| `logs/rtcm_injection.log` | `rtk_forwarder_service.py` | RTCM注入統計（時刻・累積フレーム数・累積バイト数・転送レート・エラー数） |
| `logs/rtcm_fix_transition.log` | `f9p_fix_monitor.py` | carrSoln遷移記録（時刻・経過時間・carrSoln・numSV・hAcc・位置・遷移イベント） |
| `logs/rtcm_proof_summary.txt` | `rtk_direct_inject.py` | 注入証明サマリ（総フレーム数・FLOAT/FIXED到達時間・最終ステータス） |
| `logs/preflight_check_*.json` | `preflight_check.py` | プリフライトチェック全結果（JSON形式） |

#### 期待される出力と判定基準

| 確認項目 | コマンド | 合格基準 | 不合格時の対応 |
|---------|---------|---------|---------------|
| F9P UART2 設定 | `f9p_rover_config.py --verify-only` | `All verified: YES` | STEP 1 再実行 |
| 基地局 RTCM3 到達 | `rtk_direct_inject.py` STEP 2 | `ICY 200 OK` + `preamble=0xD3` | 基地局のSurvey-In状態・ネットワーク確認 |
| RTCM注入稼働 | `systemctl status rtk-uart4-inject` | `active (running)` | `journalctl -u rtk-uart4-inject -f` でエラー確認 |
| RTCM注入流量 | `logs/rtcm_injection.log` 最終行 | `frames_per_min > 0`（通常 数百〜数千フレーム/分） | 基地局-Raspi間のネットワーク確認 |
| RTK FLOAT 到達 | `logs/rtcm_fix_transition.log` | `0→1` 遷移が記録されている | 周辺環境（上空視界）確認、アンテナ位置調整 |
| RTK FIXED 到達 | `f9p_fix_monitor.py --once` | `carrSoln=2(FIXED)` | タイムアウト時間延長（`--timeout 300`）、基地局距離確認 |
| 水平精度 | `f9p_fix_monitor.py --once` | FIXED時 `hAcc < 0.05m` | FLOATのままなら継続待機 |
| プリフライト PASS | `preflight_check.py` | `FINAL: READY FOR FLIGHT` | 各FAIL項目の `notes` を参照 |

#### systemd サービスの健全性確認

```bash
# サービス状態確認
systemctl status rtk-uart4-inject

# リアルタイムログ追跡
journalctl -u rtk-uart4-inject -f

# 過去1時間のログ
journalctl -u rtk-uart4-inject --since "1 hour ago"

# エラーのみ抽出
journalctl -u rtk-uart4-inject -p err
```

**正常時の journalctl 出力例:**
```
Jul 15 10:00:00 raspi python[1234]: RTK forwarder start: source=ntrip, forward.type=serial, destination=/dev/ttyAMA4@115200bps
Jul 15 10:00:01 raspi python[1234]: Connected to NTRIP caster: 192.168.11.100:2101 / UBLOX_EVK_F9P
Jul 15 10:00:01 raspi python[1234]: NTRIP response: ICY 200 OK
Jul 15 10:00:06 raspi python[1234]: Forward stats: packets=45, bytes=18432
Jul 15 10:00:11 raspi python[1234]: Forward stats: packets=90, bytes=36864
```

### トラブルシューティング

#### RTCM データフロー障害の系統的診断

障害が発生した場合、データフローの各段階を上流から順に診断します。

```
診断フロー:
  ① 基地局は起動しているか？
    └→ python scripts/ublox_survey_in.py --status
    └→ Survey-In が完了しているか？（最長300秒）
  
  ② NTRIP Caster にTCP接続できるか？
    └→ nc -zv 192.168.11.100 2101
    └→ 基地局のIPアドレス・ポートが正しいか確認
  
  ③ RTCM3データが流れているか？
    └→ python rtk_tools/rtk_direct_inject.py --timeout 10
    └→ STEP 2 で ICY 200 OK と 0xD3 preamble を確認
  
  ④ rtk_forwarder_service は稼働しているか？
    └→ systemctl status rtk-uart4-inject
    └→ journalctl -u rtk-uart4-inject -f
  
  ⑤ /dev/ttyAMA4 デバイスは存在するか？
    └→ ls -la /dev/ttyAMA4
    └→ dmesg | grep tty で認識状況を確認
  
  ⑥ F9P UART2 の配線は正しいか？
    └→ F9P RX2 (Pin 2) ← USB-Serial TX
    └→ F9P TX2 (Pin 3) → USB-Serial RX
    └→ GND (Pin 6)     ↔ USB-Serial GND
  
  ⑦ F9P が UBX-NAV-PVT を出力しているか？
    └→ python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --once
    └→ 応答がない場合: f9p_rover_config.py --port /dev/ttyAMA4 で再設定
```

#### よくある障害と対応

| 現象 | 考えられる原因 | 対応 |
|------|--------------|------|
| `systemctl status` が `failed` | 設定ファイルの不備、パスの誤り | `journalctl -u rtk-uart4-inject -n 50` でエラー確認 |
| NTRIP接続エラー `Connection refused` | 基地局が起動していない、またはファイアウォール | 基地局の電源・ネットワーク確認。`nc -zv` でポート到達性確認 |
| `ICY 200 OK` は返るが `Forward stats` が出ない | `forward.type` が `udp` のまま | `config/rtk_forwarder.yml` の `forward.type` を `serial` に変更 |
| シリアルポート `Permission denied` | デバイス権限不足 | `sudo usermod -a -G dialout $USER` → 再ログイン |
| `/dev/ttyAMA4` が存在しない | UART4 が有効化されていない | `/boot/firmware/config.txt` に `dtoverlay=uart4` を追加 |
| `f9p_fix_monitor` が `(no data)` を返し続ける | F9P UART2 OUTPROT-UBX 未設定、または配線ミス | `f9p_rover_config.py --verify-only` で設定確認。TX/RX 配線の入れ替え確認 |
| carrSoln が 0(NONE) から遷移しない | 基地局からのRTCM3が届いていない | `tail -f logs/rtcm_injection.log` でフレームカウント増加を確認 |
| carrSoln が 1(FLOAT) で停滞 | 衛星数不足、マルチパス、基線長過大 | 空が見える場所に移動。基地局-Rover間距離が10km以内か確認 |
| RTK FIXED 後にすぐ FLOAT に戻る | 基地局RTCM3の断続的な途切れ | `journalctl -u rtk-uart4-inject` で切断・再接続ログを確認 |
| `preflight_check` の RTK_UART2 が FAIL | モジュールのimportエラー | `pip install pyubx2 pyserial` を再実行。PYTHONPATHを確認 |

#### F9P UART2 配線の再確認

問題が解決しない場合、物理配線を再確認してください：

| F9P UART2 Pin | 信号 | USB-Serial 側 | 確認 |
|---------------|------|---------------|------|
| Pin 2 (RX2) | 3.3V TTL 入力 | TX | RTCM3データ注入用 |
| Pin 3 (TX2) | 3.3V TTL 出力 | RX | UBX-NAV-PVT受信用 |
| Pin 6 (GND) | GND | GND | 共通グラウンド |

> **ヒント:** TX/RX を入れ替えてみると解決することがあります。F9P RX2 はデータを受信する側なので、USB-Serial の TX に接続してください。

#### ログを活用した詳細診断

```bash
# RTCM 注入ログの最新10行
tail -10 logs/rtcm_injection.log

# Fix 遷移ログの全内容（carrSoln の変化を時系列で確認）
cat logs/rtcm_fix_transition.log

# 注入証明サマリ（前回の検証結果）
cat logs/rtcm_proof_summary.txt

# 注入レートの推移をグラフ表示（gnuplot 使用時）
gnuplot -e "set datafile separator ','; plot 'logs/rtcm_injection.log' using 4 with lines title 'frames/min'"
```

---

## セットアップ

### 前提条件

- Python 3.10 以上
- macOS / Windows / Linux
- [Raspberry Pi 5 + mavlink-router](#raspberry-pi-5-の設定)（実機ドローン側）
- Tailscale（推奨、リモート接続用）

### インストール

> **UV**（pipの10-100倍高速なPythonパッケージマネージャー）を使用します。
> 未インストールの場合は以下で導入してください:
> ```bash
> curl -LsSf https://astral.sh/uv/install.sh | sh
> ```
> その他のインストール方法は [UV公式ドキュメント](https://docs.astral.sh/uv/getting-started/installation/) を参照。

```bash
git clone https://github.com/KeitaTK/GCS-UmemotoLab.git
cd GCS-UmemotoLab

uv venv
source .venv/bin/activate
uv sync
```

> **従来のpip互換**: `uv sync` の代わりに `uv pip install -r requirements.txt` を使用することも可能です。
> **Raspi用**: `uv pip install -r requirements_raspi.txt` でRaspi向けの最小依存をインストールできます。

### クイック起動

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python app/main.py
```

設定ファイルの自動選択順序:
1. `$GCS_CONFIG_PATH` 環境変数
2. `config/gcs.user.local.yml`（Git管理外）
3. `config/gcs_local.yml`
4. `config/gcs.yml`

---

## Raspberry Pi 5 の設定

### 1. mavlink-router のインストール

```bash
sudo apt install mavlink-router
```

### 2. 設定ファイル: `/etc/mavlink-router/main.conf`

```ini
[General]
ReportStats=true    # デバッグ用に統計出力を有効化

[UartEndpoint pixhawk]
Device = /dev/ttyAMA0    # Pi 5: ttyAMA10 でなく ttyAMA0 を指定
Baud = 115200

[UdpEndpoint gcs]
Address = 0.0.0.0
Port = 14550
Mode = Server
```

### 3. サービスの有効化

```bash
sudo systemctl enable mavlink-router
sudo systemctl start mavlink-router
sudo systemctl status mavlink-router  # 確認
```

### 4. UART有効化（`/boot/firmware/config.txt`）

> **⚠️ Pi 5 注意**: `dtoverlay=uart0-pi5` はハードウェアフロー制御(CTS/RTS)が必要で、
> `/dev/serial0→ttyAMA10` にマッピングされる。Pixhawk TELEM1 接続では
> `/dev/ttyAMA0` を直接指定する方が安定する。

```
enable_uart=1
dtoverlay=uart0
```

---

## 接続方法

### 方法 A: SSHトンネル経由（推奨）

GCSのPC/MacとRaspiが別ネットワークでも接続可能。
**Tailscale の UDP 転送に制限があるため、SSH トンネル（TCP）を推奨します。**

```bash
# 別ターミナルでSSHトンネルを確立（バックグラウンド常駐）
ssh -f -N -L 14550:localhost:14550 raspi

# または明示的に（Tailscale IP直指定）
ssh -f -N -L 14550:localhost:14550 \
    -o ProxyCommand="tailscale nc %h %p" \
    taki@100.123.158.105
```

設定ファイル:
```yaml
# config/gcs_local.yml
connection_type: udp
udp_listen_port: 14551   # SSHトンネルが14550を使うため
drones:
  drone1:
    system_id: 1
    endpoint: "127.0.0.1:14550"  # SSHトンネル経由
    name: "Pixhawk6C Main"
```

### 方法 B: 同一ネットワーク（直接UDP）

Mac/Raspiが同じWiFiに接続されている場合。

```yaml
# 設定例
drones:
  drone1:
    endpoint: "172.20.10.12:14550"  # RaspiのローカルIP
```

### 方法 C: Raspi上でGCSを直接実行

```bash
# Raspi上で
cd GCS-UmemotoLab
source .venv/bin/activate
export GCS_CONFIG_PATH=config/gcs_raspi_direct.yml
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python app/main.py
```

---

## 操作方法

### メイン画面

| ボタン | 機能 |
|--------|------|
| **Arm** | 選択したドローンをアーム |
| **Disarm** | 選択したドローンをディスアーム |
| **Force Arm** | ⚠️ プリチェック無効化アーム（屋内テスト専用） |
| **Takeoff** | 離陸（要アーム状態） |
| **Land** | 着陸 |
| **Send Guided Position/Velocity** | NED座標でのGuided制御 |

### Force Arm（強制アーム）

屋内テストでRC非接続・GPS未Fix・EKF未初期化時にアームするための機能。

無効化するパラメータ:
- `ARMING_CHECK = 0`（プリアームチェック全スキップ）
- `FS_THR_ENABLE = 0`（ラジオフェールセーフ無効）
- `AHRS_EKF_TYPE = 0`（EKF無効）

> **⚠️ 警告**: 実飛行では絶対に使用しないでください。
> テスト後は `dispatcher.restore_arm_params()` でデフォルトに戻してください。

---

## テスト

### ダミードローンテスト（実機不要）

```bash
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python tests/test_arm_dummy.py
```

### 実機アームテスト

```bash
# SSHトンネル確立後
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python tests/test_arm_live.py
```

### 全テスト実行

```bash
pytest tests/ -v
```

---

## プロジェクト構造

```
GCS-UmemotoLab/
├── README.md                   # 本ファイル
├── CHANGELOG.md                # 変更履歴
├── requirements.txt            # Python依存
├── config/
│   ├── gcs.yml                 # デフォルト設定
│   ├── gcs_production.yml      # 本番用（SSHトンネル）
│   ├── gcs_raspi_direct.yml    # Raspi直接実行用
│   ├── gcs_local.yml           # ローカル開発用
│   └── rtk_forwarder.yml       # RTK転送サービス設定
├── app/
│   ├── main.py                 # エントリーポイント
│   ├── ui/
│   │   ├── main_window.py      # メインUI + 制御ボタン
│   │   └── telemetry_plotter.py
│   ├── mavlink/
│   │   ├── connection.py       # UDP/Serial接続管理
│   │   ├── router.py           # メッセージルーター
│   │   └── message_router.py
│   └── rtk_tools/              # GCS側RTKツール（MAVLink経由: 従来パス）
│       ├── command_dispatcher.py  # コマンド送信（Arm/ForceArm等）
│       ├── guided_control.py      # Guidedモード制御
│       ├── telemetry_store.py     # テレメトリデータ保持
│       ├── rtcm_reader.py         # RTCM TCP受信（基地局→Raspi）
│       └── rtcm_injector.py       # RTCM→GPS_RTCM_DATA変換（UART2新方式では撤廃）
├── rtk_tools/                  # RTKツール（Raspi側: UART2直接注入パス）
│   ├── rtk_direct_inject.py       # ★ RTCM注入+RTK FIXED待機 自動化
│   ├── rtk_forwarder_service.py   # ★ RTCM転送サービス (NTRIP→UART2)
│   ├── f9p_rover_config.py        # ★ Rover側F9P UART2設定
│   ├── f9p_configurator.py        # F9P設定モジュール
│   ├── f9p_fix_monitor.py         # UBX-NAV-PVT Fix監視
│   ├── rtk_base_station_v2.py     # 基地局統合サービス
│   ├── rtk_data_collector.py      # RTKデータコレクター
│   └── config_loader.py           # 設定ローダー
├── deploy/                     # デプロイメント
│   ├── rtk-uart2-inject.service   # systemd サービス定義
│   ├── install_rtk_uart2_service.sh
│   └── uninstall_rtk_uart2_service.sh
├── tools/                      # 運用ツール
│   ├── preflight_check.py         # ★ プリフライト総合チェック
│   └── mineru/                    # PDF解析ツール
├── scripts/                    # ユーティリティスクリプト
│   ├── ublox_survey_in.py         # F9P Survey-In設定
│   ├── check_gps_fix.py           # GPS Fix確認
│   └── udp_tcp_bridge.py          # UDP/TCPブリッジ
├── tests/
│   ├── test_arm_dummy.py       # ダミー機アームテスト
│   ├── test_arm_live.py         # 実機アームテスト
│   ├── test_command_dispatcher.py
│   ├── test_command_retry.py
│   ├── test_telemetry_store.py
│   ├── test_raspi_connection/   # Raspi接続確認テスト
│   └── test_rtk_integration.py  # RTK統合テスト
└── docs/                       # 詳細ドキュメント
    ├── 01-specification/       # 仕様書
    ├── 02-development/         # 開発ガイド
    ├── 03-operations/          # 運用マニュアル
    ├── 04-testing/             # テストレポート
    └── 05-implementation/      # 実装設計書
        ├── rtk_direct_uart2_injection_plan.md  # ★ UART2注入設計書
        └── preflight_rtk_checklist_uart2.md    # ★ プリフライトRTKチェックリスト
```

---

## Raspi 実機接続チェックリスト

実機テスト前に以下を確認してください：

### MAVLink 制御パス
- [ ] PixhawkのTELEM1がRaspiのGPIO 14/15に接続されている
- [ ] Pixhawkにバッテリーが接続され、LED点灯中
- [ ] Raspiの `mavlink-router` が稼働中（`systemctl status mavlink-router`）
- [ ] `/etc/mavlink-router/main.conf` の Device が `ttyAMA0` に設定されている
- [ ] SSHトンネルが確立されている（方法Aの場合）
- [ ] GCS UIを起動してドローンがリストに表示される

### RTK UART2 注入パス
- [ ] F9P UART2 (JST-GH 6pin) → USB-Serialアダプタ → Raspi の配線完了
- [ ] USB-Serialアダプタが `/dev/ttyUSB0` として認識（`ls /dev/ttyUSB*`）
- [ ] F9P Rover UART2 設定済み（`python rtk_tools/f9p_rover_config.py --port /dev/ttyUSB0` 初回実行済み）
- [ ] 基地局 F9P Survey-In 完了（`python scripts/ublox_survey_in.py --status`）
- [ ] `rtk-uart2-inject` サービス稼働中（`systemctl status rtk-uart2-inject`）
- [ ] RTK FIXED 達成確認（`python rtk_tools/f9p_fix_monitor.py --port /dev/ttyUSB0` で carrSoln=2）
- [ ] プリフライトチェック PASS（`python tools/preflight_check.py --rtk-uart-port /dev/ttyUSB0`）

### トラブルシューティング

| 現象 | 確認項目 |
|------|----------|
| ハートビートが来ない | Pixhawk電源ON? TELEM1配線? `dmesg \| grep tty` |
| ハートビートが来ない (Pi 5) | `/dev/ttyAMA0` にデータ有? `sudo systemctl stop mavlink-router; cat /dev/ttyAMA0 \| od -A x -t x1 \| head` |
| mavlink-router 受信0 | ポート衝突? `sudo ss -ulnp \| grep 14550` |
| アームが拒否される | Force Armボタンを使用、もしくは`ARMING_CHECK=0`を設定 |
| SSH接続不可 | `ssh raspi` で接続確認。Tailscale: `tailscale status` |
| UDPパケットが届かない (Tailscale) | SSHトンネル方式に切替: `ssh -f -N -L 14550:localhost:14550 raspi` |
| `bytes.append` エラー | pymavlink バグ。`.venv/.../ardupilotmega.py` の `crcbuf = bytearray(msgbuf[...])` を確認 |
| RTK FIXED にならない | `rtk_tools/f9p_fix_monitor.py` で carrSoln を確認。0=NONE, 1=FLOAT, 2=FIXED |
| RTCMが注入されない | `ls /dev/ttyUSB*` でデバイス認識確認。`sudo systemctl status rtk-uart2-inject` |
| F9P UART2未応答 | `python rtk_tools/f9p_rover_config.py --port /dev/ttyUSB0` で再設定 |
| RTK Forwarder が再接続しない | `journalctl -u rtk-uart2-inject -f` でログ確認。基地局IP到達性確認 |

---

## 参考資料

### プロジェクト内ドキュメント
- [RTK UART2 直接注入 設計書](docs/05-implementation/rtk_direct_uart2_injection_plan.md)
- [プリフライト RTK チェックリスト (UART2)](docs/05-implementation/preflight_rtk_checklist_uart2.md)
- [RTK基地局 実装計画](docs/05-implementation/RTK_BASE_STATION_IMPLEMENTATION.md)
- [RTK統合ガイド](docs/03-operations/rtk_integration_guide.md)
- [通信アーキテクチャ](docs/01-specification/communication-architecture.md)

### 外部リファレンス
- [MAVLink Protocol](https://mavlink.io/en/)
- [ArduPilot Docs](https://ardupilot.org/dev/)
- [ArduPilot RTK GPS Setup](https://ardupilot.org/copter/docs/common-rtk-gps.html)
- [pymavlink](https://github.com/ArduPilot/pymavlink)
- [mavlink-router](https://github.com/mavlink-router/mavlink-router)
- [pyubx2 (u-blox UBX protocol)](https://pypi.org/project/pyubx2/)
- [Holybro H-RTK F9P Docs](https://docs.holybro.com/gps-and-rtk-system/h-rtk-neo-f9p-series-rm3100-compass)
- [u-blox NEO-F9P Datasheet](https://www.u-blox.com/en/product/neo-f9p)
- [PySide6](https://doc.qt.io/qtforpython/)

## ライセンス

MIT License

## 問い合わせ

GitHub Issues: https://github.com/KeitaTK/GCS-UmemotoLab/issues
