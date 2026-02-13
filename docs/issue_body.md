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
- 少なくとも1台のドローンのハートビートが検出される
- `NAMED_VALUE_FLOAT`がUIに表示される
- 選択されたシステムIDへのコマンド送信が成功する
- RTCMストリームが転送され、ログに記録される

## タスク分解
- [ ] リポジトリ構造 + 設定ファイル
- [ ] MAVLink接続 + ルーティング
- [ ] テレメトリーストア + ハートビート追跡
- [ ] RTKリーダー + インジェクター
- [ ] コマンドディスパッチャー + ガイド制御
- [ ] PySide6 UI
- [ ] 1-2台のドローンでの統合テスト

## 参考資料
- docs/spec.md
- docs/design.md
- docs/dev_guide.md
- docs/task_breakdown.md
