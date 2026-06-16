# GCS UmemotoLab — ArduPilot 地上管制局

macOS/Windows/Linux 上で ArduPilot ドローンを制御・監視する**
マルチドローン対応の地上管制局（GCS）システム**です。

## 概要

| 項目 | 内容 |
|------|------|
| **通信方式** | MAVLink v2 over UDP/Serial |
| **ハードウェア** | PC + Raspberry Pi 5（通信ブリッジ）+ Pixhawk |
| **言語** | Python 3.10+ |
| **UI** | PySide6 (Qt 6) |
| **特徴** | マルチドローン、RTK補正、プリチェック無効Arm |

### 主な機能

| 機能 | 説明 |
|------|------|
| **テレメトリ受信** | HEARTBEAT, SYS_STATUS, GPS, バッテリー |
| **機体制御** | アーム/ディスアーム、離陸/着陸、Guided制御 |
| **強制アーム** | ARMING_CHECK 等を無効化してアーム（屋内テスト用） |
| **RTK補正** | RTCMストリームの受信とドローンへの配信 |
| **マルチドローン** | System ID による複数機の識別・同時制御 |
| **ロギング** | 全MAVLinkメッセージの記録 |

---

## システムアーキテクチャ

```
┌──────────────────────────┐
│        PC/Mac (GCS)      │
│  ┌────────────────────┐  │
│  │  Python App        │  │
│  │  (PySide6 + MAVLink)│  │
│  └─────────┬──────────┘  │
└────────────┼─────────────┘
             │ SSH Tunnel (推奨)
      (UDP/TCP MAVLink)
             │
┌────────────┼─────────────┐
│  Raspberry Pi 5          │
│  ┌────────────────────┐  │
│  │  mavlink-router    │  │
│  │  ttyAMA0→UDP:14550 │  │
│  └─────────┬──────────┘  │
└────────────┼─────────────┘
             │ UART (GPIO 14/15)
             │ Baud: 115200
┌────────────┼─────────────┐
│    Pixhawk (ArduPilot)   │
│    TELEM1 接続           │
│    System ID: 1          │
└──────────────────────────┘
```

### Raspi 配線

| Pixhawk TELEM1 | Raspi GPIO | 物理Pin |
|----------------|------------|---------|
| TX → | GPIO 15 (RX) | Pin 10 |
| RX → | GPIO 14 (TX) | Pin 8 |
| RTS → | GPIO 17 | Pin 11 |
| CTS → | GPIO 16 | Pin 36 |
| GND → | GND | Pin 6 |

---

## セットアップ

### 前提条件

- Python 3.10 以上
- macOS / Windows / Linux
- [Raspberry Pi 5 + mavlink-router](#raspberry-pi-5-の設定)（実機ドローン側）
- Tailscale（推奨、リモート接続用）

### インストール

```bash
git clone https://github.com/KeitaTK/GCS-UmemotoLab.git
cd GCS-UmemotoLab

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

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
├── README.md                  # 本ファイル
├── requirements.txt            # Python依存
├── config/
│   ├── gcs.yml                 # デフォルト設定
│   ├── gcs_production.yml      # 本番用（SSHトンネル）
│   ├── gcs_raspi_direct.yml    # Raspi直接実行用
│   └── gcs_local.yml           # ローカル開発用
├── app/
│   ├── main.py                 # エントリーポイント
│   ├── ui/
│   │   ├── main_window.py      # メインUI + 制御ボタン
│   │   └── telemetry_plotter.py
│   ├── mavlink/
│   │   ├── connection.py       # UDP/Serial接続管理
│   │   ├── router.py           # メッセージルーター
│   │   └── message_router.py
│   └── rtk_tools/
│       ├── command_dispatcher.py  # コマンド送信（Arm/ForceArm等）
│       ├── guided_control.py      # Guidedモード制御
│       ├── telemetry_store.py     # テレメトリデータ保持
│       ├── rtcm_reader.py
│       └── rtcm_injector.py
├── tests/
│   ├── test_arm_dummy.py       # ダミー機アームテスト
│   ├── test_arm_live.py         # 実機アームテスト
│   ├── test_command_dispatcher.py
│   ├── test_command_retry.py
│   ├── test_telemetry_store.py
│   └── test_raspi_connection/   # Raspi接続確認テスト
├── docs/                       # 詳細ドキュメント
└── scripts/                    # ビルド・デプロイスクリプト
```

---

## Raspi 実機接続チェックリスト

実機テスト前に以下を確認してください：

- [ ] PixhawkのTELEM1がRaspiのGPIO 14/15に接続されている
- [ ] Pixhawkにバッテリーが接続され、LED点灯中
- [ ] Raspiの `mavlink-router` が稼働中（`systemctl status mavlink-router`）
- [ ] `/etc/mavlink-router/main.conf` の Device が `ttyAMA0` に設定されている
- [ ] SSHトンネルが確立されている（方法Aの場合）
- [ ] GCS UIを起動してドローンがリストに表示される

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

---

## 参考資料

- [MAVLink Protocol](https://mavlink.io/en/)
- [ArduPilot Docs](https://ardupilot.org/dev/)
- [pymavlink](https://github.com/ArduPilot/pymavlink)
- [mavlink-router](https://github.com/mavlink-router/mavlink-router)
- [PySide6](https://doc.qt.io/qtforpython/)

## ライセンス

MIT License

## 問い合わせ

GitHub Issues: https://github.com/KeitaTK/GCS-UmemotoLab/issues
