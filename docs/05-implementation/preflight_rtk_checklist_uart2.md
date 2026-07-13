# Preflight RTK チェックリスト (UART2)

**最終更新**: 2026-07-13  
**ステータス**: 運用中  
**対象**: RTK UART2 Direct Injection 構成でのプリフライトチェック

---

## 1. 概要

UART2 直接注入構成での飛行前チェック手順です。
`tools/preflight_check.py` による自動チェックに加え、目視・手動で確認すべき項目をまとめています。

### 自動化スクリプト

```bash
# Raspi 上で実行
cd ~/GCS-UmemotoLab
source .venv/bin/activate

# RTK UART2 を含む全項目チェック
python tools/preflight_check.py --rtk-uart-port /dev/ttyUSB0

# モーター試験をスキップ（プロペラ非取り外し時）
python tools/preflight_check.py --rtk-uart-port /dev/ttyUSB0 --no-motor

# RTK UART2 チェックのみスキップ（非RTK飛行時）
python tools/preflight_check.py --skip-rtk-uart2
```

`--rtk-uart-port` を指定すると、以下の UART2 固有チェックが追加されます：

| チェック項目 | 内容 | 判定基準 |
|-------------|------|---------|
| F9P Rover Config モジュール | `f9p_rover_config.py` の import 確認 | モジュール存在 |
| Fix Monitor モジュール | `f9p_fix_monitor.py` の import 確認 | モジュール存在 |
| rtk_forwarder.yml 設定 | `forward.type` が `serial` か確認 | type=serial |
| UART2 デバイス存在 | `/dev/ttyUSB0` の有無 | デバイスファイル存在 |

---

## 2. チェックリスト（全項目）

### 2.1 ハードウェア確認

- [ ] **F9P UART2 配線**: Pin 2(RX2) → USB-Serial TX, Pin 3(TX2) → USB-Serial RX, Pin 6(GND) → GND
- [ ] **USB-Serial アダプタ**: Raspi に接続、`ls /dev/ttyUSB*` で認識確認
- [ ] **Pixhawk TELEM1 配線**: GPIO 14/15 接続、mavlink-router 稼働中
- [ ] **F9P CAN 接続**: Pixhawk CAN1 に接続、QGC で GPS データ受信確認
- [ ] **バッテリー**: Pixhawk に給電、LED 点灯
- [ ] **プロペラ**: モーター試験前に必ず取り外し

### 2.2 基地局確認

- [ ] **基地局 F9P Survey-In 完了**: `python scripts/ublox_survey_in.py --status` で確認
- [ ] **RTCM3 ストリーム配信中**: 基地局が TCP:2101 で RTCM3 配信中であること
- [ ] **基地局ネットワーク到達性**: Raspi から基地局に ping 到達

### 2.3 Rover F9P 設定確認（初回のみ）

```bash
python rtk_tools/f9p_rover_config.py --port /dev/ttyUSB0
```

- [ ] **UART2 RTCM3 入力有効**: `CFG-UART2INPROT-RTCM3X = 1`
- [ ] **UART2 UBX 出力有効**: `CFG-UART2OUTPROT-UBX = 1`
- [ ] **ボーレート**: 115200 bps

### 2.4 RTCM 注入状態

```bash
# systemd サービス確認
systemctl status rtk-uart2-inject
journalctl -u rtk-uart2-inject -f
```

- [ ] **rtk-uart2-inject サービス稼働中**: Active: active (running)
- [ ] **RTCM フレーム受信中**: ログに `frames_sent` 増加が確認できる
- [ ] **エラーなし**: `journalctl` に `ERROR` がない

### 2.5 RTK FIXED 確認

```bash
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyUSB0
```

- [ ] **carrSoln = 2 (RTK FIXED)**: UBX-NAV-PVT で確認
- [ ] **numSV ≥ 10**: 衛星数が十分
- [ ] **hAcc < 0.05 m**: 水平精度が RTK 品質
- [ ] **Fix 持続 30 秒以上**: 瞬時的な Fixed ではなく安定していること

### 2.6 Pixhawk 飛行準備

- [ ] **GPS_RAW_INT fix_type = 6**: Pixhawk 側も RTK FIXED 認識
- [ ] **EKF 健全**: EKF.flags の各ビットがセットされている
- [ ] **バッテリー電圧正常**: ≥ 3.7V/cell
- [ ] **プリチェック PASS**: `tools/preflight_check.py` の全項目が PASS

---

## 3. 自動チェック成功時の出力例

```
[preflight_check] =======================================================
[preflight_check]   CHECK ALL: PASS
[preflight_check] =======================================================

Summary:
  Total: 12 / Pass: 12 / Fail: 0

RTK UART2:
  [PASS] f9p_rover_config module available
  [PASS] f9p_fix_monitor module available
  [PASS] rtk_forwarder.yml forward.type = serial
  [PASS] UART2 device /dev/ttyUSB0 present
```

---

## 4. トラブルシューティング

| 現象 | 考えられる原因 | 対処 |
|------|--------------|------|
| `f9p_rover_config` import エラー | 依存パッケージ不足 | `uv sync` 再実行 |
| `rtk_forwarder.yml` type ≠ serial | 設定未変更 | `forward.type: serial` に修正 |
| `/dev/ttyUSB0` なし | USB-Serial 非認識 | `dmesg \| grep tty` で確認 |
| `carrSoln=1` (FLOAT) から進まない | 電波環境不良 / 基地局距離 | 場所を移動、2分以上待機 |
| `carrSoln=0` (NONE) | RTCM未到達 | `systemctl status rtk-uart2-inject` 確認 |
| `fix_type < 6` (Pixhawk側) | CAN未接続 / GPS_AUTO_SWITCH | QGCでGPS状態確認 |

---

## 5. 関連ドキュメント

- [RTK UART2 直接注入 設計書](rtk_direct_uart2_injection_plan.md)
- [RTK基地局 実装計画](RTK_BASE_STATION_IMPLEMENTATION.md)
- [RTK統合ガイド](../03-operations/rtk_integration_guide.md)
- [プリフライトチェックスクリプト](../../tools/preflight_check.py)
