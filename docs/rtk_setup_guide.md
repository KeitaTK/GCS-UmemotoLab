# RTK/RTCM セットアップガイド

このガイドは、u-center を使用して Pixhawk に RTK 補正を配信するための手順を説明します。

## 前提条件

- STRSSVR（u-blox RTCMストリーム配信ツール）がインストール済み
- ublox F9P（またはRTK対応GPS）が Windows PC に USB で接続済み（COM8 推奨）
- Pixhawk6C が Raspberry Pi に接続済み
- GCS Backend が動作可能な状態
- Windows PC と Raspberry Pi が同じネットワーク（LAN）に接続済み

---

## セットアップ手順

### Step 1: ublox が Windows PC に接続されていることを確認

1. ublox F9P を USB ケーブルで Windows PC に接続
2. デバイスマネージャーで COM ポートを確認（例: `COM8`）
3. 必要に応じて u-center で GPS 信号受信を確認

### Step 2: STRSSVR をインストール

STRSSVR は u-blox が提供する RTCM ストリーム配信ツールです：

1. [u-blox RTK ツールダウンロードページ](https://www.u-blox.com/product/strssvr) にアクセス
2. STRSSVR をダウンロードして解凍
3. Windows の場合：`strsvr.exe` を実行可能にする

### Step 3: STRSSVR で RTCM を TCP ポートへ配信

#### STRSSVR を起動・設定

**Windows 側で実行:**

```powershell
# STRSSVR を起動（例：C:\tools\strsvr.exe）
C:\tools\strsvr.exe
```

STRSSVR の GUI が起動します：

1. **Main tab**:
   - **Input** セクション:
     - **Mode**: `Serial` を選択
     - **Port**: ublox の接続ポート（例: `COM8`）
     - **Bitrate**: `115200`
   - **Output** セクション:
     - **Mode**: `TCP Server` を選択
     - **Port**: `2101`
     - **Server name/IP**: `0.0.0.0` （全インターフェースでリッスン）

2. **Message** tab:
   - **RTCM3** をチェック
   - **1005 (Stationary RTK reference station ARP)**
   - **1077 (GPS Full pseudo-range and carrier phases)**
   - **1087 (GLONASS Full pseudo-range and carrier phases)**

3. **Start** ボタンをクリック

**期待される出力:**
```
rtcm3 0 0
rtcm3 1005 0 0
rtcm3 1077 0 0
...
Server opened: 0.0.0.0:2101
Waiting for client connection...
```

### Step 4: GCS Backend を起動（RTCM 有効化）

Raspberry Pi で以下を実行。**STRSSVR は Windows で起動している前提です**：

```bash
# config/gcs_local.yml で RTCM を有効化
# rtcm_host を Windows PC の LAN IP に設定（例: 192.168.11.62）
ssh taki@192.168.11.19 "cat > ~/GCS-UmemotoLab/config/gcs_local.yml << 'EOF'
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
rtcm_enabled: true
rtcm_host: 192.168.11.62
rtcm_tcp_port: 2101
udp_listen_port: 14550
drones:
  drone1:
    system_id: 1
    endpoint: 127.0.0.1:14550
EOF
"

# backend_server を起動
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && timeout 60 .venv/bin/python app/backend_server.py 2>&1 | grep -E 'RTCM|heartbeat|Active drones'"
```

**重要**: `rtcm_host` は STRSSVR が起動している **Windows PC の LAN IP アドレス** に設定してください（例: `192.168.11.62`）

### Step 5: RTCM インジェクション確認

ログを監視して以下を確認：

```
[INFO] Connected to RTCM source: 127.0.0.1:2101
[INFO] RTCM data injected: X bytes in Y frame(s)
```

---

## トラブルシューティング

### 問題 1: RTCM 接続失敗

**エラーメッセージ**:
```
[ERROR] RTCM Reader error: Connection refused
```

**解決方法**:
1. STRSSVR が Windows PC で起動しているか確認：`netstat -an | findstr 2101`
2. Raspberry Pi から Windows へ接続確認：`ssh taki@192.168.11.19 "telnet 192.168.11.62 2101"`
3. rtcm_host が正しい Windows IP アドレスに設定されているか確認（`localhost` や `127.0.0.1` ではなく `192.168.11.62` など）
4. ファイアウォール設定を確認（ポート 2101 が開いているか）

### 問題 2: STRSSVR が起動しない

**確認項目**:
1. ublox が COM8（またはご使用のポート）に接続しているか確認
2. STRSSVR 起動時に「Port already in use」エラーが出ていないか
3. ポート 2101 が他のアプリケーションで使用されていないか確認：
   ```powershell
   netstat -ano | findstr :2101
   # プロセスがあれば、そのプロセスを終了する
   taskkill /PID <PID> /F
   ```

### 問題 3: STRSSVR が「Waiting for client connection」のまま応答しない

**原因**: ublox からのシリアル入力がない

**解決方法**:
1. u-center で ublox が接続しているか確認
2. STRSSVR の **Main** tab で **Input Mode** が `Serial` になっているか確認
3. ublox の LED が点灯（信号受信）しているか確認

### 問題 4: RTCM フレーム形式エラー

**エラーメッセージ**:
```
[ERROR] RTCM frame parse error
```

**解決方法**:
1. STRSSVR の **Message** tab で **RTCM3** が選択されているか確認
2. RTCM1 や RTCM2 ではなく **RTCM3** を使用してください
3. STRSSVR 出力に「rtcm3」表示があるか確認

### 問題 5: Pixhawk が RTCM を受け取らない

**確認項目**:
1. Pixhawk のシリアル接続が確立されているか確認：
   ```bash
   ssh taki@192.168.11.19 "ls -la /dev/ttyACM0"
   ```
2. backend_server のログに `GPS_RTCM_DATA` 送信が記録されているか確認
3. Pixhawk のファームウェアが RTCM インジェクションをサポートしているか確認（ArduCopter/ArduPlane v4.1 以上推奨）

---

## 動作確認

### チェックリスト

- [ ] u-center が NTRIP に接続している
- [ ] RTCM ストリームが TCP 2101 から配信されている
- [ ] backend_server が起動している
- [ ] ログに「RTCM data injected」メッセージが出力されている
- [ ] Pixhawk の GPS 精度が改善している（GPS Fix type が向上）

---

## 詳細設定

### config/gcs_local.yml の RTCM オプション

```yaml
# RTCM/RTK settings
rtcm_enabled: true              # RTCM インジェクション有効化
rtcm_host: 127.0.0.1            # RTCM ストリーム配信元ホスト
rtcm_tcp_port: 2101             # RTCM ストリーム受信ポート
```

### 複数 Drone への RTCM 配信

マルチドローン構成では、複数のシステム ID へ自動的に RTCM が配信されます：

```yaml
drones:
  drone1:
    system_id: 1
    endpoint: 127.0.0.1:14550
  drone2:
    system_id: 2
    endpoint: 127.0.0.1:14551
```

RTCM データは両ドローンに配信されます。

---

## 参考リンク

- [STRSSVR ユーザーガイド](https://www.u-blox.com/product/strssvr)
- [ublox F9P RTK 製品説明書](https://www.u-blox.com/en/product/zed-f9p-module)
- [国土地理院 GNSS 連続観測システム](https://www.gsi.go.jp/buturisokuryo/gnss_top.html)
- [RTCM フォーマット仕様](https://www.rtcm.org/)
- [ArduPilot RTK セットアップガイド](https://ardupilot.org/copter/docs/rtk-gps.html)

---

**セットアップに問題が発生した場合：**
1. STRSSVR のコンソール出力を確認
2. ファイアウォール設定を確認（ポート 2101）
3. Raspberry Pi から `telnet <Windows_IP> 2101` で TCP 接続をテスト
