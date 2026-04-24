# RTK/RTCM セットアップガイド

このガイドは、u-center を使用して Pixhawk に RTK 補正を配信するための手順を説明します。

## 前提条件

- u-center がインストール済み
- Pixhawk6C が Raspberry Pi に接続済み
- GCS Backend が動作中
- NTRIP キャスター (または RTCM ストリームソース) が利用可能

---

## セットアップ手順

### Step 1: u-center を起動

1. Windows PC で u-center を起動
2. メニュー → **Receiver** → **Connection** を選択
3. 利用可能なポートを選択して接続

### Step 2: NTRIP ストリームを設定

#### 方法 A: NTRIP キャスターから取得

1. u-center メニュー → **Tools** → **NTRIP Client** を開く
2. NTRIP キャスターのホストアドレス入力（例: `caster.rtk.provider.jp`）
3. ポート番号入力（一般的なデフォルト: `2101`）
4. マウントポイント選択（国土地理院 GNSS サービスなど）
5. **Add Stream** をクリック

#### 方法 B: ローカルホストで RTCM 配信を受ける場合

1. 別ターミナルで RTCM ストリームサーバーを起動
2. ポート `2101` でリッスン状態を確認

### Step 3: RTCM 出力を TCP ポートへ設定

1. u-center の **Tools** メニュー → **NTRIP Server** または **TCP Server**
2. TCP Server 設定:
   - **Host**: `127.0.0.1` または Raspberry Pi の IP（例: `192.168.11.19`）
   - **Port**: `2101`
3. RTCM3 フォーマットを選択
4. **Start** をクリック

### Step 4: GCS Backend を起動（RTCM 有効化）

Raspberry Pi で以下を実行:

```bash
# config/gcs_local.yml で RTCM を有効化
ssh taki@192.168.11.19 "cat > ~/GCS-UmemotoLab/config/gcs_local.yml << 'EOF'
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
rtcm_enabled: true
rtcm_host: 127.0.0.1
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
1. u-center で NTRIP Server が起動しているか確認
2. ポート番号が `2101` に設定されているか確認
3. ファイアウォール設定を確認（ポート 2101 が開いているか）
4. Windows/Raspberry Pi の IP アドレスが正しいか確認

### 問題 2: RTCM フレーム形式エラー

**エラーメッセージ**:
```
[ERROR] RTCM frame parse error
```

**解決方法**:
1. u-center で RTCM3 フォーマットが選択されているか確認
2. RTCM1 や RTCM2 ではなく **RTCM3** を使用してください

### 問題 3: Pixhawk が RTCM を受け取らない

**確認項目**:
1. Pixhawk のシリアル接続が確立されているか確認
2. ログに `GPS_RTCM_DATA` 送信が記録されているか確認
3. Pixhawk のファームウェアが RTCM インジェクションをサポートしているか確認

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

- [u-center User Guide](https://www.u-blox.com/en/product/u-center)
- [国土地理院 GNSS 連続観測システム](https://www.gsi.go.jp/buturisokuryo/gnss_top.html)
- [RTCM フォーマット仕様](https://www.rtcm.org/)

---

**セットアップに問題が発生した場合は、ログ出力を確認してください。**
