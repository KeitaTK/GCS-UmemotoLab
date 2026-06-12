#!/bin/bash
# ============================================================
# Raspberry Pi 用 Tailscale + テザリング自動接続 セットアップ
# ============================================================
# 前提: Raspberry Pi 5 (Raspberry Pi OS Bookworm, arm64)
# ユーザー: taki
#
# 使い方:
#   chmod +x tailscale_setup_raspi.sh
#   ./tailscale_setup_raspi.sh
#
# すでに設定済みの場合は何もしません。
# ============================================================

set -e

TAILSCALE_VERSION="1.98.4"
TAILSCALE_ARCH="arm64"
TAILSCALE_TGZ="tailscale_${TAILSCALE_VERSION}_${TAILSCALE_ARCH}.tgz"
TAILSCALE_URL="https://pkgs.tailscale.com/stable/${TAILSCALE_TGZ}"

echo "========================================"
echo " Raspberry Pi Tailscale 自動セットアップ"
echo "========================================"

# --------------------------------------------------
# 1. Tailscale インストール（静的バイナリ方式）
# --------------------------------------------------
echo ""
echo "[1/5] Tailscale をインストール中..."

if command -v tailscale &>/dev/null && command -v tailscaled &>/dev/null; then
    echo "  ✅ Tailscale は既にインストールされています: $(tailscale version)"
else
    echo "  静的バイナリをダウンロード中..."
    cd /tmp
    if [ ! -f "$TAILSCALE_TGZ" ]; then
        curl -fsSL "$TAILSCALE_URL" -o "$TAILSCALE_TGZ"
    fi
    tar xzf "$TAILSCALE_TGZ"
    
    sudo cp "tailscale_${TAILSCALE_VERSION}_${TAILSCALE_ARCH}/tailscale" /usr/local/bin/
    sudo cp "tailscale_${TAILSCALE_VERSION}_${TAILSCALE_ARCH}/tailscaled" /usr/local/bin/
    sudo chmod 755 /usr/local/bin/tailscale /usr/local/bin/tailscaled
    
    # 環境ファイル
    sudo mkdir -p /etc/default
    echo "PORT=41641" | sudo tee /etc/default/tailscaled > /dev/null
    
    # systemd サービス
    sudo cp "tailscale_${TAILSCALE_VERSION}_${TAILSCALE_ARCH}/systemd/tailscaled.service" /etc/systemd/system/
    sudo sed -i 's|/usr/sbin/tailscaled|/usr/local/bin/tailscaled|g' /etc/systemd/system/tailscaled.service
    sudo sed -i 's|$FLAGS||g' /etc/systemd/system/tailscaled.service
    sudo systemctl daemon-reload
    sudo systemctl enable tailscaled
    
    rm -rf "tailscale_${TAILSCALE_VERSION}_${TAILSCALE_ARCH}" "$TAILSCALE_TGZ"
    echo "  ✅ Tailscale インストール完了"
fi

# --------------------------------------------------
# 2. Tailscale 起動・認証
# --------------------------------------------------
echo ""
echo "[2/5] Tailscale を起動中..."

sudo systemctl start tailscaled 2>/dev/null || true
sleep 2

# すでに認証済みかチェック
if tailscale status 2>/dev/null | grep -q "$(hostname)"; then
    echo "  ✅ Tailscale はすでに接続済みです"
else
    echo ""
    echo "[3/5] Tailscale 認証を開始します..."
    echo "  👉 ブラウザが開かない場合は、表示されるURLを手動で開いてください。"
    echo ""
    sudo tailscale up --accept-routes --ssh
    echo ""
    echo "  ✅ Tailscale 接続完了"
fi

echo ""
echo "  === Tailscale IP ==="
tailscale ip -4
echo ""

# --------------------------------------------------
# 4. テザリング自動接続の設定
# --------------------------------------------------
echo ""
echo "[4/5] テザリング自動接続の設定..."

# NetworkManager が使われているか確認
if command -v nmcli &>/dev/null; then
    echo "  ℹ️  NetworkManager を検出しました"
    echo ""
    echo "  💡 テザリングSSIDを追加するには以下のコマンドを実行:"
    echo ""
    echo "     sudo nmcli device wifi connect \"SSID\" password \"パスワード\""
    echo ""
    echo "  登録済みのWi-Fiネットワーク:"
    nmcli -f name,autoconnect,autoconnect-priority connection 2>/dev/null | head -10 || true
elif [ -f "/etc/wpa_supplicant/wpa_supplicant.conf" ]; then
    echo "  ℹ️  現在のWi-Fi設定:"
    grep -E 'ssid|priority' /etc/wpa_supplicant/wpa_supplicant.conf | head -20 || true
    echo ""
    echo "  💡 テザリングSSIDを追加: sudo nano /etc/wpa_supplicant/wpa_supplicant.conf"
fi

# --------------------------------------------------
# 5. Mac側SSH config テンプレート
# --------------------------------------------------
echo ""
echo "[5/5] Mac側のSSH設定テンプレート"

TS_IP=$(tailscale ip -4 2>/dev/null || echo "<Tailscale_IP>")

echo ""
echo "  Macの ~/.ssh/config に以下を追加してください:"
echo ""
echo "  # Tailscale 経由のSSH"
echo "  Host raspi-ts"
echo "      HostName ${TS_IP}"
echo "      User taki"
echo "      IdentityFile ~/.ssh/id_ed25519"
echo "      ProxyCommand /opt/homebrew/bin/tailscale nc %h %p"
echo ""

echo "========================================"
echo " セットアップ完了！"
echo "========================================"
echo ""
echo " Mac から接続:"
echo "   ssh raspi-ts"
echo ""
echo " スマホのテザリングをON → ラズパイが自動接続 → Tailscale経由でSSH可能"
echo ""
