# Raspi接続設定 (mavlink-router)

## 現在の状態

現在のRaspi側 `/etc/mavlink-router/main.conf`:

```ini
[General]
ReportStats=false
MavlinkVersion=2.0

[UartEndpoint pixhawk]
Device = /dev/ttyAMA0
Baud = 115200

[UdpEndpoint gcs]
Address = 0.0.0.0
Port = 14550
Mode = Server
```

PC側 `config/gcs_raspi_bridge.yml`:
```yaml
connection_type: udp
udp_listen_port: 14551
drones:
  drone1:
    system_id: 1
    endpoint: "192.168.11.19:14550"
rtcm_enabled: false
```

## 問題

- PC側は UDP 14551 で待受 (udpin)
- Raspi側は UDP 14550 で待受 (Server mode)
- お互いに「相手からのパケット待ち」で双方向通信が確立しない

ただし mavlink-router はデフォルトで TCP 5760 も待受しており、PC側が TCP 5760 に接続すると通信が確立する。

## 解決策A: Raspi側をUDP Clientモードに変更 (推奨)

/etc/mavlink-router/main.conf の [UdpEndpoint gcs] を修正:

```ini
[UdpEndpoint gcs]
Address = 192.168.11.65
Port = 14551
Mode = Normal
```

変更後:
```bash
sudo systemctl restart mavlink-router
```

すると Raspiから能動的に PC(192.168.11.65:14551) にUDP送信するようになり、
PC側がそれを受信して双方向通信が確立する。

## 解決策B: TCPのまま運用 (現状維持)

config/gcs_raspi_bridge.yml を以下のように書き換えることでTCP接続:
```yaml
endpoint: "192.168.11.19:5760"
```

ただしMavlinkConnectionの再接続に問題あり。

## 参考

- mavlink-router ドキュメント: https://github.com/mavlink-router/mavlink-router
- PC IP: 192.168.11.65 (enp8s0) / 192.168.11.40 (wlp7s0)
- Raspi IP: 192.168.11.19
- mavlink-router TCP: 5760
- mavlink-router UDP: 14550
- PC listen UDP: 14551
