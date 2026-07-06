# Active Context — GCS-UmemotoLab

## 現在取り組んでいること

### RTK パイプライン実運用整備（✅ 完了）
- **全体アーキテクチャ**: Windows PC (F9P) → TCP:2101 → Raspi → serial(/dev/ttyAMA0) → Pixhawk → CAN → F9P Rover
- **Pixhawk 側パラメータ**: `GPS1_TYPE=9` (DroneCAN), `CAN_D1_PROTOCOL=1` (DroneCAN), `GPS_DRV_OPTIONS=64` (Rover側RTCM受信有効化)
- **base_station 設定**: `mode=auto`（USBポート自動検出 + 60秒単独測位で基準座標自動取得）
- **Raspi シリアル設定**: `/dev/ttyAMA0` @ 1M baud, RTS/CTS フロー制御有効 (`serial_rtscts: true`)

### Memory Bank 整備（🔄 進行中）
- `memory-bank/product_context.md` 作成済み
- `memory-bank/active_context.md` 更新（本ファイル）
- `memory-bank/progress.md` 更新
- `memory-bank/decision_log.md` 更新
- `memory-bank/system_patterns.md` 作成済み

## 最近の変更

| 日付 | 変更内容 | 影響範囲 |
|------|----------|----------|
| 2026-07-07 | **rtk_base_station_v2.py autoモード実装**: USB自動検出 + 単独測位で基準座標自動設定 | `rtk_base_station_v2.py`, `config/config.yml` |
| 2026-07-07 | **Windowsエラー修正3件**: multiprocessing.spawn対応(`freeze_support()`)、COMポート統一(COM3→COM8)、設定ファイルOS分離(`config.win.yml`) | `rtk_base_station_v2.py`, `config/config.win.yml` |
| 2026-07-07 | **RTCM false preamble バグ修正**: reserved bits チェック追加。0xD3検出後、予約ビット非ゼロの場合にfalse preambleとしてスキップ | `rtk_base_station_v2.py` (L283-287) |
| 2026-07-07 | **RTCM生ログ保存機能**: `logs/rtcm_raw_{timestamp}.bin` に全受信RTCMフレームをバイナリ保存 | `rtk_base_station_v2.py` (L219-244, 305-310) |
| 2026-07-07 | **Mavlink_raspi/RTK/ 整備**: `rtcm_injector.py`（RTCM→GPS_RTCM_DATA MAVLink変換）と `setup_EKF_Observer4.py`（EKF Observer設定）をRaspi上で整備 | Raspi 上の `Mavlink_raspi/RTK/` |
| 2026-07-07 | **RTS/CTS + 1M baud対応**: Raspi→Pixhawk間のシリアル通信を1Mbps + ハードウェアフロー制御に高速化 | `raspi/config.yml`, `app/mavlink/connection.py` |
| 2026-07-06 | config/ 完全統合 — config.yml 一元化 + raspi/ 移行完了 | `config/config.yml`, `raspi/`, `rtk_tools/config_loader.py` |
| 2026-06-17 | Web UIをカード方式に統一、PySide6風タブ削除 | index.html, style.css, dashboard.js, controls.js |
| 2026-06 | `pyproject.toml` 導入、UV 移行完了 | プロジェクト全体の依存管理 |

## 次のステップ

### 優先度: 高
- [ ] **RTK LED 未点灯調査**: Pixhawk 側で RTK Fix 時に LED が点灯しない問題を調査中。GPS_DRV_OPTIONS や CAN パラメータの確認が必要
- [ ] **実機飛行テスト**: プロペラあり実飛行でのRTK FIXED維持確認、全パイプラインエンドツーエンド検証
- [ ] **長時間運用テスト**: メモリリーク・CPU使用率の長期監視

### 優先度: 中
- [ ] **個別制御ボタン（Arm/Disarm/Takeoff/Land/Guided）のカード内実装**: Web UIの各ドローンカードに個別制御ボタンを追加
- [ ] **UIの自由レイアウト編集**: 複数パネルのドラッグ＆ドロップ再配置
- [ ] **NTRIP再取得**: RTCMストリーム切断時の NTRIP 再接続・認証再取得の強化

### 優先度: 低
- [ ] **GPS拡張（Phase 1-3）**: GPS_DOP 表示、衛星コンステレーション可視化
- [ ] **Sphinx ドキュメントの全モジュールカバレッジ**: `docs_sphinx/` の `.rst` ファイル拡充
- [ ] **CI/CD パイプライン**: GitHub Actions での自動テスト・ビルド

## アクティブな課題・検討事項

### 技術的課題
1. **RTK LED 未点灯（調査中）**: Pixhawk 側で RTK FIXED 達成時にも関わらず RTK LED が点灯しない。GPS_DRV_OPTIONS=64（RTCM受信有効化）、CAN_D1_PROTOCOL=1、GPS1_TYPE=9 の設定は投入済み。CAN経由でのF9P Rover → Pixhawk 間のRTCM注入パスを検証中。
2. **Raspi 側の依存管理**: UV の optional-dependencies と `requirements_raspi.txt` の二重管理状態。将来的に UV 一本化するか検討が必要。
3. **Python 3.14 要件**: `pyproject.toml` で `>=3.14` としているが、Raspi の標準 Python は 3.11 系。Raspi 側では `pyproject.toml` を参照せず `requirements_raspi.txt` を使用する運用で回避中。
4. **MAVLink メッセージパースの互換性**: `message_router.py` で pymavlink の新旧 API（`parse_buffer` / `parse_char_array` / `decode`）のフォールバック対応をしているが、pymavlink のバージョンアップで破壊的変更が入る可能性。

### 設計上の検討事項
1. **設定ファイルの優先順位**: `$GCS_CONFIG_PATH` > `config.local.yml` > `config.{win,mac}.yml` > `config.yml`。ユーザー固有設定とGit管理下設定の分離は適切か。
2. **autoモードの堅牢性**: 単独測位失敗時のフォールバック（manualモードへの誘導）はあるが、USBポート検出失敗時のリカバリが不十分。
3. **RTCM raw log のローテーション**: 現在無制限に書き込み続けるため、長時間運用でディスク容量を圧迫する可能性。
4. **ログローテーション**: 現在 5MB x 5世代。長時間フライトでログ消失のリスクはないか。

### 運用上の注意点
- **Force Arm は屋内テスト専用**: 実飛行では絶対に使用しない。テスト後は `dispatcher.restore_arm_params()` でデフォルトに戻す。
- **RTCM ホスト設定**: Windows/u-center と Raspberry Pi/GCS が別ホストの場合は `rtcm_host` を配信元 IP に変更する。
- **SSH トンネル**: 方式Aでは GCS 起動前に別ターミナルで SSH トンネルを確立しておく必要がある。
- **autoモード使用時**: F9PをUSB接続した状態で起動すること。USB検出に失敗した場合は `mode=manual` に切り替えて `fixed_lat/lon/alt` を手動設定する。
