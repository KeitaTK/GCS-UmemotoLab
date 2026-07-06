# GCS開発ガイド

## 1. リポジトリ構造
- `app/`：アプリケーションソースコード
- `config/`：実行時設定
- `docs/`：仕様と設計ドキュメント
- `third_party/`：生成されたMAVLinkライブラリ（カスタムXML出力）

## 2. Python環境
- Python 3.10+推奨
- 専用の仮想環境を使用

## 3. 依存関係（MVP）
- `pymavlink`
- `PySide6`
- `pyyaml`

## 4. 設定
- `config/gcs.yml`をコピーして、エンドポイントとシステムIDを編集

## 5. 実行（計画）
- `python -m app.main`

## 6. コードスタイルと命名
### 6.1 命名
- モジュール：`snake_case`
- クラス：`CapWords`
- 関数：`snake_case`
- 定数：`UPPER_SNAKE_CASE`

### 6.2 型
- パブリックメソッドに型ヒントを使用
- モデルオブジェクトに`dataclasses`を使用

### 6.3 ログ記録
- `logging`モジュールを使用
- 本番コードで`print`を使用しない

### 6.4 エラーポリシー
- 予測可能な失敗については`app/errors.py`でカスタム例外を発生させる
- テレメトリーデコーディングエラーについてはログを記録して継続

## 7. GitHub Copilotの使用
- ボイラープレートにCopilotを使用しますが、MAVLinkメッセージフィールドを検証
- コマンド送信にはテストまたはシミュレーションが必要

## 8. 参考資料
- https://docs.github.com/en/issues/tracking-your-work-with-issues/creating-an-issue
