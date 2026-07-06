# コンフィグ一元化 設計資料

## 1. 現状の問題点

### 設定ファイルが散逸・重複している

現在 `config/` ディレクトリには10個の設定ファイルが存在し、同じ設定値が各スクリプトのデフォルト引数としてもハードコードされている。

| 設定項目 | ハードコードされているスクリプト | コンフィグファイル |
|----------|--------------------------------|-------------------|
| F9Pシリアルポート | `rtk_data_collector.py`, `standalone_obs.py`, `ublox_survey_in.py`, `gps_compare_collect.py` | `base_station.json`, `rtk_forwarder.yml` |
| F9Pボーレート | `rtk_data_collector.py`, `standalone_obs.py`, `ublox_survey_in.py`, `rtk_base_station.py` | `base_station.json`, `rtk_forwarder.yml` |
| 基準局座標 | — | `base_station.json` のみ |
| NTRIP接続先 | `rtk_forwarder_service.py` | `rtk_forwarder.yml` のみ |

### 設定ファイル一覧（10ファイル）

```
config/
├── gcs.yml                    # GCSデフォルト（シリアル接続）
├── gcs_local.yml              # SSH Tunnel + Tailscale 自動
├── gcs_production.yml         # 手動SSH Tunnel
├── gcs_drone.yml              # Raspi直接実行
├── gcs_sshtunnel.yml          # launch_gcs_tailscale.sh用 → gcs_local.yml と同一内容
├── gcs_raspi_bridge.yml       # Raspiブリッジ → gcs_drone.yml で代替可能
├── gcs_multidrone_example.yml # マルチドローン設定例
├── gcs_multidrone_test.yml    # マルチドローンテスト → example で代替可能
├── base_station.json          # F9P基地局設定（JSON形式）
└── rtk_forwarder.yml          # RTKフォワーダー設定
```

---

## 2. 提案: `config/hardware.yml` による一元化

新しい `config/hardware.yml` を導入し、F9P/基準局/NTRIP の設定を1ファイルに集約する。全ツールはこのファイルを読み込んでデフォルト値を解決する。

### 新規作成: `config/hardware.yml`

```yaml
# config/hardware.yml — 全ツール共通のハードウェア設定
# Windows PC（F9P基地局）環境用

f9p:
  serial_port: "COM8"       # F9P 接続シリアルポート
  baudrate: 115200          # F9P ボーレート

base_station:
  fixed_lat: 35.681236      # 固定基準局 緯度
  fixed_lon: 139.767125     # 固定基準局 経度
  fixed_alt: 42.0           # 固定基準局 高度
  save_to_flash: true       # F9P設定をフラッシュに保存

forward:
  host: 127.0.0.1           # RTCM転送先ホスト
  port: 50010               # RTCM転送先ポート

retry:
  reconnect_sec: 3.0        # 再接続間隔

log:
  level: INFO
  stats_interval_sec: 5
```

> **Note**: NTRIP 設定（host, port, mountpoint など）は環境依存が強いため、`hardware.yml` に入れず別ファイル `config/ntrip.yml` または `gcs_local.yml` 内に保持する案も検討が必要。

### 環境切り替え方式

Mac と Windows でシリアルポート名が異なる（`/dev/tty.usbmodem113301` vs `COM8`）ため、以下のいずれかの方式を採用する：

**方式A: 環境変数で切り替え（推奨）**

```
config/
├── hardware.yml              # デフォルト（git管理）
├── hardware.win.yml          # Windows用上書き（git管理）
├── hardware.mac.yml          # Mac用上書き（git管理）
└── hardware.local.yml        # 個人用上書き（gitignore）
```

優先順位: `GCS_HARDWARE_CONFIG` 環境変数 → `hardware.local.yml` → `hardware.win.yml` or `hardware.mac.yml`（OS自動判定） → `hardware.yml`

**方式B: 1ファイル + --hardware-config CLI引数（シンプル）**

デフォルトの `hardware.yml` を読み、CLI引数 `--hardware-config` か環境変数で別パスを指定可能にする。

---

## 3. `config_loader.py` の拡張

`rtk_tools/config_loader.py` に `load_hardware_config()` 関数を追加する。

```python
# 追加する関数のシグネチャ

def load_hardware_config(path=None) -> dict:
    """hardware.yml を読み込み、全ツール共通のハードウェア設定を返す。

    Args:
        path: 明示的なパス（省略時は自動検出: hardware.local.yml > hardware.win/mac.yml > hardware.yml）

    Returns:
        dict: {
            'f9p': {'serial_port': str, 'baudrate': int},
            'base_station': {'fixed_lat': float, 'fixed_lon': float, 'fixed_alt': float, ...},
            'forward': {'host': str, 'port': int},
            ...
        }
    """
```

---

## 4. 修正が必要なスクリプト（8ファイル）

| ファイル | 変更内容 |
|----------|---------|
| `rtk_tools/rtk_base_station.py` | `--serial-port` デフォルト → `load_hardware_config()['f9p']['serial_port']` |
| `rtk_tools/rtk_base_station_v2.py` | `config/base_station.json` 読込 → `load_hardware_config()` に変更 |
| `rtk_tools/rtk_data_collector.py` | `--ublox-port`, `--ublox-baud` デフォルト → `load_hardware_config()['f9p']` |
| `rtk_tools/standalone_obs.py` | `--port`, `--baudrate` デフォルト → `load_hardware_config()['f9p']` |
| `rtk_tools/rtk_forwarder_service.py` | `rtk_forwarder.yml` 読込 → `load_hardware_config()` に変更 |
| `scripts/ublox_survey_in.py` | `--port`, `--baud` デフォルト → `load_hardware_config()['f9p']` |
| `scripts/gps_compare_collect.py` | `--ublox`, `--ublox-baud` デフォルト → `load_hardware_config()['f9p']` |

各スクリプトの変更パターン:

```python
# 変更前
parser.add_argument('--port', default='COM8', ...)

# 変更後
from rtk_tools.config_loader import load_hardware_config
_hw = load_hardware_config()
parser.add_argument('--port', default=_hw['f9p']['serial_port'], ...)
```

---

## 5. 削除候補コンフィグファイル（5ファイル）

| ファイル | 削除理由 |
|----------|---------|
| `config/base_station.json` | `hardware.yml` に統合 |
| `config/rtk_forwarder.yml` | `hardware.yml` に統合 |
| `config/gcs_sshtunnel.yml` | `gcs_local.yml` と同一内容 |
| `config/gcs_raspi_bridge.yml` | `gcs_drone.yml` で代替可能 |
| `config/gcs_multidrone_test.yml` | `gcs_multidrone_example.yml` で代替可能 |

---

## 6. 最終コンフィグ構成（5ファイル + 環境別 + gitignore対象）

```
config/
├── hardware.yml                 # 【新規】全ハードウェア設定（git管理）
├── hardware.win.yml             # 【新規】Windows用上書き（git管理）
├── hardware.mac.yml             # 【新規】Mac用上書き（git管理）
├── hardware.local.yml           # 【新規】個人用上書き（gitignore対象）
├── gcs.yml                      # GCSデフォルト（シリアル接続）
├── gcs_local.yml                # SSH Tunnel + Tailscale 自動
├── gcs_production.yml           # 手動SSH Tunnel
├── gcs_drone.yml                # Raspi直接実行
└── gcs_multidrone_example.yml   # マルチドローン設定例
```

---

## 7. 懸念点と注意事項

### 7.1 NTRIP 設定の扱い

`rtk_forwarder.yml` には NTRIP キャスターの `host`, `port`, `mountpoint`, `username`, `password` が含まれている。これらは環境依存が強く、`hardware.yml` に入れると git 管理上好ましくない。

**案A**: `hardware.yml` に NTRIP セクションも含める（git管理だがパスワードに注意）
**案B**: NTRIP 設定は `config/ntrip.yml` として分離し、`hardware.local.yml` 相当として gitignore する
**案C**: NTRIP 設定は `gcs_local.yml` の `rtcm_*` 設定で代用する（既存の仕組みを流用）

### 7.2 影響範囲

- 既存の起動スクリプトやシェルスクリプトで `--serial-port COM8` を明示指定している場合は影響なし
- デフォルト値に依存している起動方法（引数なし）のみ影響あり
- `rtk_base_station_v2.py` は `--config config/base_station.json` がデフォルトなので、変更後は互換性に注意

### 7.3 テストへの影響

- `tests/test_rtk_base_station_integration.py` が `config/base_station.json` を参照している可能性あり
- 単体テストは `unittest.mock.patch` で `load_hardware_config()` をモックすれば影響を局所化可能

---

## 8. 実装手順

### フェーズ1: config_loader.py 拡張 + hardware.yml 作成

1. `config/hardware.yml` を作成（F9P + 基準局 + forward + retry + log）
2. `config/hardware.win.yml` を作成（`serial_port: "COM8"` を明示）
3. `config/hardware.mac.yml` を作成（`serial_port: "/dev/tty.usbmodem113301"` を明示）
4. `rtk_tools/config_loader.py` に `load_hardware_config()` を実装
5. OS自動判定で `hardware.win.yml` / `hardware.mac.yml` をフォールバック

### フェーズ2: 各スクリプトのデフォルト値変更（8ファイル）

6. `rtk_tools/rtk_base_station.py` — `--serial-port` デフォルト変更
7. `rtk_tools/rtk_base_station_v2.py` — `config/base_station.json` → `load_hardware_config()` 
8. `rtk_tools/rtk_data_collector.py` — デフォルト値変更
9. `rtk_tools/standalone_obs.py` — デフォルト値変更
10. `rtk_tools/rtk_forwarder_service.py` — `rtk_forwarder.yml` → `load_hardware_config()`
11. `scripts/ublox_survey_in.py` — デフォルト値変更
12. `scripts/gps_compare_collect.py` — デフォルト値変更

### フェーズ3: 不要ファイルの削除

13. `config/base_station.json` 削除
14. `config/rtk_forwarder.yml` 削除
15. `config/gcs_sshtunnel.yml` 削除
16. `config/gcs_raspi_bridge.yml` 削除
17. `config/gcs_multidrone_test.yml` 削除

### フェーズ4: ドキュメント更新

18. `docs/01-specification/communication-architecture.md` — 設定ファイル参照を更新
19. `docs/03-operations/operations_manual.md` — 起動手順を更新
20. `docs/03-operations/rtk_integration_guide.md` — 設定例を更新
21. `docs/02-development/development_history.md` — 履歴を追記