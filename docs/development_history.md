### 2026-07-06 21:08: [Web UI 基地局ステータス表示修正]
- 問題: RTCM注入が正常に開始されても、Web UI の基地局パネルが「停止中」のまま更新されなかった。
- 調査: `_build_base_station_status()` が `app.state.base_station` オブジェクト（`rtk_base_station_v2.py` のスタンドアロンモード用）の存在を前提としており、統合モード（`base_station_routes.py`）の `app.state.rtcm_serial_reader` + `bs_phase` による状態管理を認識していなかった。
- 試行: `websocket.py` の `_build_base_station_status()` を修正。`app.state.base_station` が None の場合に統合モードとして `app.state.rtcm_serial_reader` と `app.state.bs_phase` を参照し、`running`/`starting`/`error`/`idle` の各フェーズで適切なステータスを返すよう分岐。
- 結果: 統合モードでも基地局の状態（観測中/稼働中/エラー）が Web UI に正しく反映されるようになった。
- 備考: スタンドアロンモード（`rtk_base_station_v2`）用の既存コードはそのまま維持。

### 2026-07-06 21:05: [Web基地局起動順序バグ修正]
- 問題: Web UI から基地局起動ボタンを押すと「MAVLink not connected. POST /api/connect first.」で失敗。基地局の10秒観測が完了する前に /api/connect が実行されていないタイミング問題。
- 調査: `base_station_routes.py` の `base_station_start()` はバックグラウンドスレッドに入る前に `api.server.connection` のチェックをしていなかった。`10秒観測→F9P設定→RTCM注入` のシーケンスが完了した後に初めて `api_srv.connection` を参照してエラーになっていた。
- 試行: (1) サーバー側: `base_station_routes.py` の `base_station_start()` 冒頭に `api.server.connection` が None なら 400 エラーを即時返却するチェックを追加。(2) フロントエンド側: `base_station.js` の `startBaseStation()` でバックエンド未接続の場合、自動的に `/api/connect` → 500ms待機 → `/api/base_station/start` の順で実行するよう修正。
- 結果: フロントエンドから基地局ボタンを押すだけで、自動的に MAVLink 接続 → 基地局起動の順で正しく処理されるようになった。接続済みの場合はそのまま基地局起動に進む。
- 備考: `base_station_routes.py` の `_run()` 内にも `mav_conn is None` の RuntimeError チェックが残っている（バックグラウンドスレッド内で中途切断された場合の安全策として維持）。

### 2026-07-06 19:30: [RTCMログ保存機能]
- 問題: RTK補正情報（RTCMデータ）がArduPilotに送信されているがRTK Fixしない問題。送信データの内容を確認する手段がなかった。
- 調査: 既存コードを確認した結果、RTCM生データおよびMAVLink注入フレームのファイル保存機能が存在しないことが判明。またTCP中継が使われておらず、ポート不一致（15000 vs 2101）で接続できていなかった。
- 試行: `app/rtk_tools/rtcm_logger.py` に `RtcmLogger` クラスを新規作成。RTCM生データとMAVLink注入フレームの両方をタイムスタンプ付きバイナリ形式で保存する機能を実装。さらにTCP中継を廃止し、F9Pシリアル直読み + Queue + MAVLink GPS_RTCM_DATA注入の単一プロセス構成に変更。`rtcm_injector.py` をpymavlink準拠のフラグメント送信対応に書き換え。`rtcm_reader.py` はarchiveへ移動。
- 結果: `app/main.py`（GUIモード）と `app/api/routes.py`（Webサーバーモード）の両方をシリアル直読みに置換完了。
- 備考: config.yml の `rtcm.f9p_serial_port` が COM8 のままで、実際のF9P(COM10)と不一致 → COM10 に修正。またArduPilot出力から `GPS 1: specified as DroneCAN1-125` が確認されており、DroneCAN GPS構成ではMAVLink `GPS_RTCM_DATA` が処理されない可能性あり。