# Product Context — GCS-UmemotoLab

## プロジェクト名
**GCS UmemotoLab** — ArduPilot 地上管制局

## 目的
macOS/Windows/Linux 上で ArduPilot ドローンを制御・監視する**マルチドローン対応の地上管制局（GCS）システム**。

Raspberry Pi 5 を通信ブリッジとして使い、Pixhawk 系フライトコントローラと MAVLink v2 で通信する。RTK/RTCM 補正、マルチドローン識別、実機テレメトリー、コマンド送信を統合的に扱う。

## 概要

| 項目 | 内容 |
|------|------|
| **通信方式** | MAVLink v2 over UDP/Serial |
| **ハードウェア** | PC + Raspberry Pi 5（通信ブリッジ）+ Pixhawk |
| **言語** | Python 3.14+ |
| **UI** | PySide6 (Qt 6) |
| **特徴** | マルチドローン、RTK補正、プリチェック無効Arm |

## アーキテクチャ図

```
┌──────────────────────────┐
│        PC/Mac (GCS)      │
│  ┌────────────────────┐  │
│  │  Python App        │  │
│  │  (PySide6 + MAVLink)│  │
│  └─────────┬──────────┘  │
└────────────┼─────────────┘
             │ SSH Tunnel / Tailscale
      (UDP/TCP MAVLink)
             │
┌────────────┼─────────────┐
│  Raspberry Pi 5          │
│  ┌────────────────────┐  │
│  │  mavlink-router    │  │
│  │  ttyAMA0→UDP:14550 │  │
│  └─────────┬──────────┘  │
└────────────┼─────────────┘
             │ UART (GPIO 14/15)
             │ Baud: 115200
┌────────────┼─────────────┐
│    Pixhawk (ArduPilot)   │
│    TELEM1 接続           │
│    System ID: 1          │
└──────────────────────────┘
```

### Raspi 配線

| Pixhawk TELEM1 | Raspi GPIO | 物理Pin |
|----------------|------------|---------|
| TX → | GPIO 15 (RX) | Pin 10 |
| RX → | GPIO 14 (TX) | Pin 8 |
| RTS → | GPIO 17 | Pin 11 |
| CTS → | GPIO 16 | Pin 36 |
| GND → | GND | Pin 6 |

## 接続方式

| 方式 | 説明 |
|------|------|
| **方式 A: SSHトンネル経由（推奨）** | GCS PC/Mac と Raspi が別ネットワークでも Tailscale 経由で接続可 |
| **方式 B: 同一ネットワーク** | Mac/Raspi が同じ WiFi に接続されている場合、Raspi のローカル IP に直接 UDP |
| **方式 C: Raspi上でGCS直接実行** | Raspi 上で `app/main.py` を直接実行（ヘッドレスも可） |

## 主要機能一覧

| 機能 | 説明 | 状態 |
|------|------|------|
| **テレメトリ受信** | HEARTBEAT, SYS_STATUS, GPS_RAW_INT, GLOBAL_POSITION_INT, バッテリー情報 | ✅ 実装済 |
| **機体制御** | アーム/ディスアーム、離陸/着陸、Guided制御（位置・速度） | ✅ 実装済 |
| **強制アーム** | ARMING_CHECK 等を無効化してアーム（屋内テスト用） | ✅ 実装済 |
| **RTK補正** | RTCMストリームの受信と GPS_RTCM_DATA としてドローンへ注入 | ✅ 実装済 |
| **マルチドローン** | System ID による複数機の識別・同時制御 | ✅ 実装済 |
| **ロギング** | 全MAVLinkメッセージの記録（RotatingFileHandler, 5MB x 5世代） | ✅ 実装済 |
| **グラフ表示** | pyqtgraph による NAMED_VALUE_FLOAT のリアルタイムグラフ | ✅ 実装済 |
| **コマンドACK追跡** | COMMAND_ACK 待機・タイムアウト検出・最大3回自動リトライ | ✅ 実装済 |
| **接続エラー回復** | UDPタイムアウト検出、シリアル自動再接続（exponential backoff） | ✅ 実装済 |
| **RTCM再接続** | RTCMストリーム切断時のTCP再接続（指数バックオフ） | ✅ 実装済 |
| **マルチタブUI** | Dashboard / Graph / Raw Data の3タブ構成 | ✅ 実装済 |

## 技術スタック

| 技術 | 用途 |
|------|------|
| **Python 3.14+** | 開発言語 |
| **PySide6 6.11+** | GUIフレームワーク（Qt 6） |
| **pymavlink 2.4.49+** | MAVLink v2 プロトコル実装 |
| **pyqtgraph 0.14+** | リアルタイムグラフ描画 |
| **matplotlib 3.11+** | 静的グラフ生成 |
| **pyserial 3.5+** | シリアル通信（Pixhawk直結時） |
| **PyYAML 6.0+** | 設定ファイル（YAML） |
| **pytest 9.0+** | テストフレームワーク |
| **pytest-mock 3.15+** | モックユーティリティ |
| **UV** | Pythonパッケージマネージャー（pipの10-100倍高速） |

## 対応プラットフォーム

- **macOS** — 主要開発環境（GUI + SITL テスト）
- **Windows** — RTK基地局運用、GUI 実行
- **Linux (Raspberry Pi 5)** — 通信ブリッジ（mavlink-router）、ヘッドレスバックエンド

## 外部依存（Raspberry Pi 側）

| 依存 | 用途 |
|------|------|
| **mavlink-router** | ttyAMA0 → UDP:14550 へ MAVLink 中継 |
| **Tailscale** | リモート接続用 VPN（PC ↔ Raspi 間 SSH トンネル） |
| **systemd** | mavlink-router の常駐管理 |
| **UART有効化** | `/boot/firmware/config.txt` の `enable_uart=1`, `dtoverlay=uart0` |

## プロジェクト構造

```
GCS-UmemotoLab/
├── README.md                  # プロジェクトREADME
├── pyproject.toml             # UV/Python プロジェクト定義
├── requirements.txt           # 標準依存（pip互換）
├── requirements_raspi.txt     # Raspi向け最小依存
├── uv.lock                    # UV ロックファイル
├── config/
│   ├── gcs.yml                # デフォルト設定
│   ├── gcs_local.yml          # ローカル開発用
│   ├── gcs_production.yml     # 本番用（SSHトンネル）
│   ├── gcs_drone.yml          # ドローン別設定
│   ├── gcs_multidrone_example.yml  # マルチドローン例
│   └── rtk_forwarder.yml      # RTK転送サービス設定
├── app/
│   ├── main.py                # エントリーポイント（GUI）
│   ├── logging_config.py      # ロギング設定
│   ├── dummy_sitl.py          # ダミーSITL
│   ├── api/
│   │   └── server.py          # REST API サーバー
│   ├── ui/
│   │   ├── main_window.py     # メインUI + 制御ボタン（3タブ構成）
│   │   └── telemetry_plotter.py  # グラフ描画
│   ├── mavlink/
│   │   ├── connection.py      # UDP/Serial接続管理 + エラーハンドリング
│   │   └── message_router.py  # メッセージルーター + COMMAND_ACK処理
│   └── rtk_tools/
│       ├── command_dispatcher.py  # コマンド送信（Arm/ForceArm等）+ リトライ
│       ├── guided_control.py      # Guidedモード制御
│       ├── telemetry_store.py     # テレメトリデータ保持
│       ├── rtcm_reader.py         # RTCM TCP受信
│       └── rtcm_injector.py       # RTCM → GPS_RTCM_DATA変換
├── rtk_tools/
│   └── config_loader.py       # 設定ファイル解決（優先順位付き）
├── tests/
│   ├── test_arm_dummy.py      # ダミー機アームテスト
│   ├── test_arm_live.py       # 実機アームテスト
│   ├── test_command_dispatcher.py
│   ├── test_command_retry.py  # コマンドリトライテスト（8ケース）
│   ├── test_connection_errors.py  # 接続エラーテスト（19ケース）
│   ├── test_telemetry_store.py
│   ├── test_rtk_integration.py
│   ├── test_rtk_base_station_integration.py
│   └── test_phase_c_integration.py
├── docs/                      # 詳細ドキュメント（23ファイル）
├── docs_sphinx/               # Sphinxドキュメント生成
├── scripts/                   # ビルド・デプロイスクリプト
└── memory-bank/               # Cline Memory Bank（本ディレクトリ）
```

## 参考資料

- [MAVLink Protocol](https://mavlink.io/en/)
- [ArduPilot Docs](https://ardupilot.org/dev/)
- [pymavlink](https://github.com/ArduPilot/pymavlink)
- [mavlink-router](https://github.com/mavlink-router/mavlink-router)
- [PySide6](https://doc.qt.io/qtforpython/)
- [UV](https://docs.astral.sh/uv/)
- [Tailscale](https://tailscale.com/)
