# 開発履歴・トライアンドエラー記録

このファイルは開発中のトライアンドエラー、バグ修正、実験的な変更の履歴を記録します。
正式なリリースノートは別途管理してください。

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