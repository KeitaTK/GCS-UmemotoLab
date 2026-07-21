# CANインターフェース セットアップ計画書

**作成日**: 2026-07-21
**ステータス**: 計画中
**目的**: Raspberry Pi 5 に CAN インターフェースを追加し、UART2 を RTCM 専用化する

---

## 1. 背景と目的

### 1.1 現状の課題

現在、F9P Rover の UART2 は以下の2役を同時に担っている:

```
F9P UART2
  ├─ RX2 ← RaspiからRTCM3補正データ注入
  └─ TX2 → RaspiへUBX-NAV-PVT出力（Fix状態監視用）
```

この双方向運用には以下の問題がある:
- UART2 の RX/TX 調停が必要
- RTCM注入と Fix 監視が同一ポートを共有するため、バッティングのリスク
- USB-Serial アダプタが単一障害点

### 1.2 移行後の構成

```
                     ┌──────────────────────┐
                     │   Raspberry Pi 5      │
                     │                       │
   [基地局RTCM]      │  UART4 (/dev/ttyAMA4) │ ──→ F9P UART2 RX2 (RTCM注入専用)
   NTRIP/TCP ───────→│  (RTCM注入専用)       │
                     │                       │
                     │  SPI0 + MCP2515       │ ──→ DroneCAN バス
                     │  (can0)              │     (CAN_GNSS_FIX2監視)
                     │                       │
                     └───────────────────────┘
                              │
                        CANバスに合流
                              │
         ┌────────────────────┼────────────────────┐
         │                    │                    │
    ┌────▼─────┐        ┌─────▼──────┐        ┌───▼──────────┐
    │  F9P     │        │  Pixhawk   │        │ 他CANノード   │
    │ (Rover)  │        │ (CAN1)     │        │ (AP_Periph等) │
    └──────────┘        └────────────┘        └──────────────┘
```

**利点**:
1. UART2 が RTCM 注入専用になる — TX/RX 調停不要
2. CAN 監視により 10 Hz の高頻度 Fix 状態取得（現行 UBX は最大 5 Hz）
3. Pixhawk と同じ視点（AP_Periph が Pixhawk に送る Fix2 メッセージ）
4. CAN バス上の全ノードを単一インターフェースから監視可能


---

## 2. CAN コントローラの選定

### 2.1 要件

| 要件 | 値 | 備考 |
|------|-----|------|
| 対応プラットフォーム | Raspberry Pi 5 | 40-pin GPIO 互換 |
| 接続方式 | SPI | MCP2515 が定番 |
| CAN 規格 | CAN 2.0B | DroneCAN は CAN 2.0 ベース |
| ボーレート | 1 Mbps | ArduPilot 標準 CAN レート |
| カーネル対応 | SocketCAN (mcp251x) | dtoverlay で有効化 |
| 電源 | 3.3V / 5V 両対応 | Raspi 40-pin から供給 |

### 2.2 候補品リスト

#### 推奨1: Waveshare RS485 CAN HAT (B) — MCP2515 版 ★★★★★

| 項目 | 内容 |
|------|------|
| チップ | MCP2515（CAN コントローラ） + SN65HVD230（CAN トランシーバ） |
| 接続 | SPI0.0 (CE0), GPIO 25 (INT) |
| 電源 | 3.3V (40-pin ヘッダから供給) |
| 特徴 | RS485 と CAN の両対応。ArduPilot/PX4 コミュニティで実績あり |
| 価格 | ¥1,200～¥1,800 |
| 調達 | Amazon, AliExpress, Waveshare 公式 |
| Raspi 5 対応 | ○（GPIO ピン配置は 40-pin 互換） |

**長所**: コミュニティ実績豊富、dtoverlay 設定が標準化、安価
**短所**: MCP2515 は CAN FD 未対応（DroneCAN は CAN 2.0 なので問題なし）

#### 推奨2: Seeed Studio 2-Channel CAN-BUS(FD) HAT — MCP2518FD 版 ★★★★☆

| 項目 | 内容 |
|------|------|
| チップ | MCP2518FD（CAN FD 対応コントローラ） ×2 |
| 接続 | SPI0.0 + SPI0.1 (2ch), GPIO 25+16 (INT ×2) |
| 電源 | 3.3V / 5V (40-pin ヘッダから供給) |
| 特徴 | CAN FD 対応、2ch 搭載で F9P/Pixhawk 両方を個別監視可能 |
| 価格 | ¥2,500～¥3,500 |
| 調達 | Amazon, Seeed Studio 公式 |
| Raspi 5 対応 | ○（GPIO ピン配置は 40-pin 互換） |

**長所**: CAN FD 対応で将来性あり、2ch で冗長化可能、ドライバ対応良好
**短所**: やや高価、2ch は本用途では不要の可能性

#### 推奨3: PiCAN2 Duo — 高耐久 ★★★☆☆

| 項目 | 内容 |
|------|------|
| チップ | MCP2515 ×2 + アイソレータ搭載 |
| 接続 | SPI0.0, GPIO 25 (INT) |
| 電源 | 5V（12V外部入力にも対応） |
| 特徴 | CAN バス絶縁（Galvanic Isolation）付き、産業環境向け |
| 価格 | ¥5,000～¥8,000 |
| 調達 | Copperhill Tech, Amazon |
| Raspi 5 対応 | ○（GPIO ピン配置は 40-pin 互換） |

**長所**: 絶縁保護、過酷環境で信頼性高い、2ch
**短所**: 高価、本用途にはややオーバースペック

### 2.3 選定結論

**Waveshare RS485 CAN HAT (B) を推奨**。理由:
1. 価格と機能のバランスが最適
2. ArduPilot/PX4 コミュニティでドキュメント・実績が豊富
3. MCP2515 の SocketCAN ドライバが Raspberry Pi OS に標準搭載

---

## 3. Raspberry Pi 5 への接続計画

### 3.1 SPI ピンアサイン

Raspberry Pi 5 の 40-pin ヘッダにおける SPI0 と MCP2515 HAT の接続:

```
    Raspi 5 GPIO 40-pin Header
    ┌──────────────────────────────┐
    │  1   2                       │  1: 3.3V    2: 5V
    │  3   4                       │  3: GPIO2   4: 5V
    │  5   6                       │  5: GPIO3   6: GND
    │  7   8  ← UART0 TX           │  7: GPIO4   8: GPIO14
    │  9  10  ← UART0 RX           │  9: GND    10: GPIO15
    │ 11  12                       │ 11: GPIO17 12: GPIO18
    │ 13  14                       │ 13: GPIO27 14: GND
    │ 15  16                       │ 15: GPIO22 16: GPIO23
    │ 17  18                       │ 17: 3.3V   18: GPIO24
    │ 19  20  ← SPI0 MOSI          │ 19: GPIO10 20: GND     ★ MCP2515 SI
    │ 21  22  ← SPI0 MISO + INT    │ 21: GPIO9  22: GPIO25  ★ MCP2515 SO + INT
    │ 23  24  ← SPI0 SCLK + CE0    │ 23: GPIO11 24: GPIO8   ★ MCP2515 SCK + CS
    │ 25  26                       │ 25: GND    26: GPIO7
    │ 27  28                       │ 27: ID_SD  28: ID_SC
    │ 29  30                       │ 29: GPIO5  30: GND
    │ 31  32  ← UART4 TX           │ 31: GPIO6  32: GPIO12 (F9P RTCM注入)
    │ 33  34  ← UART4 RX           │ 33: GPIO13 34: GND
    │ 35  36                       │ 35: GPIO19 36: GPIO16
    │ 37  38                       │ 37: GPIO26 38: GPIO20
    │ 39  40                       │ 39: GND    40: GPIO21
    └──────────────────────────────┘
```

**MCP2515 接続表 (SPI0.0)**:

| MCP2515 ピン | 信号 | 方向 | Raspi GPIO ピン | 物理ピン番号 | 備考 |
|--------------|------|------|-----------------|-------------|------|
| SCK | SPI Clock | Raspi→MCP2515 | GPIO 11 (SPI0 SCLK) | 23 | |
| SI  | MOSI | Raspi→MCP2515 | GPIO 10 (SPI0 MOSI) | 19 | |
| SO  | MISO | MCP2515→Raspi | GPIO 9 (SPI0 MISO) | 21 | |
| CS  | Chip Select | Raspi→MCP2515 | GPIO 8 (SPI0 CE0) | 24 | |
| INT | Interrupt | MCP2515→Raspi | GPIO 25 | 22 | デフォルト |
| VCC | 3.3V | — | 3.3V Power | 1 or 17 | |
| GND | Ground | — | GND | 6, 9, 14, 20, 25, 30, 34, 39 | いずれか |

**CAN バス配線**:

| Waveshare HAT 端子 | 接続先 | 備考 |
|-------------------|--------|------|
| CAN_H | Pixhawk CAN1 CAN_H | DroneCAN バス H ライン |
| CAN_L | Pixhawk CAN1 CAN_L | DroneCAN バス L ライン |
| GND（CAN側） | — | オプション（同一電源系なら不要） |

### 3.2 既存 UART ピンとの競合確認

| 機能 | GPIO | 物理ピン | 使用先 |
|------|------|---------|--------|
| UART0 (PL011) | GPIO 14/15 | 8/10 | **Pixhawk TELEM1** (mavlink-router) — 継続使用 |
| UART4 | GPIO 12/13 | 32/33 | **F9P UART2** (RTCM 注入用 USB-Serial) — 継続使用 |
| SPI0 | GPIO 8/9/10/11 | 24/21/19/23 | **MCP2515 CAN HAT** — 新規使用 |
| **INT (GPIO25)** | GPIO 25 | 22 | **MCP2515 割り込み** — 新規使用 |

> **結論**: 既存の UART ピン割り当てと競合なし。SPI0 と GPIO25 は未使用であることを確認済み。

### 3.3 Raspi 5 固有の注意点

- Raspberry Pi 5 は GPIO コントローラが RP1 に変更されたが、40-pin ヘッダの物理ピン配置は Pi 4 と完全互換
- SPI0.0 は標準で有効 (`dtparam=spi=on`) が必要
- GPIO 25 はデフォルトで input（プルアップなし）、`dtoverlay=mcp2515-can0` が適切に設定する

4. 単一 CAN バス構成（F9P + Pixhawk が同一 CAN バス上）で十分


---

## 4. カーネルモジュール設定

### 4.1 /boot/firmware/config.txt への追加

```ini
# ============================================================
# CAN Interface (MCP2515 on SPI0.0) — for DroneCAN monitoring
# ============================================================

# Enable SPI0
dtparam=spi=on

# MCP2515 CAN controller overlay
# - oscillator=16000000 : MCP2515 外部クロック周波数 (16 MHz)
# - interrupt=25       : 割り込み GPIO ピン
# - spimaxfrequency=10000000 : SPI クロック最大 10 MHz
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25,spimaxfrequency=10000000

# 注意: Raspberry Pi 5 では config.txt のパスが以下に変更されている
#        /boot/firmware/config.txt
#        (Pi 4 以前の /boot/config.txt とは異なる)
```

### 4.2 設定の反映と確認

```bash
# 1. config.txt 編集後、Raspi を再起動
sudo reboot

# 2. 起動後、CAN インターフェースの存在確認
ip link show can0
# 期待: can0: <NOARP,ECHO> mtu 16 qdisc noop state DOWN ...

# 3. SPI デバイスの確認
ls /dev/spi*
# 期待: /dev/spidev0.0  /dev/spidev0.1

# 4. dmesg でカーネルメッセージ確認
dmesg | grep -i 'can\|mcp2515\|spi'
# 期待: mcp251x spi0.0 can0: MCP2515 successfully initialized.
```

### 4.3 CAN インターフェースの起動（手動）

```bash
# CAN インターフェースを UP（ボーレート 1 Mbps = ArduPilot 標準）
sudo ip link set can0 type can bitrate 1000000
sudo ip link set up can0

# 状態確認
ip -details link show can0
# 期待: state UP, bitrate 1000000
```

### 4.4 CAN 自動起動の永続化（systemd-networkd 推奨）

```bash
sudo tee /etc/systemd/network/80-can0.network <<'EOF'
[Match]
Name=can0

[CAN]
Bitrate=1000000
RestartSec=100ms
EOF

sudo tee /etc/systemd/network/80-can0.link <<'EOF'
[Match]
OriginalName=can0

[Link]
ActivationPolicy=always-up
EOF

sudo systemctl restart systemd-networkd
sudo systemctl enable systemd-networkd
networkctl status can0
```

### 4.5 代替: /etc/network/interfaces 方式

```bash
sudo tee -a /etc/network/interfaces.d/can0 <<'EOF'
auto can0
iface can0 inet manual
    pre-up /sbin/ip link set can0 type can bitrate 1000000
    up /sbin/ip link set up can0
    down /sbin/ip link set down can0
EOF

---

## 5. ソフトウェア環境セットアップ

### 5.1 Python パッケージ追加

```bash
# 既存プロジェクトの仮想環境に追加
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# python-can (SocketCAN バックエンド)
pip install python-can>=4.4

# dronecan (DroneCAN メッセージパース)
pip install dronecan>=1.0

# または uv を使用
uv pip install python-can>=4.4 dronecan>=1.0
```

requirements_raspi.txt にも追記:
```txt
python-can>=4.4
dronecan>=1.0
```

### 5.2 動作確認（CAN ダンプ）

```bash
# can-utils のインストール（未インストールの場合）
sudo apt install -y can-utils

# can0 が UP 状態であることを確認
ip link show can0 | grep -q UP || echo "ERROR: can0 is not UP"

# CAN トラフィックのダンプ
# DroneCAN バス上にデータが流れていれば表示される
candump can0
# Ctrl+C で停止
```

### 5.3 Python 受信テスト

```python
# Python で CAN メッセージ受信テスト
import can

bus = can.interface.Bus(channel='can0', interface='socketcan')
print("Listening on can0 ... (Ctrl+C to stop)")
try:
    for msg in bus:
        print(f"ID=0x{msg.arbitration_id:08X} "
              f"DLC={msg.dlc} DATA={msg.data.hex()}")
except KeyboardInterrupt:
    print("Stopped.")
```

---

## 6. F9P CAN 接続との共存方法

### 6.1 現在の CAN バス構成

```
    Pixhawk CAN1
         │
    CAN_H├────────────┬───────────── ···
    CAN_L┼────────────┼───────────── ···
         │            │
    ┌────▼─────┐  ┌───▼──────────┐
    │  F9P     │  │  他ノード     │
    │ (Rover)  │  │  (存在する場合)│
    └──────────┘  └──────────────┘
```

### 6.2 Raspi CAN 追加後の構成

```
         ┌──────────────────────────────────┐
         │         DroneCAN バス (1 Mbps)    │
         │                                   │
    CAN_H├────┬──────────┬────────────── ···
    CAN_L┼────┼──────────┼────────────── ···
         │    │          │
    ┌────▼─┐ ┌▼──────┐ ┌─▼──────────┐
    │F9P   │ │Pixhawk│ │Raspi 5      │
    │CAN   │ │CAN1   │ │MCP2515(can0)│ ← ★ 新規追加
    └──────┘ └───────┘ └─────────────┘
```

### 6.3 共存のポイント

| 項目 | 説明 |
|------|------|
| **CAN ID 競合なし** | MCP2515 は CAN バス上の別ノードとして Listen。既存ノードの CAN ID と競合しない |
| **バス終端** | 既存の F9P-Pixhawk CAN バスに終端抵抗(120Ω)が入っていることを確認。HAT側の終端抵抗は **無効** にする（バス途中に追加するため） |
| **Waveshare HAT の終端設定** | HAT 上の 120Ω 終端抵抗ジャンパを **OFF** にする。Pixhawk CAN1 と F9P 側で終端済みのため |
| **ボーレート** | 1 Mbps（ArduPilot デフォルト）。既存バスと一致 |
| **Listen-Only モード** | 本セットアップでは Listen-Only で運用。CAN フレームの送信は不要（監視専用） |

### 6.4 Listen-Only モードの設定（推奨）

```bash
# Listen-Only モードで CAN インターフェースを起動（誤送信防止）
sudo ip link set can0 type can bitrate 1000000 listen-only on
sudo ip link set up can0
```

systemd-networkd 用設定:
```ini
# /etc/systemd/network/80-can0.network
[Match]
Name=can0

[CAN]
Bitrate=1000000
ListenOnly=true
RestartSec=100ms
```

### 6.5 終端抵抗ジャンパ設定

```
   Waveshare HAT 基板上のジャンパ
   ┌─────────────────────────────┐
   │  120Ω 終端抵抗              │
   │  ┌───┐                      │
   │  │ ○ │  ← デフォルト: 接続  │
   │  │ ○─│  ← ★ OFF にする ★   │
   │  └───┘                      │
   └─────────────────────────────┘
```

> **注意**: 終端抵抗を誤って ON にすると、バス全体のインピーダンスが低下し通信不良を起こす可能性がある。


---

## 7. セットアップ手順（ステップバイステップ）

### Step 1: HAT 調達・開封確認

- [ ] Waveshare RS485 CAN HAT (B) を入手
- [ ] 付属品確認: ピンヘッダ、スペーサー、ネジ
- [ ] ジャンパピンが 120Ω 終端 = OFF になっていることを確認

### Step 2: ハードウェア接続

```bash
# 1. Raspi の電源 OFF
sudo poweroff

# 2. Waveshare HAT を Raspi 40-pin ヘッダに装着
#    - ピンずれに注意（物理ピン 1 番 = 3.3V から合わせる）

# 3. CAN バス配線
#    - HAT の CAN_H → Pixhawk CAN1 の CAN_H
#    - HAT の CAN_L → Pixhawk CAN1 の CAN_L
#    - 配線はツイストペア（より対線）推奨、長さ ≦ 30 cm

# 4. 配線チェック
#    - テスターで CAN_H ⇔ CAN_L 間の抵抗を測定
#    - 終端抵抗が正しく入っていれば ~60Ω
#      （120Ω 終端 × 2箇所の並列 = 60Ω）

# 5. Raspi 電源 ON
```

### Step 3: config.txt 設定

```bash
# Raspberry Pi 5 では /boot/firmware/config.txt を編集
sudo nano /boot/firmware/config.txt

# 以下の行を末尾に追加:
dtparam=spi=on
dtoverlay=mcp2515-can0,oscillator=16000000,interrupt=25,spimaxfrequency=10000000

# 保存して再起動
sudo reboot
```

### Step 4: CAN インターフェース確認と起動

```bash
# can0 の存在確認
ip link show can0

# Listen-Only モードで起動（バス監視専用）
sudo ip link set can0 type can bitrate 1000000 listen-only on
sudo ip link set up can0

# 状態確認
ip -details link show can0
```

### Step 5: CAN 通信テスト

```bash
# candump で CAN トラフィック確認
sudo apt install -y can-utils
candump can0
# Ctrl+C で停止
# DroneCAN メッセージが流れていれば表示される
```

### Step 6: Python テスト

```bash
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# パッケージインストール
uv pip install python-can>=4.4 dronecan>=1.0

# Python で CAN メッセージ受信テスト
python3 -c "
import can
bus = can.interface.Bus(channel='can0', interface='socketcan')
print('Listening on can0 ... (Ctrl+C to stop)')
try:
    for msg in bus:
        print(f'ID=0x{msg.arbitration_id:08X} DLC={msg.dlc} DATA={msg.data.hex()}')
except KeyboardInterrupt:
    print('Stopped.')
"
```

### Step 7: 自動起動設定

```bash
sudo tee /etc/systemd/network/80-can0.network <<'EOF'
[Match]
Name=can0

[CAN]
Bitrate=1000000
ListenOnly=true
RestartSec=100ms
EOF

sudo tee /etc/systemd/network/80-can0.link <<'EOF'
[Match]
OriginalName=can0

[Link]
ActivationPolicy=always-up
EOF

sudo systemctl restart systemd-networkd
sudo systemctl enable systemd-networkd
networkctl status can0
```

### Step 8: 最終健全性チェック

```bash
#!/bin/bash
# can_health_check.sh
set -e
echo "=== CAN Interface Health Check ==="

echo -n "SPI device  : "
ls /dev/spidev0.* 2>/dev/null && echo "OK" || echo "MISSING"

echo -n "can0 exists : "
ip link show can0 >/dev/null 2>&1 && echo "OK" || echo "MISSING"

echo -n "can0 UP     : "
ip link show can0 | grep -q "state UP" && echo "OK" || echo "DOWN"

echo "dmesg (last 5 CAN lines):"
dmesg | grep -i 'can\|mcp2515' | tail -5

echo "=== Check complete ==="

---

## 8. 必要な購入品リスト

| # | 品名 | 型番/URL | 数量 | 参考価格 | 用途 | 必須度 |
|---|------|----------|------|---------|------|--------|
| 1 | **Waveshare RS485 CAN HAT (B)** | [Amazon検索](https://www.amazon.co.jp/s?k=Waveshare+RS485+CAN+HAT) | 1個 | ¥1,200～¥1,800 | CAN コントローラ（MCP2515 + SN65HVD230） | ★必須 |
| 2 | **ジャンパワイヤ（オス-メス）** | ブレッドボード用 | 1セット（4本） | ¥300～¥500 | CAN_H, CAN_L を Pixhawk CAN1 に分岐接続 | ★必須 |
| 3 | **（予備）JST-GH 4ピンコネクタ** | Pixhawk CAN1 コネクタ | 1個 | ¥200～¥400 | 分岐ケーブル自作時の CAN コネクタ予備 | △任意 |
| 4 | **（予備）USB-Serial アダプタ (3.3V)** | FTDI FT232RL | 1個 | ¥800～¥1,200 | UART4/Raspi 間で UART2 注入用の予備 | ○推奨 |

**購入先候補**:
- **Amazon.co.jp**: すべての品が Prime 配送可能
- **秋月電子通商**: コネクタ・ジャンパワイヤは即日発送
- **マルツオンライン**: 高品質ジャンパワイヤ・コネクタ

**合計費用目安**: ¥1,500～¥2,500（必須品のみ）

---

## 9. CAN 監視ソフトウェア改修計画（次フェーズ）

### 9.1 必要な改修

| 対象 | 改修内容 | 新規/変更 |
|------|---------|----------|
| `rtk_tools/can_fix_monitor.py` | CAN DroneCAN Fix2 メッセージ受信・Fix 状態監視 | **新規** |
| `rtk_tools/f9p_fix_monitor.py` | `--mode uart` / `--mode can` でモード切替可能に拡張 | **変更** |
| `tools/preflight_check.py` | CAN インターフェースチェック項目追加 | **変更** |
| `deploy/rtk-can-monitor.service` | can0 監視の systemd サービス定義 | **新規** |

### 9.2 CAN Fix Monitor の基本設計

```python
# rtk_tools/can_fix_monitor.py（新規作成案）
"""
DroneCAN Fix2 メッセージを can0 (SocketCAN) から受信し、
RTK Fix 状態を監視する。

受信対象:
  - DroneCAN message type: uavcan.equipment.gnss.Fix2 (ID: 1066)
  - この Fix2 は AP_Periph が F9P から取得した Fix 情報を
    DroneCAN バスにブロードキャストしているもの

status 値（uavcan.equipment.gnss.Fix2）:
  0 = No Fix
  1 = Dead Reckoning
  2 = 2D
  3 = 3D
  4 = DGPS
  5 = RTK Float
  6 = RTK Fixed  ← ★ 目標
"""
```

### 9.3 移行ロードマップ

```
Phase 0: CAN I/F 調達・セットアップ ← 本ドキュメント
    │
Phase 1: CAN 監視モジュール開発 (can_fix_monitor.py)
    │
Phase 2: 並行稼働試験（UART2 UBX 監視 + CAN 監視 のデータ一致確認）
    │
Phase 3: UART2 UBX 出力無効化（RTCM 注入専用化）
    │
Phase 4: 本番移行・運用ドキュメント更新
```

---

## 10. リスクと対策

| リスク | 影響 | 確率 | 対策 |
|--------|------|------|------|
| MCP2515 ドライバが Raspi 5 で正常動作しない | CAN 監視不能 | 低 | 事前に `dmesg` 確認、Amazon 返品期間内にテスト |
| CAN バス分岐による信号品質劣化 | 通信エラー | 中 | 分岐長を 30cm 以下に抑える、ツイストペアケーブル使用 |
| 誤って終端抵抗を ON にする | バス全体の通信不良 | 中 | セットアップ時にジャンパ位置を写真で記録 |
| F9P/Pixhawk 間 CAN 通信への干渉 | 飛行中の GPS 喪失 | 低 | Listen-Only モード必須、地上試験で 30 分以上監視 |
| python-can + dronecan の依存関係問題 | モジュールインストール失敗 | 低 | `uv pip install` でバージョン固定 |
| CAN コネクタの接触不良 | 断続的なデータ欠損 | 中 | JST-GH コネクタのロック確認、予備コネクタ携行 |

---

## 11. 参考リンク

| リソース | URL |
|----------|-----|
| Waveshare RS485 CAN HAT Wiki | https://www.waveshare.com/wiki/RS485_CAN_HAT_(B) |
| Raspberry Pi CAN Bus Setup | https://www.raspberrypi.com/documentation/computers/configuration.html#can-bus |
| MCP2515 Kernel Driver | https://www.kernel.org/doc/html/latest/networking/device_drivers/can/mcp251x.html |
| python-can Documentation | https://python-can.readthedocs.io/ |
| DroneCAN Specification | https://dronecan.github.io/Specification/ |
| ArduPilot CAN Setup | https://ardupilot.org/copter/docs/common-canbus-setup.html |
| 本プロジェクト CAN 監視可否レポート | [can_monitor_feasibility_report.md](can_monitor_feasibility_report.md) |
| RTK UART2 注入設計書 | [../05-implementation/rtk_direct_uart2_injection_plan.md](../05-implementation/rtk_direct_uart2_injection_plan.md) |
