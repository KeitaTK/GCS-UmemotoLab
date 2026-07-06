# GCS 運用マニュアル

このマニュアルは、GCS-UmemotoLab を本番環境で運用するための手順と注意事項をまとめたものです。

---

## 目次

1. [システム起動](#システム起動)
2. [日常運用](#日常運用)
3. [トラブルシューティング](#トラブルシューティング)
4. [チェックリスト](#チェックリスト)
5. [緊急時対応](#緊急時対応)

---

## システム起動

### 起動順序

**重要**: 以下の順序で起動してください。

#### Step 1: Pixhawk の起動（機体側）

```
1. Pixhawk に電源を供給
2. LED が点灯することを確認
3. 3～5 秒待機（自己診断完了まで）
```

#### Step 2: Raspberry Pi の起動

```bash
# Raspberry Pi に接続
ssh taki@100.123.158.105

# Backend サーバーを起動
cd ~/GCS-UmemotoLab
.venv/bin/python app/backend_server.py
```

**起動確認ログ**:
```
[INFO] GCS Backend Server starting
[INFO] Serial mode: /dev/ttyACM0 @ 115200 baud
[INFO] MessageRouter受信ループ開始
[INFO] Active drones: [1]
[INFO] Drone 1: heartbeat received
```

#### Step 3: Windows PC での GUI 起動（オプション）

```powershell
cd c:\Users\taita\github\GCS-UmemotoLab
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Resolve-Path .\app).Path
python .\app\main.py
```

#### Step 4: u-center の起動（RTK 使用時のみ）

```
1. u-center を起動
2. NTRIP キャスターに接続
3. TCP Server を開始 (port 2101)
```

### 起動順序の重要性

❌ **間違い**: PC → Raspberry Pi → Pixhawk
✅ **正しい**: Pixhawk → Raspberry Pi → PC → u-center

---

## 日常運用

### モニタリング

#### ポイント 1: ハートビート受信確認

```
[INFO] Active drones: [1]
[INFO] Drone 1: heartbeat received
```

**正常**: 5 秒間隔でログが出力される  
**異常**: ログが出力されない → Pixhawk 接続確認

#### ポイント 2: GPS ロック状態

```bash
# Pixhawk の GPS ロックを確認
# QGroundControl で GPS Fix Type を確認

GPS Fix: 3D-Fix 以上が理想的
```

#### ポイント 3: RTCM インジェクション（RTK 使用時）

```
[INFO] Connected to RTCM source: 127.0.0.1:2101
[INFO] RTCM data injected: X bytes in Y frame(s)
```

### 定期メンテナンス

| 項目 | 周期 | 内容 |
|------|------|------|
| **ログ確認** | 毎日 | エラーメッセージの有無確認 |
| **GPS 精度確認** | 毎週 | GPS Fix type、精度低下確認 |
| **シリアルポート確認** | 毎月 | `/dev/ttyACM0` の持続性確認 |
| **パッケージアップデート** | 四半期 | Python パッケージの更新 |

---

## マルチドローン運用

複数のドローン（System ID で識別）を同じ GCS から統一的に管理するための手順です。

### マルチドローン設定

#### Step 1: 設定ファイルをコピー

```bash
cp config/gcs_multidrone_example.yml config/gcs_local.yml
```

#### Step 2: ドローンの System ID を確認

各ドローン（Pixhawk）には固有の System ID が設定されています。Mission Planner や QGroundControl で接続時に表示されます。

#### Step 3: config/gcs_local.yml を編集

```yaml
drones:
  drone1:
    system_id: 1
    endpoint: "127.0.0.1:14550"
    name: "Main Drone"
  drone2:
    system_id: 2
    endpoint: "127.0.0.1:14551"
    name: "Support Drone"
```

#### Step 4: 接続方式を選択

**パターン A: シリアル接続（単一 Pixhawk）**

```yaml
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
```

シリアル接続の場合、1台の Pixhawk から複数ドローンデータを受信します（Raspberry Pi + mavlink-router で複数ドローンから UDP 転送を受ける場合など）。

**パターン B: UDP 接続（複数ドローン同時接続）**

```yaml
connection_type: udp
udp_listen_port: 14550
```

#### Step 5: mavlink-router で各ドローンを接続

```bash
# Raspberry Pi 上で（各ドローンを順次接続）
mavlink-routerd -e 100.123.158.105:14550 /dev/ttyUSB0:57600 &  # Drone 1
mavlink-routerd -e 192.168.11.19:14551 /dev/ttyUSB1:57600 &   # Drone 2
```

#### Step 6: Backend を起動

```bash
ssh taki@100.123.158.105 "cd ~/GCS-UmemotoLab && .venv/bin/python app/backend_server.py 2>&1"
```

起動確認ログ:
```
Active drones: [1, 2]
  Drone 1: heartbeat received
  Drone 2: heartbeat received
```

### コマンド送信（マルチドローン対応）

**個別コマンド送信**:

```python
from app.mavlink.command_dispatcher import CommandDispatcher

dispatcher = CommandDispatcher(config)
dispatcher.send_arm_command(system_id=1, arm=True)
dispatcher.send_takeoff_command(system_id=2, altitude=10.0)
dispatcher.send_land_command(system_id=3)
```

**ブロードキャスト（全ドローンに送信）**:

```python
for system_id in [1, 2, 3]:
    dispatcher.send_arm_command(system_id=system_id, arm=True)
```

### RTK 補正の配信（マルチドローン）

RTCM データは自動的に全ドローンへ配信されます。

```yaml
rtcm_enabled: true
rtcm_host: 127.0.0.1
rtcm_tcp_port: 2101
```

u-center で RTCM ストリーム配信を開始すると、全ドローンが自動的に補正データを受信します。

### テレメトリー受信

各ドローンのテレメトリーは `TelemetryStore` に格納されます。

```python
from app.mavlink.telemetry_store import TelemetryStore

store = TelemetryStore()
position_1 = store.get_latest_position(system_id=1)
hb_2 = store.get_heartbeat(system_id=2)

# 全ドローンのステータスを表示
for system_id in store.get_system_ids():
    hb = store.get_heartbeat(system_id=system_id)
    print(f"Drone {system_id}: {hb}")
```

### 運用シナリオ

#### シナリオ 1: 構内での複数ドローン運用

```
Pixhawk 1 ──→ Raspberry Pi ──→ UDP:14550 ──┐
Pixhawk 2 ──→ Raspberry Pi ──→ UDP:14551 ──┤
Pixhawk 3 ──→ Raspberry Pi ──→ UDP:14552 ──┤
                                           └→ Windows PC (GCS)
```

1. 各ドローンの Pixhawk を Raspberry Pi に接続
2. mavlink-router で UDP への転送設定
3. GCS Backend を起動
4. 全ドローンのテレメトリーを一元監視

#### シナリオ 2: RTK 補正を含む運用

```
Pixhawk 1 ──→ ┐
Pixhawk 2 ──→ ├→ Raspberry Pi ──→ Windows PC (GCS)
Pixhawk 3 ──→ ┘
                ↑
            u-center (RTCM)
              ポート 2101
```

1. u-center で NTRIP に接続
2. RTCM を TCP 2101 へ配信
3. config で rtcm_enabled: true に設定
4. Backend を起動
5. 全ドローンが自動的に RTK 補正を受信

### マルチドローントラブルシューティング

#### 問題 1: System ID が認識されない

- `dmesg | tail -20` で接続確認
- Pixhawk を再起動
- ケーブル接続を確認

#### 問題 2: 特定のドローンからデータが来ない

```bash
netstat -an | grep 1455   # 14550, 14551, 14552 が LISTEN 状態か確認
tcpdump -i eth0 -n port 14550
```

#### 問題 3: RTCM インジェクションが全ドローンに到達しない

1. 各ドローンの System ID が異なるか確認
2. ログで GPS_RTCM_DATA フレーム送信を確認
3. Pixhawk ファームウェアが RTCM インジェクションをサポートしているか確認

### マルチドローンパフォーマンス

| 項目 | 推奨値 | 備考 |
|------|--------|------|
| **最大ドローン数** | 5～10台 | ネットワーク負荷による |
| **テレメトリー周期** | 10Hz | 各ドローン共通 |
| **RTCM 更新周期** | 1Hz | 全ドローン共通 |
| **接続タイムアウト** | 10秒 | 設定で変更可能 |

---

## トラブルシューティング

### 症状別対応

#### 症状 1: Pixhawk に接続できない

**ログ**:
```
[ERROR] Serial port open failed: Permission denied
```

**原因と対処**:
1. Pixhawk の電源が入っているか確認
2. USB ケーブルが正しく接続されているか確認
3. Pixhawk を再起動
4. 別の USB ポートで試す

```bash
# USB デバイスを確認
ls -la /dev/ttyACM*

# パーミッションを修正（必要に応じて）
sudo usermod -a -G dialout $USER
```

#### 症状 2: ハートビートが受信できない

**ログ**:
```
[WARNING] Active drones: []
```

**原因と対処**:
1. Pixhawk が起動モードにあるか確認（通常は Pixhawk の青 LED が点灯）
2. Pixhawk のシリアル接続設定を確認（ボーレート 115200 か）
3. MAVLink フレームワークが有効か確認
4. backend_server を再起動

```bash
# backend_server 再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py
```

#### 症状 3: RTCM データが配信されない

**ログ**:
```
[ERROR] RTCM Reader error: Connection refused
```

**原因と対処**:
1. u-center で TCP Server が起動しているか確認
2. ポート 2101 が正しく設定されているか確認
3. ファイアウォールでポート 2101 が開いているか確認

```bash
# ポート確認
netstat -an | grep 2101

# リッスン状態が見えない場合は u-center で再設定
```

#### 症状 4: メモリ使用量が増加

**症状**: Backend プロセスのメモリが徐々に増加

**原因と対処**:
1. テレメトリーバッファが満杯 → backend を再起動
2. ログファイルが肥大化 → ログをアーカイブ・削除

```bash
# ログファイルをリセット
mv gcs.log gcs.log.bak
gzip gcs.log.bak

# Backend を再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py
```

#### 症状 5: コマンド送信が反応しない

**症状**: ARM/DISARM コマンド送信後、応答がない

**原因と対処**:
1. Pixhawk がアーム状態か確認
2. MAVLink コマンドが正しいか確認
3. System ID が一致しているか確認

```bash
# ログで Command Ack を確認
tail -f gcs.log | grep -i "command"
```

---

## チェックリスト

### 毎日の起動チェック

- [ ] Pixhawk 電源 ON
- [ ] LED が点灯確認
- [ ] Raspberry Pi SSH ログイン可能
- [ ] `backend_server` 起動成功
- [ ] ハートビート受信確認 (`Active drones: [1]`)
- [ ] GPS ロック状態確認
- [ ] (RTK 使用時) RTCM インジェクション確認

### 毎週の定期メンテナンス

- [ ] ログファイルサイズ確認
- [ ] エラーメッセージの確認
- [ ] GPS 精度が低下していないか
- [ ] Pixhawk が正常に動作しているか
- [ ] ネットワーク接続が安定しているか

### 毎月の詳細チェック

- [ ] シリアル接続の信頼性確認
- [ ] パッケージのアップデート
- [ ] ドライバーの確認（USB CDC ACM）
- [ ] ファイアウォール設定の確認

---

## 緊急時対応

### 全システム停止した場合

```bash
# 1. 接続を切断
ssh taki@100.123.158.105 "pkill -f backend_server"

# 2. Pixhawk を再起動（電源OFF → 5秒待機 → ON）

# 3. Raspberry Pi を再起動
ssh taki@100.123.158.105 "sudo reboot"

# 4. 再起動後、Backend を起動
ssh taki@100.123.158.105 "cd ~/GCS-UmemotoLab && .venv/bin/python app/backend_server.py"

# 5. ハートビート受信を確認
```

### ネットワーク接続が不安定

```bash
# 1. Raspberry Pi のネットワーク接続を確認
ssh taki@100.123.158.105 "ip addr | grep inet"

# 2. ルーターを再起動
# (物理的にルーターの電源をOFF → 10秒待機 → ON)

# 3. Raspberry Pi を再起動
ssh taki@100.123.158.105 "sudo reboot"
```

### USB シリアルポート認識エラー

```bash
# 1. ホットプラグ解除
ssh taki@100.123.158.105 "sudo tee /sys/bus/usb/devices/*/remove"

# 2. USB ポートをリセット
ssh taki@100.123.158.105 "sudo usb-devices"

# 3. Pixhawk を再接続
```

---

## よくある質問（FAQ）

**Q1: Backend を常時起動させるにはどうすれば良いか？**

A: systemd サービスを作成：

```bash
cat > /etc/systemd/system/gcs-backend.service << 'EOF'
[Unit]
Description=GCS Backend Server
After=network.target

[Service]
Type=simple
User=taki
WorkingDirectory=/home/taki/GCS-UmemotoLab
ExecStart=/home/taki/GCS-UmemotoLab/.venv/bin/python app/backend_server.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable gcs-backend
sudo systemctl start gcs-backend
```

**Q2: ログをファイルに保存するにはどうすれば良いか？**

A: Backend 起動時にリダイレクト：

```bash
.venv/bin/python app/backend_server.py >> gcs.log 2>&1 &
```

**Q3: 複数ドローンを管理する場合、何か特別な設定が必要か？**

A: config ファイルで複数 System ID を定義するだけで自動対応します。
本マニュアルの [マルチドローン運用](#マルチドローン運用) セクションを参照してください。

**Q4: 本番環境でのセキュリティ設定は？**

A: 
- ネットワークを閉鎖 LAN に限定
- SSH の公開鍵認証を使用
- ファイアウォールで不要なポートを塞ぐ

---

## サポートと連絡

問題が発生した場合：

1. このマニュアルの該当セクションを確認
2. `gcs.log` の最後の 50 行を確認
3. GitHub Issues に報告

```bash
# ログの最後を表示
tail -50 gcs.log
```

---

**最終更新**: 2026-04-24  
**バージョン**: 1.0
