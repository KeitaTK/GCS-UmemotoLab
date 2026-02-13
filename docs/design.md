# GCSシステム設計（詳細）

## 1. アーキテクチャ概要
Python（PySide6）で作成されたWindows GCSアプリケーションは、UDP経由でMAVLink v2を使用してArduPilotと通信します。アプリケーションは以下を処理します：
- MAVLink 受信/送信
- RTKインジェクション
- テレメトリー集約
- UI表示

### データフロー
1. UDP着信 -> MAVLinkデコーダー -> テレメトリーストア -> UI
2. UIコマンド -> コマンドキュー -> MAVLinkエンコーダー -> UDP発信
3. RTCM TCP -> RTCMチャンカー -> MAVLink GPS_RTCM_DATA -> UDP発信

## 2. モジュールレイアウト
```
app/
  __init__.py
  main.py
  config.py
  logging_config.py
  mavlink/
    __init__.py
    connection.py
    message_router.py
    telemetry_store.py
  rtk/
    __init__.py
    rtcm_reader.py
    rtcm_injector.py
  control/
    __init__.py
    command_dispatcher.py
    guided_control.py
  ui/
    __init__.py
    main_window.py
    widgets.py
  models/
    __init__.py
    drone_state.py
    enums.py
config/
  gcs.yml
```

## 3. 主要クラスと責任
### 3.1 MAVLink
- `MavlinkConnection`（`app/mavlink/connection.py`内）
  - `udpin`と`udpout`エンドポイントを開く
  - 失敗時に再接続
- `MessageRouter`（`app/mavlink/message_router.py`内）
  - メッセージを読み取る
  - テレメトリーストアにディスパッチ
- `TelemetryStore`（`app/mavlink/telemetry_store.py`内）
  - システムIDごとのメモリ内状態
  - スレッドセーフなアクセス（ロック）

### 3.2 RTK
- `RtcmReader`（`app/rtk/rtcm_reader.py`内）
  - TCPソースに接続
  - RTCMバイトをチャンク単位で読み取る
- `RtcmInjector`（`app/rtk/rtcm_injector.py`内）
  - `GPS_RTCM_DATA`に変換
  - ターゲットシステムIDに送信

### 3.3 制御
- `CommandDispatcher`（`app/control/command_dispatcher.py`内）
  - キューベースのコマンド送信
  - 正しいターゲットシステムIDを確保
- `GuidedControl`（`app/control/guided_control.py`内）
  - `SET_POSITION_TARGET_LOCAL_NED`メッセージを構築

### 3.4 UI
- `MainWindow`（`app/ui/main_window.py`内）
  - ドローンをリスト表示
  - アーム、離陸、着陸のボタン
  - 名前付き値のテレメトリーグラフ

### 3.5 モデル
- `DroneState`（`app/models/drone_state.py`内）
  - 最新のハートビート、位置、デバッグ値を保持

## 4. 並行処理モデル
- スレッドA：MAVLink受信ループ（`MessageRouter.run`）`threading.Thread`を使用
- スレッドB：RTCM読み取りループ（`RtcmReader.run`）`threading.Thread`を使用
- メインスレッド：Qt UIイベントループ
- MVPではマルチプロセスは使用しない。CPU負荷は低く、共有状態が必要。

### 同期 vs 非同期
- UDPとTCPのスレッドでブロッキング読み取りを使用。
- スレッド間のUIアクセスを避けるため、Qtシグナル経由でUIを更新。

## 5. エラー処理
- ソケットエラー時は指数バックオフで再接続。
- 不正な形式のMAVLinkパケットをドロップし、エラーをログに記録。
- RTCMソースが利用できない場合は、MAVLink操作を継続。

## 6. 設定の詳細
- `config/gcs.yml`フィールド：
  - `udp.listen_port: 14550`
  - `udp.broadcast: true|false`
  - `drones: { system_id: { ip, port, label } }`
  - `rtcm: { host, port, enabled }`
  - `telemetry: { named_value_filters, log_types }`

## 7. 拡張性
- カスタムMAVLink XML：生成して`third_party/mavlink`に配置。
- `TelemetryStore`をサブスクライブして新しいテレメトリーウィジェットを追加。

## 8. セキュリティ
- クローズドWi-Fiネットワークで動作。
- 外部ネットワークへの露出なし。

## 9. 参考資料
- https://docs.github.com/en/communities/using-templates-to-encourage-useful-issues-and-pull-requests/configuring-issue-templates-for-your-repository
