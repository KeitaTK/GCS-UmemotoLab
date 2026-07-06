# Progress — GCS-UmemotoLab

## 完了した機能

### コア通信基盤

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| UDP接続管理 | `app/mavlink/connection.py` | ✅ | MAVLink v2 over UDP |
| シリアル接続管理 | `app/mavlink/connection.py` | ✅ | Pixhawk 直結、RTS/CTS対応、最大1M baud |
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

### UI（Web）

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| カード方式ダッシュボード | `web/static/index.html` + `dashboard.js` | ✅ | 4スロットグリッド |
| ドローン選択（カードクリック） | `web/static/dashboard.js` | ✅ | 単一/複数選択対応 |
| WebSocketテレメトリ配信 | `web/static/websocket.js` | ✅ | FastAPI + 全クライアントブロードキャスト |
| Plotly.jsグラフ | `web/static/graph.js` | ✅ | バッテリー電圧・高度 |
| Raw Data表示 | `web/static/rawdata.js` | ✅ | JSON整形表示 |
| 全機一括制御（Broadcast） | `web/static/controls.js` | ✅ | Arm/Disarm/Takeoff/Land |
| カード単位制御（STOP/Force） | `web/static/controls.js` | ✅ | カード内ボタン |

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
| RTCM → GPS_RTCM_DATA変換 | `app/rtk_tools/rtcm_injector.py` | ✅ | MAVLink msgid=233, 180byte分割, CRC-16 CCITT |
| RTCM再接続（指数バックオフ） | `app/rtk_tools/rtcm_reader.py` | ✅ | 切断時自動復旧 |
| RTK基地局スクリプト v1 | `rtk_base_station.py` | ✅ | ublox シリアル受信→TCP配信 |
| RTK基地局スクリプト v2 | `rtk_tools/rtk_base_station_v2.py` | ✅ | F9P設定統合版, autoモード対応 |
| RTK基地局 v2: autoモード | `rtk_tools/rtk_base_station_v2.py` | ✅ | USB自動検出 + 単独測位で基準座標自動取得 |
| RTK基地局 v2: false preamble修正 | `rtk_tools/rtk_base_station_v2.py` | ✅ | reserved bits非ゼロ時にスキップ |
| RTK基地局 v2: RTCM生ログ保存 | `rtk_tools/rtk_base_station_v2.py` | ✅ | `logs/rtcm_raw_{timestamp}.bin` |
| RTK基地局 v2: Windows対応 | `rtk_tools/rtk_base_station_v2.py` | ✅ | `freeze_support()`, COM8, config.win.yml |
| RTK転送サービス | `rtk_forwarder_service.py` | ✅ | NTRIP/Serial → UDP転送 |

### Raspi 側（Raspberry Pi 5 搭載）

| 機能 | ファイル | 状態 | 備考 |
|------|----------|------|------|
| バックエンドサーバー | `raspi/backend_server.py` | ✅ | MAVLink転送 + RTCM注入 |
| Raspi設定 | `raspi/config.yml` | ✅ | serial 1M baud + RTS/CTS |
| Raspi設定ローダー | `raspi/config_loader.py` | ✅ | RASPI_CONFIG_PATH 環境変数対応 |
| Raspiインストーラー | `raspi/install.sh` | ✅ | .venv + pip + systemd + mavlink-router |
| RTCM注入（Raspi上） | `Mavlink_raspi/RTK/rtcm_injector.py` | ✅ | Raspi上でRTCM→MAVLink変換実行 |
| EKF Observer設定 | `Mavlink_raspi/RTK/setup_EKF_Observer4.py` | ✅ | Pixhawk EKF Observerパラメータ設定 |

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

### RTK LED 未点灯調査（🔍 調査中）
- Pixhawk 側で RTK FIXED 達成時にも RTK LED が点灯しない問題
- パラメータ: GPS1_TYPE=9, CAN_D1_PROTOCOL=1, GPS_DRV_OPTIONS=64
- CAN経由 F9P Rover → Pixhawk 間の RTCM 注入パスを検証中

### Memory Bank 整備（🔄 進行中）
- `memory-bank/product_context.md` ✅
- `memory-bank/active_context.md` ✅
- `memory-bank/progress.md` ✅（本ファイル）
- `memory-bank/decision_log.md` ✅
- `memory-bank/system_patterns.md` ✅

### 実機飛行テスト（⏳ 準備中）
- プロペラあり実飛行での RTK FIXED 維持確認
- 全パイプラインエンドツーエンド検証（F9P→TCP:2101→Raspi→serial→Pixhawk→CAN→F9P Rover）

### 長時間運用テスト（⏳ 待機中）
- メモリリーク・CPU使用率の長期監視
- RTCM raw log のディスク使用量監視

## 残っている作業・未実装機能

### 優先度: 高
- [ ] **RTK LED 未点灯修正**: Pixhawk側パラメータまたはArduPilotのGPS_DRV_OPTIONS設定の確認
- [ ] **実機飛行テスト総合検証**: 全機能を実飛行で確認
- [ ] **NTRIP再接続・認証再取得**: RTCMストリーム切断時の完全復旧

### 優先度: 中
- [ ] **RTCM raw log ローテーション**: 現在無制限書き込みのためディスク容量対策が必要
- [ ] **UI自由レイアウト編集**: パネルのドラッグ＆ドロップ再配置
- [ ] **Sphinx ドキュメント全モジュールカバレッジ**: `docs_sphinx/` の拡充
- [ ] **SITL統合テストの自動化**: CI/CD パイプラインでの SITL テスト実行
- [ ] **GPS拡張（Phase 1-3）**: GPS_DOP 表示、衛星コンステレーション可視化

### 優先度: 低
- [ ] **ドローン個別設定**: ドローンごとのパラメータプリセット管理
- [ ] **選択的RTCM注入**: 特定ドローンのみにRTCMを注入
- [ ] **フライトミッション管理**: ウェイポイントアップロード・ミッション監視
- [ ] **ビデオストリーム統合**: カメラ映像のGCS表示
- [ ] **Android/iOS対応**: モバイル向けUI

## 既知の問題・バグ

| 問題 | 重要度 | 状況 | 備考 |
|------|--------|------|------|
| **RTK LED 未点灯** | 🔴 高 | 調査中 | Pixhawk側でRTK FIXEDだがLED点灯せず。GPS_DRV_OPTIONS=64, CAN_D1_PROTOCOL=1, GPS1_TYPE=9 設定済み |
| HEARTBEAT保持形式の不一致（bytes vs オブジェクト） | 中 | 回避済 | `backend_server.py` で `hasattr(hb, 'base_mode')` 分岐 |
| pymavlink 新旧API互換性 | 低 | 対策済 | `parse_buffer` → `parse_char_array` → `decode` の3段フォールバック |
| Python 3.14 要件と Raspi 3.11 の乖離 | 中 | 回避済 | Raspi 側は `requirements_raspi.txt` で運用 |
| Raspi 側の依存二重管理（UV + requirements_raspi.txt） | 低 | 監視中 | UV一本化の検討が必要 |
| RTCM raw log 無制限書き込み | 中 | 監視中 | 長時間運用でディスク圧迫の可能性 |

## テスト状況

| カテゴリ | テスト数 | 成功 | 失敗 | スキップ |
|----------|----------|------|------|----------|
| ユニットテスト（コマンド） | 8 | 8 | 0 | 0 |
| ユニットテスト（接続エラー） | 19 | 19 | 0 | 0 |
| ユニットテスト（テレメトリ） | 複数 | 全件 | 0 | 0 |
| 統合テスト（RTK） | 3 | 3 | 0 | 0 |
| 統合テスト（Phase C） | 1 | 1 | 0 | 0 |
| 統合テスト（RTCM→EKF注入） | 4 | 4 | 0 | 0 |
| 実機テスト（アーム） | 1 | 1 | 0 | 0 |

**全体のテストカバレッジ**: コアモジュール（connection, message_router, command_dispatcher, telemetry_store, rtcm_reader, rtcm_injector）はユニットテストでカバー。RTCM→EKF注入のE2Eテストも実施済み（データロス0%確認）。UI と SITL 統合テストは未実施。

## 全体アーキテクチャ（最新）

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Windows PC (GCS-UmemotoLab)                                              │
│                                                                         │
│  rtk_base_station_v2.py (mode=auto)                                     │
│  ├── auto_detect_port(): USBポート自動検出                                │
│  ├── auto_observe_position(60s): 単独測位で基準座標取得                   │
│  ├── F9pConfigurator: TMODE3 Fixed + RTCM3出力設定                       │
│  ├── RtcmSerialReader: F9P→USB→RTCM3受信 (false preamble検出付き)        │
│  │   └── logs/rtcm_raw_{timestamp}.bin に全フレーム保存                   │
│  └── TcpServer: TCP :2101 で全クライアントにブロードキャスト              │
│                                                                         │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │ TCP :2101 (同一LAN または Tailscale経由)
                        │
┌───────────────────────┴─────────────────────────────────────────────────┐
│ Raspberry Pi 5 (機体搭載)                                                │
│                                                                         │
│  raspi/backend_server.py                                                │
│  ├── RtcmReader: TCP :2101 → RTCM3フレーム受信                           │
│  ├── RtcmInjector: RTCM3 → GPS_RTCM_DATA (MAVLink msgid=233) 変換       │
│  │   └── 180byte分割 + CRC-16 CCITT                                     │
│  └── MavlinkConnection: /dev/ttyAMA0 @ 1M baud, RTS/CTS                │
│                                                                         │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │ UART /dev/ttyAMA0 (GPIO 14/15 + RTS/CTS GPIO 16/17)
                        │ 1M baud, RTS/CTS フロー制御
                        │
┌───────────────────────┴─────────────────────────────────────────────────┐
│ Pixhawk 6C (ArduPilot Copter)                                            │
│                                                                         │
│  パラメータ:                                                             │
│  ├── GPS1_TYPE = 9          (DroneCAN)                                  │
│  ├── CAN_D1_PROTOCOL = 1    (DroneCAN)                                  │
│  ├── GPS_DRV_OPTIONS = 64   (Rover側 RTCM受信有効化)                     │
│  └── GPS_AUTO_CONFIG = 2    (自動設定)                                   │
│                                                                         │
└───────────────────────┬─────────────────────────────────────────────────┘
                        │ CAN Bus
                        │
┌───────────────────────┴─────────────────────────────────────────────────┐
│ u-blox ZED-F9P Rover (DroneCAN接続)                                      │
│                                                                         │
│  RTCM補正データをPixhawk経由で受信 → RTK FIXED 測位                      │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```
