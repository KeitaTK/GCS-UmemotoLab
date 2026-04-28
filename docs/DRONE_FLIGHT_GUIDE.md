# ドローン飛行ガイド - GCS-UmemotoLab

このガイドは、GCS-UmemotoLab プロジェクトで開発されたシステムを用いて、実際にドローンを飛ばすための手順をまとめたものです。

---

## システム構成

```
Pixhawk/ドローン
        ↓ USB/Serial
  Raspberry Pi 5 (RTCM注入・制御)
        ↓ TCP/Wi-Fi
  Windows PC (GCS・RTK基地局)
```

---

## ステップ 1: 準備（最初の1回のみ）

### 1-1. Pixhawk の設定

- ArduPilot ファームウェアをインストール
- ドローンに GPS/RTK モジュール（ublox F9P 推奨）を接続
- パラメータ設定：
  - `SERIAL2_PROTOCOL` = 2 (MAVLink)
  - `SYSID_THISMAV` = ドローンのシステムID（通常は 1）
  - GPS 接続確認

### 1-2. ublox（RTK基地局用GPS受信機）の設定

- Windows PC に USB で接続（COM8）
- u-center で RTCM 出力を有効化
  - MSG 配信：F5-05（RTCM 1005）、F5-4D（RTCM 1077）など
  - 出力ポート：USB
  - 出力レート：1Hz

---

## ステップ 2: 本番運用時の起動手順

### **2-1. Windows PC 側：RTK基地局の起動**

```powershell
# リポジトリディレクトリへ移動
cd c:\Users\taita\github\GCS-UmemotoLab

# 仮想環境を有効化
.\.venv\Scripts\Activate.ps1

# RTK基地局を起動（ubloxからRTCMを受信、TCP 2101で配信）
python rtk_base_station.py --serial-port COM8 --baudrate 115200 --tcp-host 0.0.0.0 --tcp-port 2101 --log-level INFO
```

**期待される出力:**
```
INFO: RTK Base Station started
INFO: Listening on 0.0.0.0:2101
INFO: RTCM frames: 3 received (106 bytes each)
```

### **2-2. Raspberry Pi 側：ドローン通信ブリッジの起動**

```powershell
# Raspberry Pi にSSH接続
ssh taki@192.168.11.19

# ディレクトリ移動と仮想環境有効化
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# backend_server を起動（RTCMを受信しドローンへ注入）
python app/backend_server.py
```

**期待される出力:**
```
INFO: RTCM connection to 192.168.11.62:2101 established
INFO: Injecting RTCM frame to Pixhawk (104 bytes)
INFO: Heartbeat from system 1
```

### **2-3. Pixhawk/ドローン を USB で接続**

- Pixhawk を Raspberry Pi に USB または UART で接続（/dev/ttyACM0 または /dev/ttyAMA0）
- `backend_server.py` の設定ファイルを確認：
  ```yaml
  # config/gcs_local.yml
  connection_type: serial
  serial_port: /dev/ttyACM0
  serial_baudrate: 115200
  ```

---

## ステップ 3: GCS（グラウンドコントロール）から操作

### **オプション A: GUI を使う場合**

```powershell
# Windows PC で GCS GUI を起動
python app/main.py
```

- テレメトリー（高度、速度、姿勢）を表示
- コマンド送信（Arm、Takeoff、Land など）

### **オプション B: CLI / スクリプトで自動制御する場合**

```powershell
# 例：ドローンを ARM する
python -c "
from app.mavlink.command_dispatcher import CommandDispatcher
from pymavlink import mavutil

# Pixhawk に接続
m = mavutil.mavlink_connection('udpin:0.0.0.0:14550')

# ARM コマンド送信
m.mav.command_long_send(
    1, 0,  # System ID, Component ID
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 1, 0, 0, 0, 0, 0
)
print('ARM command sent')
"
```

---

## 本番飛行チェックリスト

| 項目 | 確認内容 |
|------|---------|
| ✅ RTK基地局 | Windows 側 `rtk_base_station.py` が RTCM 配信中 |
| ✅ ドローンブリッジ | Raspberry Pi 側 `backend_server.py` が RTCM を受信・注入 |
| ✅ GPS信号 | Pixhawk に GPS 受信（3つ以上の衛星） |
| ✅ ネットワーク | Windows PC と Raspberry Pi が 192.168.11.x に接続 |
| ✅ 磁気センサー | Pixhawk が Compass キャリブレーション済み |
| ✅ シミュレーションモード | 初回は `--sitl` で模擬飛行テスト |

---

## トラブルシューティング

| 問題 | 原因 | 対処法 |
|------|------|--------|
| RTK基地局が起動しない | COM8 未接続 | ublox を USB で接続し、`mode com8` で確認 |
| `Connection refused: 14550` | backend_server が起動していない | Raspberry Pi で `python app/backend_server.py` を実行 |
| GPS Fix が出ない | RTCM 注入パスのエラー | `backend_server.py` のログで `Injecting RTCM` を確認 |
| ハートビート受信なし | Pixhawk 未接続 | `/dev/ttyACM0` の接続と設定ファイルを確認 |

---

## まとめ

実際にドローンを飛ばすには以下の順序で起動します：

```
1. Windows: rtk_base_station.py 起動
   ↓
2. Raspberry Pi: backend_server.py 起動
   ↓
3. Pixhawk/ドローンを接続
   ↓
4. Windows: main.py (GCS) または CLI で制御
   ↓
5. ドローン離陸・飛行
```

---

## 参照資料

- [運用マニュアル](operations_manual.md)
- [RTK基地局実装レポート](RTK_BASE_STATION_FINAL_REPORT.md)
- [トラブルシューティングガイド](troubleshooting_guide.md)
- [多機ドローン運用ガイド](multidrone_operations_guide.md)
