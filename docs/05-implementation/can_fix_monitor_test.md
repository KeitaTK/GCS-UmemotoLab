# can_fix_monitor.py テスト手順書

## 概要

`rtk_tools/can_fix_monitor.py` の動作確認手順。
Raspi CAN I/F 経由で AP_Periph (STM32) の DroneCAN Fix2 メッセージを受信できることを検証する。

---

## 前提条件

1. **CAN I/F 設定完了**
   - `deploy/can_setup_raspi.sh` が実行済みで `can0` が UP 状態
   - 確認: `ip link show can0`

2. **python-can インストール**
   ```bash
   pip install python-can
   ```

3. **AP_Periph の CAN_GNSS_FIX2_RATE 設定**
   - `CAN_GNSS_FIX2_RATE = 10` (10Hz) に設定されていること
   - 0 の場合 Fix2 は送出されない

4. **F9P が衛星を捕捉していること**
   - 屋内では受信不可。屋外または GPS リピータ環境が必要

---

## テストケース

### Test 1: 単発受信 (--once)

**手順**:
```bash
cd ~/GCS-UmemotoLab
source .venv/bin/activate
python rtk_tools/can_fix_monitor.py --once --timeout 60
```

**期待結果**:
```
Waiting for Fix2 on can0 (timeout=60s) ...
───────────────────────────────────────────────────────
mode=RTK_FIXED  status=3D_FIX  sub=0
  sats_used=28
  lat=35.xxxxxxx  lon=139.xxxxxxx
  hMSL=xxx.xxxm  hEllip=xxx.xxxm
  vel NED=(0.000,0.000,0.000) m/s
  pdop=1.2 hdop=0.7 vdop=1.0
  tdop=0.8 ndop=0.6 edop=0.5
  ts=1234567890 gnss_ts=9876543210
───────────────────────────────────────────────────────
```

**判定**:
- ✅ 成功: Fix2 メッセージが1件受信され、mode/status/sats/lat/lon/hdop が表示される
- ❌ 失敗: "No Fix2 message received (timeout)" → CAN 接続・AP_Periph 設定を確認

---

### Test 2: 連続モニタリング (--monitor)

**手順**:
```bash
python rtk_tools/can_fix_monitor.py --monitor
```

**期待結果**:
```
Continuous monitoring on can0 (Ctrl+C to stop)
elapsed  mode        status     sats  lat           lon           hMSL     hdop  vdop
───────────────────────────────────────────────────────────────────────────────────────
    0.2s  mode=RTK_FIXED  status=3D_FIX    sats= 28  lat=  35.xxxxxxx  lon= 139.xxxxxxx  hMSL=  xxx.xxm  hdop=  0.7  vdop=  1.0
    0.3s  mode=RTK_FIXED  status=3D_FIX    sats= 28  lat=  35.xxxxxxx  lon= 139.xxxxxxx  hMSL=  xxx.xxm  hdop=  0.7  vdop=  1.0
    ...
```

Ctrl+C で停止時に統計が表示される。

**判定**:
- ✅ 成功: 約10Hz (100ms間隔) で Fix2 が連続表示される
- ✅ RTK FLOAT→FIXED 遷移時にハイライト表示される
- ❌ 受信レートが 10Hz でない → AP_Periph の CAN_GNSS_FIX2_RATE を確認

---

### Test 3: デバッグログ (--log-level DEBUG)

**手順**:
```bash
python rtk_tools/can_fix_monitor.py --once --log-level DEBUG
```

**期待結果**:
CAN フレーム受信・再構築・パースの詳細ログが表示される

```
20:15:01 [INFO] can_fix_monitor: Opened: can0 (filter id=0x0042700 mask=0x1FFF00)
20:15:01 [DEBUG] can_fix_monitor: Transfer done: src=10 tid=5 size=82
```

---

### Test 4: 疑似 CAN インターフェース (vcan) でのユニットテスト

CAN ハードウェアが無い環境でも、仮想 CAN (vcan) を使ったパーサの動作確認が可能。

**セットアップ**:
```bash
# vcan 作成
sudo modprobe vcan
sudo ip link add dev vcan0 type vcan
sudo ip link set up vcan0
```

**パーサ単体テスト** (Python):
```python
# Fix2 DSDL パースの単体テスト
import struct

# Fix2 最小ペイロード (70 bytes) を構築
# ヘッダ: QQ B qq ii fff BBBB = 57 bytes
# cov_len: B = 1 byte
# DOP: eeeeee = 12 bytes
header = struct.pack("<QQBqqiifffBBBB",
    1000000, 2000000,  # ts, gnss_ts
    0,                 # num_leap_seconds
    13900000000,       # lon = 139.0 deg (1e-8)
    3500000000,         # lat = 35.0 deg (1e-8)
    50000, 40000,      # h_ellip_mm, h_msl_mm (50m, 40m)
    0.0, 0.0, 0.0,     # vel NED
    28,                # sats_used
    3,                 # status = 3D_FIX
    3,                 # mode = RTK_FIXED
    0,                 # sub_mode
)
cov_len = bytes([0])  # empty covariance
dops = struct.pack("<eeeeee", 1.2, 0.7, 1.0, 0.8, 0.6, 0.5)

payload = header + cov_len + dops
assert len(payload) == 70, f"Expected 70, got {len(payload)}"

# パース
from rtk_tools.can_fix_monitor import parse_fix2
result = parse_fix2(payload)

assert result is not None
assert result["mode"] == 3
assert result["mode_name"] == "RTK_FIXED"
assert result["status"] == 3
assert result["status_name"] == "3D_FIX"
assert result["sats_used"] == 28
assert result["lat"] == 35.0
assert result["lon"] == 139.0
assert result["hdop"] == 0.7
print("All assertions passed!")
```

---

## トラブルシュート

| 症状 | 原因 | 対処 |
|------|------|------|
| `No Fix2 message received (timeout)` | CAN 未接続 / AP_Periph 未起動 | `ip link show can0` で UP 確認、`candump can0` で生フレーム確認 |
| `python-can not installed` | 依存不足 | `pip install python-can` |
| `OSError: [Errno 19] No such device` | can0 I/F 未作成 | `deploy/can_setup_raspi.sh` を再実行 + reboot |
| 受信レートが遅い | CAN_GNSS_FIX2_RATE が低い | AP_Periph パラメータを確認し 10 以上に設定 |
| mode=UNK(255) | DSDL レイアウト不一致 | AP_Periph / DroneCAN のバージョン確認、パーサの struct フォーマット確認 |
| `struct.unpack` エラー | ペイロード破損 or DSDL 不一致 | DEBUG ログで生ペイロード長確認 |
