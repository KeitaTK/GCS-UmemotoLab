# RTK FIXED 未達 ログ解析レポート

> **対象テスト日**: 2026-07-15（初回）+ 2026-07-21（追試）
> **レポート作成日**: 2026-07-21
> **解析者**: GCS-UmemotoLab 自動解析

---

## 1. エグゼクティブサマリ

**結論**: 全セッションで `fix_type=3 (3D_FIX)` のままであり、DGPS (fix=4) すら一度も観測されなかった。
RTCM3補正データがF9P Roverの測位エンジンに到達していないことが根本原因であり、
以下の3要因が複合的に寄与している。

| # | 要因 | 深刻度 | 確度 |
|---|------|--------|------|
| 1 | RTCM注入パイプライン不整合（Legacy MAVLink pathにフォールバック） | 🔴 CRITICAL | 高 |
| 2 | F9P Rover UART2 RTCM3受信設定未完了 | 🔴 CRITICAL | 高 |
| 3 | 基地局 Survey-In未完了（auto_obs=60s、baud=38400） | 🟡 HIGH | 中 |

---

## 2. ログデータサマリ

### 2.1 gcs.log（2026-07-21 21:14:51 〜 21:21:38）

| 項目 | 値 |
|------|-----|
| 総行数 | 46,547 |
| GPS_RAW_INT メッセージ数 | 204 |
| fix=3 (3D_FIX) | **204 (100%)** |
| fix=4 (DGPS) | **0** |
| fix=5 (RTK_FLOAT) | **0** |
| fix=6 (RTK_FIXED) | **0** |
| RTCM注入ログ行数 | 870 |
| RTCMメッセージタイプ | 281 (68回), 271 (64回), 1018 (64回) |

### 2.2 gcs_web.log（2026-07-21 18:55:05 〜 21:21:38+）

| 項目 | 値 |
|------|-----|
| 総行数 | 271,886 |
| GPS_RAW_INT メッセージ数 | 9,970 |
| fix=3 (3D_FIX) | **9,970 (100%)** |
| fix=4/5/6 | **0 (0%)** |
| RTCMメッセージタイプ（全体） | 1018(1941), 271(1585), 281(915) |

### 2.3 rtcm_fix_transition.log

```
2026-07-15 12:01:04 | carrSoln=-1 (NO_RESPONSE) | F9P Rover not responding on UART2
2026-07-21 21:04:43〜21:05:11 | carrSoln=0 (NONE), hAcc=1.630〜1.950m
```

### 2.4 rtcm_injection.log（2026-07-15）

総注入フレーム数 1,100、累積 203,215 bytes、エラー0。
注入レート 300〜730 frames/min でアクティブに注入されていた。

### 2.5 rtcm_mavlink_evidence.log

- 2026-07-01: fix=3→4→5→6 遷移確認済み（MAVLink pathでRTK_FIXED到達実績あり）
- 2026-07-15: GPS_RAWログ未出力のためfix遷移観測不可。18,046フレームRTCM注入完了（エラー0）

---

## 3. fix_type 遷移の時系列分析

### 2026-07-21 セッション

```
                       RTCM注入開始
                       (21:03:19)
                           │
21:03:12 ──────────────────┼──────────────────────────────→ 21:21:38
fix=3                        fix=3                            fix=3
(3D_FIX)                     (3D_FIX)                         (3D_FIX)
sats=11                      sats=11                          sats=12
hdop=1.65                    hdop=1.48                        hdop=1.23
                             
                             Legacy RTCM pipeline開始
                             RtcmReader → RtcmInjector
                             → GPS_RTCM_DATA
                             
                             RTCM types: 271,1018,281
                             注入継続中 (870 log lines)
```

**観察事項**:
- RTCM注入開始前後で **fix_typeに変化なし**（3→3のまま）
- hdop は 1.65→1.23 とわずかに改善（GPS_RAW_INT.ephのcm→m変換値）
- 衛星数 11→12 と微増
- DGPS (fix=4) にすら遷移しないことから、RTCMデータが測位エンジンに影響を与えていない

### 比較: 2026-07-01 成功事例

```
fix=3 (3D_FIX) ──[RTCM注入開始]──→ fix=4 (DGPS) ──→ fix=5 (RTK_FLOAT) ──→ fix=6 (RTK_FIXED)
                                                   (11:51:36)              (11:54:24)
fix=3→fix=6 所要時間: 約2分48秒
```

**差分**: 2026-07-01では正常に4段階遷移。2026-07-21では fix=4 すら観測されず。

---

## 4. eph/epv（HDOP相当）の推移

GPS_RAW_INTの `eph` フィールドはHDOPのcm単位表現（`hdop = eph / 100.0`）。

```
時刻          | fix  | sats | eph(cm) | hdop(m)
--------------|------|------|---------|--------
21:03:00.169  | 3    | 11   | 165     | 1.65
21:03:12.175  | 3    | 11   | 165     | 1.65
21:14:51.021  | 3    | 11   | 148     | 1.48  ← RTCM注入後
21:16:07.395  | 3    | 12   | 132     | 1.32
21:21:29.408  | 3    | 12   | 123     | 1.23
```

- ephに若干の改善傾向（165→123cm）は見られるが、単に時間経過による衛星配置改善の可能性が高い
- **RTK補正に期待される急峻な精度改善（eph < 5cm）は一切見られない**
- RTCM注入前後でephに段階的変化（不連続点）がない → RTCM未処理を示唆

GPS_RTKメッセージは全セッションで受信ログなし。

---

## 5. RTCM注入フレームとfix遷移の相関

### 5.1 注入パイプラインの状態

```
19:49:11 → RTK architecture: UART2 direct injection (rtk_forwarder type=serial)
           RtcmReader + RtcmInjector will NOT be started.

20:01〜21:01 → 同様（UART2 direct injection 維持）

21:03:19 → RTK architecture: legacy MAVLink path (no rtk_forwarder.yml)
           RuntimeWarning: RtcmInjector is DEPRECATED
           Legacy RTCM pipeline started: RtcmReader → RtcmInjector → GPS_RTCM_DATA
```

### 5.2 パイプライン切り替え原因

`config/rtk_forwarder.yml`:
```yaml
source:
  source_type: ntrip        # ← 問題: TCP直接ではなくNTRIP
  host: MAC_TAILSCALE_IP    # ← プレースホルダーのまま未設定
  port: 2101
```

- `source_type: ntrip` + `host: MAC_TAILSCALE_IP`(未設定) → 実際の基地局TCP:2101に接続できない
- GCS側は `rtk_forwarder.yml` を見つけられず → Legacy MAVLink path にフォールバック
- **UART2直接注入もLegacy MAVLink注入も、いずれもF9P RoverにRTCMデータが到達していない**

### 5.3 RTCMメッセージタイプ分析

| Type | 名称 | 回数(gcs_web) | サイズ | 役割 |
|------|------|---------------|--------|------|
| 1018 | GLONASS Station Coords | 1,941 | 26〜38B | 基準局位置 |
| 271 | u-blox Proprietary | 1,585 | 36B | u-blox独自拡張 |
| 281 | u-blox Proprietary | 915 | 44〜53B | u-blox独自拡張 |

**標準RTCM3 MSMメッセージ（1074/1084/1094/1124等）は観測されず**。

基地局F9P設定（`f9p_configurator.py`）では type 1005/1074/1084/1094/1124/1230 が有効化されているが、
ログ上 type 1005 も観測されず type 1018 (GLONASS) のみ出現。

→ `rtcm_reader._parse_rtcm_message_type()` が誤ったオフセットでパースしている可能性:
```python
msg_type = (frame[3] << 2) | (frame[4] >> 6)  # 検証必要
```

---

## 6. 基地局 Survey-In 状態

### 設定 (config/base_station.json)

```json
{
    "mode": "survey_in",
    "serial_port": "/dev/tty.usbmodem114301",
    "baudrate": 38400,
    "auto_obs_duration": 60
}
```

### 問題点

| 項目 | 設定値 | 推奨値 | 影響 |
|------|--------|--------|------|
| `baudrate` | **38400** | 115200/230400 | RTCM3出力に帯域不足。フレーム欠落リスク |
| `auto_obs_duration` | **60s** | 120〜300s | 測位精度不十分でSurvey-In完了しない可能性 |

また `f9p_configurator.py` は **TMODE3 FIXED Mode** で設定するが、`base_station.json` は `mode: "survey_in"`。
実際にどちらのモードで動作したかは起動ログから確認不可。

---

## 7. F9P Rover 設定状態

| 日時 | 状態 | 証跡 |
|------|------|------|
| 2026-07-15 12:01 | **F9P Rover not responding on UART2** | rtcm_fix_transition.log |
| 2026-07-21 21:04 | carrSoln=0 (NONE), hAcc=1.6〜1.95m | 同上 |

UART2 RTCM3入力が有効化されていない可能性が高い:
```
CFG-UART2INPROT-RTCM3X = 1  ← これが未設定の可能性大
```

物理配線（Raspi GPIO12 → USB-Serial → F9P UART2 RX2）の導通確認も必要。

---

## 8. 根本原因特定

### 🔴 主要因: RTCM3補正データがF9P Rover測位エンジンに到達していない

**証拠**:
1. fix_type が全セッションで 3D_FIX のまま。DGPS (fix=4) すら観測されず
2. eph 値にRTCM補正特有の急峻な改善（段階的不連続）が一切見られない
3. F9P Rover UART2 が NO_RESPONSE 状態（7/15）
4. rtk_forwarder.yml の source_type/host が未設定のためUART2直接注入が機能していない

### 🟡 副要因1: RTCM注入パイプライン不整合

```
設計パス:  基地局F9P → TCP:2101 → rtk_forwarder → /dev/ttyAMA4 → F9P UART2 RX2
                                 (Raspi側、source_type=tcp必要)

実パス:   基地局F9P → TCP:2101 → rtcm_reader → rtcm_injector → GPS_RTCM_DATA
                                 (Mac側Legacy、GPS_INJECT_TO依存)
```

### 🟡 副要因2: 基地局設定の品質
- baudrate 38400 はRTCM3フルストリームに帯域不足
- auto_obs_duration 60s はSurvey-In完了に不十分

### 🟡 副要因3: RTCMメッセージタイプ解析の信頼性
- rtcm_reader のメッセージタイプ解析オフセットが正しいか検証が必要
- 本来出力されるべき type 1005/1074/1084/1094/1124 が観測されず

---

## 9. 次のテストに向けた具体的修正指示

### 9.1 🔴 P0 — F9P Rover UART2 設定確認と再有効化

```bash
# Raspi上で実行
ssh raspi
cd ~/GCS-UmemotoLab && source .venv/bin/activate

# 1. 現在の設定確認
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4 --verify-only

# 2. 未設定の場合は再設定（RTCM3入力 + UBX出力無効）
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4

# 3. 設定確認（再）
python rtk_tools/f9p_rover_config.py --port /dev/ttyAMA4 --verify-only
```

**期待出力**:
```
CFG-UART2INPROT-RTCM3X = 1  ← 要確認
CFG-UART2OUTPROT-UBX    = 0  ← UBX出力無効
CFG-UART2OUTPROT-NMEA   = 0  ← NMEA出力無効
All verified: YES
```

### 9.2 🔴 P0 — rtk_forwarder.yml 修正（UART2直接注入用）

`config/rtk_forwarder.yml` を以下のように修正:

```yaml
source:
  # 【修正】ntrip → tcp（生TCPストリーム受信）
  source_type: tcp

  # source_type: tcp の場合 → MacのRTK基地局（Tailscale IP）
  host: 100.80.225.4   # ← 実際の基地局Tailscale IPに置換
  port: 2101

  # 共通
  timeout_sec: 5.0

forward:
  # serial（変更なし）
  type: serial

  # type: serial の場合（F9P Rover UART: /dev/ttyAMA4）
  serial_port: /dev/ttyAMA4
  baudrate: 115200

retry:
  reconnect_sec: 3.0

log:
  level: INFO
  stats_interval_sec: 5
```

**修正後、Raspi側で動作確認**:
```bash
ssh raspi
cd ~/GCS-UmemotoLab && source .venv/bin/activate

# サービスの再起動
sudo systemctl restart rtk-uart2-inject
systemctl status rtk-uart2-inject
journalctl -u rtk-uart2-inject -f  # リアルタイムログ監視
```

### 9.3 🟡 P1 — 基地局設定の最適化

`config/base_station.json`:

```json
{
    "mode": "fixed",
    "serial_port": "/dev/tty.usbmodem114301",
    "baudrate": 115200,
    "fixed_lat": 36.0751418,
    "fixed_lon": 136.2133477,
    "fixed_alt": 10.50,
    "save_to_flash": true,
    "auto_obs_duration": 180
}
```

変更点:
- `mode`: `survey_in` → `fixed`（既知座標確定済みのため、Survey-In不要。即時RTCM出力開始）
- `baudrate`: `38400` → `115200`（RTCM3フル出力に十分な帯域を確保）
- `auto_obs_duration`: `60` → `180`（survey_in使用時の保険）

### 9.4 🟡 P1 — RTCMメッセージタイプ解析の検証

`app/rtk_tools/rtcm_reader.py` の `_parse_rtcm_message_type()`:
```python
msg_type = (frame[3] << 2) | (frame[4] >> 6)
```

RTCM3 v3 フレームヘッダ:
- Byte 0: Preamble (0xD3)
- Byte 1-2: Reserved (6 bits) + Message Length (10 bits)
- Byte 3-4: Message Type (12 bits)

既知のRTCM3テストフレームで検証単体テストを作成すること。

### 9.5 🟢 P2 — テスト手順書（修正後）

```bash
# ─── Mac側 ───
# 1. 基地局起動（Fixed Mode）
cd ~/GCS-UmemotoLab && source .venv/bin/activate
python rtk_tools/rtk_base_station_v2.py \
    --config config/base_station.json \
    --tcp-port 2101

# ─── Raspi側 ───
# 2. rtk-uart2-inject サービス稼働確認
ssh raspi "sudo systemctl status rtk-uart2-inject"

# 3. シリアル出力確認（RTCM3フレームの0xD3 preamble確認）
ssh raspi "timeout 5 sudo cat /dev/ttyAMA4 | xxd | head"

# ─── Mac側 ───
# 4. Webサーバー + GCS起動
python app/main.py

# 5. GCS接続 + Fix監視
python rtk_tools/gcs_fix_monitor.py \
    --gcs-url http://localhost:8000 \
    --timeout 300       # 最大5分待機
```

**目標タイムライン**:
| 経過時間 | 期待状態 | 確認方法 |
|----------|---------|----------|
| 0:00 | 基地局RTCM出力開始 | TCP:2101 telnet確認 |
| 0:00 | RTCM注入開始（UART2） | `journalctl -u rtk-uart2-inject -f` |
| 0:30 | fix=4 (DGPS) | `gcs_fix_monitor.py` ログ |
| 2:00 | fix=5 (RTK_FLOAT) | 同上 |
| 3:00 | fix=6 (RTK_FIXED) 🎉 | 同上 |

---

## 10. 参考

### ログファイル一覧
| ファイル | サイズ | 内容 |
|----------|--------|------|
| `logs/gcs.log` | 425KB | 2026-07-21 GCSアプリケーションログ |
| `/tmp/gcs_web.log` | 24MB | 2026-07-21 GCS Webサーバーログ（271,886行） |
| `logs/rtcm_fix_transition.log` | 1.4KB | Fix遷移記録 |
| `logs/rtcm_injection.log` | 4.5KB | 2026-07-15 RTCM注入統計 |
| `logs/rtcm_mavlink_evidence.log` | 3.5KB | MAVLink証跡分析 |
| `config/base_station.json` | — | 基地局設定 |
| `config/rtk_forwarder.yml` | — | RTCM転送設定 |
| `docs/ctrl/migration_summary.md` | — | 移行サマリ（2026-07-21テスト結果含む） |

### 2026-07-01 成功時の構成との差分
| 項目 | 2026-07-01（成功） | 2026-07-21（失敗） |
|------|--------------------|---------------------|
| RTCM注入パス | GPS_RTCM_DATA (MAVLink) | Legacy MAVLink / UART2 Direct混合 |
| 基地局モード | TIME mode (RTCM出力中) | Survey-In (auto_obs=60s) |
| F9P Rover応答 | 正常 | NO_RESPONSE (7/15), NONE (7/21) |
| fix遷移 | 3→4→5→6 (2分48秒) | 3→3→3 (変化なし) |
