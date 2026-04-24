# マルチドローン運用ガイド

複数のドローンを同じ GCS から統一的に管理するための手順を説明します。

## 概要

GCS-UmemotoLab は複数のドローン（System ID で識別）を同時に管理できます。

---

## マルチドローン設定

### Step 1: 設定ファイルをコピー

```bash
cp config/gcs_multidrone_example.yml config/gcs_local.yml
```

### Step 2: ドローンの System ID を確認

各ドローン（Pixhawk）には固有の System ID が設定されています。

**確認方法**:
- Mission Planner や QGroundControl で接続時に表示される
- u-center のメッセージビューで確認

### Step 3: config/gcs_local.yml を編集

```yaml
drones:
  drone1:
    system_id: 1          # ドローン 1 の System ID
    endpoint: "127.0.0.1:14550"
    name: "Main Drone"
  
  drone2:
    system_id: 2          # ドローン 2 の System ID
    endpoint: "127.0.0.1:14551"
    name: "Support Drone"
```

### Step 4: 接続方式を選択

#### パターン A: シリアル接続（単一 Pixhawk）

```yaml
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
```

⚠️ **注**: シリアル接続の場合、**1台の Pixhawk** から複数ドローンデータを受信します。
これは以下の場合に該当：
- Raspberry Pi + mavlink-router で複数ドローンから UDP 転送を受ける場合
- 各ドローンが独立した Pixhawk を持つ場合

#### パターン B: UDP 接続（複数ドローン同時接続）

```yaml
connection_type: udp
udp_listen_port: 14550
```

UDP モードでは、複数のドローンから同時に UDP ポートへメッセージが送信されます。

### Step 5: 各ドローンを接続

各ドローンの Pixhawk を Raspberry Pi に接続し、mavlink-router で UDP への転送設定を行います。

```bash
# Raspberry Pi 上で (各ドローンを順次接続)
mavlink-routerd -e 192.168.11.19:14550 /dev/ttyUSB0:57600 &  # Drone 1
mavlink-routerd -e 192.168.11.19:14551 /dev/ttyUSB1:57600 &  # Drone 2
```

### Step 6: Backend を起動

```bash
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && .venv/bin/python app/backend_server.py 2>&1"
```

ログを確認：

```
Active drones: [1, 2]
  Drone 1: heartbeat received
  Drone 2: heartbeat received
```

---

## コマンド送信（マルチドローン対応）

### 個別コマンド送信

```python
from app.mavlink.command_dispatcher import CommandDispatcher

dispatcher = CommandDispatcher(config)

# Drone 1 にアーム指令
dispatcher.send_arm_command(system_id=1, arm=True)

# Drone 2 に離陸指令
dispatcher.send_takeoff_command(system_id=2, altitude=10.0)

# Drone 3 に着陸指令
dispatcher.send_land_command(system_id=3)
```

### ブロードキャスト（全ドローンに送信）

```python
# 全ドローンにアーム指令
for system_id in [1, 2, 3]:
    dispatcher.send_arm_command(system_id=system_id, arm=True)
```

---

## RTK 補正の配信（マルチドローン）

RTCM データは自動的に全ドローンへ配信されます。

```yaml
rtcm_enabled: true
rtcm_host: 127.0.0.1
rtcm_tcp_port: 2101
```

設定後、u-center で RTCM ストリーム配信を開始すると、全ドローンが自動的に補正データを受信します。

---

## テレメトリー受信

各ドローンのテレメトリーは `TelemetryStore` に格納されます。

```python
from app.mavlink.telemetry_store import TelemetryStore

store = TelemetryStore()

# Drone 1 の位置情報を取得
position_1 = store.get_latest_position(system_id=1)

# Drone 2 のハートビートを取得
hb_2 = store.get_heartbeat(system_id=2)

# 全ドローンのステータスを表示
for system_id in store.get_system_ids():
    hb = store.get_heartbeat(system_id=system_id)
    print(f"Drone {system_id}: {hb}")
```

---

## 運用シナリオ

### シナリオ 1: 構内での複数ドローン運用

```
Pixhawk 1 ──→ Raspberry Pi ──→ UDP:14550 ──┐
Pixhawk 2 ──→ Raspberry Pi ──→ UDP:14551 ──┤
Pixhawk 3 ──→ Raspberry Pi ──→ UDP:14552 ──┤
                                           └→ Windows PC (GCS)
```

**手順**:
1. 各ドローンの Pixhawk を Raspberry Pi に接続
2. mavlink-router で UDP への転送設定
3. GCS Backend を起動
4. 全ドローンのテレメトリーを一元監視

### シナリオ 2: RTK 補正を含む運用

```
Pixhawk 1 ──→ ┐
Pixhawk 2 ──→ ├→ Raspberry Pi ──→ Windows PC (GCS)
Pixhawk 3 ──→ ┘
                ↑
            u-center (RTCM)
              ポート 2101
```

**手順**:
1. u-center で NTRIP に接続
2. RTCM を TCP 2101 へ配信
3. config で rtcm_enabled: true に設定
4. Backend を起動
5. 全ドローンが自動的に RTK 補正を受信

---

## トラブルシューティング

### 問題 1: System ID が認識されない

**原因**: ドローンの Pixhawk が起動していない、または接続されていない

**対処**:
1. `dmesg | tail -20` で接続確認
2. Pixhawk を再起動
3. ケーブル接続を確認

### 問題 2: 特定のドローンからデータが来ない

**原因**: mavlink-router のポート設定が異なる、または通信障害

**対処**:
```bash
# TCP ポートが正しいか確認
netstat -an | grep 1455
# 14550, 14551, 14552 などが LISTEN 状態

# 通信を確認
tcpdump -i eth0 -n port 14550
```

### 問題 3: RTCM インジェクションが全ドローンに到達しない

**原因**: 特定のドローンが System ID を共有している、または接続不安定

**対処**:
1. 各ドローンの System ID が異なるか確認
2. ログで GPS_RTCM_DATA フレーム送信を確認
3. Pixhawk ファームウェアが RTCM インジェクションをサポートしているか確認

---

## パフォーマンス考慮

| 項目 | 推奨値 | 備考 |
|------|--------|------|
| **最大ドローン数** | 5～10台 | ネットワーク負荷による |
| **テレメトリー周期** | 10Hz | 各ドローン共通 |
| **RTCM 更新周期** | 1Hz | 全ドローン共通 |
| **接続タイムアウト** | 10秒 | 設定で変更可能 |

---

## まとめ

- ✅ GCS は複数ドローンの同時管理に対応
- ✅ System ID で自動的にドローンを識別
- ✅ RTCM は全ドローンに自動配信
- ✅ テレメトリーは一元管理・表示可能
