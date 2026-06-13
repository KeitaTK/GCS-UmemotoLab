# raspi-deploy
Raspberry Piへのデプロイ・実行・検証を行う際は、`.github/skills/raspi-deploy/SKILL.md` の手順に従い、コマンド実行などを自動化してください。

コードやドキュメントを編集した際は、`.github/skills/development-history/SKILL.md` の手順に従って `docs/development_history.md` の先頭へ開発履歴を追記してください。

ローカル環境固有の設定や実行手順が必要な場合は、存在すれば `.github/skills/local-environment/SKILL.md` を参照してください。この skill はローカル専用で Git 管理対象外です。

# Cline
Cline で本リポジトリを操作する際は、以下の点に注意してください：

- 本リポジトリのルートディレクトリは `GCS-UmemotoLab/` です。すべてのファイル操作はこのルートからの相対パスで行います。
- `.cline/` ディレクトリは Kanban が自動生成するワークツリーであり、Git 管理対象外です。このディレクトリ内のファイルを直接編集しないでください。
- `memory-bank/` は別リポジトリで管理されるメモリバンクです。本リポジトリにはコミットしません。
- `uv.lock` は決定論的ビルドのためコミット対象です。依存関係の変更時は必ず `uv.lock` も更新してください。
- `pyproject.toml` はコミット対象です。
- コード編集時は、上記の raspi-deploy / development-history スキルを Copilot 同様に参照・実行してください。
