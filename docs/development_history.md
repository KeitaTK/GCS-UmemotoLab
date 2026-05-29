# 開発履歴・トライアンドエラー記録

このファイルは開発中のトライアンドエラー、バグ修正、実験的な変更の履歴を記録します。
正式なリリースノートは別途管理してください。

### 2026-05-29 23:59: [未実装機能の実装拡張]
- **問題**: 実装機能ドキュメントで未実装扱いになっていた UI 表示、ガイドモード、コマンド制御、複数フィールド表示、RTK 状態監視をまとめて実装したかった。
- **調査**: `TelemetryStore` は単一メッセージ保持だったため、NAMED_VALUE_FLOAT の履歴集約が必要だった。`MavlinkConnection` には送信 API がなく、`MainWindow` も単一選択前提だった。
- **試行**: `TelemetryStore` に NAMED_VALUE_FLOAT 履歴を追加し、`TelemetryPlotter` を複数フィールド比較表示へ拡張した。`MavlinkConnection` に `COMMAND_LONG` と `SET_POSITION_TARGET_LOCAL_NED` の送信 API を追加し、`CommandDispatcher` に再送用パラメータ保持・複数選択送信・降下率付き着陸を追加した。`MainWindow` に SYS_STATUS/GLOBAL_POSITION_INT 表示、Takeoff 高度入力、ARM 状態チェック、Land 降下率、Guided 位置/速度制御、RTK 統計表示、複数選択操作を追加した。
- **結果**: コマンド、RTK、テレメトリー、ガイド制御の主要な未実装項目を実装し、既存のコマンド再送/RTK 統合テストも通過した。
- **備考**: 複数パネルの自由レイアウト編集、NTRIP 再取得、厳密なグループ同期制御は今後の改善対象。

### 2026-05-29 23:50: [実装機能ドキュメントの現状反映]
- **問題**: `docs/IMPLEMENTATION_DETAILS.md` に、現在のコードと一致しない未実装表現が残っていた。
- **調査**: `app/mavlink/command_dispatcher.py` では `COMMAND_ACK` の追跡とタイムアウト/リトライがあり、`app/ui/main_window.py` と `app/ui/telemetry_plotter.py` では NAMED_VALUE_FLOAT のグラフ表示が実装済みだった。`app/mavlink/rtcm_reader.py` には再接続処理も追加済みだった。
- **試行**: コマンド ACK、グラフ表示、RTCM 自動再接続、既知の制限事項、実装状況マトリクスを現状に合わせて更新した。
- **結果**: ドキュメントが実装済み機能と未対応機能を正しく区別する内容になった。
- **備考**: UI の自由レイアウト編集や高度な複数コマンド制御は今後の改善候補。

### 2026-05-29 23:30: [RTCM切断復帰の再接続実装]
- **問題**: RTCM ストリームが切断されると `RtcmReader` が再接続せず、RTK 注入が止まる状態だった。
- **調査**: `app/mavlink/rtcm_reader.py` の受信ループでは `recv()` が空データを返すと終了しており、切断後の再接続処理がなかった。`docs/IMPLEMENTATION_DETAILS.md` でも切断時対応が未実装として残っていた。
- **試行**: `RtcmReader` に TCP 再接続ループ、指数バックオフ、接続統計を追加し、`tests/test_rtk_integration.py` に切断後の再接続を検証するテストを追加した。
- **結果**: 切断後も reader が再接続して RTCM フレームを再受信できるようになった。関連ドキュメントの未実装メモも更新した。
- **備考**: NTRIP の再取得や高度な状態復旧は今後の拡張対象。

### 2026-05-29 21:30: [エラーハンドリング実装 - Phase 3-2実装完了] ✅
- **目標**: UDP/Serial の接続エラーを検出・回復し、ユーザーに接続状態を可視化する。
- **実装内容**:
  - **connection.py 拡張** (エラーハンドリングと回復):
    - `error_callbacks`: エラー発生時のコールバック登録システム
    - `register_error_callback(callback)`: コールバック登録メソッド
    - `get_connection_status()`: 接続状態を dict で返す (`is_connected`, `connection_type`, `packet_received`, `packet_loss`, `last_error`)
    - `_trigger_error_callback(error_type, message)`: 登録済みコールバック実行（全callback順序実行保証）
    - UDP タイムアウト検出: `socket.settimeout(5.0)` + 10回連続タイムアウトで UDP_TIMEOUT エラー
    - Serial 自動再接続: exponential backoff (1.0 → 1.5 → 2.25 → 3.375 → 5.0秒 cap、無限ループ防止)
    - パケット損失追跡: `packet_loss_count`, `packet_received_count` カウンター
  - **main_window.py 統合** (UI表示):
    - `connection` パラメータを __init__ に追加
    - Connection Status Group パネル追加 (4ラベル: Status/Type/Packets/Error)
    - `_setup_connection_callbacks()`: error コールバック登録 + エラーダイアログ表示
    - `_update_connection_status_display()`: Connection Status Group 自動更新
    - `update_displays()` に `_update_connection_status_display()` 呼び出し追加
    - エラーダイアログ: CRITICAL/TIMEOUT 時に warning dialog 表示
  - **main.py 統合**:
    - `MainWindow(telemetry_store, dispatcher=dispatcher, connection=mav_conn)` に変更
    - connection インスタンスを UI に渡す
  - **テストスイート作成** (test_connection_errors.py):
    - 19個の包括的テストケース作成:
      - エラーコールバック登録・実行・複数コールバック対応 (6テスト)
      - UDP タイムアウト検出 (1テスト)
      - Serial exponential backoff (2テスト)
      - 接続状態追跡・パケットカウント (3テスト)
      - エラータイプ分類 (3テスト)
      - 接続状態更新 (2テスト)
      - コールバック実行順序・一貫性 (2テスト)
    - テスト構成: `create_temp_config()` で YAML config ファイル自動生成、各テスト独立実行
    - 構文チェック: ✅ PASS (全ファイル)
- **テスト結果**: ✅ **19/19 PASS** (test_connection_errors.py)
- **統合テスト**: ✅ **27/27 PASS** (test_command_retry.py 8 + test_connection_errors.py 19)
- **技術的ハイライト**:
  - Exponential backoff: Serial 接続エラーから自動回復 (無限ループ防止)
  - Callback-based architecture: エラー検出 → UI 通知までの流れを非同期で実行
  - Connection state persistence: パケットカウント・エラーカウント・接続状態を1秒ごと更新
  - 実行順序保証: 複数コールバック登録時の確実な実行順序保証
- **ファイル変更**:
  ```
  app/mavlink/connection.py:       connection state tracking, error callbacks, UDP/Serial recovery
  app/ui/main_window.py:           connection parameter, Connection Status Group UI, error display, key name alignment
  app/main.py:                     pass connection to MainWindow
  tests/test_connection_errors.py: 19 comprehensive test cases (PASS 19/19)
  ```
- **次ステップ**:
  - Raspberry Pi での実機テスト検証
  - 実際のネットワークエラー条件での検証
  - Phase 1-3 (GPS 拡張) または Phase 3-1 (Guided Mode 実機テスト) の実施

### 2026-05-29 21:00: [グラフ化機能実装 - Phase 1-2実装完了]
- **目標**: 複数の NAMED_VALUE_FLOAT テレメトリーをグラフ表示し、データトレンドを可視化する。
- **実装内容**:
  - **main_window.py 大幅リファクタリング**:
    - QTabWidget を導入して 3 つのタブ構造に変更（Dashboard/Graph/Raw Data）
    - `_create_dashboard_tab()`: 既存の System Status/Battery/GPS/Command Status パネルを構成
    - `_create_graph_tab()`: telemetry_plotter.py の TelemetryPlotter をタブに統合
    - `_create_raw_data_tab()`: 選択中のドローンの MAVLink メッセージを JSON 風に表示
    - `update_displays()` に統合：Dashboard/Graph/Raw Data を毎 1 秒更新
    - `update_dashboard()`: テレメトリー更新処理を分離
    - `update_graph()`: plotter.update_data() を呼び出してグラフを自動更新
    - `update_raw_data()`: 受信メッセージの最初の 10 件を表示
  - **UI レイアウト改善**:
    - Window サイズを 1200x800 にデフォルト設定
    - ドローンリストはタブの左にそのまま配置（コンテキスト保持）
    - タブビューが右パネルの大部分を占有（スケーラブル）
    - ScrollArea で各タブの内容をスクロール対応
  - **telemetry_plotter.py の整合性確認**:
    - pyqtgraph での real-time plot 表示対応
    - Drone/Field コンボボックスでフィルタリング機能
    - Clear ボタンでグラフデータリセット
    - 最大 500 ポイント履歴保持
- **構文チェック**: ✅ PASS（2ファイル全て OK）
- **ファイル変更**:
  ```
  ✅ app/ui/main_window.py         (完全リファクタリング: 3 タブ構造導入)
  ✅ app/ui/telemetry_plotter.py   (既に実装済み、整合性確認)
  ```
- **UI 構成**:
  - Tab 1 (Dashboard): System Status・Battery・GPS・Command Status・制御ボタン
  - Tab 2 (Graph): pyqtgraph による real-time 折れ線グラフ（Drone/Field 選択可能）
  - Tab 3 (Raw Data): 選択ドローンのメッセージリスト表示
- **状態**: **実装完全確定、UI 動作テスト待ち**

### 2026-05-29 22:00: [タイムアウト・リトライ機構実装 - Phase 2-2実装完了]
- **目標**: コマンド実行時のタイムアウトを自動検出し、最大 3 回まで自動リトライする機構を実装・検証。
- **実装内容**:
  - **command_dispatcher.py 強化**:
    - `_track_command()` に `component_id` と `params` を保存して、リトライ時の再送信に対応
    - `check_timeouts()` メソッド内でリトライ対象コマンドをリスト化し、ロック外で再送信
    - `_resend_command()` 新規メソッド：タイムアウト時の自動再送信処理
    - リトライ回数 0→1→2→3 で追跡可能
    - 最大リトライ超過後は timeout コールバックを実行して待機リストから削除
  - **main_window.py UI 拡張**:
    - Command Status グループを「Command Status & Retry」に改名
    - 新ラベル `cmd_retry_label` を追加：「Retries: X/3」形式で表示
    - リトライ回数による色分け：0 回=緑、1-2 回=オレンジ、3 回=赤
    - `_update_command_status_display()` でリトライ情報を毎 1 秒更新
  - **test_command_retry.py 作成**:
    - CommandDispatcher のリトライ機能を網羅的にテスト
    - 8 つのテストケース：
      1. `test_track_command_creates_pending_entry`: コマンド追跡の初期化確認
      2. `test_handle_command_ack_accepted`: ACK（result=0）の処理確認
      3. `test_handle_command_ack_denied`: 拒否（result=2）の処理確認
      4. `test_check_timeouts_triggers_retry`: タイムアウト時の自動リトライ確認
      5. `test_check_timeouts_marks_failed_after_max_retries`: 最大リトライ超過時の処理確認
      6. `test_ack_callback_registration`: コールバック登録と実行確認
      7. `test_get_ack_status_string`: MAV_RESULT コード変換確認
      8. `test_multiple_pending_commands`: 複数コマンド同時追跡確認
- **テスト結果**: ✅ 8/8 PASS（pytest 8.4.2）
- **構文チェック**: ✅ PASS（2ファイル OK）
- **ファイル変更**:
  ```
  ✅ app/mavlink/command_dispatcher.py    (リトライ機構強化, _resend_command 追加)
  ✅ app/ui/main_window.py                (リトライ UI 表示機能追加)
  ✅ tests/test_command_retry.py          (新規作成: 8 テストケース)
  ```
- **動作仕様**:
  - コマンド送信 → 5 秒タイムアウト検出 → 自動リトライ
  - リトライ 3 回まで：timeout コールバック実行後も待機継続
  - リトライ 3 回超過 → timeout コールバック実行 → 待機リストから削除
  - UI：リトライ回数をリアルタイム表示、色分け表示で状態を可視化
- **状態**: **実装完全確定、実機テスト待ち**

### 2026-05-29 20:00: [COMMAND_ACK確認応答処理実装 - Phase 2-1実装完了]
- **目標**: コマンド実行時に COMMAND_ACK メッセージを待機し、応答状態を UI に表示する機能を実装。
- **実装内容**:
  - **command_dispatcher.py 大幅拡張**:
    - `_pending_commands` 辞書でコマンド追跡（送信時刻・リトライ回数・状態管理）
    - `handle_command_ack()` メソッドで COMMAND_ACK 受信時に待機コマンド更新
    - `check_timeouts()` メソッドで 5 秒超過コマンドを自動リトライ（最大 3 回）
    - ACK/タイムアウト コールバック登録機構実装
    - `get_pending_commands()` で保留中コマンド一覧取得
    - MAV_RESULT コード（0=ACCEPTED, 2=DENIED, 4=FAILED など）を人間が読める文字列に変換
  - **message_router.py 強化**:
    - CommandDispatcher インスタンスを受け取る設計に変更
    - `_parse_mavlink_message()` メソッドで受信メッセージを MAVLink デコード
    - `_handle_command_ack()` 専用メソッドで COMMAND_ACK を検出→dispatcher に通知
    - 500ms ごとにコマンドタイムアウト自動チェック
  - **main.py 初期化順序改善**:
    - CommandDispatcher → MessageRouter 初期化順序を変更し、MessageRouter で ACK を処理可能に
    - `dispatcher.guided` 初期化を前倒し
  - **main_window.py UI 拡張**:
    - 新グループボックス「Command Status」追加：最後のコマンド名・ACK ステータス・待機中コマンド数を表示
    - `_setup_dispatcher_callbacks()` で ACK コールバック登録
    - ACK ステータスに色分け：ACCEPTED=緑、TIMEOUT/FAILED=赤、その他=オレンジ
    - `_update_command_status_display()` で毎 1 秒更新
- **構文チェック**: ✅ PASS（4ファイル全て OK）
- **ファイル変更**:
  ```
  ✅ app/mavlink/command_dispatcher.py    (大幅拡張: 140行以上追加)
  ✅ app/mavlink/message_router.py        (初期化パラメータ追加, ACK処理実装)
  ✅ app/main.py                          (初期化順序改善)
  ✅ app/ui/main_window.py                (ACK/タイムアウト UI + コールバック統合)
  ```
- **動作仕様**:
  - コマンド送信時に `_track_command()` で内部追跡開始
  - 500ms ごとに timeout チェック→タイムアウト時は自動リトライ
  - COMMAND_ACK 受信で即座に待機コマンド更新→UI 表示更新
  - 最大 3 回リトライしてもタイムアウトなら failure コールバック実行
- **状態**: **実装完全確定、ドローンコマンド送受信テスト待ち**

### 2026-05-29 19:00: [GCS UI強化 - Phase 1-1実装完了・確定版]
- 問題: main_window.py の System Status 表示機能の実装途中で複数回の形式崩れが発生。
- 調査: git checkout で元のバージョンにリセットしてから段階的に改善を加える方針に変更。
- 実装内容:
  - **import 充実**: QGroupBox, QGridLayout を追加
  - **UI パネル追加**: System Status（Armed/Mode）、Battery（電圧・電流・残量）、GPS（衛星数・位置・高度）
  - **update_label 拡張**: テレメトリー表示処理を大幅拡張、SYS_STATUS と GLOBAL_POSITION_INT に対応
  - **ドローン選択時の即座更新**: `_on_drone_selected` メソッド実装、itemSelectionChanged シグナル接続
  - **エラー処理強化**: コマンド送信前に drone 選択確認、詳細ログ出力
- 構文チェック: ✅ PASS（3ファイル全て OK）
- ファイル変更:
  ```
  ✅ app/ui/main_window.py      (完全改善版)
  ✅ app/mavlink/telemetry_store.py  (既に実装済み)
  ✅ app/main.py                (既に実装済み)
  ```
- 状態: **実装完全確定、動作テスト待ち**

### 2026-05-29 18:00: [GCS未実装機能の実装開始 - Phase 1-1完了]
- 問題: GCS の UI が基本的なテレメトリー表示しか対応しておらず、バッテリー・GPS 情報が表示されていなかった。
- 調査: IMPLEMENTATION_DETAILS.md でテレメトリー受信機能は実装済みだが UI 表示が未完成であることを確認。telemetry_store.py の設計を確認し、SYS_STATUS 抽出メソッド追加の必要性を特定。
- 実装内容:
  - **telemetry_store.py**: `get_sys_status()` と `get_global_position()` メソッドを追加（HEARTBEAT と同じパターン）
  - **main_window.py**: SYS_STATUS（バッテリー電圧・電流・残量）、GPS（衛星数・位置・高度）表示用の UI パネル群を追加
  - **main.py**: dispatcher に guided オブジェクトを付与し、UI から Guided Mode を操作可能に


  - **requirements.txt**: pyqtgraph・matplotlib を追加（後続のグラフ化に対応）
- 状態: 
  - ✅ SYS_STATUS（バッテリー）表示: 実装完了
  - ✅ GPS 情報表示: 実装完了
  - ⏳ グラフ化: telemetry_plotter.py 作成済み、UI 統合待ち
  - ⏳ Guided Mode UI: 制御入力フィールド実装済み、テスト待ち
- 次ステップ: Phase 1-2（グラフ化）は telemetry_plotter.py の UI 統合、Phase 2-1（COMMAND_ACK）は command_dispatcher.py 改善

### 2026-04-28 15:35: [docs統合/総合ドキュメント作成]
- 問題: docs 配下の資料が複数に分散しており、入口となる1本の案内がなかった。
- 調査: `docs/project_presentation.md` と各種 RTK/運用ガイドを確認し、情報の重複が大きい一方で参照先が分散していることを確認した。
- 試行: `docs/README.md` を総合ドキュメントとして新規作成し、`docs/project_presentation.md` の案内もそこへ集約した。
- 結果: docs の入口を 1 本化し、まず読むべき資料を明確にした。
- 備考: 詳細な個別資料は補助資料として残している。

### 2026-04-28 15:25: [報告書の一本化]
- 問題: 実装レポートと旧テスト報告書が別ファイルに分かれており、最新の成果物を追いにくかった。
- 調査: `docs/RTK_BASE_STATION_FINAL_REPORT.md` に Phase A/B/C の実装内容がまとまっている一方で、`docs/test_report_20260424.md` に 2026-04-24 の実機・統合テスト結果が残っていた。
- 試行: 旧テスト報告書の内容を `docs/RTK_BASE_STATION_FINAL_REPORT.md` に付録として統合し、`docs/project_presentation.md` の参照先を一本化した。
- 結果: 報告書を 1 本にまとめる構成へ整理できた。
- 備考: 旧ファイル `docs/test_report_20260424.md` は削除する。

### 2026-04-28 15:20: [不要ドキュメント整理]
- 問題: 古いテスト報告書が複数あり、最新版として参照されている資料と役割が重複していた。
- 調査: `docs/test_report.md` はコードベースから参照されておらず、`docs/project_presentation.md` では `docs/test_report_20260424.md` のみが参照されていた。
- 試行: 参照のない旧レポート `docs/test_report.md` を削除した。
- 結果: 現在参照されているテスト報告書だけを残し、資料を整理できた。
- 備考: 後続の整理で `docs/test_report_20260424.md` も一本化対象として削除した。

### 2026-04-28 15:12: [PHASE C-1/RTCM接続先修正]
- 問題: Raspberry Pi 側の RTCM 設定が `127.0.0.1` を指しており、Windows PC 上で起動した `rtk_base_station.py` に接続できなかった。
- 調査: Windows 側の LAN IP を確認したところ `192.168.11.62` だった。Pi 側の `backend_server.py` 起動ログでも `Connection refused` が出ており、接続先不一致が原因と判断した。
- 試行: `config/gcs_local.yml` の `rtcm_host` を `192.168.11.62` に更新した。
- 結果: Pi が Windows 側の基地局へ接続する前提が整った。
- 備考: `backend_server.py` は再起動して設定を読み直す必要がある。

### 2026-04-28 15:10: [RTK基地局/COMポート修正]
- 問題: RTK基地局の実行例とデフォルト設定に COM3 が残っており、実際の接続ポート COM8 と不一致だった。
- 調査: `rtk_base_station.py` の既定値と CLI 引数、`docs/RTK_BASE_STATION_IMPLEMENTATION.md` と `docs/RTK_BASE_STATION_FINAL_REPORT.md` の実行例を確認し、COM3 表記が複数箇所に残存していることを確認した。
- 試行: シリアルポートのデフォルト値とヘルプ文言を COM8 に更新し、関連ドキュメントの実行例も COM8 に統一した。
- 結果: 基地局のコードと文書のポート表記が実機接続に合わせて整合した。
- 備考: 今後は Windows 側の ublox 接続ポートを COM8 前提で案内する。

### 2026-04-28 14:55: [RTK基地局オールインワン化 - Phase A完了]
- 問題: RTK補正データの取得から配信までがシリアル分散されており、統合されていなかった。ublox ← PC（シリアル）→ Raspberry Pi（TCP/WiFi）→ ドローン という構成を一元化する必要があった。
- 調査: 既存の `rtk_rtcp_receiver.py`（NTRIP受信）、`rtk_forwarder_service.py`（サービス化）を確認。PC側でubloxのシリアル受信を一元化するスクリプトが不足していた。
- 試行:
  - `rtk_base_station.py` を新規作成。ubloxからシリアルでRTCM v3フレーム受信し、TCP サーバーで Raspberry Pi へ配信。マルチスレッド構成（SerialReader + TcpServer + UdpBroadcaster）。
  - `test_rtk_base_station_integration.py` を新規作成。ublox シミュレータを使ったローカルテスト、Raspberry Pi 統合確認。
- 結果: 
  - テスト1（ローカル）: ✓ PASS - 92 フレーム受信確認（30秒間、106バイト/フレーム、約3fps）
  - テスト2（Raspberry Pi統合）: 接続確認段階（Raspberry Pi起動待ち）
- 備考: PC 側 RTCMサービスは完成。次は Raspberry Pi 側での受信・ドローン送信の統合テストが必要。

### 2026-04-28 00:15: [RTCM インジェクション検証完了]
- 問題: RTCM インジェクション機能が正常に動作するか、単体テストのみで実装検証が終了していなかった。
- 調査: `tests/test_rtk_integration.py` に 3 つのテストケースが存在: `test_rtcm_reader()`、`test_rtcm_injector()`、`test_rtk_integration()`。各テストはダミーサーバーを内部起動してテストシーケンスを自動検証するユニットテスト。
- 試行: 
  - ローカル環境 (Windows / Python 3.13.7) で全テストを実行 → 3/3 PASS
  - Raspberry Pi 環境 (Linux arm64 / Python 3.11.2) へリポジトリ更新後、全テストを再実行 → 3/3 PASS
- 結果: RTCM Reader、RTCM Injector、RTK 統合動作が両環境で正常に動作することを確認。RTCM データの受信→分割→MAVLink MSG_ID 67 への変換フロー、およびバイトカウント・フレーム統計が正常に機能している。
- 備考: テストはダミーサーバーを使用した局所テストで、実機の Pixhawk との通信テストは別途。次ステップは u-center を使った実 RTCM ストリームの注入テストが必要。

### 2026-04-27 17:30: [RTK/Forwarder Service Integration]
- 問題: NTRIP受信・シリアル受信のスクリプトが分かれており、再接続や設定管理を含む常時運用向けの統合サービスがなかった。
- 調査: 既存の `rtk_rtcp_receiver.py` / `rtk_rtcp_receiver2.py` は手動実行向けで、運用時に引数管理と障害復帰が煩雑になる構成だった。
- 試行: `rtk_forwarder_service.py` を新規作成し、YAML設定で `ntrip` / `serial` ソースを切り替え、UDP転送、定期統計ログ、自動再接続を実装。あわせて `config/rtk_forwarder.yml` と `README.md` に運用手順を追加した。
- 結果: 1つのサービスで基地局データ取得からPC転送までを継続運用できる構成になった。
- 備考: 認証付きNTRIPを使う場合は `config/rtk_forwarder.yml` の `username` / `password` を設定する。

### 2026-04-27 16:40: [RTK/RTCM Receiver Forwarding]
- 問題: 取得したNTRIP/RTCMデータを受信表示するだけで、別PCへストリーム転送する機能が不足していた。
- 調査: `rtk_rtcp_receiver.py` はNTRIP受信のみ、`rtk_rtcp_receiver2.py` はシリアル解析のみで、どちらもネットワーク転送先を指定できなかった。
- 試行: 両スクリプトをCLI引数対応に拡張し、UDP転送先IP/ポートを指定可能にした。NTRIP側はレスポンスヘッダを分離してペイロードのみ転送し、シリアル側はRTCM生データを転送しつつ解析ログを維持した。
- 結果: 2つのスクリプトのどちらからでも、受信した補正データをPCへリアルタイム送信できる運用に改善した。
- 備考: 受信PC側では同じUDPポートで受信待ちを行う必要がある。初期値は `50010` と `50011`。

### 2026-04-27 14:10: [Phase7/運用安定化]
- 問題: Phase 7 長時間テストで `app/backend_server.py` の CPU 使用率が高く、`monitoring.log` の更新が初回のみで継続監視が不足していた。
- 調査: `app/mavlink/message_router.py` に `while self.running: pass` のビジーウェイトがあり、`app/mavlink/connection.py` のシリアル受信ループも無受信時に待機なしで反復していた。監視は `scripts/monitor_backend.sh` があるが定期実行設定がなかった。
- 試行: `message_router.py` に 50ms 待機を追加し、`connection.py` に無受信時 10ms 待機と例外時 50ms 待機を追加。さらに `scripts/setup_monitoring_cron.sh` を新規作成し、`monitor_backend.sh` を 5 分間隔で実行する cron 登録を自動化した。
- 結果: CPU 高負荷の主因だったビジーウェイトを解消し、監視ログの継続収集設定を実施できる状態になった。
- 備考: Raspberry Pi 側で `bash ~/GCS-UmemotoLab/scripts/setup_monitoring_cron.sh` を一度実行して cron を有効化する。

### 2026-04-24 15:10: [実機テスト完了: Pixhawk6C USB接続検証]
- 問題: ローカル SITL テストは成功したが、実機での動作確認が必要だった。
- 調査: Raspberry Pi 上で Pixhawk6C が USB `/dev/ttyACM0` で接続されていることを確認。デバイスログから Pixhawk6C (Holybro) が正常にマウントされていることを検出。
- 試行: 設定ファイル `config/gcs_local.yml` をシリアルモード `/dev/ttyACM0:115200` に更新し、`app/backend_server.py` を起動。
- 結果: 実機 Pixhawk6C からのハートビート受信に成功。5秒間隔で継続的にハートビートを受信し、System ID 1 として正常に認識。接続安定性が確認された。
- 備考: USB 接続により信号の安定性が向上。今後はコマンド送信テスト（ARM/DISARM、離陸、着陸）と RTCM インジェクション検証を実施予定。

### 2026-04-17 16:15: [BackendServer Heartbeat Logging Fix]
- 問題: `app/backend_server.py` 実行中、`telemetry_store.get_heartbeat()` の戻り値が `bytes` のケースで `hb.base_mode` 参照によりクラッシュした。
- 調査: シリアル経路の実行時にHEARTBEAT保持形式がオブジェクト固定ではなく、ログ出力部が型前提で落ちていた。
- 試行: HEARTBEAT状態ログを防御的に変更し、`hasattr(hb, 'base_mode')` で分岐。オブジェクトでない場合は型名のみログ出力するよう修正した。
- 結果: 定期ステータスログが原因の致命的停止を回避でき、RTCM注入検証を継続実行できるようになった。
- 備考: HEARTBEAT保持形式は将来的に `TelemetryStore` 側で統一するのが望ましい。

### 2026-04-17 16:10: [RTK/BackendServer Headless Injection]
- 問題: u-center の `RXM-RTCM` が 0 のままで、ヘッドレス実行時にRTCM注入が確認できなかった。
- 調査: `app/main.py` には `RtcmReader` + `RtcmInjector` が実装されていたが、Raspberry Piで実行している `app/backend_server.py` にはRTCM処理が未実装だった。
- 試行: `app/backend_server.py` にRTCM読取・注入処理を追加し、`rtcm_enabled/rtcm_host/rtcm_tcp_port` を設定ファイルから読んでヘッドレスでも注入するよう統合した。
- 結果: GUIなしのバックエンド実行でもRTCM受信→`GPS_RTCM_DATA`送信パスが動作する構成になり、u-center検証の前提が整った。
- 備考: 実機確認時は `config/gcs.yml` の `rtcm_host` と `rtcm_tcp_port` を実配信元に合わせる。

### 2026-04-15 00:00: [RTK/RTCM Injection Validation]
- 問題: u-center でのRTCMインジェクション検証を実施する際、RTCM接続先ホストがコード上で明示されず、手順が抽象的で検証しづらかった。
- 調査: `app/main.py` の `RtcmReader` 初期化で `port` のみ指定され、`host` はデフォルト依存だった。`docs/test_cases.md` のRTCM項目も実行手順・判定条件が不足していた。
- 試行: `app/main.py` に `rtcm_host` 設定読込を追加し、`config/gcs.yml` と `config/gcs_local.yml` に `rtcm_host` を追加。加えて `docs/test_cases.md` に u-center 検証手順、判定条件、トラブルシュートを追記し、`README.md` の設定例も更新した。
- 結果: u-center 出力先と GCS 側接続先を設定ファイルで一致させられるようになり、RTCMインジェクションの統合検証を再現可能な手順で実施できる状態になった。
- 備考: Windows/u-center と Raspberry Pi/GCS が別ホストの場合は `rtcm_host` を配信元IPに変更して運用する。

### 2026-03-14 08:35: [DevelopmentHistory/Workflow]
- 問題: 履歴記録の運用は導入済みだったが、「編集の都度必ず記録する」必須性をより明確にしたい要望があった。
- 調査: 全体指示には development-history skill 参照があり、履歴ファイルも存在するが、skill 側に必須ルールの強調を追加できる余地があった。
- 試行: `.github/skills/development-history/SKILL.md` に「最重要ルール（必須）」を追加し、編集の都度追記・先頭追記・コミット前確認を明文化した。
- 結果: 履歴運用が「任意」ではなく「必須」として明確化され、今後の編集ごとの追記ルールが強化された。
- 備考: 新規履歴は常にこのファイルの先頭へ追加する。

### 2026-03-14 00:00: [Environment/Setup]
- 問題: Windows ローカル環境で GUI 実行用の .venv、依存関係、ローカル専用設定、履歴記録ルールが未整備だった。
- 調査: 実行設定が `config/gcs.yml` 固定で Linux 向け serial 設定を読み込んでおり、`pyserial` も requirements に含まれていなかった。
- 試行: ローカル設定優先の設定ローダーを追加し、`.github/skills/development-history/SKILL.md` とローカル専用 skill の参照導線を整備し、`.venv` とローカル設定ファイルの ignore 方針を明文化した。
- 結果: Windows 上でローカル設定を優先して GUI 起動できる構成に変更し、`.venv` 上で `pytest tests -q` が 9 件成功、`app/main.py` も `config/gcs.user.local.yml` を使って GUI イベントループ開始まで確認した。
- 備考: ローカル専用 skill は `.github/skills/local-environment/SKILL.md`、ローカル専用設定は `config/gcs.user.local.yml` を使用する。`.gitignore1` は Git の対象外なので、実際の ignore 設定は `.gitignore` に追加した。

## 記録ルール

- **履歴は必ずファイルの一番上（最新が最上段）に追記してください。**
- 各エントリは下記の「記録形式」に従って記載してください。
- **このファイルは必ず直接編集してください（他ファイルや別所で管理せず、このファイル自体を編集すること）。**

## 記録形式

各エントリは以下の形式で記録：

```md
### YYYY-MM-DD HH:MM: [機能名/コンポーネント]
- 問題: [発生した問題の簡潔な説明]
- 調査: [調査内容・原因]
- 試行: [実施した変更・試したこと]
- 結果: [最終的な結果・解決方法]
- 備考: [その他重要な情報]
```

---