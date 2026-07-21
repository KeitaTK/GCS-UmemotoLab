# WiFi切替作業ログ: スマホテザリング → Buffalo-5G-5F50 (大学5F)

**作業日時**: 2026-07-21 (Tue) 14:26 - 14:32 JST
**作業者**: Cline (AI)
**対象機器**: Raspberry Pi 5 (raspi5-1)
**Tailscale IP**: 100.69.75.96

---

## 目的

Raspberry Pi 5 のWiFi接続をスマホテザリングから大学5Fの Buffalo-5G-5F50 (5GHz) に切り替え、起動時に自動接続されるように設定する。

## WiFi認証情報

| 項目 | 値 |
|------|-----|
| SSID | Buffalo-5G-5F50 |
| Password | 3t67rhfc7ccnt |
| Security | WPA2-PSK |

---

## Step 1: 現状確認

### SSH接続

ssh -o ProxyCommand="tailscale nc %h %p" taki@100.69.75.96

結果: OK 接続成功

### WiFi接続状態（変更前）

IN-USE  BSSID              SSID                    MODE   CHAN  RATE        SIGNAL  SECURITY
*       68:E1:DC:AA:5F:52  Buffalo-2G-5F50         Infra  3     260 Mbit/s  100     WPA2
        68:E1:DC:AA:5F:53  Buffalo-2G-5F50-WPA3    Infra  3     260 Mbit/s  100     WPA3
        68:E1:DC:AA:5F:59  Buffalo-5G-5F50         Infra  40    540 Mbit/s  100     WPA2  <- 5GHz
        68:E1:DC:AA:5F:5A  Buffalo-5G-5F50-WPA3    Infra  40    540 Mbit/s  100     WPA3

接続中: Buffalo-2G-5F50 (2.4GHz, channel 3, signal 100%)

### 既存プロファイル（変更前）

| NAME | TYPE | DEVICE | AUTOCONNECT | PRIORITY |
|------|------|--------|-------------|----------|
| Wired connection 1 | ethernet | eth0 | yes | -999 |
| Buffalo-2G-5F50 | wifi | wlan0 | yes | 5 |
| Buffalo-5G-5F50 | wifi | -- | yes | 10 |
| tethering | wifi | -- | yes | 1 |

### IPアドレス（変更前）

| Interface | IP |
|-----------|-----|
| eth0 | 192.168.11.19/24 |
| wlan0 | 192.168.11.50/24 |
| tailscale0 | 100.69.75.96/32 |

### Tailscale状態（変更前）

100.69.75.96     raspi5-1         linux  active; direct 10.0.3.33:21124
100.75.83.95     mac-mini         macOS  -
100.80.225.4     macbook-air      macOS  active; direct 10.50.19.27:41641
 SSID 'Buffalo-5G-5F50' found.

原因分析:
- Buffalo-5G-5F50 (5GHz, channel 40, BSSID 68:E1:DC:AA:5F:59) が断続的にしか表示されない
- 5GHz帯の電波がRaspberry Piの設置場所まで安定して届いていない
- 5GHzは2.4GHzより壁などの障害物に弱く、到達距離が短い

---

## Step 4: 最終状態

### WiFi接続

接続中: Buffalo-2G-5F50 (2.4GHz) OK

| NAME | TYPE | DEVICE | AUTOCONNECT | PRIORITY |
|------|------|--------|-------------|----------|
| Buffalo-5G-5F50 | wifi | -- | yes | 20 <- 5GHz (最優先、電波来たら自動切替) |
| Buffalo-2G-5F50 | wifi | wlan0 | yes | 10 <- 2.4GHz (現在接続中) |
| tethering | wifi | -- | yes | 0  <- テザリング (バックアップ) |

### IPアドレス（変更なし）

| Interface | IP | Change |
|-----------|-----|--------|
| eth0 | 192.168.11.19/24 | 変更なし |
| wlan0 | 192.168.11.50/24 | 変更なし |
| tailscale0 | 100.69.75.96/32 | 変更なし |

### Tailscale状態

100.69.75.96     raspi5-1         linux  active; direct 10.0.3.33:21124
100.102.197.101  iphone-13-mini   iOS    offline, last seen 2m ago
100.75.83.95     mac-mini         macOS  -
100.80.225.4     macbook-air      macOS  active; direct 10.50.19.27:41641
100.123.158.105  raspi5           linux  offline, last seen 15d ago
100.105.70.118   ts-kanban-nambu  linux  -

---

## 結果サマリ

### 完了した設定

1. Buffalo-5G-5F50 プロファイル作成・パスワード設定
2. Autoconnect優先度設定:
   - 5GHz: priority 20（最優先）
   - 2.4GHz: priority 10（次点）
   - テザリング: priority 0（最低）
3. テザリング設定維持（削除せずpriority 0で残存）

### 制限事項

- 5GHz帯の電波が不安定で、現在の設置場所では Buffalo-5G-5F50 に接続できない
- 現在は2.4GHzの Buffalo-2G-5F50 で安定接続中
- 5GHz電波が入れば autoconnect priority 20 により自動的に5GHzに切替
- 起動時も優先度に従い自動接続される

### 設定ファイル更新

Tailscale IP (100.69.75.96) に変更がないため、リポジトリ内の設定ファイル更新は不要。

### 推奨事項

1. Piの設置場所を5GHz電波の届きやすい場所に移動すれば自動切替される
2. 2.4GHzでも十分な通信速度（260Mbps）が得られている
3. WPA3対応の Buffalo-5G-5F50-WPA3 も存在するが、互換性のためWPA2を使用

---

## 使用コマンド一覧

SSH接続:
  ssh -o ProxyCommand="tailscale nc %h %p" taki@100.69.75.96

WiFiスキャン:
  nmcli device wifi list

プロファイル確認:
  nmcli connection show
  nmcli connection show Buffalo-5G-5F50
  nmcli connection show Buffalo-2G-5F50

プロファイル設定:
  sudo nmcli connection modify Buffalo-5G-5F50 wifi-sec.psk "3t67rhfc7ccnt"
  sudo nmcli connection modify Buffalo-5G-5F50 connection.autoconnect-priority 20
  sudo nmcli connection modify Buffalo-2G-5F50 connection.autoconnect-priority 10
  sudo nmcli connection modify tethering connection.autoconnect-priority 0

プロファイル再作成:
  sudo nmcli connection delete Buffalo-5G-5F50
  sudo nmcli connection add type wifi con-name "Buffalo-5G-5F50" \
      ifname wlan0 ssid "Buffalo-5G-5F50" \
      wifi-sec.key-mgmt wpa-psk wifi-sec.psk "3t67rhfc7ccnt" \
      connection.autoconnect yes connection.autoconnect-priority 20

接続試行:
  sudo nmcli device wifi connect "Buffalo-5G-5F50" password "3t67rhfc7ccnt"

ログ確認:
  sudo journalctl -u NetworkManager --no-pager -n 50 | grep 5F50

状態確認:
  nmcli -f name,type,device,autoconnect,autoconnect-priority connection
  ip addr show | grep inet
  tailscale status
  tailscale ip -4
