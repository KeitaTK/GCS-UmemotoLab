# GCS-UmemotoLab Web UI 設計仕様書

> **バージョン**: 2.0.0  
> **最終更新**: 2026-06-13  
> **FastAPI タイトル**: `GCS-UmemotoLab API`

---

## 1. 概要

GCS-UmemotoLab Web UI は、ArduPilot ドローンをブラウザからリアルタイム監視・制御するための Web フロントエンド + REST API + WebSocket 基盤である。バックエンドは FastAPI（Python）で動作し、MAVLink v2 経由で Pixhawk と通信する。

### 1.1 目的

- ドローンのテレメトリ（心拍/バッテリー/GPS/RTK/コマンド状態）をリアルタイム可視化
- REST API によるアーム・離陸・着陸・Guided 制御
- マルチドローン対応（System ID で識別）
- Tailscale 経由での安全なリモートアクセス

### 1.2 設計方針

| 方針 | 説明 |
|------|------|
| **軽量起動** | サーバ起動時にバックエンド接続せず、`POST /api/connect` でオンデマンド接続 |
| **関心の分離** | REST API (`api/server.py`)、コマンド系 (`api/routes.py`)、WebSocket (`api/websocket.py`) をモジュール分割 |
| **シングルバイナリ** | `app/main.py` で Web サーバモードと PySide6 GUI モードを切り替え |
| **ダークテーマ** | 全 UI はダークテーマ (`#1a1a2e` 背景) で統一 |

## 2. アーキテクチャ

```
┌──────────┐     WebSocket / REST      ┌────────────────┐     MAVLink v2 UDP     ┌──────────┐
│  Browser │ ◄──────────────────────► │   FastAPI      │ ◄───────────────────► │ Pixhawk  │
│ (HTML/JS)│     ws://host/ws/telemetry │   (uvicorn)    │   port 14550          │ (ArduPilot│
│          │     http://host/api/*      │  100.95.30.60  │                       │ Copter)  │
└──────────┘                           │   :8000        │                       └──────────┘
       │                                │                │
       │                                │  ┌──────────┐  │
       │  Plotly.js CDN                 │  │Telemetry │  │
       │  (graph rendering)             │  │ Store    │  │
       │                                │  ├──────────┤  │
       │                                │  │Command   │  │
       │                                │  │Dispatcher│  │
       │                                │  ├──────────┤  │
       │                                │  │RTCM      │  │
       │                                │  │Reader    │──┼──► RTCM TCP Source
       │                                │  └──────────┘  │     (127.0.0.1:2101)
       │                                └────────────────┘
```

### 2.1 データフロー

1. **上り（テレメトリ）**: Pixhawk → UDP → `MavlinkConnection` → `MessageRouter` → `TelemetryStore` → WebSocket broadcast → Browser
2. **下り（コマンド）**: Browser → REST API → `CommandDispatcher` → MAVLink encode → UDP → Pixhawk
3. **RTCM 注入**: RTCM TCP Source → `RtcmReader` → `RtcmInjector` → MAVLink `GPS_RTCM_DATA` → UDP → Pixhawk

### 2.2 並行処理モデル（Web サーバモード）

| コンポーネント | 方式 | 説明 |
|---------------|------|------|
| FastAPI サーバ | asyncio (uvicorn) | メインイベントループ |
| MAVLink 受信 | `threading.Thread` | `MessageRouter.run()` でブロッキング受信 |
| RTCM 受信 | `threading.Thread` | `RtcmReader` でブロッキング TCP 受信 |
| WebSocket broadcast | `asyncio.create_task` | 2 系統: legacy 0.5s (2Hz) + enhanced 1s (1Hz) |

---

## 3. ディレクトリ構造

```
GCS-UmemotoLab/
├── app/
│   ├── main.py                  # エントリポイント（Web/GUI 分岐）
│   ├── server.py                # FastAPI サーバ起動スクリプト
│   ├── logging_config.py        # ロギング設定
│   ├── dummy_sitl.py            # SITL モック
│   ├── api/
│   │   ├── __init__.py
│   │   ├── server.py            # FastAPIアプリ定義 + 静的RESTエンドポイント
│   │   ├── routes.py            # コマンド系RESTエンドポイント (/api/connect含む)
│   │   └── websocket.py         # WebSocket (/ws/telemetry) + 1Hz broadcast
│   ├── mavlink/
│   │   ├── __init__.py
│   │   ├── connection.py        # MavlinkConnection (UDP/Serial)
│   │   └── message_router.py    # MessageRouter (MAVLink → TelemetryStore)
│   ├── rtk_tools/
│   │   ├── telemetry_store.py   # TelemetryStore (System ID別メモリ内状態)
│   │   ├── command_dispatcher.py # CommandDispatcher (キューイング+ACK)
│   │   ├── guided_control.py    # GuidedControl (SET_POSITION_TARGET_LOCAL_NED)
│   │   ├── rtcm_reader.py       # RtcmReader (TCP RTCM受信)
│   │   ├── rtcm_injector.py     # RtcmInjector (GPS_RTCM_DATA送信)
│   │   ├── config_loader.py     # 設定ファイルローダー
│   │   └── test_rtcm.py
│   └── ui/
│       ├── main_window.py       # PySide6 GUI (--nativeモード用)
│       └── telemetry_plotter.py
├── web/
│   └── static/
│       ├── index.html           # SPAエントリポイント
│       ├── css/
│       │   └── style.css        # ダークテーマスタイルシート
│       └── js/
│           ├── websocket.js     # WebSocket接続管理 + telemetryState
│           ├── dashboard.js     # Dashboardタブ更新 + ドローンリスト
│           ├── controls.js      # フライトコントロールボタンイベント
│           ├── graph.js         # Plotly.jsリアルタイムグラフ
│           └── rawdata.js       # Raw Dataタブ表示
├── config/
│   ├── gcs.yml                  # デフォルト設定
│   ├── gcs_local.yml            # ローカル開発用
│   ├── gcs_production.yml       # 本番用（SSHトンネル）
│   ├── gcs_multidrone_example.yml
│   └── gcs_multidrone_test.yml
├── docs/
│   └── web-ui-spec.md           # 本書
└── pyproject.toml
```

### 3.1 モジュール間依存関係

```
main.py
  ├── server.py ──► api/server.py ──► FastAPI app
  │                   ├── api/routes.py  (APIRouter, prefix=/api)
  │                   └── api/websocket.py (APIRouter, /ws/telemetry)
  ├── mavlink/connection.py
  ├── mavlink/message_router.py
  ├── rtk_tools/telemetry_store.py
  ├── rtk_tools/command_dispatcher.py
  ├── rtk_tools/guided_control.py
  ├── rtk_tools/rtcm_reader.py
  └── rtk_tools/rtcm_injector.py
```

---

## 4. REST API 全エンドポイント

ベース URL: `http://100.95.30.60:8000`

### 4.1 静的・ヘルスチェック系

| メソッド | パス | リクエスト | レスポンス | 説明 |
|----------|------|-----------|-----------|------|
| `GET` | `/` | — | `text/html` (index.html) | Web UI 本体を返す。`web/static/index.html` が存在すればそれを、なければ `app/web/index.html` を試行。どちらも無ければプレーンテキスト。 |
| `GET` | `/api/health` | — | `{"status":"ok", "drones":[...]}` | サーバ死活 + 接続中ドローン System ID 一覧。バックエンド未初期化時も 200。 |
| `GET` | `/api/status` | — | `{"status":"ok", "server":{...}, "connection":{...}, "drones_connected":N, "drone_ids":[...]}` | 接続状態・パケット統計・ドローン一覧の詳細。バックエンド未接続でも `is_connected:false` で応答。 |

### 4.2 テレメトリ取得系

| メソッド | パス | リクエスト | レスポンス | 説明 |
|----------|------|-----------|-----------|------|
| `GET` | `/api/drones` | — | `{"drones":[{system_id, armed, mode, gps_fix, gps_sats, lat, lon, alt, hdop, battery_voltage, battery_remaining},...]}` | 全ドローンの基本情報一覧。バックエンド未初期化時は 503。 |
| `GET` | `/api/telemetry/{system_id}` | パス: `system_id` (int) | `{"system_id":N, "telemetry":{MSG_TYPE: {...}}}` | 指定ドローンの全 MAVLink メッセージをシリアライズ。`NAMED_VALUE_FLOAT_*` は除外。503/404。 |
| `GET` | `/api/telemetry/{system_id}/{msg_type}` | パス: `system_id` (int), `msg_type` (str) | `{"system_id":N, "message_type":"...", "data":{...}}` | 指定ドローンの特定メッセージタイプのみ取得。503/404。 |

### 4.3 接続管理系

| メソッド | パス | リクエスト | レスポンス | 説明 |
|----------|------|-----------|-----------|------|
| `POST` | `/api/connect` | `{"config_path": "config/gcs.yml"}` (任意) | `{"status":"connected", "connection":{...}, "config_path":"..."}` | バックエンド初期化 + Pixhawk 接続。全コンポーネントを起動。既接続時は 409。 |
| `POST` | `/api/disconnect` | — | `{"status":"disconnected", "errors":[...]}` | 全バックエンドコンポーネント停止 + グローバル参照クリア。未接続時は 400。 |

> **補足**: `POST /api/connect` の内部処理:
> 1. `TelemetryStore()` 生成
> 2. `MavlinkConnection(config_path)` で MAVLink 接続開始
> 3. `CommandDispatcher` + `GuidedControl` 初期化
> 4. `MessageRouter` 開始（テレメトリ受信スレッド）
> 5. データストリーム要求送信（2秒待機後、`REQUEST_DATA_STREAM` で 5Hz 要求）
> 6. `RtcmReader` + `RtcmInjector` 開始（RTCM 有効時）
> 7. `api.server.init_api()` でグローバル参照注入

### 4.4 コマンド系

| メソッド | パス | リクエストボディ | レスポンス | 説明 |
|----------|------|-----------------|-----------|------|
| `POST` | `/api/arm` | `{"system_ids":[1,2], "component_id":1}` | `{"status":"ok", "command":"arm", "system_ids":[...]}` | アーム指示。全選択ドローンに送信。 |
| `POST` | `/api/disarm` | `{"system_ids":[1,2], "component_id":1}` | `{"status":"ok", "command":"disarm", "system_ids":[...]}` | ディスアーム指示。 |
| `POST` | `/api/force_arm` | `{"system_ids":[1,2], "component_id":1, "confirmed":true}` | `{"status":"ok", "command":"force_arm", "system_ids":[...], "warning":"..."}` | 強制アーム。`confirmed:true` 必須（false 時 400）。Pre-arm チェック無効化。 |
| `POST` | `/api/takeoff` | `{"system_ids":[1,2], "component_id":1, "altitude":10.0}` | `{"status":"ok", "command":"takeoff", "altitude":10.0, "results":[...]}` | 離陸指示。非アーム機は `skipped`。`altitude`: 0.5〜500m。 |
| `POST` | `/api/land` | `{"system_ids":[1,2], "component_id":1, "descent_rate":1.5}` | `{"status":"ok", "command":"land", "system_ids":[...], "descent_rate":1.5}` | 着陸指示。`descent_rate`: 0〜20 m/s。 |
| `POST` | `/api/guided/position` | `{"system_ids":[1,2], "component_id":1, "north":0.0, "east":0.0, "down":0.0, "yaw":0.0}` | `{"status":"ok", "command":"guided_position", "system_ids":[...], "position":{...}, "yaw":0.0}` | Guided 位置制御 (NED)。`down` は負値推奨。yaw: -180〜180°。 |
| `POST` | `/api/guided/velocity` | `{"system_ids":[1,2], "component_id":1, "vx":0.0, "vy":0.0, "vz":0.0, "yaw":0.0}` | `{"status":"ok", "command":"guided_velocity", "system_ids":[...], "velocity":{...}, "yaw":0.0}` | Guided 速度制御 (m/s)。各軸 -20〜20 m/s。 |

### 4.5 共通エラーレスポンス

| ステータス | 条件 | レスポンス例 |
|-----------|------|-------------|
| `400` | リクエスト不正（confirmed:false 等） | `{"detail":"Force-arm requires 'confirmed: true'."}` |
| `404` | テレメトリデータなし | `{"error":"No data for system_id=1, type=ATTITUDE"}` |
| `409` | 既に接続済み | `{"status":"error","detail":"Already connected. POST /api/disconnect first."}` |
| `503` | バックエンド未初期化 | `{"error":"Backend not initialized"}` |
| `500` | バックエンド初期化失敗 | `{"status":"error","detail":"..."}` |

---

## 5. WebSocket 仕様

### 5.1 エンドポイント

```
ws://100.95.30.60:8000/ws/telemetry
```

- プロトコル: WebSocket (RFC 6455)
- 接続管理: 複数クライアント同時接続可（`_active_clients: Set[WebSocket]`）
- 切断検知: `WebSocketDisconnect` 例外 + broadcast 失敗時に自動除去

### 5.2 ブロードキャスト

サーバ起動時に 2 系統のブロードキャストタスクが開始される:

| 名称 | 周期 | ファイル | ペイロード形式 |
|------|------|----------|---------------|
| `broadcast_telemetry()` | 0.5s (2Hz) | `api/server.py` | レガシー形式: `{"type":"telemetry", "drones":[...]}` |
| `broadcast_loop()` | 1.0s (1Hz) | `api/websocket.py` | フルペイロード (推奨形式) |

> **実質的な更新レート**: 1Hz（`broadcast_loop` がフルデータを提供）

### 5.3 ペイロード仕様 (1Hz broadcast_loop)

トップレベル構造: `{"type":"telemetry", "timestamp":..., "connection":{...}, "drones":{sysid:{...}}, "rtk":{...}}`

以下、各サブオブジェクトのフィールド詳細を示す。

#### connection
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `is_connected` | bool | MAVLink 接続状態 |
| `type` | string | 接続種別 (`udp`, `serial`, `unknown`, `error`) |
| `packets_received` | int | 受信パケット総数 |
| `packet_loss` | int | 損失パケット数 |
| `last_error` | string\|null | 最終エラー |

#### drones.{sysid}.heartbeat / system_state
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `armed` | bool | アーム状態 |
| `mode` | string | フライトモード名 |
| `base_mode` | int | MAVLink base_mode |
| `custom_mode` | int | MAVLink custom_mode |

#### drones.{sysid}.battery
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `voltage` | float\|null | 電圧 (V) |
| `current` | float\|null | 電流 (A) |
| `remaining` | int\|null | 残量 (%, -1ならnull) |

#### drones.{sysid}.gps
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `fix_type` | int | GPS fix 種別 (0〜8) |
| `fix_name` | string | fix 種別名 |
| `satellites` | int | 捕捉衛星数 |
| `lat` | float\|null | 緯度 (deg, 小数点7桁) |
| `lon` | float\|null | 経度 (deg, 小数点7桁) |
| `alt` | float\|null | 高度 (m) |
| `hdop` | float\|null | 水平精度低下率 (m) |

#### drones.{sysid}.command_state
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `pending_count` | int | 未完了コマンド数 |
| `last_ack` | object\|null | `{"command":"説明","status":"acked/failed/timeout"}` |

#### rtk
| フィールド | 型 | 説明 |
|-----------|-----|------|
| `enabled` | bool | RTCM 有効/無効 |
| `messages_received` | int | RTCM 受信数 |
| `connections` | int | 接続回数 |
| `reconnects` | int | 再接続回数 |

### 5.4 GPS Fix Type 一覧

| fix_type | fix_name | 説明 |
|----------|----------|------|
| 0 | `NO_GPS` | GPS なし |
| 1 | `NO_FIX` | Fix 未確定 |
| 2 | `2D_FIX` | 2D Fix |
| 3 | `3D_FIX` | 3D Fix |
| 4 | `DGPS` | DGPS |
| 5 | `RTK_FLOAT` | RTK Float |
| 6 | `RTK_FIXED` | RTK Fixed |
| 7 | `STATIC` | 静的測位 |
| 8 | `PPP` | PPP |

### 5.5 フライトモード一覧

| custom_mode | モード名 | custom_mode | モード名 |
|-------------|---------|-------------|---------|
| 0 | STABILIZE | 14 | SPORT |
| 1 | ACRO | 16 | BRAKE |
| 2 | ALT_HOLD | 17 | THROW |
| 3 | AUTO | 18 | AVOID_ADSB |
| 4 | GUIDED | 19 | GUIDED_NOGPS |
| 5 | LOITER | 20 | SMART_RTL |
| 6 | RTH | 21 | FLOWHOLD |
| 7 | CIRCLE | 22 | FOLLOW |
| 9 | LAND | 23 | ZIGZAG |
| 10 | OPTFLOW | 24 | SYSTEMID |
| 11 | POSHOLD | 25 | AUTOROTATE |
| 13 | AUTO_TUNE | 26 | AUTO_RTL |


---

## 6. フロントエンド仕様

### 6.1 技術スタック

| 技術 | 用途 |
|------|------|
| HTML5 | 構造 (SPA) |
| CSS3 | ダークテーマスタイル |
| Vanilla JavaScript (ES5/ES6) | クライアントロジック（フレームワーク不使用） |
| Plotly.js 2.32.0 (CDN) | グラフ描画 |
| WebSocket API | リアルタイムデータ受信 |
| Fetch API | REST API 通信 |

### 6.2 画面構成

```
+------------+-----------------------------------------+
|  Sidebar   |  WebSocket Status Bar                   |
|  (250px)   +-----------------------------------------+
|            |  [Dashboard] [Graph] [Raw Data]         |
|  Drones    +-----------------------------------------+
|  +-------+ |                                         |
|  |   1   | |  Backend Connection [Connect][Disconnect]|
|  |   2   | |  Connection Status                      |
|  +-------+ |  System Status                          |
|  |Sel All| |  Battery Status                         |
|  | Clear | |  GPS Status                             |
|  +-------+ |  RTK Status                             |
|            |  Command Status                         |
|            |  Flight Control                         |
+------------+-----------------------------------------+
```

### 6.3 タブ構成

| タブ | ID | パネルID | 内容 |
|------|-----|----------|------|
| Dashboard | `tab-dashboard` | `panel-dashboard` | 接続/システム/バッテリー/GPS/RTK/コマンド/フライト制御 |
| Graph | `tab-graph` | `panel-graph` | Plotly.js バッテリー電圧 + GPS高度グラフ |
| Raw Data | `tab-raw` | `panel-raw` | 選択ドローンの全テレメトリ JSON 表示 |

タブ切り替え: `switchTab(tabName)` (index.html インライン)。Graph/Rawタブは非アクティブ時更新スキップ。

### 6.4 データフロー（フロントエンド）

```
WebSocket (/ws/telemetry)
    |
    v
websocket.js: telemetryState に格納
    |
    +--> dashboard.js: updateDashboard()
    |       +-- updateDroneList()
    |       +-- updateConnectionStatus()
    |       +-- updateSystemStatus()
    |       +-- updateBatteryStatus()
    |       +-- updateGpsStatus()
    |       +-- updateRtkStatus()
    |       +-- updateCommandStatus()
    |
    +--> graph.js: updateGraphs()  <- タブアクティブ時のみ
    |       +-- Battery Voltage (MAX_POINTS=60)
    |       +-- GPS Altitude (MAX_POINTS=60)
    |
    +--> rawdata.js: updateRawData() <- タブアクティブ時のみ
```

#### ドローン選択ロジック

- クリック → 単一選択
- Ctrl/Cmd+クリック → 複数選択トグル
- `Select All` / `Clear` ボタン
- `getSelectedSystemId()`: 先頭選択 ID（Dashboard 表示用）
- `getSelectedSystemIds()`: 全選択 ID（コマンド送信用）

### 6.5 色分けルール

#### 4 状態クラス

| クラス | 色 | 用途 |
|--------|-----|------|
| `status-ok` | `#2ecc71` (緑) | 正常（接続中、アーム中、RTK Fixed、ACK成功） |
| `status-warn` | `#f39c12` (橙) | 警告（再接続中、3D/DGPS Fix、ACK待ち） |
| `status-error` | `#e74c3c` (赤) | エラー（切断、ディスアーム、No Fix、ACK失敗） |
| `status-neutral` | `#888` (灰) | 未確定（N/A、初期値） |

#### GPS Fix 色分け

| Fix Type | クラス | 色 |
|----------|--------|-----|
| >= 5 (RTK_FLOAT以上) | `status-ok` | 緑 |
| 3~4 (3D_FIX, DGPS) | `status-warn` | 橙 |
| 0~2 | `status-error` | 赤 |

#### バッテリー残量 色分け

| 残量 | クラス | 色 |
|------|--------|-----|
| >= 20% | `status-ok` | 緑 |
| < 20% | `status-error` | 赤 |

#### HDOP 色分け

| HDOP | クラス | 色 |
|------|--------|-----|
| < 1.0m | `status-ok` | 緑 |
| >= 1.0m | `status-warn` | 橙 |

### 6.6 WebSocket ステータスバー

| 状態 | ドット色 | テキスト | CSSクラス |
|------|---------|---------|-----------|
| 接続中 | 緑 (点灯) | `Connected` | `connected` |
| 切断 | 赤 (点灯) | `Disconnected` | `disconnected` |
| 再接続中 | 橙 (pulse点滅) | `Reconnecting... (n/10)` | `reconnecting` |

再接続: 指数バックオフ `min(5000 * 2^n, 60000)`ms、最大10回。

### 6.7 フライトコントロールパネル

全ボタンは選択ドローンに対して動作。

| ボタン | ID | API | パラメータ |
|--------|-----|-----|-----------|
| Arm | `btn-arm` | `POST /api/arm` | `system_ids`, `component_id:1` |
| Disarm | `btn-disarm` | `POST /api/disarm` | 同上 |
| Force Arm | `btn-force-arm` | `POST /api/force_arm` | + `confirmed:true` (confirm必須) |
| Takeoff | `btn-takeoff` | `POST /api/takeoff` | + `altitude` (default 10m) |
| Land | `btn-land` | `POST /api/land` | + `descent_rate` (default 1.5m/s) |
| Send Position | `btn-guided-position` | `POST /api/guided/position` | + `north/east/down/yaw` |
| Send Velocity | `btn-guided-velocity` | `POST /api/guided/velocity` | + `vx/vy/vz/yaw` |

### 6.8 バックエンド接続パネル

| ボタン | ID | API | 動作 |
|--------|-----|-----|------|
| Connect | `btn-connect` | `POST /api/connect` | バックエンド初期化 + Pixhawk接続 |
| Disconnect | `btn-disconnect` | `POST /api/disconnect` | 全バックエンド停止 |

### 6.9 グラフタブ

- ライブラリ: Plotly.js 2.32.0 (CDN: `cdn.plot.ly/plotly-2.32.0.min.js`)
- 起動: `window.load` で初期化。未ロード時 200ms リトライ
- データ保持: MAX_POINTS=60
- X軸: 相対時刻（秒前）
- Graph 1: Battery Voltage (`#graph-container`), オレンジ線 `#e67e22`
- Graph 2: GPS Altitude (`#graph-altitude-container`), 緑線 `#2ecc71`
- テーマ: ダーク (`plot_bgcolor: #16213e`, `paper_bgcolor: #16213e`)

### 6.10 Raw Data タブ

- セクション: `[CONNECTION]`, `[HEARTBEAT]`, `[BATTERY]`, `[GPS]`, `[SYSTEM_STATE]`, `[COMMAND_STATE]`, `[RTK]`
- スクロール位置保存
- 非アクティブ時更新スキップ

---

## 7. セキュリティ

### 7.1 バインドアドレス

- **デフォルト**: `100.95.30.60`（Tailscale IP）
- Tailscale メッシュネットワーク内のデバイスのみアクセス可能

### 7.2 CORS

`app/server.py` で全オリジン許可（開発用設定）:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

> **注意**: 本番環境では `allow_origins` を Tailscale IP に絞ることを推奨。

### 7.3 認証

- 現バージョンでは認証機構なし
- Tailscale MagicDNS + IP バインディングでネットワークレベルアクセス制御
- Force Arm のみブラウザ `confirm()` ダイアログで二重確認

---

## 8. 設定ファイル

### 8.1 設定ファイル優先順位

```
$GCS_CONFIG_PATH (環境変数) > config/gcs.user.local.yml > config/gcs_local.yml > config/gcs.yml
```

### 8.2 config/gcs.yml 項目説明

```yaml
connection_type: serial          # 接続種別: 'udp' または 'serial'
serial_port: /dev/ttyACM0       # シリアルデバイスパス
serial_baudrate: 115200         # シリアルボーレート
udp_listen_port: 14550          # UDP 待受ポート
drones:
  drone1:
    system_id: 1                # MAVLink System ID
    endpoint: "127.0.0.1:14550" # UDP 送信先
rtcm_enabled: true              # RTCM 有効/無効
rtcm_host: 127.0.0.1            # RTCM TCP ソースホスト
rtcm_tcp_port: 2101             # RTCM TCP ソースポート
```

| キー | 型 | デフォルト | 説明 |
|------|-----|-----------|------|
| `connection_type` | string | `serial` | `udp` または `serial` |
| `serial_port` | string | `/dev/ttyACM0` | シリアルデバイスパス |
| `serial_baudrate` | int | `115200` | シリアルボーレート |
| `udp_listen_port` | int | `14550` | UDP 待受ポート |
| `drones.drone1.system_id` | int | `1` | Pixhawk System ID |
| `drones.drone1.endpoint` | string | `127.0.0.1:14550` | 送信先 |
| `rtcm_enabled` | bool | `true` | RTCM 注入の有効/無効 |
| `rtcm_host` | string | `127.0.0.1` | RTCM TCP ホスト |
| `rtcm_tcp_port` | int | `2101` | RTCM TCP ポート |

---

## 9. 起動方法

### 9.1 Web サーバモード（デフォルト）

```bash
# 基本起動（Tailscale IP 100.95.30.60:8000）
uv run python app/main.py

# ホスト・ポート指定
uv run python app/main.py --host 0.0.0.0 --port 8080

# 本番設定ファイル指定
GCS_CONFIG_PATH=config/gcs_production.yml uv run python app/main.py
```

### 9.2 ネイティブ GUI モード（PySide6）

```bash
uv run python app/main.py --native
```

### 9.3 直接 uvicorn 起動（開発用）

```bash
uv run uvicorn app.server:app --host 100.95.30.60 --port 8000 --reload
```

### 9.4 コマンドラインオプション

| オプション | デフォルト | 説明 |
|-----------|-----------|------|
| `--native` | (フラグ) | PySide6 GUI モード（未指定時は Web サーバ） |
| `--host` | `100.95.30.60` | サーババインドアドレス |
| `--port` | `8000` | サーバポート番号 |

### 9.5 起動シーケンス

```
1. app/main.py 起動
2. setup_logging() → ロギング設定
3. uvicorn.run("app.server:app", host, port)
4. FastAPI startup event:
   a. setup_logging()
   b. asyncio.create_task(broadcast_telemetry())  ← 0.5s ループ
   c. asyncio.create_task(broadcast_loop())        ← 1s ループ
5. "=== GCS Web Server started (100.95.30.60:8000) ==="
6. ブラウザで http://100.95.30.60:8000/ → Web UI 表示
7. "Connect" ボタン → POST /api/connect → バックエンド起動 → テレメトリ開始
```

### 9.6 終了シーケンス

```
1. FastAPI shutdown event:
   a. router.stop()      (MessageRouter)
   b. mav_conn.stop()    (MavlinkConnection)
   c. rtcm_reader.stop() (RTCM Reader)
2. "=== Server shutdown complete ==="
```

---

## 10. 静的ファイル配信

| パス | 実体 | MIME |
|------|------|------|
| `/` | `web/static/index.html` | `text/html` |
| `/static/css/style.css` | `web/static/css/style.css` | `text/css` |
| `/static/js/websocket.js` | `web/static/js/websocket.js` | `application/javascript` |
| `/static/js/dashboard.js` | `web/static/js/dashboard.js` | `application/javascript` |
| `/static/js/controls.js` | `web/static/js/controls.js` | `application/javascript` |
| `/static/js/graph.js` | `web/static/js/graph.js` | `application/javascript` |
| `/static/js/rawdata.js` | `web/static/js/rawdata.js` | `application/javascript` |

`/static/*` は `StaticFiles(directory="web/static")` でマウント。

---

## 11. 運用上の注意

1. **バックエンド接続のライフサイクル**: サーバは軽量起動し、`POST /api/connect` でバックエンドを初期化。再起動不要で接続/切断可能。
2. **マルチドローン**: 同一 MAVLink ネットワーク上の全 System ID を自動検出し、サイドバーに表示。
3. **ブラウザ要件**: WebSocket 対応ブラウザ（Chrome/Firefox/Edge/Safari 最新版）。Plotly.js CDN のためインターネット接続が必要。
4. **パフォーマンス**: グラフデータは最大 60 点保持。非アクティブタブは更新スキップ。
5. **デバッグ**: ブラウザ DevTools Console に WebSocket 接続状態・エラーが出力される。

---

## 12. 改訂履歴

| 日付 | バージョン | 変更内容 |
|------|-----------|---------|
| 2026-06-13 | 2.0.0 | 初版。全 API / WebSocket / フロントエンド / アーキテクチャを網羅。 |
