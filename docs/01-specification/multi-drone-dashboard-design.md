# GCS-UmemotoLab マルチドローン同時表示ダッシュボード 設計提案書

> **バージョン**: 1.0.0  
> **作成日**: 2026-06-14  
> **前提ドキュメント**: [web-ui-spec.md](./web-ui-spec.md) v2.0.0  
> **対象**: バックエンド全機能を精査した上での、マルチドローン同時監視・制御用 GCS ダッシュボード設計

---

## 1. 概要

### 1.1 目的

現行の GCS ダッシュボード (`web-ui-spec.md`) は **単一ドローンを選択して表示する設計** であり、最大の問題は「全ドローンの状態を同時に一目で把握できない」ことにある。

本設計提案は、**最大 4 機のドローンを固定 4 カラム看板風レイアウトで同時表示** し、全機の Armed 状態／Flight Mode／バッテリー／GPS Fix を一瞥できるダッシュボードを実現する。

### 1.2 設計方針

| 方針 | 説明 |
|------|------|
| **固定 4 カラム** | 接続台数が 4 未満でも枠を維持（空き枠はプレースホルダー表示） |
| **看板風カード** | 各ドローン = 1 カード。最重要情報を巨大バッジで表示 |
| **バックエンド完全活用** | `arm_all`/`disarm_all`/`takeoff_all`/`land_all` 等の既存一斉制御を UI 化 |
| **関心の分離** | 単一ドローン制御は各カード内、全機制御は下部パネル、接続管理は上部 |
| **Vanilla JS 継続** | 既存のフレームワーク不使用方針を踏襲 |
| **ダークテーマ継承** | 既存 `#1a1a2e` 背景、`#e67e22` アクセントを踏襲 |

---

## 2. バックエンド調査：全データソース

> **情報ソース**: `app/api/websocket.py` `_build_payload()`、`app/rtk_tools/telemetry_store.py`、`app/mavlink/connection.py`

### 2.1 WebSocket ペイロード (`/ws/telemetry`, 1Hz)

WebSocket の `broadcast_loop()` (`app/api/websocket.py:61-95`) が 1 秒毎に以下の全データを配信する。  
本ダッシュボードはこの 1 つのペイロードから全カードを更新する。

```json
{
  "type": "telemetry",
  "timestamp": 1718000000.123,
  "connection": { ... },
  "drones": {
    "1": { "heartbeat":{...}, "battery":{...}, "gps":{...}, "system_state":{...}, "command_state":{...} },
    "2": { ... }
  },
  "rtk": { ... }
}
```

#### 2.1.1 `connection` — MAVLink 接続全体の状態

| フィールド | 型 | ソース (websocket.py) | 説明 | 用途 |
|-----------|-----|----------------------|------|------|
| `is_connected` | bool | `_build_connection_status():151` | MAVLink UDP/Serial 接続中か | アラートバー、RTK バー |
| `type` | string | 同上:152 | `"udp"` / `"serial"` / `"unknown"` / `"error"` | 表示 |
| `packets_received` | int | 同上:153 (`packet_received`) | 受信パケット総数 | RTK バー補足 |
| `packet_loss` | int | 同上:154 | 損失パケット数 | アラート条件 |
| `last_error` | string\|null | 同上:155 | 最終エラー文字列 | アラート条件 |

> **注意**: `connection.py:77` のキー名は `packet_received`（単数形）。websocket.py:153 で `packets_received`（複数形）に変換される。

#### 2.1.2 `drones.{sysid}.heartbeat` / `system_state` — 機体状態

| フィールド | 型 | ソース | 説明 |
|-----------|-----|--------|------|
| `armed` | bool | `_build_heartbeat():166` | `base_mode & 0x80 != 0` |
| `mode` | string | 同上:170 (`_COPTER_MODES`) | フライトモード名（STABILIZE/GUIDED/LOITER 等） |
| `base_mode` | int | 同上:171 | MAVLink base_mode 生値 |
| `custom_mode` | int | 同上:172 | MAVLink custom_mode 生値（-1 = N/A） |

> **備考**: `system_state` は `_build_system_state()` (websocket.py:232) で `_build_heartbeat()` をそのまま返すエイリアス。

#### 2.1.3 `drones.{sysid}.battery` — バッテリー状態

| フィールド | 型 | ソース | 説明 |
|-----------|-----|--------|------|
| `voltage` | float\|null | `_build_battery():183` | 電圧 (V)。`voltage_battery / 1000.0` |
| `current` | float\|null | 同上:184 | 電流 (A)。`current_battery / 100.0` |
| `remaining` | int\|null | 同上:185 | 残量 (%, -1 は null に変換) |

#### 2.1.4 `drones.{sysid}.gps` — GPS 測位

| フィールド | 型 | ソース | 説明 |
|-----------|-----|--------|------|
| `fix_type` | int | `_build_gps():211` | GPS fix 種別 (0〜8)。-1 = N/A |
| `fix_name` | string | 同上:213 (`_FIX_NAMES`) | 種別名 (NO_GPS/3D_FIX/RTK_FIXED 等) |
| `satellites` | int | 同上:214 | 捕捉衛星数 |
| `lat` | float\|null | 同上:222 | 緯度 (deg, `lat / 1e7`) |
| `lon` | float\|null | 同上:223 | 経度 (deg, `lon / 1e7`) |
| `alt` | float\|null | 同上:224 | 高度 (m, `alt / 1000.0`)。**GLOBAL_POSITION_INT.alt は AMSL。相対高度は `relative_alt/1000`** |
| `hdop` | float\|null | 同上:216 | 水平精度低下率 (m, `eph / 100.0`)。eph=65535 時 null |

> **Fix Type 一覧** (`websocket.py:100-104`): `0:NO_GPS, 1:NO_FIX, 2:2D_FIX, 3:3D_FIX, 4:DGPS, 5:RTK_FLOAT, 6:RTK_FIXED, 7:STATIC, 8:PPP`

#### 2.1.5 `drones.{sysid}.command_state` — コマンド状態

| フィールド | 型 | ソース | 説明 |
|-----------|-----|--------|------|
| `pending_count` | int | `_build_command_state():255` | 未完了コマンド数 |
| `last_ack` | object\|null | 同上:248-252 | `{"command":"ARM", "status":"acked/failed/timeout"}` |

> **ACK ステータス**: `acked`, `failed`, `timeout` (`command_dispatcher.py:199-203,272`)

#### 2.1.6 `rtk` — RTK 基地局

| フィールド | 型 | ソース | 説明 |
|-----------|-----|--------|------|
| `enabled` | bool | `_build_rtk_status():266` | RTCM 有効/無効 |
| `messages_received` | int | 同上:267 (`rtcm_reader.stats`) | RTCM メッセージ受信数 |
| `connections` | int | 同上:268 | 接続回数 |
| `reconnects` | int | 同上:269 | 再接続回数 |

> **RTK 統計の詳細** (`rtcm_reader.py:25-31`): 追加で `bytes_received`, `last_message_time` も保持。WebSocket ペイロードには未出力（拡張可能）。



---

## 3. バックエンド調査：全コマンド

> **情報ソース**: `app/api/routes.py` (REST エンドポイント)、`app/rtk_tools/command_dispatcher.py` (内部メソッド)

### 3.1 REST API コマンド一覧

| エンドポイント | メソッド | キーパラメータ | ソース行 |
|---------------|---------|---------------|---------|
| `POST /api/connect` | — | `config_path` (任意) | `routes.py:107` |
| `POST /api/disconnect` | — | — | `routes.py:194` |
| `POST /api/arm` | — | `system_ids`, `component_id`(default:1) | `routes.py:283` |
| `POST /api/disarm` | — | `system_ids`, `component_id`(default:1) | `routes.py:296` |
| `POST /api/force_arm` | — | `system_ids`, `component_id`, `confirmed:true` (**必須**) | `routes.py:309` |
| `POST /api/takeoff` | — | `system_ids`, `component_id`, `altitude`(0.5〜500m) | `routes.py:331` |
| `POST /api/land` | — | `system_ids`, `component_id`, `descent_rate`(0〜20 m/s) | `routes.py:364` |
| `POST /api/guided/position` | — | `system_ids`, `component_id`, `north`, `east`, `down`, `yaw`(-180〜180°) | `routes.py:389` |
| `POST /api/guided/velocity` | — | `system_ids`, `component_id`, `vx`, `vy`, `vz`(-20〜20), `yaw`(-180〜180°) | `routes.py:411` |

### 3.2 CommandDispatcher 内部コマンド（一斉制御メソッド）

> **ソース**: `app/rtk_tools/command_dispatcher.py`

| メソッド | 行 | 説明 | シグネチャ |
|---------|-----|------|-----------|
| `arm_all()` | 48 | 全指定ドローンに ARM (cmd=400, param1=1) | `arm_all(system_ids=None, component_id=1)` |
| `disarm_all()` | 51 | 全指定ドローンに DISARM (cmd=400, param1=0) | `disarm_all(system_ids=None, component_id=1)` |
| `takeoff_all()` | 54 | 全指定ドローンに TAKEOFF (cmd=22, param7=altitude) | `takeoff_all(altitude, system_ids=None, component_id=1)` |
| `land_all()` | 57 | 全指定ドローンに LAND（個別 `land()` をループ呼出） | `land_all(system_ids=None, component_id=1, descent_rate=None)` |
| `arm()` | 111 | 単機 ARM（MODE GUIDED → 0.3s 後 ARM） | `arm(system_id, component_id)` |
| `disarm()` | 127 | 単機 DISARM (cmd=400, param1=0) | `disarm(system_id, component_id)` |
| `takeoff()` | 133 | 単機 TAKEOFF (cmd=22) | `takeoff(system_id, component_id, altitude)` |
| `land()` | 139 | 単機 LAND (cmd=21) | `land(system_id, component_id, descent_rate)` |
| `force_arm()` | 75 | 強制 ARM（ARMING_CHECK=0 → 0.5s 後 ARM） | `force_arm(system_id, component_id)` |
| `restore_arm_params()` | 101 | ARMING_CHECK/FS_THR_ENABLE/AHRS_EKF_TYPE 復元 | `restore_arm_params(system_id, component_id)` |

> **重要**: `arm_all`/`disarm_all`/`takeoff_all`/`land_all` は **バックエンドには存在するが REST API エンドポイントが未定義**。本設計では新規エンドポイント追加を提案する（後述 §9.1）。

### 3.3 コマンドパラメータ制約一覧

| コマンド | パラメータ | 型 | 範囲 | デフォルト | ソース |
|---------|-----------|-----|------|-----------|--------|
| Takeoff | `altitude` | float | 0.5 〜 500.0 m | 2.0 | `routes.py:63` |
| Land | `descent_rate` | float | 0.0 〜 20.0 m/s | 0.5 | `routes.py:67` |
| Guided Position | `north`, `east`, `down` | float | 制約なし (Pydantic) | 0, 0, -5.0 | `routes.py:71-73` |
|  | `yaw` | float | -180.0 〜 180.0° | 0 | `routes.py:74` |
| Guided Velocity | `vx`, `vy`, `vz` | float | -20.0 〜 20.0 m/s | 0 | `routes.py:78-80` |
|  | `yaw` | float | -180.0 〜 180.0° | 0 | `routes.py:81` |

### 3.4 接続管理

| エンドポイント | 内部処理 | ソース |
|---------------|---------|--------|
| `POST /api/connect` | TelemetryStore → MavlinkConnection → CommandDispatcher → MessageRouter(thread) → REQUEST_DATA_STREAM(5Hz) → RtcmReader+RtcmInjector(thread) | `routes.py:122-177` |
| `POST /api/disconnect` | RtcmReader.stop() → MessageRouter.stop() → MavlinkConnection.stop() → グローバル参照クリア | `routes.py:210-237` |

---

## 4. レイアウト設計

### 4.1 全体構成

```
┌──────────────────────────────────────────────────────────────────────┐
│  [WebSocket ● Connected]  [Backend: Connected]    All Systems Nominal│ ← ステータスバー
├──────────────────────────────────────────────────────────────────────┤
│  ⚠ ALERT: Drone-2 GPS Fix Lost (0sats), Drone-4 Battery 18%         │ ← アラートバー
├──────────────┬──────────────┬──────────────┬──────────────────────────┤
│  DRONE 1     │  DRONE 2     │  DRONE 3     │  DRONE 4                │
│  [ARMED ●]   │  [DISARMED ○]│  [ARMED ●]   │  [OFFLINE]              │
│  GUIDED      │  LOITER      │  LAND        │  --                     │
│              │              │              │                         │
│  🔋 11.5V    │  🔋 10.8V    │  🔋 11.9V    │  🔋 --                  │
│  ████░░ 72%  │  ██░░░ 38%   │  █████ 88%   │  ░░░░░ --              │
│              │              │              │                         │
│  🛰 RTK FIXED│  🛰 3D_FIX   │  🛰 DGPS     │  🛰 --                  │
│  ▲ 12.5m     │  ▲ 8.2m      │  ▲ 0.3m      │  ▲ --                  │
│  18 sats     │  12 sats     │  8 sats      │  --                    │
│              │              │              │                         │
│  [Land ⏹]    │  [Land ⏹]    │  [Land ⏹]    │  [--]                  │
├──────────────┴──────────────┴──────────────┴──────────────────────────┤
│  📡 RTK Base: Connected | Msgs: 1234 | Reconnects: 0                 │
├──────────────────────────────────────────────────────────────────────┤
│  [🔓 ARM ALL] [🔒 DISARM ALL] [🚀 TAKEOFF ALL(alt:10m)] [🛬 LAND ALL]│
│  [Connect Backend] [Disconnect]                                       │
└──────────────────────────────────────────────────────────────────────┘
```

### 4.2 CSS Grid 実装：固定 4 カラム

```css
/* マルチドローンダッシュボード: 固定4カラム看板レイアウト */
.multi-drone-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 12px;
    align-items: start;
    width: 100%;
}

/* 各ドローンカード */
.drone-card {
    background: #16213e;
    border-radius: 10px;
    padding: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.35);
    border: 2px solid #0f3460;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-height: 420px; /* カードの一貫した高さ */
    transition: border-color 0.3s, opacity 0.3s;
}

/* Armed ドローン: 緑ボーダーで強調 */
.drone-card.armed {
    border-color: #2ecc71;
    box-shadow: 0 0 20px rgba(46, 204, 113, 0.15);
}

/* オフラインドローン: グレーアウト */
.drone-card.offline {
    opacity: 0.45;
    filter: grayscale(60%);
    border-color: #333;
}

/* 空き枠: プレースホルダー */
.drone-card.placeholder {
    opacity: 0.25;
    border-style: dashed;
    border-color: #0f3460;
    display: flex;
    align-items: center;
    justify-content: center;
}
```

### 4.3 レスポンシブ対応

---

## 5. ドローンカード詳細設計

### 5.1 カード内要素の優先度分類

```
┌──────────────────────────┐
│  DRONE 1        [sysid] │ ← ヘッダー（SysID + 接続ランプ）
├──────────────────────────┤
│     【最重要エリア】       │
│   ┌──────────────────┐   │
│   │   ● ARMED        │   │ ← Armed バッジ（大型 24px）
│   │   GUIDED         │   │ ← Flight Mode（18px）
│   └──────────────────┘   │
│                          │
│     【重要エリア】         │
│   🔋 11.5V  ████░░ 72%  │ ← バッテリーゲージ
│   🛰 RTK_FIXED           │ ← GPS Fix 種別
│   ▲ 12.5m                │ ← 高度
│                          │
│     【補足エリア】         │
│   18 sats  HDOP 0.55     │ ← 衛星数 + HDOP
│   35.1234, 139.5678      │ ← 座標（省略表示）
│                          │
│     【制御エリア】         │
│   [🛬 EMERGENCY LAND]     │ ← 緊急着陸（個別、赤）
├──────────────────────────┤
│  ACK: LAND acked         │ ← コマンドACK フィードバック
└──────────────────────────┘
```

### 5.2 最重要エリア：Armed バッジ + Flight Mode

| 状態 | バッジ表示 | 色 | CSS クラス |
|------|-----------|-----|-----------|
| Armed | **● ARMED** | 緑 `#2ecc71` | `status-ok` |
| Disarmed | **○ DISARMED** | 橙 `#f39c12` | `status-warn` |
| Offline | **◎ OFFLINE** | 灰 `#666` | `status-neutral` |

```html
<div class="armed-badge-wrap">
    <span class="armed-badge-large status-ok">● ARMED</span>
</div>
<div class="mode-display">
    <span class="mode-label">FLIGHT MODE</span>
    <span class="mode-value">GUIDED</span>
</div>
```

```css
.armed-badge-large {
    display: inline-block; padding: 10px 28px; border-radius: 8px;
    font-size: 24px; font-weight: 900; letter-spacing: 2px;
    text-transform: uppercase; transition: all 0.3s;
}
.armed-badge-large.status-ok {
    background: rgba(46, 204, 113, 0.2); border: 3px solid #2ecc71;
    color: #2ecc71; box-shadow: 0 0 20px rgba(46, 204, 113, 0.3);
    animation: armed-glow 2s infinite;
}
.armed-badge-large.status-warn {
    background: rgba(243, 156, 18, 0.2); border: 3px solid #f39c12;
    color: #f39c12;
}
.armed-badge-large.status-neutral {
    background: rgba(100, 100, 100, 0.15); border: 3px solid #555;
    color: #666;
}
```

### 5.3 バッテリーゲージ（コンパクト表示）

```html
<div class="battery-compact">
    <span class="battery-voltage">11.5V</span>
    <div class="battery-gauge-mini">
        <div class="battery-gauge-fill-mini green" style="width:72%"></div>
    </div>
    <span class="battery-pct">72%</span>
</div>
```

```css
.battery-compact { display: flex; align-items: center; gap: 6px;
    padding: 6px 10px; background: #0f0f23; border-radius: 6px; }
.battery-gauge-mini { flex: 1; height: 14px; background: #1a1a2e;
    border-radius: 7px; overflow: hidden; border: 1px solid #0f3460; }
.battery-gauge-fill-mini { height: 100%; border-radius: 6px;
    transition: width 0.6s ease; }
.battery-gauge-fill-mini.green  { background: linear-gradient(90deg, #27ae60, #2ecc71); }
.battery-gauge-fill-mini.yellow { background: linear-gradient(90deg, #d35400, #f39c12); }
.battery-gauge-fill-mini.red    { background: linear-gradient(90deg, #c0392b, #e74c3c); }
```

### 5.4 GPS Fix バッジ + 高度

```html
<div class="gps-compact">
    <span class="gps-fix-badge status-ok">RTK_FIXED</span>
    <span class="gps-altitude">▲ 12.5m</span>
</div>
<div class="gps-supplement">
    <span>📡 18 sats</span><span>HDOP 0.55</span>
    <span class="gps-coords-small">35.1234, 139.5678</span>
</div>
```

### 5.5 緊急着陸ボタン

```html
<button class="btn-emergency-land" onclick="emergencyLandDrone(1)">
    🛑 EMERGENCY LAND
</button>
```

```css
.btn-emergency-land {
    width: 100%; padding: 12px; border-radius: 8px;
    background: linear-gradient(135deg, #e74c3c, #c0392b);
    color: #fff; border: 2px solid #e74c3c;
    font-size: 15px; font-weight: 900; cursor: pointer;
    animation: emergency-pulse 1.5s infinite;
}
@keyframes emergency-pulse {
    0%, 100% { box-shadow: 0 0 8px rgba(231, 76, 60, 0.3); }
    50% { box-shadow: 0 0 22px rgba(231, 76, 60, 0.5); }
}
.drone-card:not(.armed) .btn-emergency-land {
    opacity: 0.4; pointer-events: none; animation: none;
}


### 5.6 カード描画 JavaScript

```javascript
function renderDroneCard(systemId, droneData) {
    const isOnline = droneData !== null;
    const hb = isOnline ? (droneData.heartbeat || {}) : null;
    const bat = isOnline ? (droneData.battery || {}) : null;
    const gps = isOnline ? (droneData.gps || {}) : null;

    return `<div class="drone-card ${isOnline ? (hb.armed ? 'armed' : '') : 'offline'}">
        <div class="card-header">
            <span class="drone-label">DRONE ${systemId}</span>
            <span class="conn-dot ${isOnline ? 'on' : 'off'}"></span>
        </div>
        <div class="armed-badge-wrap">
            <span class="armed-badge-large ${armedColorClass(hb, isOnline)}">
                ${isOnline ? (hb.armed ? '● ARMED' : '○ DISARMED') : '◎ OFFLINE'}
            </span>
        </div>
        <div class="mode-value">${isOnline ? hb.mode : '--'}</div>
        ${isOnline ? renderBatteryRow(bat) : '<div class="battery-compact offline">🔋 --</div>'}
        ${isOnline ? renderGpsRow(gps) : '<div class="gps-compact offline">🛰 --</div>'}
        <button class="btn-emergency-land" ${isOnline && hb.armed ? '' : 'disabled'}
                onclick="emergencyLandDrone(${systemId})">
            ${isOnline && hb.armed ? '🛑 EMERGENCY LAND' : '--'}
        </button></div>`;
}

function renderAllCards(dronesData) {
    const grid = document.getElementById('multi-drone-grid');
    const MAX_SLOTS = 4;
    let html = '';
    for (let i = 1; i <= MAX_SLOTS; i++) {
        html += renderDroneCard(i, dronesData[String(i)] || null);
    }
    grid.innerHTML = html;
}
```

---

## 6. アラートバーの設計

### 6.1 概要

全ドローンの異常を集約し、上部固定バーに表示。異常がなければ緑で `All Systems Nominal`。

### 6.2 異常検出条件

| 異常種別 | 検出条件 | 深刻度 | アラート文言例 |
|---------|---------|--------|-------------|
| 接続切断 | `heartbeat` が null | 🔴 CRITICAL | `Drone-2 connection lost` |
| バッテリー低下 | `remaining < 25`（かつ >=0） | 🟠 WARNING | `Drone-4 Battery 18%` |
| GPS Fix 喪失 | `fix_type <= 2` | 🟠 WARNING | `Drone-2 GPS Fix Lost (NO_FIX)` |
| コマンドACK異常 | `last_ack.status === 'failed'` | 🟡 CAUTION | `Drone-3 ARM command failed` |
| HDOP 不良 | `hdop >= 2.0` | 🟡 CAUTION | `Drone-1 HDOP=3.2` |

### 6.3 HTML / CSS

```html
<div id="alert-bar" class="alert-bar alert-ok">
    <span id="alert-icon">✅</span>
    <span id="alert-text">All Systems Nominal</span>
</div>
```

```css
.alert-bar { display: flex; align-items: center; gap: 10px;
    padding: 6px 16px; font-size: 13px; font-weight: bold;
    border-bottom: 2px solid; flex-shrink: 0; min-height: 34px; }
.alert-bar.alert-ok { background: rgba(46,204,113,0.1); border-color: #2ecc71; color: #2ecc71; }
.alert-bar.alert-warn { background: rgba(243,156,18,0.15); border-color: #f39c12; color: #f39c12; }
.alert-bar.alert-critical { background: rgba(231,76,60,0.2); border-color: #e74c3c; color: #e74c3c;
    animation: alert-flash 0.5s infinite; }
@keyframes alert-flash { 0%,100%{opacity:1} 50%{opacity:0.7} }
```

### 6.4 JavaScript

```javascript
function updateAlertBar(dronesData) {
    const alerts = [];
    for (const [sysid, drone] of Object.entries(dronesData)) {
        const hb = drone.heartbeat, bat = drone.battery;
        const gps = drone.gps, cmd = drone.command_state;

        if (!hb || hb.mode === 'N/A') {
            alerts.push({ level: 'critical', msg: `Drone-${sysid} connection lost` });
            continue;
        }
        if (bat && bat.remaining !== null && bat.remaining < 25)
            alerts.push({ level: 'warning', msg: `Drone-${sysid} Battery ${bat.remaining}%` });
        if (gps && gps.fix_type >= 0 && gps.fix_type <= 2)
            alerts.push({ level: 'warning', msg: `Drone-${sysid} GPS ${gps.fix_name}` });
        if (gps && gps.hdop !== null && gps.hdop >= 2.0)
            alerts.push({ level: 'caution', msg: `Drone-${sysid} HDOP=${gps.hdop}` });
        if (cmd && cmd.last_ack &&
            (cmd.last_ack.status === 'failed' || cmd.last_ack.status === 'timeout'))
            alerts.push({ level: 'caution',
                msg: `Drone-${sysid} ${cmd.last_ack.command} ${cmd.last_ack.status}` });
    }

    const bar = document.getElementById('alert-bar');
    const icon = document.getElementById('alert-icon');
    const text = document.getElementById('alert-text');
    if (alerts.length === 0) {
        bar.className = 'alert-bar alert-ok';
        icon.textContent = '✅'; text.textContent = 'All Systems Nominal';
    } else {
        const maxLevel = alerts.some(a => a.level === 'critical') ? 'critical' :
                         alerts.some(a => a.level === 'warning') ? 'warning' : 'caution';
        bar.className = `alert-bar alert-${maxLevel === 'caution' ? 'warn' : maxLevel}`;
        icon.textContent = maxLevel === 'critical' ? '🔴' : '⚠️';
        text.textContent = alerts.map(a => a.msg).join(' | ');
    }
}
```

---

## 7. RTK 基地局表示

カードグリッドの下部に細いバーで常時表示。

```html
<div id="rtk-bar" class="rtk-bar">
    <span class="rtk-label">📡 RTK Base</span>
    <span id="rtk-status-text">Disabled</span> |
    <span>Messages: <span id="rtk-msgs">0</span></span> |
    <span>Reconnects: <span id="rtk-reconns">0</span></span>
</div>
```

```css
.rtk-bar { display: flex; align-items: center; gap: 10px; padding: 5px 16px;
    background: #0f0f23; border-top: 1px solid #0f3460; font-size: 11px; color: #aaa; }
.rtk-label { color: #e67e22; font-weight: bold; }
```

---

## 8. 一斉制御 + 個別制御

### 8.1 一斉制御パネル（下部）

```html
<div id="broadcast-panel" class="broadcast-panel">
    <div class="broadcast-label">📢 ALL DRONES</div>
    <button class="btn btn-arm" onclick="broadcastCmd('arm')">🔓 ARM ALL</button>
    <button class="btn btn-disarm" onclick="broadcastCmd('disarm')">🔒 DISARM ALL</button>
    <input type="number" id="takeoff-all-alt" value="10" min="0.5" max="500" step="0.5">
    <button class="btn btn-takeoff" onclick="broadcastCmd('takeoff')">🚀 TAKEOFF ALL</button>
    <button class="btn btn-land" onclick="broadcastCmd('land')">🛬 LAND ALL</button>
    <button class="btn btn-connect">🟢 Connect</button>
    <button class="btn btn-disconnect">🔴 Disconnect</button>
</div>
```

```css
.broadcast-panel { background: #16213e; border-radius: 10px; padding: 12px 16px;
    border: 2px solid #e67e22; display: flex; align-items: center;
    gap: 12px; flex-shrink: 0; flex-wrap: wrap; }
```

### 8.2 JavaScript 制御コード

```javascript
function emergencyLandDrone(systemId) {
    const drone = getTelemetryState().drones[String(systemId)];
    if (!drone) return;
    if (!confirm(`EMERGENCY LAND: Drone ${systemId}?`)) return;
    fetch('/api/land', {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({system_ids:[systemId], component_id:1, descent_rate:1.5})
    }).then(r => r.json());
}

function broadcastCmd(command) {
    const ids = getAllOnlineDroneIds();
    if (ids.length === 0) { alert('No online drones'); return; }
    let body = { system_ids: ids, component_id: 1 };
    if (command === 'takeoff')
        body.altitude = parseFloat(document.getElementById('takeoff-all-alt').value) || 10;
    if (!confirm(`${command.toUpperCase()} ALL: ${ids.length} drones?`)) return;
    fetch(`/api/${command}`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify(body)
    }).then(r => r.json());
}

function getAllOnlineDroneIds() {
    const state = getTelemetryState();
    if (!state || !state.drones) return [];
    return Object.keys(state.drones)
        .filter(id => state.drones[id].heartbeat)
        .map(Number);
}
```

### 8.3 Force Arm 安全対策

- **一斉制御パネルには非配置**（全機一斉 Force Arm は危険すぎる）
- 各ドローンカードの展開メニュー内に格納（個別のみ）
- 二重 `confirm()` ダイアログ必須
- 実行後は `restore_arm_params` の使用を促すアラート表示

---

## 9. 実装上の懸念と提案

### 9.1 一斉制御用 REST エンドポイントの新設（推奨）

`CommandDispatcher` に `arm_all`/`disarm_all`/`takeoff_all`/`land_all` が存在するが REST API エンドポイントがない。`POST /api/broadcast/{arm,disarm,takeoff,land}` を `app/api/routes.py` に追加することを推奨。

```python
@router.post("/broadcast/arm")
async def cmd_arm_all(req: SystemIdsRequest):
    disp = _get_disp()
    disp.arm_all(system_ids=req.system_ids, component_id=req.component_id)
    return {"status":"ok","command":"arm_all","system_ids":req.system_ids}
```

### 9.2 CSS Grid 4カラム固定実装

常に 4 つの `.drone-card` を DOM に配置し、未接続分は `.placeholder` で表示することで左寄せを防止。

### 9.3 更新頻度とパフォーマンス

| 項目 | 頻度 | 方式 |
|------|------|------|
| WebSocket 受信 | 1Hz | `broadcast_loop()` |
| 全カード再描画 | 1Hz | `innerHTML` 一括置換（4カードで ~1ms） |

### 9.4 WebSocket→カード データフロー

```javascript
function onTelemetryUpdate(payload) {
    updateAlertBar(payload.drones);
    renderAllCards(payload.drones);
    updateRtkBar(payload.rtk);
}
```

### 9.5 レスポンシブ対応

```css
@media (max-width: 1400px) { .multi-drone-grid { grid-template-columns: repeat(2, 1fr); } }
@media (max-width: 1000px) { .multi-drone-grid { grid-template-columns: 1fr; } }
```

### 9.6 Force Arm 安全対策

一斉制御パネルには非配置。個別カードの展開メニュー内にのみ配置し二重 confirm 必須。

### 9.7 コマンド ACK フィードバック

`command_state.last_ack.status` で色分け: `acked`→緑, `pending`→黄, `failed/timeout`→赤。

### 9.8 Classic タブとの統合

Multi-Drone タブ（新規）と Classic タブ（既存）を共存。Graph/Raw Data タブは変更不要。

---

## 10. ファイル構成（提案）

```
web/static/
├── index.html                    # 更新: 新タブ追加
├── css/style.css                 # 更新: マルチドローン用CSS追加
└── js/
    ├── websocket.js              # 変更なし
    ├── dashboard.js              # 更新: マルチドローン分岐追加
    ├── multi-drone.js            # 【新規】カード描画 + アラート + 一斉制御
    ├── controls.js               # 更新: 一斉制御 + 緊急着陸
    ├── graph.js                  # 変更なし
    └── rawdata.js                # 変更なし
```

---

## 11. バックエンド変更必要箇所（まとめ）

| # | 変更内容 | ファイル | 優先度 |
|---|---------|---------|--------|
| 1 | `POST /api/broadcast/{arm,disarm,takeoff,land}` 追加 | `app/api/routes.py` | **高** |
| 2 | WebSocket payload に `bytes_received` 追加（任意） | `app/api/websocket.py` | 低 |

---

## 12. 改訂履歴

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2026-06-14 | 1.0.0 | 初版。バックエンド全機能精査に基づくマルチドローン同時表示ダッシュボード設計提案 |
