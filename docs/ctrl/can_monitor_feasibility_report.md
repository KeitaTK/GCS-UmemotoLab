# CAN監視 移行可否 レポート

**作成日**: 2026-07-21
**目的**: F9Pモジュール上のAP_Periph(STM32)のDroneCANパラメータをMAVLink経由で読み取り、UART2 UBX-NAV-PVT直接監視からCAN DroneCAN Fix2監視への移行可否を判断する。

---

## 1. 調査結果サマリ

### Step 1-3: GCS接続 (127.0.0.1:14551) → 利用不可

```
Scanning for components...
Done. Found 0 components.
```

GCS MAVLink接続 (`udp:127.0.0.1:14551`) が確立できなかったため、Step 1（Component ID特定）、Step 2（PARAM_REQUEST_LIST）、Step 3（CAN_GNSS_*パラメータ確認）は**未実施**。

**推奨**: 実機が接続可能な状態で再度実行し、以下の実パラメータを確認すること:
- `CAN_GNSS_FIX2_RATE` — 送信レート (デフォルト 10 Hz)
- `CAN_GNSS_FIX2_EN` — 有効/無効 (デフォルト 1)
- `CAN_GNSS_FIX2_ID` — DroneCAN message ID

### Step 4: F9P UART2 UBX-NAV-PVT 出力レート設定 → 未設定（デフォルト依存）

`rtk_tools/f9p_rover_config.py` の `_UART2_RTCM_CFG_KEYS` を調査:

```python
_UART2_RTCM_CFG_KEYS = [
    ('CFG-UART2-BAUDRATE',        115200),
    ('CFG-UART2INPROT-UBX',       0),
    ('CFG-UART2INPROT-NMEA',      0),
    ('CFG-UART2INPROT-RTCM3X',    1),        # ★ RTCM3入力を有効化
    ('CFG-UART2OUTPROT-UBX',      1),        # ★ UBX出力を有効化 (NAV-PVT用)
    ('CFG-UART2OUTPROT-NMEA',     0),
    ('CFG-NAVHPG-DGNSSMODE',      3),        # RTK Fixedモード
]
```

**所見**: 
- `CFG-UART2OUTPROT-UBX=1` によりUBXプロトコル出力は有効化
- `CFG-MSGOUT-UBX-NAV-PVT-UART2` が**未設定**
- `CFG-RATE-MEAS` も**未設定**


u-blox F9Pのデフォルト動作:

| パラメータ | デフォルト値 | 意味 |
|---|---|---|
| `CFG-RATE-MEAS` | 1000 ms | 測位演算周期 1 Hz |
| `CFG-MSGOUT-UBX-NAV-PVT-UART2` | 1 | 測位演算毎に1回出力 (= 1 Hz) |

→ **F9P UART2 からの UBX-NAV-PVT 出力レートは 1 Hz（デフォルト）**

> **注意**: ユーザ想定の「最大25Hz」は、`CFG-RATE-MEAS=40ms` かつ `CFG-MSGOUT-UBX-NAV-PVT-UART2=1` に設定した場合の理論最大値。現在の設定では達成されていない。

---

## 2. レート比較

| 項目 | レート | 更新間隔 | 備考 |
|---|---|---|---|
| **F9P UART2 UBX-NAV-PVT** (現在のFix監視) | **1 Hz** (推定) | 1000 ms | 設定未指定のためF9Pデフォルト値 |
| **AP_Periph CAN_GNSS_FIX2** (CAN監視候補) | **10 Hz** (デフォルト) | 100 ms | 実測未。GCS接続不可のため未確認 |

**逆転現象**: F9PのUBX出力が1 Hzなら、むしろAP_PeriphのDroneCAN 10 Hzの方が**10倍高速**。

---

## 3. RTK FIXED遷移検知への影響評価

### 3.1 carrSoln遷移のタイムライン

RTK測位のcarrSolnは以下の順で遷移:

```
carrSoln=0 (NONE) → carrSoln=1 (FLOAT) → carrSoln=2 (FIXED)
```

FLOAT→FIXED遷移は通常 **数秒〜数十秒** かけて行われる。瞬間的な遷移ではないため、1Hzでも10Hzでも遷移検知の成否に致命的な差は生じない。

### 3.2 レート別の検知遅延

| レート | 最悪遅延 | 典型的遅延 | 評価 |
|---|---|---|---|
| 1 Hz (F9P UART2) | 1000 ms | ~500 ms | FLOAT→FIXED遷移(数秒単位)に対して許容範囲 |
| 10 Hz (CAN Fix2) | 100 ms | ~50 ms | 高精度だが、アプリケーション上の実益は限定的 |

### 3.3 f9p_fix_monitor.py のポーリング方式

現在の `f9p_fix_monitor.py` はパッシブポーリング方式:
```python
def poll_nav_pvt(self, timeout: float = 3.0) -> Optional[dict]:
    # UBXReaderでNAV-PVTを1件受信するまでブロック
```
- F9Pが出力した瞬間に受信可能（プッシュ型に近い）
- タイムアウト3秒でリトライ
- 実質的な遅延 = F9Pのメッセージ出力周期

---

## 4. CAN監視移行の判断

### 4.1 移行メリット

| 項目 | 説明 |
|---|---|
| **UART2のRTCM専用化** | UART2をRTCM注入専用にでき、TX(注入)/RX(UBX受信)の調停が不要になる |
| **高レート(10Hz想定)** | F9P生出力より高頻度のFix状態取得が可能 |
| **一本化** | DroneCANバス上の全ノードをCANから監視可能 |
| **Pixhawkと同じ視点** | AP_PeriphがPixhawkに送っているのと同じFix2メッセージを読むため、Pixhawkの認識と一致 |

### 4.2 移行課題

| 項目 | 説明 | 対策 |
|---|---|---|
| **CAN I/F の追加** | RaspiにCANインターフェース（MCP2515等）が必要 | SPI接続CANモジュールの追加 |
| **パラメータ未確認** | CAN_GNSS_FIX2_RATEの実値が不明 | GCS再接続時に確認必須 |
| **追加のCANトラフィック** | Fix2(10Hz) + Aux + Status 等でCAN負荷増 | 軽微（1Mbps CANに対して数%未満） |
| **コード改修** | `f9p_fix_monitor.py` 相当のCAN監視モジュールを新規作成 | python-can + dronecan ライブラリ使用 |

### 4.3 推奨アクション

1. **F9P UBX出力レートの向上**（必須）
   - 現在のデフォルト1 Hz → 5〜10 Hz に設定
   - `CFG-MSGOUT-UBX-NAV-PVT-UART2 = 1`（毎測位演算）を追加
   - `CFG-RATE-MEAS = 200`（5 Hz）を追加

2. **GCS再接続時のパラメータ確認**（必須）

3. **段階的移行**
   - Phase 1: F9P UBXレートを5Hzに引き上げた上で現行のUART2監視を継続
   - Phase 2: CAN I/FをRaspiに追加し、CAN監視モジュールを試験実装
   - Phase 3: 両監視を並行稼働させてデータ一致を確認
   - Phase 4: UART2監視を廃止、CAN監視に完全移行

---

## 5. 結論

**CAN監視への移行は「条件付きで推奨」。**

現在のF9P UBX-NAV-PVT出力レートが推定1 Hz（デフォルト）であり、AP_PeriphのDroneCAN Fix2（デフォルト10 Hz）より低レートである。したがって、CAN監視に移行することで監視の分解能が向上する可能性が高い。

ただし、以下の前提条件を満たす必要がある:
1. Raspi側にCANインターフェース（ハードウェア）を追加すること
2. AP_Periphの `CAN_GNSS_FIX2_RATE` 実値を確認し、十分なレート（≧5 Hz）であること
3. F9P UART2のUBX-NAV-PVTレートを明示的に設定し、少なくとも5 Hzに引き上げること

これらの条件が満たされれば、UART2をRTCM注入専用にできる運用上のメリットが、CAN監視への移行コストを上回る。



## 付録A: F9P UBXレート明示設定（推奨パッチ）

`rtk_tools/f9p_rover_config.py` の `_UART2_RTCM_CFG_KEYS` に以下を追加:

```python
_UART2_RTCM_CFG_KEYS = [
    # ... 既存の設定 ...
    ('CFG-RATE-MEAS',                  200),       # ★ 測位演算周期 200ms (5Hz) ★
    ('CFG-RATE-NAV',                   1),         # ★ ナビゲーション出力比 1:1 ★
    ('CFG-MSGOUT-UBX-NAV-PVT-UART2',   1),         # ★ NAV-PVTを毎測位演算で出力 ★
]
```

## 付録B: GCS再接続時のパラメータ確認スクリプト

```python
#!/usr/bin/env python3
"""AP_Periph CAN_GNSS パラメータ確認スクリプト"""
from pymavlink import mavutil
import time

mav = mavutil.mavlink_connection('udp:127.0.0.1:14551')

# HEARTBEAT収集でAP_PeriphのComponent IDを特定（~15秒）
print('Scanning for AP_Periph...')
seen = set()
start = time.time()
target_sys, target_comp = None, None

while time.time() - start < 15:
    msg = mav.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
    if msg:
        key = (msg.get_srcSystem(), msg.get_srcComponent())
        if key not in seen:
            seen.add(key)
            comp = msg.get_srcComponent()
            # AP_Periph GPS: component 158+, 220(GPS), 221(GPS2)
            if comp >= 150:
                target_sys, target_comp = msg.get_srcSystem(), comp
                print(f'  AP_Periph candidate: Sys={target_sys} Comp={target_comp} type={msg.type}')

if target_sys is None:
    print('ERROR: No AP_Periph component found')
    exit(1)

print(f'\nRequesting params from System={target_sys} Component={target_comp}...')
mav.mav.param_request_list_send(target_sys, target_comp)

# Collect CAN_GNSS_* parameters
can_gnss_params = {}
start = time.time()
while time.time() - start < 30:
    msg = mav.recv_match(type='PARAM_VALUE', blocking=True, timeout=2)
    if msg is None:
        break
    param_id = msg.param_id.strip()
    if param_id.startswith('CAN_GNSS'):
        can_gnss_params[param_id] = msg.param_value
        print(f'  {param_id} = {msg.param_value}')

print(f'\n=== CAN_GNSS Parameters ===')
for k, v in sorted(can_gnss_params.items()):
    print(f'  {k:30s} = {v}')
if not can_gnss_params:
    print('  (none - may use different firmware version)')
```
