# UART2 Fix監視 移行サマリ

## 移行概要

| 項目 | 旧方式 (Before) | 新方式 (After) |
|------|----------------|----------------|
| **Fix監視ソース** | UBX-NAV-PVT (UART2 TX2 直接読取) | MAVLink GPS_RAW_INT.fix_type (GCS REST API) |
| **監視スクリプト** | `rtk_tools/f9p_fix_monitor.py` | `rtk_tools/gcs_fix_monitor.py` |
| **UART2 用途** | RTCM3入力 + UBX出力 (双方向) | RTCM3入力専用 (UBX出力=無効) |
| **必要なHW変更** | — | なし（ゼロ） |
| **ログフォーマット** | `rtcm_fix_transition.log` (CSV) | 同左（互換性維持） |

## 変更ファイル一覧

### 新規作成

| ファイル | 説明 |
|----------|------|
| `rtk_tools/gcs_fix_monitor.py` | MAVLink GPS_RAW_INT.fix_type を GCS REST API 経由で監視する新スクリプト |

### 変更

| ファイル | 変更内容 |
|----------|---------|
| `rtk_tools/f9p_fix_monitor.py` | `[DEPRECATED]` マーク追加。モジュール本体は残置 |
| `rtk_tools/f9p_rover_config.py` | `CFG-UART2OUTPROT-UBX`: 1→0, `CFG-MSGOUT-UBX-NAV-PVT-UART2`: 1→0 |
| `scripts/operation_full.sh` | STEP5: Fix監視を MAVLink ベースに変更 |
| `README.md` | アーキテクチャ図・データフロー図・手順書を更新 |

### 新規ドキュメント

| ファイル | 説明 |
|----------|------|
| `docs/ctrl/migration_summary.md` | 本ファイル |

## アーキテクチャ変更点

### 旧: UART2双方向
```
Raspi TX → F9P UART2 RX2 (RTCM3注入)
F9P UART2 TX2 → Raspi RX (UBX-NAV-PVT監視)
```

### 新: UART2 RTCM注入専用 + MAVLink Fix監視
```
Raspi TX → F9P UART2 RX2 (RTCM3注入専用)
F9P → DroneCAN → Pixhawk → MAVLink GPS_RAW_INT → GCS REST API → gcs_fix_monitor.py
```

## fix_type マッピング（ログ互換性）

`rtcm_fix_transition.log` の `carrSoln` 列には以下のマッピング値を書き込む：

| MAVLink fix_type | 名称 | carrSoln (ログ互換値) |
|-----------------|------|----------------------|
| 0〜4 | NO_GPS 〜 DGPS | 0 (NONE) |
| 5 | RTK_FLOAT | 1 (FLOAT) |
| 6 | RTK_FIXED | 2 (FIXED) |
| 7〜8 | STATIC / PPP | 0 (NONE) |

## F9P UART2 設定変更

`f9p_rover_config.py` の設定キー変更：

```python
# 旧
('CFG-UART2OUTPROT-UBX',      1),   # UBX 出力を有効化
('CFG-MSGOUT-UBX-NAV-PVT-UART2', 1), # NAV-PVT 出力

# 新
('CFG-UART2OUTPROT-UBX',      0),   # UBX 出力を無効化 (UART2=RTCM注入専用)
('CFG-MSGOUT-UBX-NAV-PVT-UART2', 0), # NAV-PVT 出力 無効
```

Verify期待値: `CFG-UART2OUTPROT-UBX` expected=1→0

## 使用方法

### Fix監視（新方式）
```bash
# GCS起動済みの状態で
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --timeout 120
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --once
python rtk_tools/gcs_fix_monitor.py --gcs-url http://localhost:8000 --monitor
```

### F9P Rover 再設定（UBX出力無効化）
```bash
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4 --verify-only
```

### 旧方式（非推奨・参照用）
```bash
# ⛔ 非推奨。UART2 UBX出力=無効のため機能しない
python rtk_tools/f9p_fix_monitor.py --port /dev/ttyAMA4 --once
```

## ハードウェア変更

**なし（ゼロ）**

- F9P UART2 の物理配線変更不要
- UART2 TX2 (Pin 3) は未使用となるが、接続したままでも問題なし
- DroneCAN バス (F9P→Pixhawk) は変更なし

## 移行日

2026-07-21
