# GCS 実装機能ドキュメント

**対象**: 現在の GCS 実装 (2026年5月29日)  
**レビュー対象**: 実装済み機能、動作確認状況  
**目的**: 実装の現状把握と機能の整理

---

## 📌 概要

このドキュメントは、GCS-UmemotoLab プロジェクトの **現在実装されている機能** を整理したものです。
各機能について、実装状況、使用方法、現在の制限事項を記載しています。

---

## 🔗 システム全体の構成

### 起動フロー

```
app/main.py (GUI版)
  ├─ config_loader.py        → 設定ファイル読み込み
  ├─ MavlinkConnection        → UDP/Serial接続
  ├─ MessageRouter            → メッセージ受信・ルーティング
  ├─ TelemetryStore           → データ保存
  ├─ RtcmReader               → RTCM TCP受信
  ├─ RtcmInjector             → RTCM→MAVLink変換
  ├─ CommandDispatcher        → コマンド送信
  └─ MainWindow (PySide6)     → GUI表示

app/backend_server.py (ヘッドレス版)
  └─ (同じバックエンド + GUIなし)
```

---

## 🎯 実装済み機能

### 1️⃣ 接続・通信

#### 1.1 UDP接続（マルチドローン対応）

**ファイル**: `app/mavlink/connection.py`

**機能**:
- ポート `14550` でリッスン
- 複数ドローンからの受信を自動識別（System ID ベース）
- 低遅延受信（UDP ブロッキング読み込み）

**使用条件**:
```yaml
# config/gcs.yml
connection_type: udp
udp_listen_port: 14550
drones:
  drone1:
    system_id: 1
    endpoint: "127.0.0.1:14550"
```

**実装状況**: ✅ 動作確認済み

**制限事項**:
- Raspberry Pi 経由の場合、`mavlink-router` が別途必要
- UDP は信頼性なし（再送なし）

---

#### 1.2 シリアル接続（直結ドローン対応）

**ファイル**: `app/mavlink/connection.py`

**機能**:
- `/dev/ttyACM0` など USB/UART での直接接続
- ボーレート設定可能（デフォルト 115200 bps）

**使用条件**:
```yaml
# config/gcs.yml
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
```

**実装状況**: ✅ 実装済み（Raspberry Pi でのテスト未実施）

**制限事項**:
- 1 ドローンのみ対応
- デバイスパスが固定（動的認識なし）

---

### 2️⃣ テレメトリー受信・表示

#### 2.1 HEARTBEAT メッセージ

**ファイル**: `app/mavlink/message_router.py`, `app/mavlink/telemetry_store.py`

**受信内容**:
- System ID
- Component ID
- Base Mode (Armed/Disarmed 状態)
- Custom Mode
- System Status

**UI表示**: ✅ ドローンリストに System ID を表示

**実装状況**: ✅ 動作確認済み

---

#### 2.2 SYS_STATUS メッセージ

**受信内容**:
- バッテリー電圧・電流
- GPS 衛星数
- メモリ使用量
- エラーカウント

**UI表示**: ✅ 実装済み

**実装状況**: ✅ 受信処理・UI表示ともに実装済み

**コード例** (`message_router.py`内):
```python
if message_type == 'SYS_STATUS':
    telemetry_store.update(sysid, 'SYS_STATUS', message)
```

---

#### 2.3 GLOBAL_POSITION_INT メッセージ

**受信内容**:
- GPS 座標（緯度・経度）
- 高度 (MSL)
- 相対高度
- 速度 (東西南北成分)

**UI表示**: ✅ 実装済み

**実装状況**: ✅ 受信処理・UI表示ともに実装済み

---

#### 2.4 NAMED_VALUE_FLOAT メッセージ

**受信内容**:
- カスタム値（任意の浮動小数点値）
- 時間スタンプ
- 値の名前（文字列）

**UI表示**: ✅ UI に表示（テキスト + リアルタイムグラフ）

**実装状況**: ✅ 受信・表示動作確認済み

**UI コード** (`main_window.py`):
```python
self.plotter = TelemetryPlotter(self.telemetry_store)
# 1秒ごとに update_data() で更新
```

**制限事項**:
- UI 上の自由なグラフレイアウト編集は未対応

---

### 3️⃣ コマンド・制御機能

#### 3.1 Arm/Disarm（飛行準備）

**ファイル**: `app/mavlink/command_dispatcher.py`

**機能**:
- `MAV_CMD_COMPONENT_ARM_DISARM` (コマンド ID: 400) を送信
- System ID を指定してターゲットドローンを選択

**UI操作**:
```
1. ドローンリストから対象ドローンを選択
2. [Arm] / [Disarm] ボタンをクリック
3. コマンド送信（ACK 追跡あり）
```

**実装状況**: ✅ 基本実装完了

**コード例**:
```python
dispatcher.arm(system_id=1, component_id=1)     # アーム
dispatcher.disarm(system_id=1, component_id=1)  # ディスアーム
```

**制限事項**:
- 実機の拒否理由に応じた UI ガイダンスは未実装

---

#### 3.2 Takeoff（離陸）

**ファイル**: `app/mavlink/command_dispatcher.py`

**機能**:
- `MAV_CMD_NAV_TAKEOFF` (コマンド ID: 22) を送信
- 離陸高度を指定可能（デフォルト 10m）

**UI操作**:
```
[Takeoff (10m)] ボタン → System ID が選択されている場合に実行
```

**実装状況**: ✅ 基本実装完了

**コード例**:
```python
dispatcher.takeoff(system_id=1, component_id=1, altitude=10.0)
```

**制限事項**:
- 高度の詳細プリセットは未実装

---

#### 3.3 Land（着陸）

**ファイル**: `app/mavlink/command_dispatcher.py`

**機能**:
- `MAV_CMD_NAV_LAND` (コマンド ID: 21) を送信
- 降下率を簡易設定可能

**UI操作**:
```
[Land] ボタン → コマンド送信
```

**実装状況**: ✅ 基本実装完了

**制限事項**:
- 降下率は簡易設定で、機体依存の厳密な制御は未対応

---

#### 3.4 ガイドモード（位置指定飛行）

**ファイル**: `app/mavlink/guided_control.py`

**機能**:
- `SET_POSITION_TARGET_LOCAL_NED` メッセージで位置指定飛行可能
- 相対座標系 (NED: North-East-Down) での指定

**実装状況**: ✅ 実装済み（UI 統合済み）

**コード例**:
```python
guided = GuidedControl(mav_conn)
guided.send_position_target(
    system_id=1,
    north=10.0,      # 北方向 10m
    east=5.0,        # 東方向 5m
    down=-2.0        # 下方向 -2m（上昇 2m）
)
```

**制限事項**:
- 高度なミッション計画連携は未対応

---

### 4️⃣ RTK/RTCM 補正機能

#### 4.1 RTCM TCP 受信

**ファイル**: `app/mavlink/rtcm_reader.py`

**機能**:
- TCP ポート `2101` で RTCM ストリーム受信
- u-center など RTCM 配信ツールからのデータ受け取り

**設定例**:
```yaml
rtcm_enabled: true
rtcm_host: 127.0.0.1
rtcm_tcp_port: 2101
```

**実装状況**: ✅ 動作確認済み

**補足**:
- 切断時は自動再接続し、指数バックオフで再試行する
- 受信統計として接続回数・再接続回数・受信フレーム数を保持する

**使用方法**:
```bash
# u-centerで RTCM ストリーム出力を GCS PC (127.0.0.1:2101) に設定
# GCS が自動的に受信・処理
```

---

#### 4.2 RTCM→MAVLink 変換・送信

**ファイル**: `app/mavlink/rtcm_injector.py`

**機能**:
- RTCM フレームを `GPS_RTCM_DATA` メッセージに変換
- 複数ドローンへのブロードキャスト対応

**実装状況**: ✅ 動作確認済み

**自動動作**:
```python
# main.py 内で自動設定
rtcm_injector.set_send_callback(send_rtcm_message)
rtcm_reader.register_callback(on_rtcm_data)

# RTCM 受信 → Injector → MAVLink GPS_RTCM_DATA → 全ドローンに送信
```

**制限事項**:
- ブロードキャストのみ（ドローン選択不可）
- RTCM フレーム数の詳細な履歴分析は未対応

---

### 5️⃣ ユーザーインターフェース（GUI）

#### 5.1 メインウィンドウ（PySide6/Qt）

**ファイル**: `app/ui/main_window.py`

**UI要素**:

| 要素 | 機能 | 状態 |
|------|------|------|
| ドローンリスト | 接続中のドローン一覧表示 | ✅ 実装 |
| [Update Drone List] ボタン | テスト用リスト更新 | ✅ 実装 |
| [Arm] ボタン | 選択ドローンをアーム | ✅ 実装 |
| [Disarm] ボタン | 選択ドローンをディスアーム | ✅ 実装 |
| [Takeoff (10m)] ボタン | 選択ドローンを 10m 離陸 | ✅ 実装 |
| [Land] ボタン | 選択ドローンを着陸 | ✅ 実装 |
| NAMED_VALUE_FLOAT ラベル | 最新受信値表示 | ✅ 実装 |
| グラフプレースホルダー | リアルタイムグラフ表示 | ✅ 実装 |
| RTK ステータス | RTK 状態表示 | ✅ 実装 |

**実装状況**: ⚠️ 基本機能実装済み、詳細UI未完成

---

#### 5.2 ドローンリスト選択

**動作**:
1. HEARTBEAT 受信時に System ID をリストに追加
2. ユーザーがドローンを選択
3. 制御コマンドはそのドローンへ送信

**実装コード** (`main_window.py`):
```python
def get_selected_system_id(self):
    selected_items = self.drone_list.selectedItems()
    if not selected_items:
        QMessageBox.warning(self, "Warning", "Please select a drone from the list first.")
        return None
    return int(selected_items[0].text())
```

---

#### 5.3 テレメトリー表示（リアルタイム更新）

**タイマー**: 1 秒ごとに `update_label()` を実行

```python
def _setup_timer(self):
    self.timer = QTimer(self)
    self.timer.timeout.connect(self.update_label)
    self.timer.start(1000)  # 1000ms = 1秒
```

**表示内容**:
- 最新の NAMED_VALUE_FLOAT 値
- 受信したドローンの System ID

---

### 6️⃣ ロギング・デバッグ

#### 6.1 ログレベル設定

**ファイル**: `app/logging_config.py`

**実装状況**: ✅ 実装済み

**設定例**:
```python
# ログファイル: gcs.log
# レベル: DEBUG以上をファイルに記録
```

**ログ出力例**:
```
[2026-05-29 15:30:21,123] INFO: GCSアプリケーションが起動しました。
[2026-05-29 15:30:21,456] INFO: 設定ファイルを使用します: config/gcs.yml
[2026-05-29 15:30:22,789] INFO: MessageRouter started.
[2026-05-29 15:30:23,012] INFO: RTCM injection started: enabled=True, source=127.0.0.1:2101
```

---

#### 6.2 コマンド送信ログ

**自動記録**:
```python
# command_dispatcher.py
self.logger.info(f"Sending ARM command to system_id={system_id}, component_id={component_id}")
print(f"[LOG] ARM command sent: system_id={system_id}, component_id={component_id}")
```

---

### 7️⃣ ヘッドレス（サーバー）モード

**ファイル**: `app/backend_server.py`

**機能**:
- GUI なしでバックエンド機能を実行
- Raspberry Pi でのデーモン運用想定
- テレメトリー受信・RTK 補正を継続

**起動方法**:
```bash
python app/backend_server.py
```

**ログ出力**（5 秒ごと）:
```
[...] INFO: Active drones: [1, 2]
[...] INFO:   Drone 1: type=1, armed=True, mode=16
[...] INFO:   Drone 2: type=1, armed=False, mode=0
```

**実装状況**: ✅ 動作確認済み

---

## ⚙️ 設定ファイル

### config/gcs.yml

```yaml
# 接続タイプ
connection_type: serial  # 'udp' または 'serial'

# シリアル接続設定
serial_port: /dev/ttyACM0
serial_baudrate: 115200

# UDP設定（connection_type: udp の場合）
udp_listen_port: 14550
drones:
  drone1:
    system_id: 1
    endpoint: "127.0.0.1:14550"

# RTCM/RTK設定
rtcm_enabled: true
rtcm_host: 127.0.0.1
rtcm_tcp_port: 2101
```

---

## 📊 マトリックス: 実装状況サマリー

| 機能 | 実装 | テスト | UI | 備考 |
|------|------|--------|-----|------|
| **接続** | | | | |
| UDP マルチドローン | ✅ | ✅ | N/A | 動作確認済み |
| シリアル（直結） | ✅ | ❌ | N/A | 実装済み、未テスト |
| **テレメトリー** | | | | |
| HEARTBEAT | ✅ | ✅ | ✅ | ドローンリスト表示 |
| SYS_STATUS | ✅ | ✅ | ✅ | バッテリー/GPS 表示 |
| GLOBAL_POSITION_INT | ✅ | ✅ | ✅ | 位置/高度表示 |
| NAMED_VALUE_FLOAT | ✅ | ✅ | ✅ | テキスト + 複数フィールド比較表示 |
| **制御** | | | | |
| Arm/Disarm | ✅ | ✅ | ✅ | ボタン実装 |
| Takeoff | ✅ | ✅ | ✅ | 高度固定 10m |
| Land | ✅ | ✅ | ✅ | 降下率オプションあり |
| Guided Mode | ✅ | ❌ | ✅ | UI 統合済み |
| **RTK** | | | | |
| RTCM 受信 | ✅ | ✅ | N/A | TCP 2101、自動再接続あり、統計表示あり |
| RTK 注入 | ✅ | ✅ | N/A | ブロードキャスト |
| **その他** | | | | |
| ロギング | ✅ | ✅ | N/A | gcs.log に記録 |
| ヘッドレスモード | ✅ | ✅ | N/A | backend_server.py |

**凡例**:
- ✅ = 実装済み・動作確認済み
- ⚠️ = 部分実装・確認中
- ❌ = 未実装

---

## 🔴 既知の制限事項

### 1. UI の限定性

- グラフ表示は実装済みだが、複数パネルの自由なレイアウト編集は未対応
- 位置情報の地図表示は未対応

### 2. コマンド制御の高度化

- 複数コマンドキューイングの高度な優先度制御は未対応
- GUI からのミッション編集や機体依存の細かい制御は未対応

### 3. テレメトリー表示の遅延

- 1秒ごとの UI 更新（リアルタイム性が限定）
- スレッド間通信でのラグ

### 4. エラーハンドリング

- UDP パケット損失時の再送なし
- シリアル接続エラー時の自動復旧が簡易的
- RTCM ストリーム切断時の自動再接続は実装済みだが、NTRIP 再取得や高度な状態復旧は未対応

### 5. マルチドローン制御

- ドローン選択後の一括送信は対応済みだが、専用のブロードキャスト UI は未整備
- 高度なグループ制御ロジックは未対応
- 同時マルチコマンド実行の厳密な同期は未対応

---

## 🚀 デプロイ・実行

### ローカル (Windows/macOS/Linux)

```bash
# 1. 仮想環境作成
python -m venv .venv
source .venv/bin/activate

# 2. 依存パッケージインストール
pip install -r requirements.txt

# 3. GUI版実行
python app/main.py

# または ヘッドレス版実行
python app/backend_server.py
```

### Raspberry Pi (ラズパイ)

```bash
# SSH ログイン
ssh taki@192.168.11.19

# リポジトリ更新
cd ~/GCS-UmemotoLab
git pull

# ヘッドレス版を実行
cd ~/GCS-UmemotoLab
source .venv/bin/activate
timeout 30 python app/backend_server.py
```

---

## 📚 関連ドキュメント

- **docs/spec.md** - 機能要件の詳細
- **docs/design.md** - システム設計
- **docs/dev_guide.md** - 開発環境構築手順
- **docs/rtk_integration_guide.md** - RTK 機能の詳細
- **README.md** - クイックスタート

---

## 📋 次フェーズの改善提案（参考）

以下は実装後の改善候補です：

1. **UI 強化**
   - グラフ表示機能（matplotlib/pyqtgraph 連携）
   - SYS_STATUS（バッテリー）表示
   - GPS 位置情報の地図表示（Folium など）

2. **コマンド制御の堅牢化**
   - COMMAND_ACK 確認応答処理
   - タイムアウト・リトライ機構
   - コマンドキュー実装

3. **RTK/マルチドローン**
   - ドローン選択式の RTK 注入
   - グループ制御コマンド
   - ブロードキャストメッセージ最適化

4. **テスト自動化**
   - ユニットテスト拡張
   - 実機統合テスト
   - 性能ベンチマーク

---

**作成日**: 2026年5月29日  
**文書バージョン**: 1.0  
**ステータス**: 実装機能レビュー用
