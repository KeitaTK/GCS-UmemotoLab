# トラブルシューティングレポート: ドローン非認識問題 (2026-06-16)

## 概要

Tailscale 経由で SSH 接続した Raspberry Pi 5 上で mavlink-router が稼働しているにも関わらず、GCS UI 上でドローン（Pixhawk 6C）が認識されない問題を調査・修正した。

## 環境

| 項目 | 値 |
|------|-----|
| 日時 | 2026-06-16 |
| Raspberry Pi | Pi 5 (raspi5), Raspberry Pi OS Bookworm |
| Tailscale IP (Pi) | `100.123.158.105` |
| mavlink-router | v4-16-g2362c62 |
| GCS PC | macOS (MacBook Air) |
| Pixhawk | Pixhawk 6C (ArduPilot), System ID=1 |
| 接続方式 | Pixhawk TELEM1 ↔ Raspi GPIO (UART) |

## 発見された問題と修正

### 問題1: UART デバイスの誤り 🔴 Critical

**症状**: mavlink-router が `/dev/serial0`（→ `ttyAMA10`）で UART を開いているが、Pixhawk からのデータを全く受信していなかった（Received: 0）。

**原因**: Raspberry Pi 5 では `dtoverlay=uart0-pi5` が設定されている場合:
- `/dev/serial0` → `ttyAMA10`（RP1 チップの PL011 rev2 UART）
- 実際の Pixhawk データは `/dev/ttyAMA0`（BCM2712 の PL011 AXI UART）に流れていた

`ttyAMA10` は GPIO 14/15 にマッピングされる UART だが、ハードウェアフロー制御（CTS/RTS）の設定不備により Pixhawk からのデータが到達していなかった。

**確認方法**:
```bash
# mavlink-router を停止し、直接シリアルを読み取る
sudo systemctl stop mavlink-router
python3 -c "
import serial
ser = serial.Serial('/dev/ttyAMA0', 115200, timeout=1)
print('ttyAMA0:', ser.read(100).hex())
ser.close()
"
# → MAVLink v2 パケット (0xFD で始まる) を確認
```

**修正**: `/etc/mavlink-router/main.conf` の `Device` を変更
```ini
# 修正前
Device = /dev/serial0    # → ttyAMA10 (データなし)

# 修正後
Device = /dev/ttyAMA0    # 実データあり
```

---

### 問題2: MAVLink v1/v2 バージョン不一致 🟡 Warning

**症状**: GCS が生成する MAVLink パケットが v1（magic=0xFE）だが、mavlink-router が v2（magic=0xFD）のみを受け付ける設定になっていた。

**原因**: 
- `config/gcs.yml` の `MavlinkVersion=2.0` 設定
- pymavlink がデフォルトで v1 パケットを生成していた（Python 3.14 + pymavlink 最新版の仕様）

**修正**: `/etc/mavlink-router/main.conf` から `MavlinkVersion` 行を削除し、自動検出（両対応）に変更
```ini
# 修正前
[General]
MavlinkVersion=2.0

# 修正後  
[General]
# MavlinkVersion を指定しない → 自動検出（v1/v2 両対応）
```

---

### 問題3: Tailscale 経由 UDP パケット不達 🔴 Critical

**症状**: Mac → Pi への Tailscale 経由 UDP パケットが mavlink-router のポート 14550 に到達しなかった。

**調査結果**:
1. Mac → Pi の UDP 到達性はポート 14551, 14552, 14555 で Python リスナーにより確認済み ✅
2. 同一ポート 14550 でも Python リスナーは `127.0.0.1`（ローカルホスト）からのパケットを受信 ✅
3. しかし mavlink-router は Tailscale 経由のパケットを全く受信せず ❌
4. Pi 上の nftables（Tailscale 管理）では、tailscale0 インターフェース経由の全トラフィックが許可されている
5. 原因は未特定だが、Tailscale のカーネルネットワークスタックと mavlink-router のソケット間で特定ポートのトラフィックが欠落する現象と推測される

**回避策**: **SSH トンネル方式に切り替え**

SSH トンネルは Tailscale の TCP（SSH）を利用するため、UDP の不達問題を回避できる。

```bash
# SSH トンネル確立
ssh -f -N -L 14550:localhost:14550 -L 5760:localhost:5760 raspi

# GCS 設定を SSH トンネル用に更新
# endpoint: "127.0.0.1:14550"
# udp_listen_port: 14551
```

**注意**: Tailscale の `userspace-networking` モード（`--tun=userspace-networking`）が有効な環境では、
UDP 転送に既知の制限がある。`tailscale up --tun=auto` で kernel networking モードに切り替えることで
改善する可能性がある。

---

### 問題4: pymavlink decode() バグ 🟡 Warning

**症状**: `conn.mav.decode(data)` 呼び出し時に `'bytes' object has no attribute 'append'` エラーが発生。

**原因**: pymavlink の生成コード（`dialects/v10/ardupilotmega.py` line 15725）で、`crcbuf` が `bytes` 型として生成され、`.append()` メソッドが存在しなかった。

```python
# バグのあるコード
crcbuf = msgbuf[1 : -(2 + signature_len)]  # bytes 型
crcbuf.append(crc_extra)                    # AttributeError!
```

Python 3.14 の `bytes` 型の厳格化、または pymavlink の生成コードの不具合が原因。

**修正**: `.venv/lib/python3.14/site-packages/pymavlink/dialects/v10/ardupilotmega.py`
```python
# 修正後
crcbuf = bytearray(msgbuf[1 : -(2 + signature_len)])
```

> **注意**: これは仮想環境内のファイルを直接編集した修正であり、`pip install` の再実行で上書きされる。
> 恒久対応として `requirements.txt` に pymavlink のパッチバージョンを固定することを推奨。

**関連修正**: `app/mavlink/connection.py`
```python
# 修正前
self.mav = mavutil.mavlink.MAVLink(None)

# 修正後
self.mav = mavutil.mavlink.MAVLink(bytearray())
```
`bytearray()` を使用することで MAVLink デコーダの内部バッファがミュータブルになることを保証。

---

## 設定ファイルの変更

### Mac (GCS) 側: `config/gcs_local.yml`

```yaml
# 修正前: Tailscale 直結 UDP モード
udp_listen_port: 14550
drones:
  drone1:
    endpoint: "100.123.158.105:14550"

# 修正後: SSH トンネルモード
udp_listen_port: 14551  # SSH トンネルが 14550 を使用
drones:
  drone1:
    endpoint: "127.0.0.1:14550"
    name: "Pixhawk6C Main"
```

### Raspberry Pi 側: `/etc/mavlink-router/main.conf`

```ini
# 修正後
[General]
ReportStats=true

[UartEndpoint pixhawk]
Device = /dev/ttyAMA0
Baud = 115200

[UdpEndpoint gcs]
Address = 0.0.0.0
Port = 14550
Mode = Server
```

## 検証結果

```text
✅ 9 HEARTBEATs received in 8 seconds
   SysID=1, Type=2 (MAV_TYPE_QUADROTOR)
   Autopilot=3 (MAV_AUTOPILOT_ARDUPILOTMEGA)
   Status=4 (MAV_STATE_ACTIVE)
   Base Mode=0xd8 (armed + custom mode + safety enabled)
```

## 起動手順（修正後）

```bash
# 1. SSH トンネル確立（別ターミナル）
ssh -f -N -L 14550:localhost:14550 -L 5760:localhost:5760 raspi

# 2. GCS 起動
cd GCS-UmemotoLab
source .venv/bin/activate
export GCS_CONFIG_PATH=config/gcs_local.yml
export PYTHONPATH=$PYTHONPATH:$(pwd)/app
python app/main.py
```

## 教訓

1. **Raspberry Pi 5 の UART マッピング**: `dtoverlay=uart0-pi5` は `/dev/serial0 → ttyAMA10` にマッピングするが、ハードウェアフロー制御（CTS/RTS）が正しく設定されないと Pixhawk からのデータを受信できない場合がある。`/dev/ttyAMA0` を直接指定する方が安全。

2. **Tailscale UDP 転送**: Tailscale の UDP 転送は TCP ほど信頼性が高くない。特に mavlink-router との組み合わせでは SSH トンネル（TCP）の利用を推奨。

3. **MAVLink バージョン**: mavlink-router の `MavlinkVersion` は指定しないことで v1/v2 両対応になる。

4. **pymavlink のバージョン管理**: Python のマイナーバージョンアップグレード時に pymavlink の生成コードに非互換が生じる可能性がある。
