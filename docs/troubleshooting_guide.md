# トラブルシューティングガイド

GCS-UmemotoLab で発生する可能性のある問題と解決方法をまとめています。

---

## クイックリファレンス

| 症状 | 原因 | 解決方法 |
|------|------|---------|
| Pixhawk に接続できない | USB 接続不良 | ケーブル確認、別ポートで試す |
| ハートビート受信なし | Pixhawk 非起動 | Pixhawk 電源確認 |
| RTCM 接続エラー | u-center 未起動 | u-center 起動、TCP Server 開始 |
| メモリ使用量増加 | バッファ満杯 | Backend 再起動 |
| GPS Fix が改善しない | RTK 未設定 | RTCM 配信設定確認 |

---

## 詳細トラブルシューティング

### カテゴリ 1: 接続関連

#### 1-1. "Permission denied" エラー

**完全なエラーメッセージ**:
```
[ERROR] Serial port open failed: Permission denied
```

**原因**:
- ユーザーが dialout グループに属していない
- USB デバイスのパーミッションが制限されている

**解決手順**:

```bash
# Step 1: 現在のグループを確認
groups $USER

# Step 2: dialout グループに追加
sudo usermod -a -G dialout $USER

# Step 3: 新規グループ設定を反映
# ← ログアウト・ログインが必要

# または一度シェルを再起動
exec su - $USER

# Step 4: 確認
groups $USER | grep dialout
```

#### 1-2. "Device not found" エラー

**完全なエラーメッセージ**:
```
[ERROR] Serial port /dev/ttyACM0 not found
```

**原因**:
- Pixhawk が接続されていない
- USB ケーブルが不良
- Pixhawk が起動していない

**解決手順**:

```bash
# Step 1: USB デバイスを確認
lsusb
# Pixhawk6C の場合: "Holybro" または "Pixhawk" が表示されるはず

# Step 2: シリアルポートを確認
ls -la /dev/ttyACM*
ls -la /dev/ttyUSB*

# Step 3: ケーブルの再接続
# ケーブルを抜いて 10 秒待機してから再度接続

# Step 4: Pixhawk を再起動
# 物理的に電源を OFF → 5 秒待機 → ON

# Step 5: デバイスが再認識されたか確認
dmesg | tail -10 | grep -i "tty\|acm"
```

#### 1-3. "Connection timed out" エラー

**完全なエラーメッセージ**:
```
[ERROR] Connection timed out: Connection refused
```

**原因**:
- Pixhawk が起動していない
- シリアル通信が確立されていない
- ボーレート設定が不正

**解決手順**:

```bash
# Step 1: Pixhawk が起動しているか確認（LED が点灯）

# Step 2: ボーレート設定を確認
# config/gcs_local.yml で serial_baudrate を確認（115200 が標準）

# Step 3: 別のシリアルツールで接続確認
sudo minicom -D /dev/ttyACM0 -b 115200

# Step 4: Pixhawk のシリアル設定を確認
# QGroundControl で接続して確認

# Step 5: Backend を再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py
```

---

### カテゴリ 2: テレメトリー関連

#### 2-1. "Active drones: []" - ドローン未検出

**症状**:
```
[INFO] Active drones: []
```

が表示され続ける

**原因**:
- Pixhawk が HEARTBEAT を送信していない
- MAVLink フレームワークが無効
- ボーレート不一致

**解決手順**:

```bash
# Step 1: Pixhawk の MAVLink ストリームを確認
sudo mavproxy.py --master=/dev/ttyACM0 --baudrate=115200 --out=127.0.0.1:14550 &

# Step 2: ストリームが出力されているか確認
# 「Received X msgs」 という表示が増加していれば正常

# Step 3: ボーレート設定を確認
# QGroundControl で接続 → 設定 → Pixhawk → SRx_* パラメータ確認

# Step 4: Pixhawk の再起動
# 電源を OFF → 5 秒待機 → ON

# Step 5: Backend を再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py
```

#### 2-2. "Heartbeat received" だがテレメトリーが来ない

**症状**:
```
[INFO] Drone 1: heartbeat received (bytes)
```
が表示されるが、位置情報などのデータがない

**原因**:
- テレメトリーストリーム レート設定が低い
-特定のメッセージタイプがフィルタリングされている
- Pixhawk の設定ファイルが不正

**解決手順**:

```bash
# Step 1: テレメトリーレート設定を確認
# QGroundControl でパラメータを確認

# Step 2: ストリームレート を上げる
# SRx_EXT_STAT: 5 Hz
# SRx_EXTRA1: 5 Hz
# SRx_EXTRA2: 5 Hz
# SRx_EXTRA3: 2 Hz

# Step 3: Pixhawk を再起動
# 設定が反映されるまで待機

# Step 4: ログで受信メッセージを確認
.venv/bin/python app/backend_server.py 2>&1 | grep -i "SYS_STATUS\|GLOBAL_POSITION"
```

---

### カテゴリ 3: RTK/RTCM 関連

#### 3-1. "RTCM Reader error: Connection refused"

**完全なエラーメッセージ**:
```
[ERROR] RTCM Reader error: Connection refused
```

**原因**:
- STRSSVR が起動していない
- STRSSVR の Output TCP Server が起動していない
- ポート 2101 が誤設定

**解決手順**:

```bash
# Step 1: Windows PC で STRSSVR を起動
# C:\\tools\\strsvr.exe を実行

# Step 2: STRSSVR を設定
# - Input: Serial モード (COM8, 115200 baud)
# - Output: TCP Server (0.0.0.0:2101)
# - Message: RTCM3 を選択

# Step 3: Start をクリック

# Step 4: Raspberry Pi で設定を確認
ssh taki@192.168.11.19 "cat ~/GCS-UmemotoLab/config/gcs_local.yml | grep rtcm"

# Step 5: Backend を再起動して接続確認
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py 2>&1 | head -20
```

#### 3-2. "RTCM data injected" ログが出ない

**症状**:
```
[INFO] Connected to RTCM source: 127.0.0.1:2101
```

は出るが、その後 `RTCM data injected` ログがない

**原因**:
- Pixhawk が GPS_RTCM_DATA メッセージを受け入れていない
- RTCM フレームが形式不正
- Pixhawk ファームウェアが対応していない

**解決手順**:

```bash
# Step 1: RTCM フォーマットを確認
# STRSSVR で RTCM3 を選択しているか確認

# Step 2: Pixhawk ファームウェアを確認
# QGroundControl で接続
# About をクリック → Firmware Version を確認
# Pixhawk6C は GPS_RTCM_DATA をサポートしているはず

# Step 3: ログで GPS_RTCM_DATA フレーム送信を確認
.venv/bin/python app/backend_server.py 2>&1 | grep -i "GPS_RTCM_DATA"

# Step 4: Pixhawk で GPS ステータスを確認
# QGroundControl: Vehicle ページ → GPS
# RTK が有効か確認
```

---

### カテゴリ 4: パフォーマンス関連

#### 4-1. メモリ使用量が徐々に増加

**症状**:
```
# ps aux で確認
# backend_server プロセスのメモリが 10% → 20% → 30% ...
```

**原因**:
- テレメトリーバッファがメモリリーク
- ログファイルが肥大化
- 接続が頻繁に確立・切断されている

**解決手順**:

```bash
# Step 1: メモリ使用量を確認
ps aux | grep backend_server

# Step 2: プロセスを再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py &

# Step 3: ログファイルサイズを確認
du -h gcs.log

# Step 4: ログをアーカイブ・削除
mv gcs.log gcs.log.bak
gzip gcs.log.bak

# Step 5: 定期的にログをローテーションするスクリプトを設定
cat > rotate_logs.sh << 'EOF'
#!/bin/bash
if [ -f gcs.log ] && [ $(stat -f%z gcs.log) -gt 100000000 ]; then
  mv gcs.log gcs.log.$(date +%Y%m%d)
  gzip gcs.log.*
fi
EOF

# crontab で定期実行
crontab -e
# 毎日 00:00 に実行
# 0 0 * * * /home/taki/GCS-UmemotoLab/rotate_logs.sh
```

#### 4-2. CPU 使用率が高い

**症状**:
```
# top コマンドで backend_server の CPU が 50% 以上
```

**原因**:
- メッセージ処理が追いつかない
- ポーリング間隔が短すぎる
- ログ出力が多すぎる

**解決手順**:

```bash
# Step 1: CPU 使用率を確認
top -p $(pgrep -f backend_server)

# Step 2: ログレベルを下げる
# app/logging_config.py で DEBUG → INFO に変更

# Step 3: ポーリング間隔を調整
# app/mavlink/message_router.py の sleep 時間を増加

# Step 4: Backend を再起動
pkill -f backend_server
sleep 2
.venv/bin/python app/backend_server.py &
```

---

### カテゴリ 5: 複数ドローン関連

#### 5-1. 特定のドローンからデータが来ない

**症状**:
```
[INFO] Active drones: [1, 2]
[INFO] Drone 1: heartbeat received
# Drone 2 のメッセージが出ない
```

**原因**:
- Drone 2 の Pixhawk が接続されていない
- System ID が重複している
- ボーレート設定が異なる

**解決手順**:

```bash
# Step 1: config で System ID を確認
cat config/gcs_local.yml | grep system_id

# Step 2: 各ドローンの Pixhawk を物理的に確認

# Step 3: System ID の重複を確認
# QGroundControl で各ドローンに接続 → パラメータ確認
# SYSID_THISMAV パラメータを確認

# Step 4: 接続ポートを確認
# mavlink-router の設定を確認
ssh taki@192.168.11.19 "ps aux | grep mavlink"

# Step 5: 各ドローンを個別に テスト
# Drone 1 だけ接続 → 動作確認
# Drone 2 だけ接続 → 動作確認
```

---

## 自動診断スクリプト

以下のスクリプトで自動診断が可能です：

```bash
#!/bin/bash
echo "=== GCS Diagnostics ==="
echo "1. Pixhawk Connection"
ls -la /dev/ttyACM* 2>/dev/null || echo "  No device found"

echo "2. Network"
ping -c 1 192.168.11.19 && echo "  Raspberry Pi reachable" || echo "  Raspberry Pi unreachable"

echo "3. Backend Process"
ps aux | grep backend_server | grep -v grep && echo "  Backend running" || echo "  Backend not running"

echo "4. Recent Errors"
tail -20 gcs.log | grep ERROR

echo "5. Drone Status"
tail -20 gcs.log | grep "Active drones"
```

---

## 問い合わせ・報告

問題解決できない場合は、以下の情報を含めて報告してください：

1. 完全なエラーメッセージ
2. `gcs.log` の最後 50 行
3. `lsusb` の出力
4. `ps aux | grep backend` の出力
5. 実施した対応ステップ

```bash
# 診断ファイルをまとめる
mkdir diagnostic_$(date +%Y%m%d_%H%M%S)
cp gcs.log diagnostic_*/
dmesg > diagnostic_*/dmesg.txt
lsusb > diagnostic_*/lsusb.txt
ps aux > diagnostic_*/ps.txt
tar -czf diagnostic.tar.gz diagnostic_*/
```

---

**最終更新**: 2026-04-24  
**バージョン**: 1.0
