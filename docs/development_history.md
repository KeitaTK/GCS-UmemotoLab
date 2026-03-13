# 開発履歴・トライアンドエラー記録

このファイルは開発中のトライアンドエラー、バグ修正、実験的な変更の履歴を記録します。
正式なリリースノートは別途管理してください。

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