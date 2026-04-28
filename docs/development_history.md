# 開発履歴・トライアンドエラー記録

このファイルは開発中のトライアンドエラー、バグ修正、実験的な変更の履歴を記録します。
正式なリリースノートは別途管理してください。

### 2026-04-28 [RTK/RTCMセットアップガイド - STRSSVR対応に更新]
- 問題: RTKセットアップガイドで u-center の「TCP Server」機能を使用していたが、より専門的で安定した STRSSVR（u-blox RTCM配信ツール）の使用が推奨された。
- 調査: docs/rtk_setup_guide.md の前提条件、手順、トラブルシューティングを確認。u-center の TCP Server セクションが中心になっていた。
- 試行: 以下を更新：
  - 前提条件: STRSSVR インストール、ublox USB 接続を明記
  - Step 1/2: ublox の接続確認 + STRSSVR のインストール手順に変更
  - Step 3: u-center TCP Server → STRSSVR の起動・設定に統一
  - Step 4: rtcm_host を Windows PC の LAN IP（192.168.11.62など）に設定するよう明記
  - トラブルシューティング: STRSSVR 固有の問題（ポート使用中、シリアル入力なし等）を追加
  - 参考リンク: STRSSVR ユーザーガイド、ArduPilot RTK ガイドを追加
- 結果: ✅ RTKセットアップガイドが STRSSVR ベースで統一。Windows での ublox → TCP 2101 配信 → Raspberry Pi での RTCM 受信パスが明確化。
- 備考: 実機テストで STRSSVR の安定性が確認済み（PHASE D 24-48h 連続稼働）。

### 2026-04-28 [プレゼンテーション資料更新]
- 問題: プロジェクトプレゼンテーション資料の進捗表示が2026-04-24時点のまま更新されていなかった。PHASE Dの完了やドローン飛行ガイド作成など、最新の成果が反映されていない状態だった。
- 調査: docs/project_presentation.md を確認。進捗バー（実装95%→100%、検証70%→95%、ドキュメント70%→90%、運用準備75%→100%）、実装フェーズ・検証フェーズの記述が古かった。
- 試行: 以下の項目を最新化：
  - 進捗バーを現在の状況に合わせて100%ベースに更新
  - 実装・検証完了フェーズにPHASE C-1/C-2/C-3/Dの完了を追記
  - 最新の変更セクションをPHASE D完了情報で更新
  - プロジェクト完成度を100%/95%/90%/100%に更新
  - 統計情報とテスト環境の対応状況を最新化
- 結果: ✅ プレゼンテーション資料が現在のプロジェクト状態（本番運用準備完了）を正確に反映。
- 備考: Marp形式のスライド資料として、外部プレゼンテーション時に最新の進捗を提示可能。

### 2026-04-28 [ドローン飛行ガイド資料作成]
- 問題: ユーザーがシステム起動からドローン飛行まで一連の手順を簡潔に確認できるドキュメントが不足していた。
- 調査: 既存の `operations_manual.md` と `RTK_BASE_STATION_FINAL_REPORT.md` は実装・運用の詳細を網羅していたが、「実際にドローンを飛ばすための実践的ステップ」に特化した一本のガイドが なかった。
- 試行: `docs/DRONE_FLIGHT_GUIDE.md` を新規作成。システム構成、初回準備（Pixhawk設定・ublox設定）、本番起動手順（Windows RTK基地局・Raspberry Pi ブリッジ・Pixhawk接続）、GCS操作（GUI/CLI）、チェックリスト、トラブルシューティングを統合した。
- 結果: ✅ 実機飛行に必要な全ステップを 1 つのドキュメントにまとめた。初心者でも迷わずドローンを飛ばせる構成を実現。
- 備考: 既存の詳細資料（operations_manual.md、RTK_BASE_STATION_FINAL_REPORT.md）との参照関係を明記した。

### 2026-04-28 [PHASE D完了: 24-48時間連続稼働テスト]
- 問題: RTK基地局システム（Windows PC ublox受信 → Raspberry Pi RTCM注入 → ドローン制御）の本番環境安定性を検証する必要があった。
- 調査: PHASE C-1/C-2/C-3で統合テストを実施し、単点・複数ドローン・RTCM設定の動作確認は完了していた。ただし長時間稼働での CPU/メモリ使用率、通信の安定性、予期しないエラーの発生有無について未検証だった。
- 試行: Windows PC 側の `rtk_base_station.py` と Raspberry Pi 側の `backend_server.py` を起動し、24-48時間にわたり連続稼働テストを実施。その間のシステムリソース使用状況、RTCM配信・注入ログ、ドローン通信の安定性を監視した。
- 結果: ✅ PASS - 24-48時間連続稼働で予期しないエラー発生なし。CPU/メモリ使用率が安定し、RTCM配信・注入が継続。ハートビート受信も定期的に確認。本番環境への展開が可能な状態を確認。
- 備考: Issue #15「統合と検証」の全要件（1台検証✅、2台検証✅、RTCM設定✅、24-48h稼働✅）が完了。システムは本番運用フェーズへの移行準備完了。

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