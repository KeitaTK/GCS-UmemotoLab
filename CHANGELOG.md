# Changelog

All notable changes to GCS-UmemotoLab will be documented in this file.

---

## [2026-07-13] RTK UART2 Direct Injection — GA リリース

### Added
- **RTK UART2 Direct Injection アーキテクチャ**: MAVLink GPS_RTCM_DATA に依存しない、RTCM3 の F9P UART2 直接注入を実装
  - `rtk_tools/rtk_direct_inject.py` — RTCM注入 + RTK FIXED 待機の自動化スクリプト
  - `rtk_tools/rtk_forwarder_service.py` — NTRIP/TCP → UART2 シリアル転送サービス
  - `rtk_tools/f9p_rover_config.py` — Rover 側 F9P の UART2 RTCM3 入力 + UBX 出力設定
  - `rtk_tools/f9p_fix_monitor.py` — UBX-NAV-PVT の carrSoln による RTK FIXED 監視
- **systemd サービス**: 起動時自動 RTCM 注入 (`deploy/rtk-uart2-inject.service`)
  - `deploy/install_rtk_uart2_service.sh` — インストーラ
  - `deploy/uninstall_rtk_uart2_service.sh` — アンインストーラ
- **Preflight Check 拡張**: RTK UART2 チェック (`--rtk-uart-port` / `--skip-rtk-uart2` オプション)
  - F9P Rover Config モジュール確認
  - Fix Monitor モジュール確認
  - rtk_forwarder.yml 設定確認
  - UART2 デバイス存在確認
- **ドキュメント**: 新アーキテクチャ設計書とチェックリスト
  - `docs/05-implementation/rtk_direct_uart2_injection_plan.md` — 実装完了に更新
  - `docs/05-implementation/preflight_rtk_checklist_uart2.md` — プリフライトチェックリスト（新規）

### Changed
- **README.md**: RTK タイトル追加、2アーキテクチャ共存図、RTK Quick Start、構造とチェックリスト更新、参考文献追加
- **rtk_direct_uart2_injection_plan.md**: ステータスを「設計フェーズ」→「実装完了」に更新、新規ファイルリンク追加

### Architecture
```
パスA: MAVLink 制御 (従来から継続)
  PC/Mac → SSH → Raspi (mavlink-router) → UART → Pixhawk TELEM1

パスB: RTK UART2 直接注入 (新規)
  基地局F9P → NTRIP/TCP → Raspi (rtk_forwarder) → USB-Serial → Rover F9P UART2
  Rover F9P UART2 → UBX-NAV-PVT → Raspi (Fix監視)
  Rover F9P CAN → Pixhawk CAN1 (位置情報: 維持)
```

### Deprecated
- `app/rtk_tools/rtcm_injector.py`: MAVLink GPS_RTCM_DATA 注入パスは新アーキテクチャでは不要（ファイル自体は後方互換用に維持）

---

## [2026-07-10] RTK 基地局・マルチドローン基盤

### Added
- RTK 基地局 v2 (`rtk_tools/rtk_base_station_v2.py`)
- F9P 設定モジュール (`rtk_tools/f9p_configurator.py`)
- RTCM 転送サービス基盤 (`rtk_tools/rtk_forwarder.py`, `config/rtk_forwarder.yml`)
- F9P Survey-In スクリプト (`scripts/ublox_survey_in.py`)
- GPS Fix 確認 (`scripts/check_gps_fix.py`)
- マルチドローン対応設定 (`config/gcs_multidrone_example.yml`)

---

## [2026-06] GCS MVP

### Added
- MAVLink 通信基盤 (`app/mavlink/connection.py`, `message_router.py`)
- PySide6 UI (`app/ui/main_window.py`, `telemetry_plotter.py`)
- Force Arm 機能 (`app/rtk_tools/command_dispatcher.py`)
- Guided 制御 (`app/rtk_tools/guided_control.py`)
- テレメトリ保存 (`app/rtk_tools/telemetry_store.py`)
- Raspi mavlink-router 構成
- SSH Tunnel 接続方式
- ダミー機テスト (`tests/test_arm_dummy.py`)
- 実機テスト (`tests/test_arm_live.py`)
