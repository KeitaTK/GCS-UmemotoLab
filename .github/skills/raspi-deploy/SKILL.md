---
name: raspi-deploy
description: "Tailscale経由でRaspberry Piにコードをデプロイ・実行・検証する。'デプロイ', 'ラズパイで実行', 'Raspberry Piでテスト', 'raspi deploy' で呼び出し。"
argument-hint: "実行する操作 (例: main.py を起動, mavlink-router を設定, テストを実行)"
---

# raspi-deploy スキル

Tailscale 経由で Raspberry Pi 5 へのデプロイ・実行サイクルを自動化します。

## 対象環境

| 項目 | 値 |
|------|-----|
| Raspberry Pi (Tailscale) | `taki@100.123.158.105` |
| SSH 接続 | `ssh -o ProxyCommand="tailscale nc %h %p" taki@100.123.158.105` |
| リポジトリパス | `~/GCS-UmemotoLab` |
| 仮想環境 | `~/GCS-UmemotoLab/.venv` |

### ~/.ssh/config

```ssh-config
Host raspi
    HostName 100.123.158.105
    User taki
    IdentityFile ~/.ssh/id_ed25519
    ProxyCommand tailscale nc %h %p
    ServerAliveInterval 30
```

---

## ワークフロー

### 1. 変更をプッシュ

```bash
git add .
git commit -m "変更内容"
git push origin main
```

### 2. Raspi で git pull

```bash
ssh raspi "cd ~/GCS-UmemotoLab && git pull"
```

### 3. 実行

```bash
# GCS アプリ
ssh raspi "cd ~/GCS-UmemotoLab && source .venv/bin/activate && python app/main.py"

# テスト
ssh raspi "cd ~/GCS-UmemotoLab && source .venv/bin/activate && python -m pytest tests/ -v"
```

### 4. mavlink-router 管理

```bash
# 状態確認
ssh raspi "sudo systemctl status mavlink-router"

# 再起動
ssh raspi "sudo systemctl restart mavlink-router"

# 設定確認
ssh raspi "cat /etc/mavlink-router/main.conf"
```

---

## トラブルシューティング

| エラー | 対処 |
|--------|------|
| SSH 接続不可 | `tailscale status` で接続状態確認 |
| `ModuleNotFoundError` | `ssh raspi "cd ~/GCS-UmemotoLab && .venv/bin/pip install <pkg>"` |
| ハートビート未受信 | Pixhawk 電源・配線確認、`dmesg \| grep tty` |
| mavlink-router 未起動 | `ssh raspi "sudo systemctl start mavlink-router"` |
