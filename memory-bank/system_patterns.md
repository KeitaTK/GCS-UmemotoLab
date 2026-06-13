# System Patterns — GCS-UmemotoLab

## ディレクトリ構造とその意図

```
GCS-UmemotoLab/
├── app/                    # メインアプリケーションコード
│   ├── main.py             # エントリーポイント（GUI）
│   ├── logging_config.py   # ロギング設定（dictConfig）
│   ├── ui/                 # GUI層（PySide6）
│   ├── mavlink/            # MAVLink通信層
│   ├── rtk_tools/          # 機体制御・RTKツール層
│   └── api/                # REST API層
├── rtk_tools/              # プロジェクトルートのユーティリティ
│   └── config_loader.py    # 設定ファイル解決（app/からも参照）
├── config/                 # 設定ファイル（YAML）
├── tests/                  # テストコード
├── docs/                   # ドキュメント
├── docs_sphinx/            # Sphinxドキュメント生成
├── scripts/                # ビルド・デプロイスクリプト
└── memory-bank/            # Cline Memory Bank
```

### 設計意図
- **レイヤードアーキテクチャ**: UI層（`ui/`）→ 制御層（`rtk_tools/`）→ 通信層（`mavlink/`）の3層構造。上位層が下位層に依存するが、下位層は上位層に依存しない。
- **`rtk_tools/` の2拠点配置**: `app/rtk_tools/` はアプリケーションのコアロジック、`rtk_tools/`（ルート直下）はアプリ外からも利用されるユーティリティ（設定ローダー等）。将来的に統合を検討。
- **`app/` をパッケージとして扱う**: `PYTHONPATH` に `app/` を追加して `from mavlink.connection import ...` のように参照。

## コーディング規約

### ファイル構成
- 1ファイル1クラスを基本とする（`connection.py` = `MavlinkConnection` クラス）
- ユーティリティ関数はクラス外のモジュールレベル関数として定義
- `__init__.py` はパッケージマーカーとして配置（空でも可）

### インポート
- 標準ライブラリ → サードパーティ → プロジェクト内の順でグループ化
- プロジェクト内インポートは `PYTHONPATH` を前提とした絶対インポートを使用
- `main.py` では `sys.path.append()` でルートディレクトリを追加

```python
import sys
import threading
import logging

from pymavlink import mavutil
from PySide6.QtWidgets import QApplication

from mavlink.connection import MavlinkConnection
from rtk_tools.telemetry_store import TelemetryStore
```

### 命名規則

| 種類 | 規則 | 例 |
|------|------|-----|
| クラス名 | PascalCase | `MavlinkConnection`, `MessageRouter` |
| メソッド/関数名 | snake_case | `send_command_long()`, `_parse_mavlink_message()` |
| プライベートメソッド | `_` プレフィックス | `_recv_loop()`, `_handle_command_ack()` |
| 変数名 | snake_case | `telemetry_store`, `mav_conn` |
| 定数 | UPPER_SNAKE_CASE | `LOGGING_CONFIG`, `MAX_RETRIES` |
| ファイル名 | snake_case | `message_router.py`, `telemetry_store.py` |
| 設定キー | snake_case | `connection_type`, `udp_listen_port` |

### ドキュメンテーション
- 日本語の docstring を使用（ユーザー・開発者が日本人）
- 公開メソッドには docstring を必須とする
- 複雑なロジックにはインラインコメントを付与

## エラーハンドリングパターン

### コールバックベースのエラー通知
```python
# MavlinkConnection でエラーを検出し、登録済みコールバックを呼び出す
def _trigger_error_callback(self, error_type: str, message: str):
    self.connection_error = message
    for callback in self.error_callbacks:
        try:
            callback(error_type, message)
        except Exception as e:
            self.logger.error(f"Error callback error: {e}")

# UI 側でコールバックを登録
mav_conn.register_error_callback(self._on_connection_error)
```

### 指数バックオフ再接続
```python
# シリアル接続とRTCM TCP接続の両方で使用
reconnect_delay = 1.0
while True:
    try:
        connect()
        reconnect_delay = 1.0  # 成功時にリセット
    except ConnectionError:
        reconnect_delay = min(reconnect_delay * 1.5, 5.0)
        time.sleep(reconnect_delay)
```


## MAVLinkメッセージ処理パターン

### 受信 → パース → ルーティング → 保存

```
UDP/Serial 受信
    ↓
MavlinkConnection._recv_loop()  → callback(data, addr)
    ↓
MessageRouter._parse_mavlink_message()
    ├── msg.get_type() → メッセージタイプ判別
    ├── COMMAND_ACK  → _handle_command_ack()
    └── 全メッセージ → telemetry_store.update()
```

### コマンド送信 → ACK待機 → リトライ

```
コマンド送信
    ↓
CommandDispatcher._track_command()  → _pending_commands に登録
    ↓
COMMAND_ACK 受信  → 待機解除 + コールバック
    または
5秒タイムアウト → リトライ（最大3回）
    ↓
3回失敗 → timeout コールバック + 削除
```

### RTCM注入フロー

```
RtcmReader (TCP受信)
    ↓ callback(on_rtcm_data)
RtcmInjector.inject(data)
    ├── フレーム分割（RTCM v3）
    └── GPS_RTCM_DATA メッセージ構築
         ↓
send_rtcm_message(frame_data)
    └── MavlinkConnection.send_to_system(1) + send_to_system(2)
```

### 防御的プログラミング
```python
# 型チェックによる安全な分岐（HEARTBEATの例）
if hasattr(hb, 'base_mode'):
    armed = bool(hb.base_mode & 0b10000000)
else:
    self.logger.warning(f"Unexpected heartbeat type: {type(hb)}")
```

### フォールバックチェーン
```python
# pymavlink の新旧API対応
try:
    msgs = self.mav.parse_buffer(data)           # 新API
except (AttributeError, TypeError):
    try:
        msgs = mav.parse_char_array(data)        # 旧API
    except (AttributeError, TypeError):
        msgs = mav.decode(data)                   # 最終手段
```


## テストパターン

### ユニットテスト
- テストファイルは `tests/` 配下に `test_<モジュール名>.py` 形式で配置
- pytest を使用し、モックには `pytest-mock` を利用
- 外部依存（ソケット、シリアル）はモック化

```python
# test_command_retry.py のパターン
def test_track_command_creates_pending_entry():
    dispatcher = CommandDispatcher(mock_connection)
    dispatcher._track_command(system_id=1, command_id=400, ...)
    assert 1 in dispatcher._pending_commands
    assert len(dispatcher._pending_commands[1]) == 1
```

### 統合テスト
- ダミーサーバーを内部起動してテスト
- 実機テストは `test_arm_live.py` のように分離

### テスト命名規則
- `test_<機能名>.py` 形式
- テストメソッドは `test_<検証内容>` 形式
- テストは独立して実行可能であること

## 設定ファイルパターン

### 優先順位（config_loader.py）
```
$GCS_CONFIG_PATH 環境変数  →  最優先
config/gcs.user.local.yml   →  Git管理外（個人設定）
config/gcs_local.yml        →  ローカル開発用
config/gcs.yml              →  デフォルト設定
```

### 設定値の読み取りパターン
```python
connection_type = self.config.get('connection_type', 'udp')
rtcm_enabled = mav_conn.config.get('rtcm_enabled', True)
```

## スレッド管理パターン

### デーモンスレッドの使用
- すべてのバックグラウンドスレッドは `daemon=True` で起動
- メインスレッド終了時に自動的にクリーンアップ

```python
self.recv_thread = threading.Thread(target=self._recv_loop, daemon=True)
threading.Thread(target=request_streams, daemon=True).start()
```

### スレッド間通信
- MAVLink 受信は専用スレッド、UI 更新はメインスレッド
- コールバックでスレッド間のデータ受け渡し
- `TelemetryStore` はスレッドセーフ（dict + ロック）

## ロギングパターン

### 設定（logging_config.py）
- RotatingFileHandler: 5MB x 5世代
- ログレベル: DEBUG（全ハンドラ共通）
- ログファイル: `logs/gcs.log`

### ログレベル指針
- `DEBUG`: 受信メッセージの詳細、内部状態変化
- `INFO`: 接続確立/切断、コマンド送信/ACK受信、GPS Fix状態
- `WARNING`: タイムアウト、再接続試行、パケットロス
- `ERROR`: 接続エラー、パース失敗、コマンド失敗

## 今後の拡張に備えたパターン

### 新機能追加時のチェックリスト
1. `app/` 配下の適切なレイヤーにモジュールを追加
2. 設定が必要な場合は `config/gcs.yml` にキーを追加（デフォルト値付き）
3. UI 変更は `main_window.py` の対応する `_create_*_tab()` メソッドに追加
4. テストは `tests/` 配下に `test_<新機能>.py` を作成
5. ドキュメントは `docs/` に追加、README.md の主要機能一覧を更新

### 新たなドローンタイプの追加
```yaml
# config/gcs.yml に新しいエントリを追加
drones:
  drone2:
    system_id: 2
    endpoint: "192.168.1.100:14550"
    name: "New Drone"
```

### 新たなMAVLinkメッセージタイプの処理
```python
# message_router.py の _parse_mavlink_message() に追加
if msg_type == 'NEW_MESSAGE_TYPE':
    self._handle_new_message_type(system_id, msg)
```
