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
ssh taki@192.168.11.19

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
ssh taki@192.168.11.19 "pkill -f backend_server"

# 2. Pixhawk を再起動（電源OFF → 5秒待機 → ON）

# 3. Raspberry Pi を再起動
ssh taki@192.168.11.19 "sudo reboot"

# 4. 再起動後、Backend を起動
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && .venv/bin/python app/backend_server.py"

# 5. ハートビート受信を確認
```

### ネットワーク接続が不安定

```bash
# 1. Raspberry Pi のネットワーク接続を確認
ssh taki@192.168.11.19 "ip addr | grep inet"

# 2. ルーターを再起動
# (物理的にルーターの電源をOFF → 10秒待機 → ON)

# 3. Raspberry Pi を再起動
ssh taki@192.168.11.19 "sudo reboot"
```

### USB シリアルポート認識エラー

```bash
# 1. ホットプラグ解除
ssh taki@192.168.11.19 "sudo tee /sys/bus/usb/devices/*/remove"

# 2. USB ポートをリセット
ssh taki@192.168.11.19 "sudo usb-devices"

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
詳細は [マルチドローン運用ガイド](./multidrone_operations_guide.md) を参照。

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
