# 開発履歴・トライアンドエラー記録

このファイルは開発中のトライアンドエラー、バグ修正、実験的な変更の履歴を記録します。
正式なリリースノートは別途管理してください。

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