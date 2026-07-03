# 2026年7月3日 テスト総括報告書

> **明日（2026-07-04）のテスト飛行に向けた総括資料**
>
> **作成日**: 2026-07-03
> **プロジェクト**: GCS-UmemotoLab / 複数台同時飛行の第一歩
> **対象機体**: Pixhawk 6C + Raspberry Pi 5 + u-blox ZED-F9P

---

## 1. 概要

### 1.1 実施日時・目的・場所

| 項目 | 内容 |
|------|------|
| 実施日 | 2026年7月3日（金） |
| 主目的 | RTKfixデータ収集と誤差計測、プロペラなし地上モータテスト、明日の初飛行準備 |
| 実施場所 | 屋外（GPS受信可能環境）— 推定: 福井県福井市周辺 (lat=36.0757, lon=136.2134) |
| GCS環境 | MacBook Air (launchd常時稼働) + Web UI (localhost:8000) |

### 1.2 システム構成図

```
┌─────────────────────────────────────────────────────┐
│              u-blox ZED-F9P 基準局                    │
│  (USB接続: /dev/tty.usbmodem113301, RTCM v3出力)      │
│  [7/2 18:03稼働 → 7/3未稼働]                         │
└──────────────────────┬──────────────────────────────┘
                       │ USBシリアル / RTCM TCP (127.0.0.1:2101)
┌──────────────────────┴──────────────────────────────┐
│             GCS (MacBook Air)                         │
│  - rtk_base_station.py / rtk_rtcp_receiver2.py       │
│  - RTCM → Pixhawk 注入 (GPS_RTCM_DATA, msg#67)       │
│  - Web UI: http://localhost:8000                      │
│  - MAVLink UDP bridge: 127.0.0.1:14552               │
└──────────────────────┬──────────────────────────────┘
                       │ Tailscale VPN
                       │ Raspi IP: 100.123.158.105:5760
┌──────────────────────┴──────────────────────────────┐
│          Raspberry Pi 5 (機体搭載)                     │
│  - mavlink-routerd (UDP→Serial中継)                   │
│  - backend_server.py (MAVLink転送)                    │
└──────────────────────┬──────────────────────────────┘
                       │ Serial USB
┌──────────────────────┴──────────────────────────────┐
│          Pixhawk 6C (ArduPilot Copter)                │
│  - GPS_TYPE=9 (DroneCAN ZED-F9P Rover)               │
│  - GPS_INJECT_TO=127, GPS_AUTO_CONFIG=2              │
│  - EKF3 healthy                                       │
└─────────────────────────────────────────────────────┘
```

### 1.3 プロジェクトの位置づけ

本プロジェクトは複数台ドローン同時自律飛行の実現を最終目標としている。本日はその第一歩として、1台のドローンでの初飛行（フェーズC）に必要なデータ収集と地上テストを実施した。

| フェーズ | 名称 | 目標 | 状況 |
|---------|------|------|------|
| A | 飛行前チェック | 機体・FCパラメータ・センサー確認 | 🔄 一部未完了 |
| B | 地上テスト | プロペラなし全動作確認 | 🔄 モータテスト未実施 |
| **C** | **初飛行** | **低高度ホバリング・手動/自動切替確認** | **⏳ 明日予定** |
| D | 自律飛行テスト | NED精密移動・ウェイポイント・RTL | 未着手 |
| E | 安全確認・チューニング | PID最適化・振動解析・緊急停止検証 | 未着手 |

---

## 2. RTKfixデータ収集結果

### 2.1 結論: RTK FIXED (fix=6) 達成！ ✅

**サンプル5（2026-07-01）にて、プロジェクト史上初の RTK FIXED を達成した。**

### 2.2 RTK FIXED データ詳細

#### 基準局（u-blox ZED-F9P）

| 項目 | 値 | 備考 |
|------|-----|------|
| 座標 | データなし | サンプル5取得時、u-blox側の同時ログ未記録 |
| Survey-In状態 | 不明 | 基準局が稼働中だったか未確認 |
| RTCMタイプ | type 268, 271, 273, 281, 1018 他 | 7/2 18:03の注入ログより確認 |

#### 移動局（Pixhawk 6C + DroneCAN ZED-F9P Rover）

| 項目 | 値 |
|------|-----|
| Fix Type | **6 (RTK FIXED)** |
| 緯度 (lat) | 36.07572630° |
| 経度 (lon) | 136.21371010° |
| 高度 (alt) | 2.9 m |
| 衛星数 | 27 |
| サンプル数 | 20（全サンプル同一座標） |

### 2.3 水平誤差・垂直誤差

> ⚠️ **注意**: 専用の誤差計測データファイル (`rtk_error_*.csv`) は存在しない。
> サンプル5では20サンプル全てが同一座標（lat, lon, alt 完全一致）であったため、
> 標準偏差は 0 と推定されるが、これは比較的低い分解能での記録による可能性がある。

| 指標 | 水平方向 | 垂直方向 | 備考 |
|------|---------|---------|------|
| 平均誤差 | データなし | データなし | 基準局座標が未記録のため絶対誤差算出不可 |
| 標準偏差 | 0 (20サンプル) | 0 (20サンプル) | 全サンプル同一座標 |
| 最大誤差 | データなし | データなし | — |

> 📊 **考察**: 20サンプル連続で完全同一のRTK FIXED座標が得られたことは、
> RTK ambiguity（整数値バイアス）解決後の位置保持が極めて安定していることを示す。
> cm級精度（RTK FIXEDの期待精度: 水平±2cm、垂直±3cm）が達成されている可能性が高い。

### 2.4 Fix品質の分布

| Fix Type | 名称 | サンプル5 出現回数 | 割合 |
|----------|------|-------------------|------|
| fix=3 | 3D_FIX | 0 | 0% |
| fix=4 | DGPS | 0 | 0% |
| fix=5 | RTK FLOAT | 0 | 0% |
| **fix=6** | **RTK FIXED** | **20** | **100%** |

### 2.5 Fix Type 遷移の経緯

```
fix=3 (3D_FIX) ──[RTCM注入開始]──→ fix=4 (DGPS) ──[ambiguity解決]──→ fix=6 (RTK FIXED)
     │                                    │                              │
     │ 6/29: 1,476回観測                  │ 6/30: 1,540回観測            │ 7/1: 20回観測 🎉
     │ gcs.log.1                          │ gcs.log.3〜5                  │ compare_sample5.csv
     │                                    │                              │
     └── fix=5 (RTK FLOAT) ── 全期間で0回観測 ──────────────┘
```

> **重要な知見**: 本プロジェクトでは fix=5 (RTK FLOAT) が一度も観測されずに fix=6 に到達した。
> DroneCAN ZED-F9P の ambiguity解決が FLOAT を経ずに即座に FIXED へ遷移した、
> あるいはログの記録粒度（1Hz）では FLOAT 状態が捕捉できなかった可能性を示唆する。

### 2.6 未達時の補足（サンプル6）

| サンプル | 日付 | u-blox Fix | Pixhawk Fix | 状況 |
|----------|------|-----------|-------------|------|
| sample6_v3 | 7/2 16:53 | fix=2 (12 sats) | データなし | Pixhawk未接続 |
| sample6_both | 7/2 17:10 | fix=2 (12 sats) | fix=3 (29-32 sats) | RTCM未注入 |

サンプル6では u-blox基準局のfixが不良（fix=2, 12衛星）のため、有効なRTCM補正データが生成できず、
Pixhawk側も fix=3 (3D_FIX) に留まった。

---

## 3. 地上テスト結果

### 3.1 テスト実施概要

| 項目 | 内容 |
|------|------|
| 実行ツール | `tools/preflight_check.py` |
| 実行モード | `--no-motor`（モータテストスキップ） |
| 実行日時 | 2026-07-03 15:47:14 〜 15:47:51 JST |
| 実行回数 | 3回（154714, 154719, 154751） |
| 最終結果 | **18 PASS / 7 FAIL → 飛行未準備（NOT READY FOR FLIGHT）** |

### 3.2 システム状態サマリ

| カテゴリ | 項目 | 結果 | 詳細 |
|----------|------|------|------|
| GCS | Web Server | ✅ PASS | drones=[1, 255, 0] |
| Comm | MAVLink | ✅ PASS | type=udp pkts=62577, connected |
| Comm | Drones detected | ✅ PASS | 3 drones: [1, 255, 0] |
| System | Heartbeat | ✅ PASS | armed=False, mode=STABILIZE |
| Battery | Voltage | ✅ PASS | **19.04V** (5S LiPo想定、正常範囲) |
| Battery | Remaining | ❌ FAIL | No data |
| GPS | Fix | ✅ PASS | **3D_FIX**, sats=28, hdop=0.72 |
| GPS | Position | ✅ PASS | lat=36.0757028, lon=136.2133523 |
| EKF | Status | ❌ FAIL | EKF_STATUS_REPORT not available (warmup不足の可能性) |
| Sensor | IMU(accel) | ❌ FAIL | RAW_IMU unavailable → Step3で再確認しPASS |
| Sensor | Barometer | ❌ FAIL | SCALED_PRESSURE unavailable → Step3で再確認しPASS |
| Sensor | Compass | ❌ FAIL | IMU available → compass presumed OK |
| System | Warnings | ✅ PASS | No warnings |
| MotorTest | — | ⏭️ SKIPPED | --no-motor flag |
| Comm | Tailscale/Raspi ping | ✅ PASS | ping 100.123.158.105 → OK |
| Comm | RTCM injection | ✅ PASS | Check GCS Web UI (実際は基準局未起動のため要確認) |
| Actuator | Servo output | ❌ FAIL | SERVO_OUTPUT_RAW unavailable (非ARM時は正常) |
| Actuator | RC input | ❌ FAIL | RC_CHANNELS unavailable (GCS制御ならOK) |
| Safety | Failsafe | ✅ PASS | Default Pixhawk failsafe active |
| Safety | Geofence | ✅ PASS | FENCE_ENABLE 要確認 |
| Safety | Battery failsafe | ✅ PASS | BATT_LOW_VOLT 要確認 |

### 3.3 モータテスト結果

| 項目 | 結果 |
|------|------|
| 実施有無 | **未実施** |
| 理由 | `--no-motor` フラグによりスキップ |
| モータテストログ | `logs/motor_test_*.log` — **ファイル未生成** |

### 3.4 通信チェック結果

| 項目 | 結果 | 詳細 |
|------|------|------|
| GCS→Raspi (Tailscale) | ✅ 到達可能 | ping 100.123.158.105 → OK |
| MAVLink パケット | ✅ 62,577 packets received | 長時間の通信実績あり |
| RTCM 注入 | ⚠️ 要注意 | 7/2 18:03までは正常（5,600フレーム注入成功）<br>7/3 00:07以降 **RTCM socket timeout**（基準局未起動） |

### 3.5 センサーチェック結果

Step 1ではRAW_IMU/SCALED_PRESSUREがGCS API経由で取得できなかったが、
Step 3の再確認では全センサーがStep 1で確認済みとしてPASS判定された。
APIの内部エラー（HTTP 500）が原因であり、センサー自体の異常ではない可能性が高い。

### 3.6 飛行可否の最終判定

| 判定 | 結果 |
|------|------|
| **総合判定** | ❌ **NOT READY FOR FLIGHT** |
| PASS数 | 18 / 25 |
| FAIL数 | 7 / 25 |
| **ブロッキング課題** | ① モータテスト未実施 ② RTCM基準局未起動（fix=3 のまま） ③ EKFステータス未確認 |
| **非ブロッキング課題** | ① Battery Remaining データなし ② テレメトリAPI 500エラー（断続的） |

---

## 4. 課題と改善点

### 4.1 見つかった問題点

| # | 問題 | 深刻度 | 詳細 |
|---|------|--------|------|
| 1 | **モータテスト未実施** | 🔴 高 | プロペラなし地上モータテストが未実施。ARM/DISARMの遠隔操作検証が未完了。飛行前に必須。 |
| 2 | **RTCM基準局未起動（7/3）** | 🔴 高 | 7/3の全ログで `RTCM socket timeout` が1,672回記録。7/2 18:03以降、基準局が停止している。RTK FIXEDにはRTCM注入が必須。 |
| 3 | **テレメトリAPI 500エラー** | 🟡 中 | 飛行前チェック1回目・2回目で `/api/telemetry/1` がHTTP 500エラーを返した。3回目では一部回復。GCS内部のデータ取得に不安定性あり。 |
| 4 | **Battery Remaining 未取得** | 🟡 中 | Pixhawkからバッテリー残量（%）がテレメトリされていない。電圧19.04Vは正常だが、飛行中の残量監視に支障。 |
| 5 | **EKF_STATUS_REPORT 未受信** | 🟡 中 | EKFの状態フラグが取得できていない。warmup時間不足の可能性（1〜2分待機推奨）。 |
| 6 | **u-blox基準局座標がconfigのデフォルト値** | 🟢 低 | `config/base_station.json` の座標が東京（35.681236, 139.767125）。実際のテスト場所（福井県）とは異なる。Survey-In modeでの自動設定が推奨。 |

### 4.2 改善優先度マトリクス

| 優先度 | 項目 | 対応内容 | 期限 |
|--------|------|----------|------|
| 🔴 P0 | モータテスト実施 | `python tools/preflight_check.py --system-id 1` （--no-motor 外す） | 明日の飛行前 |
| 🔴 P0 | RTCM基準局起動 | `python rtk_tools/rtk_base_station.py` 起動 + RTCM注入確認 | 明日の飛行前 |
| 🔴 P0 | fix=6 (RTK FIXED) 再確認 | 基準局起動後、15分以上安定したfix=6を確認 | 明日の飛行前 |
| 🟡 P1 | テレメトリAPI安定化 | GCS再起動、または `/api/telemetry/1` のエラーハンドリング改善 | 今週中 |
| 🟡 P1 | Battery Remaining 対応 | `BATT_MONITOR` パラメータ確認、または電圧ベースの残量推定実装 | 今週中 |
| 🟢 P2 | EKFステータス取得 | 起動後warmup時間を十分に確保（3〜5分）して再チェック | 次回テスト時 |
## 5. 明日のテスト飛行計画（2026-07-04）

> **参照**: `docs/flight_roadmap.md` フェーズC「初飛行」

### 5.1 目的

1. 低高度（1〜2m）での安定ホバリングの実証
2. GCSからのARM/TAKEOFF/LAND遠隔操作の動作確認
3. RTK FIXED (fix=6) 状態での位置保持精度の初確認
4. 手動制御（ラジコン）とGCS制御の切替検証

### 5.2 前提条件（飛行前に必ず満たすこと）

- [ ] フェーズA: 全チェック項目合格
- [ ] フェーズB: モータテスト含む全地上テスト合格
- [ ] RTK FIXED (fix=6) が15分以上安定継続
- [ ] バッテリー満充電（4.2V/セル、5Sなら21.0V）
- [ ] 風速 2m/s以下、降雨なし
- [ ] 飛行エリア: 最低 10m×10m のオープンスペース確保
- [ ] 安全確認者（補助者）1名以上配置
- [ ] 消火器を手の届く場所に準備

### 5.3 テスト手順

#### Step 1: 飛行前最終確認（所要: 15分）

| # | チェック項目 | 確認方法 |
|---|-------------|----------|
| 1.1 | 天候確認 | 風速計・目視 |
| 1.2 | 飛行エリア安全確認 | 周囲に人・車・障害物なし |
| 1.3 | GPS RTK FIXED (fix=6) | GCS Web UI で fix type 確認 (15分以上安定) |
| 1.4 | バッテリー満充電 | GCSテレメトリ電圧 + テスター実測 |
| 1.5 | ラジコン送信機 ON・スロットル最低 | スロットルカットスイッチ確認 |
| 1.6 | GCS Web UI 接続・テレメトリ正常 | localhost:8000 で全項目緑表示 |
| 1.7 | 安全確認者との合図確認 | 緊急停止の合図を事前打合せ |
| 1.8 | プロペラ装着・ナット増し締め | CW/CCW方向別確認、逆ネジ注意 |
| 1.9 | ジオフェンス設定確認 | FENCE_ENABLE=1, FENCE_RADIUS=30m, FENCE_ALT_MAX=10m |

#### Step 2: 低高度ホバリング（所要: 5分）

| # | テスト項目 | 操作手順 | 合否基準 | 所要時間 |
|---|-----------|----------|----------|----------|
| 2.1 | **ラジコン ARM → 離陸** | ラジコンでアーム → スロットル上昇 → 高度1m | 安定ホバリング、異常振動なし | 30秒 |
| 2.2 | **姿勢安定性確認** | ホバリング中にロール/ピッチ/ヨー微小入力 | 各軸とも安定応答、オーバーシュート小 | 60秒 |
| 2.3 | **高度1m ホバリング継続** | スロットル中央付近で高度維持 | 高度変動 ±0.3m以内 | 60秒 |
| 2.4 | **高度2m ホバリング** | スロットル微増で上昇→高度維持 | 安定ホバリング | 30秒 |
| 2.5 | **ラジコン着陸** | スロットル下降→接地→ディスアーム | ソフトランディング、転倒なし | 30秒 |

#### Step 3: GCS遠隔操作確認（所要: 5分）

| # | テスト項目 | 操作手順 | 合否基準 |
|---|-----------|----------|----------|
| 3.1 | **GCS ARM** | Web UI → ARMボタン | アーム成功、全モーター始動 |
| 3.2 | **GCS TAKEOFF (2m)** | Web UI → Takeoff Alt=2 → 確認 | 自動離陸→高度2mでホバリング |
| 3.3 | **RTK位置保持精度確認** | GCSテレメトリでGPS座標監視 | 水平変動 3cm以内（RTK FIXED期待値） |
| 3.4 | **GCS LAND** | Web UI → LANDボタン | 自動着陸→接地→モーター停止 |
| 3.5 | **GCS DISARM** | 着陸後 → DISARMボタン | アーム解除 |

#### Step 4: 手動/GCS制御切替確認（所要: 3分）

| # | テスト項目 | 操作手順 | 合否基準 |
|---|-----------|----------|----------|
| 4.1 | **Guided → 手動切替** | GCS TAKEOFF後 → ラジコンSWをStabilize/AltHoldに | 即時手動操作に移行 |
| 4.2 | **手動 → Guided切替** | 手動ホバリング中 → SWをGuided → GCSからTAKEOFF | モード切替成功 |
| 4.3 | **緊急時ラジコン介入** | GCS制御中にスロットル最低＋DISARM | 即時モーター停止 |

### 5.4 安全対策

| # | 対策 | 詳細 |
|---|------|------|
| S1 | **ジオフェンス** | FENCE_RADIUS=30m, FENCE_ALT_MAX=10m を事前設定 |
| S2 | **フェールセーフ** | FS_GCS_ENABLE=1, FS_THR_ENABLE=1, FS_BATT_ENABLE=1 |
| S3 | **ラジコン緊急停止** | スロットルカットスイッチ＋DISARMで即時モーター停止 |
| S4 | **安全距離確保** | 飛行中はドローンから最低5m離れる。補助者も同様。 |
| S5 | **消火器準備** | CO2消火器または粉末消火器を手の届く場所に |
| S6 | **RTL設定** | RTL_ALT=10m（周囲障害物より高く） |
| S7 | **DISARM_DELAY** | 5秒（着陸後自動ディスアーム） |

### 5.5 成功基準

| レベル | 基準 |
|--------|------|
| ✅ **最低限の成功** | ラジコンで高度1mホバリング5秒以上継続 → 安全に着陸 |
| ✅✅ **目標達成** | GCSからのTAKEOFF/LAND操作成功 + RTK位置保持確認 |
| ✅✅✅ **完全成功** | 全Step (2〜4) のテスト項目を全て合格 |

### 5.6 緊急時対応

| 状況 | 対応 |
|------|------|
| **ドローンが制御不能** | ① ラジコンDISARM（即時モーター停止） ② それでも止まらない場合: ラジコン電源OFF → FS_THR_ENABLEでRTL発動期待 |
| **GCS通信断** | FS_GCS_ENABLE=1 により自動RTL発動（10秒以内）。再開はGCS再起動→再接続を待つ |
| **バッテリー低下** | FS_BATT_ENABLE=1 により自動着陸。事前にBATT_LOW_VOLT確認 |
| **火災・発煙** | 即時DISARM → 消火器使用 → バッテリーコネクタ切断（絶縁手袋着用） |
| **人への接近** | 最優先でDISARM（落下による怪我のリスクより接触回避を優先） |

### 5.7 飛行後タスク

- [ ] 飛行ログ回収（Pixhawk FlashログBIN + GCSテレメトリログ）
- [ ] GPS軌跡と目標経路の偏差分析
- [ ] バッテリー消費データ記録
- [ ] モータ・ESC温度確認
- [ ] プロペラ・機体の損傷確認
## 6. 付録

### 6.1 全ログデータの格納場所

| データ | パス | 説明 |
|--------|------|------|
| 飛行前チェック結果 (最新) | `logs/preflight_check_20260703_154751.json` | 25項目、18 PASS / 7 FAIL |
| 飛行前チェック結果 (1回目) | `logs/preflight_check_20260703_154714.json` | 22項目、16 PASS / 6 FAIL |
| 飛行前チェック結果 (2回目) | `logs/preflight_check_20260703_154719.json` | 22項目、16 PASS / 6 FAIL |
| GCSメインログ | `logs/gcs.log` | 7/2 18:03〜7/3 15:52、4.4MB、RTCM注入5,600回 + タイムアウト1,672回 |
| GCSログ (ローテート1〜5) | `logs/gcs.log.1` 〜 `logs/gcs.log.5` | 6/29のfix=3/4データ含む |
| サンプル5 (RTK FIXED) | `logs/compare_sample5.csv` | fix=6, 20サンプル同一座標 |
| サンプル6 (比較) | `logs/compare_sample6_both.csv` | u-blox fix=2 vs Pixhawk fix=3 |
| サンプル6 (v3) | `logs/compare_sample6_v3.csv` | u-blox fix=2のみ |
| RTK誤差データ | **ファイル未生成** | `logs/rtk_error_*.csv` — 存在せず |
| RTK分析結果 | **ファイル未生成** | `logs/rtk_analysis_*.json` — 存在せず |
| モータテストログ | **ファイル未生成** | `logs/motor_test_*.log` — 存在せず（モータテスト未実施） |
| 基準局設定 | `config/base_station.json` | ⚠️ 東京のデフォルト座標（要更新） |

### 6.2 使用スクリプト一覧

| スクリプト | パス | 用途 |
|------------|------|------|
| 飛行前チェック | `tools/preflight_check.py` | 地上テスト自動実行 |
| RTK基準局 | `rtk_tools/rtk_base_station.py` | u-blox受信 + TCP配信 |
| RTK基準局 v2 | `rtk_tools/rtk_base_station_v2.py` | 改良版基準局 |
| RTCM受信 | `rtk_tools/rtk_rtcp_receiver2.py` | RTCMストリーム受信 |
| RTCM注入 | `app/rtk_tools/rtcm_injector.py` | PixhawkへRTCM注入 |
| GPS比較収集 | `scripts/gps_compare_collect.py` | u-blox vs Pixhawk GPS比較 |
| GPS Fix確認 | `scripts/check_gps_fix.py` | GPS Fix Type確認 |
| UDP-TCPブリッジ | `scripts/udp_tcp_bridge.py` | GCS→Raspi通信中継 |
| ダイレクトブリッジ | `scripts/direct_bridge.py` | 簡易ブリッジ |

### 6.3 パラメータ設定値一覧

| パラメータ | 設定値 | 意味 |
|------------|--------|------|
| `GPS_TYPE` | 9 | DroneCAN接続（ZED-F9P Rover） |
| `GPS_AUTO_CONFIG` | 2 | DroneCAN自動設定ON |
| `GPS_INJECT_TO` | 127 | RTCM全GPSに注入 |
| `AHRS_EKF_TYPE` | 3 | EKF3 使用 |
| `ARMING_CHECK` | 1 | 全チェック有効（要確認） |
| `FS_THR_ENABLE` | 1 | ラジオフェールセーフ有効（要確認） |
| `FS_GCS_ENABLE` | 1 | GCS通信断検知（要確認） |
| `FS_BATT_ENABLE` | 1 | バッテリーフェールセーフ有効（要確認） |
| `FENCE_ENABLE` | 1 | ジオフェンス有効（要確認） |
| `RTL_ALT` | 10m（推奨） | RTL上昇高度 |
| u-blox基準局ポート | `/dev/tty.usbmodem113301` | USBシリアル |
| u-bloxボーレート | 38400 | — |
| RTCM TCPポート | 127.0.0.1:2101 | localhost |
| Raspi IP (Tailscale) | 100.123.158.105 | VPN経由 |
| Raspi MAVLinkポート | 5760 | mavlink-routerd |
| GCS Web UI | http://localhost:8000 | MacBook Air |

---

*本報告書は入手可能なデータに基づいて作成されました。*
*`logs/rtk_error_*.csv`、`logs/rtk_analysis_*.json`、`logs/motor_test_*.log` は存在しないため、該当データは「データなし」と表記しています。*
