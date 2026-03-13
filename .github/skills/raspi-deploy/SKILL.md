---
name: raspi-deploy
description: "コードを編集してRaspberry Piでデバッグ・実行するワークフロー。使用するとき: コードに変更を加えた後にRaspberry Pi (taki@10.0.0.19) へデプロイして実行・検証したいとき。gh cli でプッシュ → SSH で git pull → 仮想環境(.venv)で実行 → 結果を検証 → エラーがあれば再編集してループというサイクルを自動化する。'デプロイ', 'ラズパイで実行', 'Raspberry Piでテスト', 'raspi deploy', 'deploy and test', 'mavlink-routerを起動' などのフレーズで呼び出される。"
argument-hint: "実行する操作 (例: main.py を起動, mavlink-router を設定, テストを実行)"
---

# raspi-deploy スキル

Raspberry Pi 5 (taki@10.0.0.19) へのデプロイ・実行・検証サイクルを自動化するスキルです。

## 対象環境

| 項目 | 値 |
|------|-----|
| Raspberry Pi ホスト | `taki@10.0.0.19` |
| リポジトリパス (raspi) | `~/GCS-UmemotoLab` |
| 仮想環境 | `~/GCS-UmemotoLab/.venv` |
| アプリディレクトリ | `~/GCS-UmemotoLab/app/` |
| ローカルリポジトリ | `c:\Users\taki\Local\local\GCS-UmemotoLab` |

---

## STEP 0: SSH 公開鍵認証のセットアップ（初回のみ・未設定の場合）

> **現状**: ラズパイへの SSH 自動認証（パスワードなしログイン）は未設定。
> 以下の手順を一度実行しておくと、以降のデプロイが大幅に楽になる。

### 0-1. SSH 鍵ペアの確認・生成（Windows 側）

PowerShell で実行:

```powershell
# 既存の鍵を確認
Test-Path "$env:USERPROFILE\.ssh\id_ed25519"
```

`True` が返れば鍵は既にある。`False` の場合は以下で生成:

```powershell
ssh-keygen -t ed25519 -C "taki-gcs" -f "$env:USERPROFILE\.ssh\id_ed25519"
# パスフレーズは Enter×2 で空にするとパスワードなしログインが可能
```

### 0-2. 公開鍵をラズパイへコピー

```powershell
# 方法A: ssh-copy-id が使える場合（Git Bash / WSL）
ssh-copy-id taki@10.0.0.19

# 方法B: PowerShell ネイティブ（ssh-copy-id がない場合）
$pubkey = Get-Content "$env:USERPROFILE\.ssh\id_ed25519.pub"
ssh taki@10.0.0.19 "mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$pubkey' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
# ← ここだけパスワード入力が必要
```

### 0-3. 動作確認

```powershell
ssh taki@10.0.0.19 "echo 'SSH auth OK'"
# パスワードなしで "SSH auth OK" が表示されれば成功
```

### 0-4. トラブルシューティング（鍵認証が通らない場合）

```powershell
# ラズパイ側の SSH 設定確認
ssh taki@10.0.0.19 "sudo grep -E 'PubkeyAuthentication|AuthorizedKeysFile' /etc/ssh/sshd_config"
# → PubkeyAuthentication yes になっていること

# ラズパイ側のパーミッション確認・修正
ssh taki@10.0.0.19 "ls -la ~/.ssh/"
ssh taki@10.0.0.19 "chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"

# ラズパイ側 SSH デーモンを再起動
ssh taki@10.0.0.19 "sudo systemctl restart ssh"

# Windows 側 known_hosts をリセット（IP 変更後などに必要）
ssh-keygen -R 10.0.0.19
```

---

## STEP 1: 初回セットアップ（リポジトリ・仮想環境の準備）

### 1-1. ラズパイにリポジトリをクローン

```powershell
ssh taki@10.0.0.19 "git clone https://github.com/KeitaTK/GCS-UmemotoLab.git ~/GCS-UmemotoLab"
```

### 1-2. 仮想環境を作成してパッケージをインストール

```powershell
ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
```

> **注意**: PySide6 は Raspberry Pi OS (arm64) 向けビルドが必要な場合がある。
> 失敗する場合は `pyside6` を除いた `requirements_raspi.txt` を用意することを検討。

### 1-3. mavlink-router のインストール（通信ブリッジ用）

```powershell
ssh taki@10.0.0.19 "sudo apt update && sudo apt install -y mavlink-router"
```

インストール後の動作確認:

```powershell
ssh taki@10.0.0.19 "mavlink-routerd --version"
```

---

## ワークフロー手順


### ステップ 1: 変更をプッシュ（GitHub CLI対応）

```zsh
# 変更をステージング
git add .

# コミット
git commit -m "<変更内容を簡潔に記述>"

# GitHub CLIでリポジトリをセット
gh repo set-default KeitaTK/GCS-UmemotoLab

# プッシュ
git push origin main
```

### ステップ 2: Raspberry Pi で git pull


```zsh
ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && git pull"
```

出力に `Already up to date.` または変更ファイルのリストが表示されることを確認。

### ステップ 3: アプリケーションを実行

#### 3-A: GCS アプリ本体（main.py）を起動

ヘッドレス環境（Raspberry Pi に画面なし）では GCS の Qt UI は動かないため、
バックグラウンドサービス部分のみ起動する場合:

```powershell
ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && source .venv/bin/activate && timeout 30 python3 app/main.py 2>&1"
```

#### 3-B: テストを実行

```powershell
ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && source .venv/bin/activate && python3 -m pytest tests/ -v 2>&1"
```

#### 3-C: mavlink-router を起動（ArduPilot との通信ブリッジ）

シリアル接続のドローン（Pixhawk）から UDP で GCS へ中継する場合:

```powershell
ssh taki@10.0.0.19 "mavlink-routerd -e 10.0.0.19:14550 /dev/ttyAMA0:57600 &"
```

| 引数 | 内容 |
|------|------|
| `-e 10.0.0.19:14550` | GCS（このラズパイ）へ UDP 転送 |
| `/dev/ttyAMA0:57600` | Pixhawk シリアル接続 (ボーレート要確認) |

mavlink-router の設定ファイルを使う場合:

```powershell
ssh taki@10.0.0.19 "cat /etc/mavlink-router/main.conf"
```

### ステップ 4: 結果を検証

出力を解析して以下を確認:

1. **Python エラー** (`Traceback`, `Error:`, `Exception`) → エラー箇所を特定
2. **接続エラー** (`Connection refused`, `timeout`, `No route to host`) → IP・ポート設定を確認
3. **MAVLink エラー** (`Bad CRC`, `unknown message`) → pymavlink バージョンを確認
4. **正常動作の確認** (期待するログ・データが出力されているか)

### ステップ 5: 判定

- **問題なし** → ワークフロー完了
- **コードのバグ** → ローカルでコードを修正してステップ1に戻る
- **環境の問題** → Raspberry Pi 側の設定を確認（パッケージ不足など）

---

## 全自動デプロイスクリプト

より手軽に実行する場合は [deploy_and_run.ps1](./scripts/deploy_and_run.ps1) を使用:

```powershell
.\scripts\deploy_and_run.ps1 -CommitMessage "fix: バグ修正" -TimeoutSec 30
```

---

## よくある問題と対処法

| エラー | 原因 | 対処 |
|--------|------|------|
| `Permission denied (publickey)` | SSH鍵未設定 | STEP 0 の手順を実施 |
| `Password:` プロンプトが毎回出る | SSH鍵未設定 | STEP 0 の手順を実施 |
| `ssh-copy-id: command not found` | Git Bash/WSL なし | 方法Bの PowerShell コマンドを使う |
| `Host key verification failed` | known_hosts の古いエントリ | `ssh-keygen -R 10.0.0.19` を実行 |
| `ModuleNotFoundError` | パッケージ未インストール | `ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && .venv/bin/pip install <pkg>"` |
| `PySide6 install failed` | arm64 ビルド問題 | `pip install PySide6` の代わりに `apt install python3-pyside6` を試す |
| `connection refused: 14550` | mavlink-router 未起動 | ステップ 3-C を実行 |
| `git pull` で競合 | ラズパイ側に変更あり | `ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && git stash && git pull"` |
| `.venv` が存在しない | 初回セットアップ未実施 | STEP 1-2 のコマンドを実行 |
| `serial.SerialException` | Pixhawk 未接続 | USB/UART 接続を確認、`ls /dev/ttyAMA*` で存在確認 |

## ループ制御

エラーが3回以上連続する場合:
1. より根本的な原因を調査する
2. ラズパイ上のログを確認: `ssh taki@10.0.0.19 "journalctl -n 50"`
3. 仮想環境の再構築:
   ```powershell
   ssh taki@10.0.0.19 "cd ~/GCS-UmemotoLab && rm -rf .venv && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
   ```
