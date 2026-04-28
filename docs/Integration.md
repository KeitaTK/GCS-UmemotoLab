# GCS-UmemotoLab 総合ドキュメント

この文書は、GCS-UmemotoLab の機能・構成・運用・検証を1か所にまとめた入口です。

## プロジェクト概要

GCS-UmemotoLab は、Windows 上で動作する ArduPilot 用カスタム GCS です。Raspberry Pi 5 を通信ブリッジとして使い、Pixhawk 系フライトコントローラと MAVLink v2 で通信します。RTK/RTCM 補正、マルチドローン識別、実機テレメトリー、コマンド送信をまとめて扱います。

### 構成

- Windows PC: GCS 本体、RTCM 配信元、UI 実行
- Raspberry Pi 5: 中継・受信・RTCM 注入
- Pixhawk / ArduPilot: 飛行制御とテレメトリー

```text
Windows PC -> TCP/Wi-Fi -> Raspberry Pi 5 -> Serial/USB -> Pixhawk
```

## 使い方の入口

### 1. 起動

```powershell
# Windows 側
python rtk_base_station.py --serial-port COM8 --baudrate 115200 --tcp-host 0.0.0.0 --tcp-port 2101 --log-level INFO

# Raspberry Pi 側
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && source .venv/bin/activate && python app/backend_server.py"
```

### 2. 設定

- `config/gcs.yml`: 標準設定
- `config/gcs_local.yml`: ローカル実行用設定
- `config/gcs.user.local.yml`: Git 管理外の個人設定
- `config/rtk_forwarder.yml`: RTK 転送サービス設定

### 3. 主要コンポーネント

- `app/main.py`: GUI 実行の入口
- `app/backend_server.py`: Raspberry Pi 用ヘッドレス実行
- `rtk_base_station.py`: Windows 側 RTK 基地局
- `app/mavlink/rtcm_reader.py`: RTCM 受信
- `app/mavlink/rtcm_injector.py`: RTCM → GPS_RTCM_DATA 変換
- `app/mavlink/message_router.py`: MAVLink メッセージ中継

## RTK / RTCM

RTK まわりの構成は、Windows 側で RTCM を受信して Raspberry Pi へ配信し、Pi 側で Pixhawk へ注入する流れです。

### 標準フロー

1. `rtk_base_station.py` が ublox から RTCM を受信
2. TCP で Raspberry Pi に配信
3. `backend_server.py` が RTCM を受信
4. `RtcmInjector` が MAVLink `GPS_RTCM_DATA` に変換
5. Pixhawk が RTK Fix に遷移

### 実機確認ポイント

- COM ポートは COM8
- Raspberry Pi 側の `rtcm_host` は Windows PC の LAN IP に合わせる
- `rtcm_enabled: true` を有効にする

## テストと検証

- ユニットテスト: `pytest tests/`
- RTK 統合: `tests/test_rtk_integration.py`
- 基地局統合: `tests/test_rtk_base_station_integration.py`
- Phase C 統合: `tests/test_phase_c_integration.py`

### 実行例

```bash
python tests/test_rtk_base_station_integration.py
```

```bash
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && source .venv/bin/activate && python tests/test_phase_c_integration.py"
```

## 運用メモ

- Raspberry Pi では `app/backend_server.py` をヘッドレス実行する
- 監視や常駐運用は `scripts/` 配下の補助スクリプトを使う
- 詳細な履歴は `docs/development_history.md` を参照する

## トラブルシューティング

- `Connection refused`: Windows 側基地局または `rtcm_host` 設定を確認
- `Permission denied (publickey)`: SSH 鍵設定を確認
- `serial.SerialException`: COM ポートまたは接続ケーブルを確認
- `RTK Fix が出ない`: u-center 側の RTCM 受信設定と注入ログを確認

## 参照コード

- [README](../README.md)
- [RTK 基地局実装レポート](RTK_BASE_STATION_FINAL_REPORT.md)
- [開発履歴](development_history.md)
