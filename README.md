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
