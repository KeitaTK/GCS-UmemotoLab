# Progress — GCS-UmemotoLab

## 完了した機能

### コア通信基盤

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| UDP接続管理 | `app/mavlink/connection.py` | ✅ | MAVLink v2 over UDP |
| シリアル接続管理 | `app/mavlink/connection.py` | ✅ | Pixhawk 直結（`/dev/ttyACM0`） |
| MAVLinkメッセージパース | `app/mavlink/message_router.py` | ✅ | pymavlink 新旧API対応 |
| メッセージルーティング | `app/mavlink/message_router.py` | ✅ | メッセージタイプ別ディスパッチ |
| データストリーム要求 | `app/main.py` | ✅ | REQUEST_DATA_STREAM (5Hz) |

### UI（PySide6）

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| メインウィンドウ（3タブ構成） | `app/ui/main_window.py` | ✅ | Dashboard / Graph / Raw Data |
| ドローンリスト表示・選択 | `app/ui/main_window.py` | ✅ | System ID ベース |
| System Status 表示（Armed/Mode） | `app/ui/main_window.py` | ✅ | HEARTBEAT から抽出 |
| バッテリー情報表示（電圧・電流・残量） | `app/ui/main_window.py` | ✅ | SYS_STATUS から抽出 |
| GPS 情報表示（衛星数・位置・高度） | `app/ui/main_window.py` | ✅ | GPS_RAW_INT, GLOBAL_POSITION_INT |
| リアルタイムグラフ | `app/ui/telemetry_plotter.py` | ✅ | pyqtgraph, NAMED_VALUE_FLOAT |
| 接続状態パネル | `app/ui/main_window.py` | ✅ | Status/Type/Packets/Error |
| コマンド状態・リトライ表示 | `app/ui/main_window.py` | ✅ | 色分け表示 |
| RTK統計表示 | `app/ui/main_window.py` | ✅ | RTK Fix状態 |

### 機体制御

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| アーム/ディスアーム | `app/rtk_tools/command_dispatcher.py` | ✅ | COMMAND_LONG |
| 強制アーム（Force Arm） | `app/rtk_tools/command_dispatcher.py` | ✅ | ARMING_CHECK=0 等 |
| 離陸（Takeoff） | `app/rtk_tools/command_dispatcher.py` | ✅ | 高度指定可能 |
| 着陸（Land） | `app/rtk_tools/command_dispatcher.py` | ✅ | 降下率指定可能 |
| Guided位置制御 | `app/rtk_tools/guided_control.py` | ✅ | SET_POSITION_TARGET_LOCAL_NED |
| Guided速度制御 | `app/rtk_tools/guided_control.py` | ✅ | 速度ベクトル指定 |
| COMMAND_ACK追跡 | `app/rtk_tools/command_dispatcher.py` | ✅ | MAV_RESULT コード表示 |
| コマンドタイムアウト検出 | `app/rtk_tools/command_dispatcher.py` | ✅ | 5秒タイムアウト |
| 自動リトライ（最大3回） | `app/rtk_tools/command_dispatcher.py` | ✅ | exponential backoff |
| 複数ドローン同時制御 | `app/rtk_tools/command_dispatcher.py` | ✅ | 複数選択→一括送信 |

### RTK / RTCM

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| RTCM TCP受信 | `app/rtk_tools/rtcm_reader.py` | ✅ | コールバックベース |
| RTCM → GPS_RTCM_DATA変換 | `app/rtk_tools/rtcm_injector.py` | ✅ | MAVLink MSG_ID 67 |
| RTCM再接続（指数バックオフ） | `app/rtk_tools/rtcm_reader.py` | ✅ | 切断時自動復旧 |
| RTK基地局スクリプト | `rtk_base_station.py` | ✅ | ublox シリアル受信→TCP配信 |
| RTK転送サービス | `rtk_forwarder_service.py` | ✅ | NTRIP/Serial → UDP転送 |

### エラーハンドリング

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| UDPタイムアウト検出 | `app/mavlink/connection.py` | ✅ | 30回連続で警告 |
| シリアル自動再接続 | `app/mavlink/connection.py` | ✅ | exponential backoff |
| エラーコールバック登録 | `app/mavlink/connection.py` | ✅ | 複数コールバック対応 |
| 接続状態トラッキング | `app/mavlink/connection.py` | ✅ | `get_connection_status()` |
| エラーダイアログ表示 | `app/ui/main_window.py` | ✅ | CRITICAL/TIMEOUT 時 |

### テレメトリ・ロギング

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| テレメトリデータ保持 | `app/rtk_tools/telemetry_store.py` | ✅ | システムID別管理 |
| NAMED_VALUE_FLOAT履歴集約 | `app/rtk_tools/telemetry_store.py` | ✅ | 最大500ポイント |
| GPS Fix タイプ名変換 | `app/mavlink/message_router.py` | ✅ | NO_GPS〜RTK_FIXED |
| ファイルロギング | `app/logging_config.py` | ✅ | RotatingFileHandler 5MB x 5 |
| コンソールロギング | `app/logging_config.py` | ✅ | DEBUG レベル |

### テスト

| テスト | ファイル | 結果 | 備考 |
|--------|----------|------|------|
| コマンドリトライ | `tests/test_command_retry.py` | ✅ 8/8 | pytest |
| 接続エラー | `tests/test_connection_errors.py` | ✅ 19/19 | pytest |
| テレメトリ保存 | `tests/test_telemetry_store.py` | ✅ | pytest |
| コマンドディスパッチャ | `tests/test_command_dispatcher.py` | ✅ | pytest |
| RTK統合 | `tests/test_rtk_integration.py` | ✅ 3/3 | ローカル + Raspi |
| RTK基地局統合 | `tests/test_rtk_base_station_integration.py` | ✅ | 92フレーム確認 |
| Phase C統合 | `tests/test_phase_c_integration.py` | ✅ | Raspi 実機 |
| ダミーアーム | `tests/test_arm_dummy.py` | ✅ | 実機不要 |
| 実機アーム | `tests/test_arm_live.py` | ✅ | SSHトンネル要 |
| Raspi接続確認 | `tests/test_raspi_connection/` | ✅ | MAVLink受信確認 |

## 現在進行中の作業

### Memory Bank 整備（🔄 進行中）
- `memory-bank/product_context.md` 作成
- `memory-bank/active_context.md` 作成
- `memory-bank/progress.md` 作成（本ファイル）
- `memory-bank/decision_log.md` 作成予定
- `memory-bank/system_patterns.md` 作成予定

### 実機テスト検証（⏳ 待機中）
- Raspberry Pi + Pixhawk6C 実機接続での総合テスト
- コマンド送信（ARM/DISARM/Takeoff/Land）の実機確認
- RTCM注入のエンドツーエンド検証（u-center → PC → Raspi → Pixhawk）
- 長時間運用テスト（Phase 7 継続）

## 残っている作業・未実装機能

### 優先度: 高
- [ ] **実機テスト総合検証**: 全機能を実機で一通り確認（特に接続エラー回復、RTCM再接続）
- [ ] **NTRIP再接続・認証再取得**: RTCMストリーム切断時の完全復旧
- [ ] **Phase 1-3（GPS拡張）**: GPS_DOP 表示、衛星コンステレーション可視化

### 優先度: 中
- [ ] **UI自由レイアウト編集**: パネルのドラッグ＆ドロップ再配置
- [ ] **厳密なグループ同期制御**: 複数機の同時離陸・同時着陸
- [ ] **Sphinx ドキュメント全モジュールカバレッジ**: `docs_sphinx/` の拡充
- [ ] **SITL統合テストの自動化**: CI/CD パイプラインでの SITL テスト実行

### 優先度: 低
- [ ] **ドローン個別設定**: ドローンごとのパラメータプリセット管理
- [ ] **選択的RTCM注入**: 特定ドローンのみにRTCMを注入
- [ ] **フライトミッション管理**: ウェイポイントアップロード・ミッション監視
- [ ] **ビデオストリーム統合**: カメラ映像のGCS表示
- [ ] **Android/iOS対応**: モバイル向けUI

## 既知の問題・バグ

| 問題 | 重要度 | 状況 | 備考 |
|------|--------|------|------|
| HEARTBEAT保持形式の不一致（bytes vs オブジェクト） | 中 | 回避済 | `backend_server.py` で `hasattr(hb, 'base_mode')` 分岐 |
| pymavlink 新旧API互換性 | 低 | 対策済 | `parse_buffer` → `parse_char_array` → `decode` の3段フォールバック |
| Python 3.14 要件と Raspi 3.11 の乖離 | 中 | 回避済 | Raspi 側は `requirements_raspi.txt` で運用 |
| Raspi 側の依存二重管理（UV + requirements_raspi.txt） | 低 | 監視中 | UV一本化の検討が必要 |

## テスト状況

| カテゴリ | テスト数 | 成功 | 失敗 | スキップ |
|----------|----------|------|------|----------|
| ユニットテスト（コマンド） | 8 | 8 | 0 | 0 |
| ユニットテスト（接続エラー） | 19 | 19 | 0 | 0 |
| ユニットテスト（テレメトリ） | 複数 | 全件 | 0 | 0 |
| 統合テスト（RTK） | 3 | 3 | 0 | 0 |
| 統合テスト（Phase C） | 1 | 1 | 0 | 0 |
| 実機テスト（アーム） | 1 | 1 | 0 | 0 |

**全体のテストカバレッジ**: コアモジュール（connection, message_router, command_dispatcher, telemetry_store, rtcm_reader, rtcm_injector）はユニットテストでカバー。UI と SITL 統合テストは未実施。
