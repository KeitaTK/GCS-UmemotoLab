# Raspberry Pi 5 用 GCS Backend セットアップ・運用マニュアル

## ディレクトリ構成

```
raspi/
├── config.yml            # 単一設定ファイル（編集するのはこれだけ）
├── config_loader.py      # 設定ローダーライブラリ
├── backend_server.py     # メインスクリプト（ラズパイ上で実行）
├── requirements.txt      # 依存パッケージリスト
├── install.sh            # 初回セットアップスクリプト
└── README.md             # このファイル
```

---

## 1. 初回セットアップ

```bash
# リポジトリをクローン（または pull）
cd ~/GCS-UmemotoLab
git pull

# セットアップスクリプトを実行
cd raspi
bash install.sh
```

`install.sh` は以下を自動実行します:
1. Python 仮想環境 `~/.venv` の作成
2. `pip install -r requirements.txt`（pymavlink, PyYAML, pyserial）
3. systemd サービス `/etc/systemd/system/gcs-backend.service` の作成
4. UART / mavlink-router の設定確認

---

## 2. 設定

`raspi/config.yml` の値を環境に合わせて編集してください。

```yaml
# 主な設定項目
connection:
  type: serial                  # Pixhawkとの接続方式
  serial_port: /dev/ttyAMA0     # UART デバイス（GPIO直結）

rtcm:
  enabled: true
  host: 192.168.11.62           # ★ PC側のIPアドレスに変更！
  port: 2101                    # rtk_base_station.py の --tcp-port と同じ

drones:
  - system_id: 1
    name: "Pixhawk6C Main"
```

### 設定値の優先順位

1. 環境変数 `RASPI_CONFIG_PATH` で指定したパス
2. `raspi/config.yml`（デフォルト）

---

## 3. 起動方法

### 手動起動（テスト用）

```bash
cd ~/GCS-UmemotoLab/raspi
source ../.venv/bin/activate
python backend_server.py
```

### systemd サービス（常時稼働用）

```bash
# 起動
sudo systemctl start gcs-backend

# 自動起動登録
sudo systemctl enable gcs-backend

# 状態確認
sudo systemctl status gcs-backend

# ログ監視
sudo journalctl -u gcs-backend -f
```

---

## 4. 各コンポーネントの役割

### mavlink-router（systemd サービス）

Pixhawk（UART）↔ GCS（UDP）の透過ブリッジ。**ラズパイ起動時に自動実行**されます。

設定ファイル: `/etc/mavlink-router/main.conf`

```ini
[General]
ReportStats=false
MavlinkVersion=2.0

[UartEndpoint pixhawk]
Device = /dev/ttyAMA0
Baud = 115200

[UdpEndpoint gcs]
Address = 0.0.0.0
Port = 14550
Mode = Server
```

### backend_server.py

PC 側の RTK 基地局から RTCM 補正データを TCP 受信し、MAVLink `GPS_RTCM_DATA` メッセージに変換して Pixhawk に注入します。`raspi/config.yml` の `rtcm.host` と `rtcm.port` で接続先を指定します。

### Pixhawk 配線

| Pixhawk TELEM1 | Raspi GPIO | Pin |
|----------------|------------|-----|
| TX | GPIO 15 (RX) | Pin 10 |
| RX | GPIO 14 (TX) | Pin 8 |
| GND | GND | Pin 6 |

---

## 5. PC 側の準備

ラズパイ側を起動する前に、**PC側で RTK 基地局**を起動しておく必要があります。

```bash
# Windows PC / Mac で実行
cd ~/GCS-UmemotoLab
python rtk_tools/rtk_base_station_v2.py \
    --tcp-port 2101
```

PC 側の `config/hardware.yml` で F9P のシリアルポートと基準局座標を設定します（`hardware.local.yml` で環境別上書き可能）。

---

## 6. トラブルシューティング

| 症状 | 原因 | 対処 |
|------|------|------|
| `Connection refused` | PC 側の rtk_base_station 未起動 | PC で基地局を起動してからラズパイ側を起動 |
| `No heartbeat` | UART 配線 or mavlink-router 未起動 | `sudo systemctl status mavlink-router` 確認 |
| RTCM 未注入 | `rtcm.host` が間違っている | `raspi/config.yml` の host を PC の IP に修正 |
| RTK Float のまま | RTCM ストリーム未到達 | PC 側の F9P が Survey-In 完了しているか確認 |

---

## 7. 更新手順

```bash
cd ~/GCS-UmemotoLab
git pull

# systemd サービス再起動
sudo systemctl restart gcs-backend