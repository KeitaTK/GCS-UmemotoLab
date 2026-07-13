# RTK Direct UART2 Injection — 実装設計書

**作成日**: 2026-07-10  
**最終更新日**: 2026-07-13  
**ステータス**: 実装完了  
**対象モジュール**: Holybro DroneCAN H-RTK F9P Helical (Rover側)

---

## 1. 現状構成と問題点

### 1.1 現在のRTCMパイプライン

```
┌──────────────────────────────────────────────────────────────────────┐
│                        現行アーキテクチャ                              │
│                                                                      │
│  ┌──────────┐   USB/Serial    ┌──────────┐   TCP:2101   ┌──────────┐│
│  │ 基地局F9P │ ──────────────→│  PC/Mac  │─────────────→│ Raspi 5  ││
│  │ (TMODE3)  │   RTCM3 frame  │(rtk_base │  RTCM3 frame │          ││
│  └──────────┘                 │_station) │              │          ││
│                               └──────────┘              └────┬─────┘│
│                                                             │       │
│                                              MAVLink GPS_RTCM_DATA  │
│                                              (msgid=233, 分割送信)   │
│                                                             │       │
│                                                      ┌──────▼─────┐│
│                                                      │  Pixhawk   ││
│                                                      │ (ArduPilot)││
│                                                      └──────┬─────┘│
│                                                             │       │
│                                                      DroneCAN BUS  │
│                                                             │       │
│                                                      ┌──────▼─────┐│
│                                                      │  Rover F9P ││
│                                                      │ (移動局)    ││
│                                                      └────────────┘│
└──────────────────────────────────────────────────────────────────────┘
```

**データフロー詳細**:

| 段階 | モジュール | 場所 | 処理内容 |
|------|-----------|------|---------|
| ① F9P基地局設定 | `f9p_configurator.py` | PC/Mac | TMODE3 Fixed + RTCM3出力有効化 |
| ② RTCMシリアル受信 | `RtcmSerialReader` | PC/Mac | F9P→USBシリアル、0xD3フレーム検出 |
| ③ TCP配信 | `TcpServer` (rtk_base_station_v2.py) | PC/Mac | TCP:2101でブロードキャスト |
| ④ RTCM受信(Raspi) | `RtcmReader` (rtcm_reader.py) | Raspi | TCP:2101→RTCM3フレーム |
| ⑤ MAVLink変換 | `RtcmInjector` (rtcm_injector.py) | Raspi | RTCM→GPS_RTCM_DATA(233)、180byte分割 |
| ⑥ Pixhawk注入 | `MavlinkConnection.send_to_system()` | Raspi | シリアル /dev/ttyACM0 → Pixhawk |

### 1.2 問題点

#### 問題1: GPS_RTCM_DATA のフラグメント分割による透過性欠如

`app/rtk_tools/rtcm_injector.py` ではRTCM3フレームをGPS_RTCM_DATA(msgid=233)に変換する際、ペイロードが180バイトを超えると複数フレームに分割。これによりPixhawk側での再組み立て失敗、フレーム損失時の不完全RTCM、DroneCAN経由での到着順序変動が発生する可能性がある。

#### 問題2: DroneCAN 経由の不透明さ

Pixhawkが受信したGPS_RTCM_DATAはファームウェア内部でDroneCANバスを通じてF9Pに転送される。この経路はArduPilot内部のブラックボックス処理であり、RTCM注入の成功/失敗を直接確認できない。

#### 問題3: message_router ログ途絶で送信確認不可

`app/mavlink/message_router.py` のログ出力が途絶えた場合、RTCMデータが実際にPixhawkへ到達したかどうかの確認手段がない。ログベースの確認のみであり、ハードウェアレベルでの到達確認が不可能。

---

## 2. 提案アーキテクチャ

### 2.1 新RTCMパイプライン

```
┌──────────────────────────────────────────────────────────────────────┐
│                        提案アーキテクチャ                              │
│                                                                      │
│  ┌──────────┐                           ┌──────────────────────────┐ │
│  │ 基地局F9P │  NTRIP/TCP/UDP           │      Raspberry Pi 5      │ │
│  │ (TMODE3)  │─────────────────────────→│                          │ │
│  └──────────┘  RTCM3 stream             │  rtk_forwarder (serial)  │ │
│                                         │  ↓                       │ │
│                                         │  USB-Serial Adapter      │ │
│                                         │  (/dev/ttyUSB0)          │ │
│                                         └───────────┬──────────────┘ │
│                                                     │ UART (3.3V)   │
│                                                     │ RTCM3 + UBX   │
│                                         ┌───────────▼──────────────┐ │
│                                         │  Holybro H-RTK F9P       │ │
│                                         │  Helical (Rover)         │ │
│                                         │  UART2 ← RTCM3入力       │ │
│                                         │  UART2 → UBX-NAV-PVT出力 │ │
│                                         └───────────┬──────────────┘ │
│                                                     │ DroneCAN BUS  │
│                                                     │ (位置情報供給)  │
│                                         ┌───────────▼──────────────┐ │
│                                         │  Pixhawk (ArduPilot)     │ │
│                                         │  CAN経由でGPS位置受信     │ │
│                                         └──────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.2 設計上の利点

| # | 利点 | 説明 |
|---|------|------|
| 1 | **MAVLink完全排除** | RTCM注入にGPS_RTCM_DATAが不要。フラグメント分割問題が消滅 |
| 2 | **Fix状態の直接監視** | UART2からUBX-NAV-PVTをRaspiで直接受信。`carrSoln`でRTK Fixed確認 |
| 3 | **フォールトトレランス** | Raspi障害時もCAN経由の位置情報供給は生き続ける（精度低下のみ） |
| 4 | **低レイテンシ** | MAVLink変換・分割・DroneCAN転送のオーバーヘッド消滅 |
| 5 | **デバッグ容易性** | UART2上のバイトストリームを直接観測可能 |

### 2.3 対象GPSモジュール

- **製品名**: Holybro DroneCAN H-RTK F9P Helical
- **GNSSチップ**: u-blox NEO-F9P
- **プロトコル**: NMEA, UBX binary, RTCM 3.3, SPARTN 2.0.1
- **通信**: DroneCAN 1Mbit/s + UART2 (内部JST-GH 6pin)
- **動作電圧**: 4.75V〜5.25V
- **UART2ロジック**: 3.3V TTL


---

## 3. ハードウェア配線

### 3.1 Holybro H-RTK F9P の UART2 ピン配置

出典: [Holybro Docs — NEO-F9P Rover Pinout](https://docs.holybro.com/gps-and-rtk-system/h-rtk-neo-f9p-series-rm3100-compass/neo-f9p-rover-pinout)

UART2 は筐体内部の JST-GH 6ピンコネクタ:

```
   UART2 (Inside Casing) — JST-GH 6-pin
   ┌─────────────────────────┐
   │ Pin 1 (Red)   VCC  5.0V │  ← F9P給電（CANから別途供給のため通常不要）
   │ Pin 2         RX2   3.3V│  ← Raspi TXD → ここにRTCM注入 ★
   │ Pin 3         TX2   3.3V│  ← UBX-NAV-PVT読み出し用 ★
   │ Pin 4         EXTINT    │  ← 未使用
   │ Pin 5         PPS       │  ← 未使用（タイムパルス出力）
   │ Pin 6         GND        │  ← Raspi GNDと共通 ★
   └─────────────────────────┘
```

### 3.2 配線表

| F9P UART2 ピン | 信号 | 方向 | Raspberry Pi側 | 備考 |
|---------------|------|------|---------------|------|
| Pin 2 (RX2) | UART RX (3.3V TTL) | Raspi→F9P | USB-Serial TX | RTCM3データ注入 |
| Pin 3 (TX2) | UART TX (3.3V TTL) | F9P→Raspi | USB-Serial RX | UBX-NAV-PVT受信 |
| Pin 6 (GND) | GND | — | USB-Serial GND | 共通グラウンド |

### 3.3 レベル変換と電源

- **ロジックレベル**: UART2のRX2/TX2は3.3V TTL。Raspi側のUSB-Serialアダプタ（FTDI FT232RL等）も3.3V対応 → **レベル変換不要**
- **電源**: F9PはCANコネクタ経由でPixhawkから5V給電済み。UART2のVCC接続不要。GNDのみ接続
- **USB-Serialアダプタ推奨**: FTDI FT232RL (3.3V)、CP2102 (3.3V)

### 3.4 既存接続（変更なし）

```
  F9P ──(CAN H/L)── Pixhawk CAN1        ← 位置情報供給（維持）
  Pixhawk TELEM1 ──(UART)── Raspi ttyAMA0 ← MAVLink通信（維持）
```

### 3.5 全体接続図

```
                    ┌────────────────────────────────────┐
                    │         Raspberry Pi 5              │
                    │                                     │
  [基地局RTCM]      │  eth0/wlan0 ← RTCMストリーム受信    │
  NTRIP/TCP ───────→│                                     │
                    │  USB-Serial Adapter (/dev/ttyUSB0)  │
                    │  ├─ TX ─────────────┐               │
                    │  ├─ RX ───────────┐ │               │
                    │  └─ GND ────────┐ │ │               │
                    │                 │ │ │               │
                    │  ttyAMA0        │ │ │               │
                    │  ├─ TX ───┐     │ │ │               │
                    │  └─ RX ─┐ │     │ │ │               │
                    └─────────┼─┼─────┼─┼─┼───────────────┘
                              │ │     │ │ │
                    ┌─────────┼─┼─────┼─┼─┼───────────────┐
                    │ Pixhawk │ │     │ │ │               │
                    │ TELEM1←┘ │     │ │ │               │
                    │ CAN1 ────┼─────┼─┼─┼──┐            │
                    └──────────┼─────┼─┼─┼──┼────────────┘
                               │     │ │ │  │ (CAN BUS)
                    ┌──────────┼─────┼─┼─┼──┼────────────┐
                    │ H-RTK F9P Helical  │ │ │  │         │
                    │ CAN ───────────────┘ │ │  │         │
                    │ UART2 RX2 ←──────────┘ │  │         │
                    │ UART2 TX2 ─────────────┘  │         │
                    │ UART2 GND ────────────────┘         │
                    └─────────────────────────────────────┘
```


---

## 4. u-blox F9P 設定（Rover側）

### 4.1 設定アーキテクチャ

F9P Rover の UART2 で RTCM3 補正データ受信＋UBX-NAV-PVT出力を有効化する。

```
      UART2 (Rover側F9P)
  ┌─────────────────────────────────┐
  │ 入力プロトコル: RTCM3           │  ← CFG-UART2INPROT-RTCM3X = 1 ★
  │ 出力プロトコル: UBX             │  ← CFG-UART2OUTPROT-UBX = 1 ★
  │ ボーレート: 115200              │
  └─────────────────────────────────┘
```

### 4.2 必須設定項目

`f9p_configurator.py` の `UBXMessage.config_set()` パターンを流用:

```python
from pyubx2 import UBXMessage

# Layer bitmask (f9p_configurator.pyより流用)
LAYER_RAM   = 1
LAYER_BBR   = 2
LAYER_FLASH = 4
LAYER_ALL   = LAYER_RAM | LAYER_BBR | LAYER_FLASH

# === Rover 側 F9P 設定 (UART2 で RTCM3 入力 + UBX出力) ===
rover_cfg = [
    # --- UART2基本設定 ---
    ('CFG-UART2-BAUDRATE',       115200),   # ボーレート
    ('CFG-UART2INPROT-UBX',      0),        # UBX入力を無効化
    ('CFG-UART2INPROT-NMEA',     0),        # NMEA入力を無効化
    ('CFG-UART2INPROT-RTCM3X',   1),        # ★ RTCM3入力を有効化 ★
    ('CFG-UART2OUTPROT-UBX',     1),        # ★ UBX出力を有効化 (NAV-PVT用) ★
    ('CFG-UART2OUTPROT-NMEA',    0),        # NMEA出力を無効化

    # --- ナビゲーション設定 ---
    ('CFG-NAVHPG-DGNSSMODE',     3),        # RTK FIXEDモード (3=RTK Fixed)
    ('CFG-SIGNAL-GPS_ENA',       1),        # GPS L1C/A有効
    ('CFG-SIGNAL-GPS_L5_ENA',    1),        # GPS L5有効
    ('CFG-SIGNAL-GAL_ENA',       1),        # Galileo有効
    ('CFG-SIGNAL-GAL_E5A_ENA',   1),        # Galileo E5a有効
    ('CFG-SIGNAL-BDS_ENA',       1),        # BeiDou有効
    ('CFG-SIGNAL-GLO_ENA',       1),        # GLONASS有効
]

# 送信 (USB-Serial経由でF9P UART2へ)
msg = UBXMessage.config_set(LAYER_ALL, 0, rover_cfg)
serial_port.write(msg.serialize())
```

### 4.3 設定確認（ポーリング）

```python
# CFG-VALGET で設定を読み戻して確認
poll_keys = [
    'CFG-UART2-BAUDRATE',
    'CFG-UART2INPROT-RTCM3X',
    'CFG-UART2OUTPROT-UBX',
]
poll_msg = UBXMessage.config_poll(0, 0, poll_keys)
# 応答を UBXReader でパースして確認
```

### 4.4 基地局側 Survey-In 設定（参考）

| パラメータ | 推奨値 | 説明 |
|-----------|--------|------|
| `svInMinDur` | 120 (秒) | Survey-In 最小観測時間 |
| `svInAccLimit` | 20000 (2.0m×10000) | 目標精度 0.1mm単位 |
| TMODE-MODE | 1 (Survey-In) または 2 (Fixed) | Survey-In自動 or 既知座標指定 |


---

## 5. RTCM注入・Fix監視の実装方針

### 5.1 RTCM直接注入

```python
import serial

class RtcmDirectInjector:
    """
    RTCM3データをUART2経由でF9P Roverに直接注入。
    MAVLink GPS_RTCM_DATA は一切使用しない。
    """
    def __init__(self, serial_port='/dev/ttyUSB0', baudrate=115200):
        self.serial_port = serial_port
        self.baudrate = baudrate
        self._ser = None
        self.stats = {'bytes_sent': 0, 'frames_sent': 0}

    def open(self):
        self._ser = serial.Serial(
            port=self.serial_port, baudrate=self.baudrate, timeout=1.0)
        self._ser.reset_output_buffer()

    def inject(self, rtcm_frame: bytes) -> bool:
        """RTCM3フレームをUART2にそのまま書き込む"""
        if self._ser is None or not self._ser.is_open:
            return False
        try:
            self._ser.write(rtcm_frame)
            self._ser.flush()
            self.stats['bytes_sent'] += len(rtcm_frame)
            self.stats['frames_sent'] += 1
            return True
        except serial.SerialException:
            return False

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
```

**ポイント**: RTCM3バイト列をそのままシリアルに書き込むだけ。MAVLink変換もフラグメント分割も不要。

### 5.2 RTCM受信（基地局からのデータ取得）

既存 `config/rtk_forwarder.yml` に `forward.type` を追加してシリアル転送に対応:

```yaml
# config/rtk_forwarder.yml 拡張案 (Rover側Raspi用)
source:
  source_type: ntrip
  host: 192.168.11.100        # 基地局PCのIP
  port: 2101
  mountpoint: UBLOX_EVK_F9P

forward:
  type: serial                 # 新規: forward先をシリアルに
  serial_port: /dev/ttyUSB0    # F9P UART2へのUSB-Serialポート
  baudrate: 115200
```

### 5.3 Fix監視（UBX-NAV-PVT ポーリング）

```python
from pyubx2 import UBXReader, UBX_PROTOCOL
import time, serial

class F9pFixMonitor:
    """
    UART2のTX2から UBX-NAV-PVT を読み取り、
    carrSoln でRTK Fix状態を監視。
    carrSoln: 0=NoRTK, 1=RTK Float, 2=RTK Fixed
    """
    CARRSOLN_NAMES = {0: 'NONE', 1: 'FLOAT', 2: 'FIXED'}

    def __init__(self, serial_port='/dev/ttyUSB0', baudrate=115200):
        self.serial_port = serial_port
        self.baudrate = baudrate

    def open(self):
        self._ser = serial.Serial(self.serial_port, self.baudrate, timeout=1.0)
        self._reader = UBXReader(self._ser, protfilter=UBX_PROTOCOL)

    def poll_nav_pvt(self, timeout=3.0):
        """UBX-NAV-PVT (cls=0x01, mid=0x07) を1件読み取り"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                raw, parsed = self._reader.read()
            except Exception:
                continue
            if parsed and parsed.msg_cls == 0x01 and parsed.msg_id == 0x07:
                return {
                    'carrSoln': getattr(parsed, 'carrSoln', -1),
                    'carrSoln_name': self.CARRSOLN_NAMES.get(
                        getattr(parsed, 'carrSoln', -1), 'UNKNOWN'),
                    'fixType': getattr(parsed, 'fixType', -1),
                    'numSV': getattr(parsed, 'numSV', 0),
                    'lat': getattr(parsed, 'lat', 0) * 1e-7,
                    'lon': getattr(parsed, 'lon', 0) * 1e-7,
                    'hMSL': getattr(parsed, 'hMSL', 0) * 0.001,
                    'hAcc': getattr(parsed, 'hAcc', 0) * 0.001,
                }
        return None

    def wait_for_rtk_fixed(self, timeout=120.0):
        """carrSoln=2 (RTK Fixed) になるまで待機"""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            result = self.poll_nav_pvt(timeout=3.0)
            if result and result['carrSoln'] == 2:
                return True
            time.sleep(0.5)
        return False

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()
```

### 5.4 既存コードとの関係

| 既存モジュール | 本構成での扱い |
|---------------|---------------|
| `app/rtk_tools/rtcm_injector.py` | **撤廃** — GPS_RTCM_DATA注入は不要 |
| `app/rtk_tools/rtcm_reader.py` | **流用可** — 基地局→RaspiのRTCM受信に使用 |
| `rtk_tools/f9p_configurator.py` | **流用** — config_set()パターンをRover設定に転用 |
| `rtk_tools/rtk_data_collector.py` | **流用** — UbloxReaderのシリアル読取パターン |
| `config/rtk_forwarder.yml` | **拡張** — forward.type: serial 追加 |
| `scripts/ublox_survey_in.py` | 基地局用として維持 |
| `rtk_tools/rtk_base_station_v2.py` | 基地局用として維持 |


---

## 6. 自動化スクリプト設計

### 6.1 全体フロー

```
  スクリプト実行
       |
  ┌────▼────────────────────────────────────────────┐
  │ STEP 1: F9P Rover UART2設定                      │
  │   - UART2 RTCM3入力有効化 (UART2INPROT-RTCM3X=1) │
  │   - UART2 UBX出力有効化 (NAV-PVT用)              │
  │   - CFG-VALGET ポーリングで設定確認               │
  └────┬────────────────────────────────────────────┘
       |
  ┌────▼────────────────────────────────────────────┐
  │ STEP 2: 基地局確認                               │
  │   - 基地局NTRIP接続・RTCM3配信確認               │
  │   - F9P基地局がSurvey-In 完了済みであること       │
  └────┬────────────────────────────────────────────┘
       |
  ┌────▼────────────────────────────────────────────┐
  │ STEP 3: RTCM注入開始                             │
  │   - 基地局->Raspi RTCMストリーム確立              │
  │   - UART2シリアルポートにRTCM書き込み開始         │
  └────┬────────────────────────────────────────────┘
       |
  ┌────▼────────────────────────────────────────────┐
  │ STEP 4: RTK Fix 確認                             │
  │   - UBX-NAV-PVT carrSoln ポーリング              │
  │   - carrSoln=2 (RTK Fixed) 到達を待機            │
  │   - 到達後、Fix状態・位置精度を表示                │
  └────┬────────────────────────────────────────────┘
       |
  ┌────▼────────────────────────────────────────────┐
  │ STEP 5: Pixhawk フライト準備確認                  │
  │   - pymavlink で GPS fix_type=6 確認             │
  │   - EKF健全性チェック                             │
  │   - アーム前プリフライトチェック実行               │
  └────┬────────────────────────────────────────────┘
       |
       ▼
   ✅ 飛行準備完了
```


### 6.2 自動化スクリプト骨格

新規ファイル: `rtk_tools/rtk_direct_inject.py`

```python
#!/usr/bin/env python3
"""
rtk_direct_inject.py - RTCM UART2直接注入 + RTK Fix確認 自動化

Usage:
  python rtk_tools/rtk_direct_inject.py
  python rtk_tools/rtk_direct_inject.py --uart-port /dev/ttyUSB0 --timeout 120
  python rtk_tools/rtk_direct_inject.py --skip-f9p-config
"""

import argparse, logging, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pyubx2 import UBXMessage, UBXReader, UBX_PROTOCOL
import serial

logger = logging.getLogger("rtk_direct_inject")

# Layer mask (from f9p_configurator.py)
LAYER_RAM, LAYER_BBR, LAYER_FLASH = 1, 2, 4
LAYER_ALL = LAYER_RAM | LAYER_BBR | LAYER_FLASH


class Config:
    uart_port: str = '/dev/ttyUSB0'
    uart_baud: int = 115200
    base_host: str = '192.168.11.100'
    base_port: int = 2101
    rtk_fixed_timeout: float = 120.0
    skip_f9p_config: bool = False


def step1_configure_rover_f9p(cfg: Config) -> bool:
    """Rover側F9PのUART2をRTCM3入力+UBX出力に設定"""
    logger.info("=" * 60)
    logger.info("STEP 1: Rover F9P UART2 Configuration")
    logger.info("=" * 60)

    if cfg.skip_f9p_config:
        logger.info("  Skipped (--skip-f9p-config)")
        return True

    ser = serial.Serial(cfg.uart_port, cfg.uart_baud, timeout=2.0)
    try:
        rover_cfg_data = [
            ('CFG-UART2-BAUDRATE',       115200),
            ('CFG-UART2INPROT-UBX',      0),
            ('CFG-UART2INPROT-NMEA',     0),
            ('CFG-UART2INPROT-RTCM3X',   1),
            ('CFG-UART2OUTPROT-UBX',     1),
            ('CFG-UART2OUTPROT-NMEA',    0),
            ('CFG-NAVHPG-DGNSSMODE',     3),
        ]
        msg = UBXMessage.config_set(LAYER_ALL, 0, rover_cfg_data)
        ser.write(msg.serialize())
        ser.flush()
        time.sleep(1.0)
        logger.info("  UART2 RTCM3 input + UBX output: OK")
        return True
    except Exception as e:
        logger.error(f"  STEP 1 failed: {e}")
        return False
    finally:
        ser.close()


def step2_verify_base_station(cfg: Config) -> bool:
    """基地局がRTCM3を配信していることを確認"""
    logger.info("=" * 60)
    logger.info("STEP 2: Base Station Verification")
    logger.info("=" * 60)
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5.0)
        sock.connect((cfg.base_host, cfg.base_port))
        sock.sendall(
            f"GET / HTTP/1.0\r\nUser-Agent: rtk_inject\r\n\r\n".encode()
        )
        resp = sock.recv(4096)
        sock.close()
        if b'200' in resp:
            logger.info("  Base station NTRIP OK (200)")
            return True
        logger.warning(f"  Unexpected response: {resp[:100]}")
        return False
    except Exception as e:
        logger.error(f"  STEP 2 failed: {e}")
        return False


def step3_start_rtcm_injection(cfg: Config) -> None:
    """RTCMストリーム受信->UART2注入を開始"""
    logger.info("=" * 60)
    logger.info("STEP 3: RTCM Injection Started")
    logger.info(f"  UART: {cfg.uart_port} @ {cfg.uart_baud}")
    logger.info(f"  Source: {cfg.base_host}:{cfg.base_port}")
    logger.info("=" * 60)
    # 実装: rtk_forwarder拡張 or 専用スレッド


def step4_wait_for_rtk_fixed(cfg: Config) -> bool:
    """UART2のUBX-NAV-PVTをポーリングしcarrSoln=2を待つ"""
    logger.info("=" * 60)
    logger.info("STEP 4: Waiting for RTK Fixed...")
    logger.info(f"  Timeout: {cfg.rtk_fixed_timeout}s")
    logger.info("=" * 60)

    CARRSOLN = {0: 'NONE', 1: 'FLOAT', 2: 'FIXED'}
    ser = serial.Serial(cfg.uart_port, cfg.uart_baud, timeout=1.0)
    ubr = UBXReader(ser, protfilter=UBX_PROTOCOL)
    start = time.monotonic()

    try:
        while time.monotonic() - start < cfg.rtk_fixed_timeout:
            try:
                raw, parsed = ubr.read()
            except Exception:
                time.sleep(0.05)
                continue

            if parsed and parsed.msg_cls == 0x01 and parsed.msg_id == 0x07:
                cs = getattr(parsed, 'carrSoln', -1)
                fix = getattr(parsed, 'fixType', -1)
                sv = getattr(parsed, 'numSV', 0)
                hAcc = getattr(parsed, 'hAcc', 0) * 0.001
                elapsed = time.monotonic() - start
                logger.info(
                    f"  t={elapsed:5.1f}s  carrSoln={cs}"
                    f"({CARRSOLN.get(cs,'?')})  "
                    f"fixType={fix}  numSV={sv}  hAcc={hAcc:.3f}m"
                )
                if cs == 2:
                    lat = getattr(parsed, 'lat', 0) * 1e-7
                    lon = getattr(parsed, 'lon', 0) * 1e-7
                    alt = getattr(parsed, 'hMSL', 0) * 0.001
                    logger.info("=" * 60)
                    logger.info("  RTK FIXED ACHIEVED!")
                    logger.info(
                        f"  Position: lat={lat:.7f} lon={lon:.7f}"
                        f" alt={alt:.2f}m"
                    )
                    logger.info(f"  Accuracy: hAcc={hAcc:.3f}m")
                    logger.info(f"  Time to fix: {elapsed:.1f}s")
                    logger.info("=" * 60)
                    return True
        logger.warning(
            f"  RTK Fixed not achieved in {cfg.rtk_fixed_timeout}s"
        )
        return False
    finally:
        ser.close()


def step5_preflight_check(cfg: Config) -> bool:
    """pymavlink経由でPixhawk飛行準備状態を確認"""
    logger.info("=" * 60)
    logger.info("STEP 5: Pixhawk Preflight Check")
    logger.info("=" * 60)
    try:
        from pymavlink import mavutil
        mav = mavutil.mavlink_connection('/dev/ttyAMA0', baud=115200)
        logger.info("  MAVLink connection opened")
        gps_msg = mav.recv_match(
            type='GPS_RAW_INT', blocking=True, timeout=10
        )
        if gps_msg:
            ft = gps_msg.fix_type
            fix_names = {
                0:'NO_GPS',1:'NO_FIX',2:'2D',3:'3D',
                4:'DGPS',5:'RTK_FLOAT',6:'RTK_FIXED'
            }
            logger.info(
                f"  GPS fix_type={ft} ({fix_names.get(ft, '?')})"
            )
            if ft == 6:
                logger.info("  Pixhawk GPS: RTK FIXED")
                return True
            logger.warning(f"  Pixhawk GPS: {fix_names.get(ft, '?')}")
            return False
        logger.warning("  GPS_RAW_INT not received")
        return False
    except Exception as e:
        logger.error(f"  STEP 5 failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='RTK Direct UART2 Injection')
    parser.add_argument('--uart-port', default='/dev/ttyUSB0')
    parser.add_argument('--uart-baud', type=int, default=115200)
    parser.add_argument('--base-host', default='192.168.11.100')
    parser.add_argument('--base-port', type=int, default=2101)
    parser.add_argument('--timeout', type=float, default=120.0)
    parser.add_argument('--skip-f9p-config', action='store_true')
    parser.add_argument('--log-level', default='INFO')
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
    )

    cfg = Config()
    cfg.uart_port = args.uart_port
    cfg.uart_baud = args.uart_baud
    cfg.base_host = args.base_host
    cfg.base_port = args.base_port
    cfg.rtk_fixed_timeout = args.timeout
    cfg.skip_f9p_config = args.skip_f9p_config

    logger.info("RTK Direct UART2 Injection - Startup")
    logger.info(f"  UART: {cfg.uart_port} @ {cfg.uart_baud}")

    results = {}
    results['step1'] = step1_configure_rover_f9p(cfg)
    if not results['step1']:
        logger.error("STEP 1 failed. Abort.")
        return 1
    results['step2'] = step2_verify_base_station(cfg)
    step3_start_rtcm_injection(cfg)
    results['step4'] = step4_wait_for_rtk_fixed(cfg)
    if not results['step4']:
        logger.error("RTK Fixed not achieved.")
        return 1
    results['step5'] = step5_preflight_check(cfg)

    all_ok = all(results.values())
    logger.info(f"\n{'='*60}")
    logger.info(f"  FINAL: {'READY FOR FLIGHT' if all_ok else 'NOT READY'}")
    logger.info(f"{'='*60}")
    return 0 if all_ok else 1


if __name__ == '__main__':
    sys.exit(main())
```

### 6.3 運用時の実行手順

```bash
# Raspi上で実行
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# 初回: F9P設定含む全自動モード
python rtk_tools/rtk_direct_inject.py \
  --uart-port /dev/ttyUSB0 \
  --base-host 192.168.11.100 \
  --timeout 120

# 2回目以降: F9P設定済みスキップ
python rtk_tools/rtk_direct_inject.py \
  --skip-f9p-config \
  --timeout 60
```

---

## 7. GPS_INPUT について

### 7.1 本構成では GPS_INPUT は不要

本アーキテクチャでは、F9P（Rover）とPixhawkの間のCAN接続が維持されているため、**位置情報はDroneCAN経由でPixhawkに供給される**。したがって、MAVLink `GPS_INPUT` (#232) メッセージは不要。

```
  F9P (Rover)
  +-- UART2 <-- RTCM3補正データ (Raspiから直接注入)
  +-- CAN ---> Pixhawk CAN1 (位置情報: lat, lon, alt, fix_type, ...)
```

### 7.2 補足: 将来GPSをラズパイ直結に移行する場合

将来的にF9PのCAN接続を廃止し、UART2からRaspiが直接NMEA/UBXデータを読み取り、MAVLink GPS_INPUT でPixhawkに位置情報を注入する構成に移行することも可能。その場合の注意点:

**GPS_INPUT メッセージ仕様 (MAVLink v2, msgid=232)**:

| フィールド | 型 | 説明 |
|-----------|-----|------|
| `time_usec` | uint64 | GPS時刻 (UNIX epoch, usec) |
| `gps_id` | uint8 | GPSインスタンスID (0〜) |
| `ignore_flags` | uint16 | 無視するフィールドのビットマスク |
| `lat` | int32 | 緯度 [degE7] |
| `lon` | int32 | 経度 [degE7] |
| `alt` | float32 | 高度 [m] (MSL) |
| `eph` | float32 | **水平精度推定値 [m]** ← 重要 |
| `epv` | float32 | **垂直精度推定値 [m]** ← 重要 |
| `vel` | float32 | 対地速度 [m/s] |
| `vn, ve, vd` | float32 | NED速度成分 |
| `cog` | float32 | 対地進路 [deg] |
| `satellites_visible` | uint8 | 可視衛星数 |
| `fix_type` | uint8 | Fix種別 (3=3D, 4=DGPS, 5=RTK_FLOAT, 6=RTK_FIXED) |
| `yaw` | float32 | 機首方位 [deg] (GPS heading利用時) |

**eph/epv 設定の注意**:
- ArduPilotのEKFは `eph` 値をGPSの信頼度重みとして使用する
- 過小な `eph` 設定 (例: 0.01m) → EKFがGPSを過信し、IMUとの不整合時に発散
- 過大な `eph` 設定 (例: 5.0m) → EKFがGPSを無視し、RTK精度が活かされない
- **RTK Fixed時の推奨値**: `eph=0.05`〜`0.3`、`epv=0.1`〜`0.5`
- UBX-NAV-PVTの `hAcc`/`vAcc` 値をそのまま設定するのが最も安全

```python
# GPS_INPUT メッセージ生成例（将来の参考）
from pymavlink.dialects.v20 import ardupilotmega as mavlink

msg = mavlink.MAVLink_gps_input_message(
    time_usec=int(time.time() * 1e6),
    gps_id=0,
    ignore_flags=0,
    lat=int(lat * 1e7),
    lon=int(lon * 1e7),
    alt=alt_msl,
    eph=hAcc_m,       # UBX-NAV-PVTのhAccをそのまま使用
    epv=vAcc_m,       # UBX-NAV-PVTのvAccをそのまま使用
    vel=0,
    vn=0, ve=0, vd=0,
    cog=0,
    satellites_visible=num_sv,
    fix_type=6,       # RTK FIXED
    yaw=0,
)
```

---

## 8. 全体ロードマップ

### 8.1 フェーズ構成

```
  Phase 1          Phase 2           Phase 3           Phase 4          Phase 5
  +---------+     +----------+      +-----------+     +----------+     +----------+
  | (1)基礎  |     | (2)u-blox |      | (3)RTCM注入|     | (4)自動化 |     | (5)運用  |
  |   理解   |--->|   設定    |----->|   Fix監視 |---->|  Pixhawk |----->|   整備   |
  |          |     |          |      |           |     |   操作   |     |          |
  +---------+     +----------+      +-----------+     +----------+     +----------+
```

### 8.2 各フェーズ詳細

#### (1) 基礎理解・配線確認（推定: 2〜4時間）

| タスク | 詳細 | 完了条件 |
|--------|------|---------|
| F9P筐体開封 | UART2 JST-GHコネクタの位置確認 | 物理アクセス可能 |
| USB-Serial調達 | FTDI FT232RL (3.3V) または同等品 | デバイス認識確認 |
| 配線作成 | F9P UART2 → USB-Serial のジャンパワイヤ作成 | 導通確認 |
| Raspi認識確認 | `ls /dev/ttyUSB*` で確認 | `/dev/ttyUSB0` 出現 |
| 既存CAN接続確認 | F9P-Pixhawk CAN通信が正常であること | QGCでGPSデータ表示 |

**依存**: なし

#### (2) u-blox F9P 設定（推定: 1〜2時間）

| タスク | 詳細 | 完了条件 |
|--------|------|---------|
| Rover F9P設定スクリプト作成 | `f9p_configurator.py` の config_set パターン流用 | 設定送信成功 |
| 設定確認 | CFG-VALGET で UART2INPROT-RTCM3X=1 確認 | ポーリング応答OK |
| UBX-NAV-PVT出力確認 | UART2からNAV-PVTが出力されることを確認 | NAV-PVT受信 |
| 基地局側確認 | 既存基地局がRTCM3配信中であること | RTCMストリーム確認 |

**依存**: (1) 完了

#### (3) RTCM注入・Fix監視 実装（推定: 3〜6時間）

| タスク | 詳細 | 完了条件 |
|--------|------|---------|
| `rtk_forwarder` シリアル転送対応 | `config/rtk_forwarder.yml` を拡張 | RTCMがUART2に到達 |
| UBX-NAV-PVT ポーリング実装 | `F9pFixMonitor` クラス実装 | `carrSoln` 読み取り成功 |
| RTK Fixed 到達テスト | 屋外で実際にRTK Fixedを待機 | `carrSoln=2` 達成 |
| ログ収集 | RTCM注入量・Fix到達時間・精度の記録 | CSVログ出力 |

**依存**: (1)(2) 完了。屋外環境必要

#### (4) Pixhawk操作の自動化（推定: 2〜4時間）

| タスク | 詳細 | 完了条件 |
|--------|------|---------|
| pymavlink統合 | `mavutil` でPixhawk接続・GPS状態取得 | GPS_RAW_INT受信 |
| 自動化スクリプト完成 | `rtk_direct_inject.py` の全STEP実装・テスト | 全STEP PASS |
| プリフライト統合 | `tools/preflight_check.py` との連携 | 一貫チェックOK |
| エラーハンドリング | タイムアウト・再接続・異常系対応 | 全異常系テスト |

**依存**: (3) 完了

#### (5) 運用整備（推定: 2〜4時間）

| タスク | 詳細 | 完了条件 |
|--------|------|---------|
| systemd サービス化 | 自動起動スクリプトのサービス登録 | `systemctl start rtk-inject` |
| ログローテーション | 長期運用向けログ管理 | 自動ローテーション |
| ドキュメント最終化 | 本設計書の運用実績反映 | 実績値記載 |
| 冗長テスト | Raspi切断→CAN経由フォールバック動作確認 | 位置情報継続確認 |

**依存**: (4) 完了

### 8.3 依存関係図

```
  (1) ---> (2) ---> (3) ---> (4) ---> (5)
   |       |       |       |       |
   |       |       | 屋外   |       |
   |       |       | 必須   |       |
   |       |       |       |       |
   +-並行可能-+       +--並行可能--+
   (基地局側)         (ログ収集)
```

---

## 9. 参考情報

### 9.1 公式ドキュメント

| リソース | URL |
|----------|-----|
| Holybro Docs トップ | https://docs.holybro.com/ |
| H-RTK NEO-F9P Overview | https://docs.holybro.com/gps-and-rtk-system/h-rtk-neo-f9p-series-rm3100-compass/overview |
| NEO-F9P Rover Pinout (UART2) | https://docs.holybro.com/gps-and-rtk-system/h-rtk-neo-f9p-series-rm3100-compass/neo-f9p-rover-pinout |
| u-blox NEO-F9P Datasheet | https://www.u-blox.com/en/product/neo-f9p |
| u-blox ZED-F9P Interface Description | https://www.u-blox.com/en/product/zed-f9p-module |
| ArduPilot RTK GPS Setup | https://ardupilot.org/copter/docs/common-rtk-gps.html |
| ArduPilot GPS_INPUT | https://ardupilot.org/copter/docs/common-gps-input.html |
| ArduPilot EKF | https://ardupilot.org/dev/docs/extended-kalman-filter.html |
| MAVLink GPS_RTCM_DATA | https://mavlink.io/en/messages/common.html#GPS_RTCM_DATA |
| MAVLink GPS_INPUT | https://mavlink.io/en/messages/common.html#GPS_INPUT |
| pyubx2 Documentation | https://pypi.org/project/pyubx2/ |
| pymavlink Documentation | https://pypi.org/project/pymavlink/ |

### 9.2 プロジェクト内関連ファイル

| ファイル | 説明 |
|----------|------|
| `config/rtk_forwarder.yml` | RTCM転送サービス設定。source_type: serial 対応済み |
| `rtk_tools/rtk_forwarder_service.py` | RTCM転送サービス (NTRIP/Serial → UDP) |
| `rtk_tools/f9p_configurator.py` | F9P設定モジュール。UBXMessage.config_set() パターン |
| `rtk_tools/rtk_base_station_v2.py` | 基地局統合サービス |
| `rtk_tools/rtk_data_collector.py` | RTKデータコレクター。UbloxReaderクラス |
| `scripts/ublox_survey_in.py` | F9P Survey-In 設定・モニタリング |
| `app/rtk_tools/rtcm_reader.py` | RTCM TCP受信（基地局→RaspiのRTCM受信に流用可） |
| `app/rtk_tools/rtcm_injector.py` | RTCM→GPS_RTCM_DATA変換（本構成では撤廃） |
| `tools/preflight_check.py` | プリフライトチェック (GPS/EKF/バッテリー/モーター) |
| `scripts/check_gps_fix.py` | GPS Fix状態確認スクリプト |
| `config/gcs.yml` | GCSデフォルト設定 |
| `config/gcs_local.yml` | SSH Tunnel接続設定 |
| `config/gcs_drone.yml` | Raspi上直接実行設定 |
| `rtk_tools/rtk_direct_inject.py` | ★ RTCM注入+RTK FIXED待機 自動化スクリプト |
| `rtk_tools/f9p_rover_config.py` | ★ Rover側F9P UART2設定専用ツール |
| `rtk_tools/f9p_fix_monitor.py` | ★ UBX-NAV-PVT Fix状態ポーリング |
| `deploy/rtk-uart2-inject.service` | ★ systemd サービス定義 |
| `deploy/install_rtk_uart2_service.sh` | ★ サービスインストールスクリプト |
| `docs/05-implementation/preflight_rtk_checklist_uart2.md` | ★ プリフライトRTKチェックリスト (UART2) |
| `CHANGELOG.md` | ★ 変更履歴 |
| `docs/01-specification/communication-architecture.md` | 通信アーキテクチャ完全ドキュメント |
| `docs/03-operations/rtk_integration_guide.md` | RTK統合ガイド |
| `docs/05-implementation/RTK_BASE_STATION_IMPLEMENTATION.md` | RTK基地局実装計画 |

### 9.3 Holybro H-RTK F9P UART2 ピン配置（再掲）

```
   UART2 (Inside Casing) - JST-GH 6-pin
   +-------------------------+
   | Pin 1 (Red)  VCC   5.0V |
   | Pin 2        RX2   3.3V | <-- Raspi TX -> RTCM注入
   | Pin 3        TX2   3.3V | <-- UBX-NAV-PVT読取
   | Pin 4        EXTINT     |
   | Pin 5        PPS        |
   | Pin 6        GND         |
   +-------------------------+
```

---

## 付録A: 新旧比較表

| 項目 | 現行（MAVLink経由） | 提案（UART2直結） |
|------|-------------------|-------------------|
| RTCM注入経路 | Raspi→Pixhawk(MAVLink)→DroneCAN→F9P | Raspi→UART2→F9P |
| MAVLink依存 | GPS_RTCM_DATA (msgid=233) 必須 | **不要** |
| フラグメント分割 | あり (180byte/chunk) | **不要** |
| Fix状態監視 | Pixhawk GPS_RAW_INT経由（間接的） | UBX-NAV-PVT 直接読取 |
| フォールトトレランス | 全断 (Raspi障害でRTCM途絶) | CAN経由位置情報は生存 |
| 設定ツール依存 | QGC / u-center | Pythonスクリプト自動化 |
| 遅延 | MAVLink + DroneCAN 2段階 | シリアル直接（最小） |
| デバッグ | ログ確認のみ | UART2上のバイト列直接観測 |

---

## 付録B: 想定リスクと対策

| リスク | 影響 | 対策 |
|--------|------|------|
| UART2配線の物理的損傷 | RTCM注入不能 | 筐体内部の配線固定、ストレインリリーフ |
| USB-Serialアダプタ故障 | RTCM注入不能 | 予備アダプタ携行、CAN経由フォールバック |
| UART2ボーレート不一致 | RTCM未到達 | CFG-VALSETで明示的に115200設定 |
| 基地局RTCMストリーム切断 | RTK Fixed喪失 | rtk_forwarder 自動再接続機能 |
| GPS電波環境不良 | RTK Fixed未達成 | タイムアウト設定、環境チェック事前実施 |
| Pixhawk側GPSとの二重供給 | 競合の可能性 | CAN位置情報との競合はArduPilotが自動調停 (GPS_AUTO_SWITCH) |

---

## 付録C: 撤廃対象・新規作成・維持の判別

```
+------------------------------------------------------------+
|                        撤廃対象                             |
|  app/rtk_tools/rtcm_injector.py                            |
|  +-- MAVLink GPS_RTCM_DATA (msgid=233) 注入パス             |
+------------------------------------------------------------+
|                        流用                                |
|  rtk_tools/f9p_configurator.py   +-- UBXMessage.config_set() |
|  rtk_tools/rtk_data_collector.py +-- UbloxReader クラス     |
|  app/rtk_tools/rtcm_reader.py    +-- RTCM TCP受信           |
|  config/rtk_forwarder.yml        +-- serial source設定      |
|  scripts/ublox_survey_in.py      +-- Survey-In設定         |
+------------------------------------------------------------+
|                        新規作成                             |
|  rtk_tools/rtk_direct_inject.py  +-- 自動化統合スクリプト   |
|  rtk_tools/f9p_rover_config.py   +-- Rover側F9P設定特化     |
|  rtk_tools/f9p_fix_monitor.py    +-- UBX-NAV-PVTポーリング  |
+------------------------------------------------------------+
|                        維持                                 |
|  rtk_tools/rtk_base_station_v2.py  +-- 基地局側（変更なし） |
|  tools/preflight_check.py          +-- プリフライトチェック |
|  config/gcs*.yml                   +-- GCS設定（変更なし）   |
|  app/mavlink/connection.py         +-- MAVLink通信（変更なし）|
|  app/mavlink/message_router.py     +-- メッセージルーター    |
+------------------------------------------------------------+
```
