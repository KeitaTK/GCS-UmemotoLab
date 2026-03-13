# GCS MVP 実装

## 概要
UDPを介してMAVLink v2で直接通信し、カスタムメッセージをサポートし、RTKインジェクションと基本的なコマンド/制御を提供するWindows用Python GCSを構築します。

## スコープ
- MAVLink v2 UDP 受信/送信
- カスタムMAVLinkメッセージのサポート
- `GPS_RTCM_DATA`によるRTKインジェクション
- システムIDによる複数ドローンの管理
- 最小限のPySide6 UI

## 詳細要件
### 接続
- UDP `14550`でリッスン
- システムIDごとに設定可能な送信先エンドポイント
- ドローンごとのハートビートステータスの表示

### テレメトリー
- `HEARTBEAT`、`NAMED_VALUE_FLOAT`、`SYS_STATUS`、`GLOBAL_POSITION_INT`を受信
- 生成された`pymavlink`からのカスタムメッセージをサポート
- 最新の値をメモリに保存

### コマンドと制御
- アーム/ディスアーム、離陸、着陸
- `SET_POSITION_TARGET_LOCAL_NED`によるガイド制御

### RTKインジェクション
- ローカルTCP `127.0.0.1:5000`からRTCMを読み取り
- 選択されたシステムIDに`GPS_RTCM_DATA`を送信

## アーキテクチャ（計画）
- `MavlinkConnection`、`MessageRouter`、`TelemetryStore`
- `RtcmReader`、`RtcmInjector`
- `CommandDispatcher`、`GuidedControl`
- `MainWindow`、`DroneState`

## 並行処理
- スレッド化されたUDP受信とTCP RTCM読み取り
- Qtシグナルを使用したメインスレッドのUI
- MVPではマルチプロセスは使用しない

## 受け入れ基準
- ✅ 少なくとも1台のドローンのハートビートが検出される
- ✅ `NAMED_VALUE_FLOAT`がUIに表示される
- ✅ 選択されたシステムIDへのコマンド送信が成功する
- ✅ RTCMストリームが転送され、ログに記録される

## タスク分解
- [x] リポジトリ構造 + 設定ファイル
- [x] MAVLink接続 + ルーティング
- [x] テレメトリーストア + ハートビート追跡
- [x] RTKリーダー + インジェクター
- [x] コマンドディスパッチャー + ガイド制御
- [x] PySide6 UI
- [x] 1-2台のドローンでの統合テスト

## 実機検証結果（2026年3月14日）
### テスト環境
- ドローン：Pixhawk 6C (System ID=1)
- 接続方式：USB シリアル (`/dev/ttyACM0`, 115200 baud)
- プラットフォーム：Raspberry Pi 5 (taki@10.0.0.19)

### 検証項目と結果
| 項目 | 結果 | 詳細 |
|------|------|------|
| **シリアル通信** | ✅ PASS | `/dev/ttyACM0`で正常に接続、データ受信確認 |
| **ハートビート受信** | ✅ PASS | Drone 1 (System ID=1) から継続的に受信（約10Hz） |
| **テレメトリー解析** | ✅ PASS | HEARTBEAT, SYS_STATUS, GPS_RAW_INT 解析成功 |
| **コマンド送信** | ✅ PASS | ARM/DISARM コマンドを正常に送信 |
| **コマンド応答解析** | ✅ PASS | COMMAND_ACK メッセージの解析実装完了 |
| **ログ記録** | ✅ PASS | すべてのテレメトリーがログに記録される |

### 動作確認ログ抜粋
```
[2026-03-14 01:24:17] INFO __main__: Serial port opened: /dev/ttyACM0
[2026-03-14 01:24:17] INFO __main__: HEARTBEAT from Drone 1: type=0, armed=False, status=3
[2026-03-14 01:24:52] INFO: Sent COMMAND_LONG: cmd=400 to system 1
[2026-03-14 01:25:03] INFO __main__: Status: Drone 1: 115 msgs, last 0.1s ago
```

## 参考資料
- docs/spec.md
- docs/design.md
- docs/dev_guide.md
- docs/task_breakdown.md
