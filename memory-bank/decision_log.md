# Decision Log — GCS-UmemotoLab

> このファイルはプロジェクトの重要なアーキテクチャ・技術判断を記録します。
> 各エントリは日付降順（新しい決定が上）。

---

## 2026-07-07: 全体アーキテクチャ — F9P→TCP→Raspi→Pixhawk→CAN→F9P Rover

- **決定内容**: RTK補正データの配信経路を「Windows F9P→TCP:2101→Raspi→serial→Pixhawk→CAN→F9P Rover」に確定。Pixhawk側に `GPS1_TYPE=9` (DroneCAN), `CAN_D1_PROTOCOL=1`, `GPS_DRV_OPTIONS=64` を設定。
- **理由**:
  - F9P RoverをDroneCAN経由でPixhawkに接続し、RTCM補正データをPixhawk経由で注入する方式がArduPilotの推奨構成
  - GPS_DRV_OPTIONS=64 でRover側のRTCM受信を有効化
  - Raspi→Pixhawk間は1M baud + RTS/CTSで高速・信頼性を確保
- **影響**:
  - `raspi/config.yml` に `serial_baudrate: 1000000`, `serial_rtscts: true` を設定
  - `app/mavlink/connection.py` に `serial_rtscts` パラメータ追加
  - Pixhawkパラメータマニュアル設定が必要（GPS1_TYPE=9, CAN_D1_PROTOCOL=1, GPS_DRV_OPTIONS=64）
- **代替案**: Serial直結（却下：F9P RoverをCANで接続する方が配線と拡張性で優位）

---

## 2026-07-07: rtk_base_station_v2.py autoモード採用

- **決定内容**: `config/config.yml` の `base_station.mode` を `auto` に設定。USBポート自動検出 + 60秒単独測位で基準座標を自動取得する方式をデフォルトとする。
- **理由**:
  - F9PをUSB接続するだけで基地局が起動でき、手動での座標設定が不要
  - フィールドでの設置が簡略化され、ヒューマンエラーを防止
  - 60秒の単独測位で十分な精度の基準座標が得られる（サンプル5で検証済み）
- **影響**:
  - `rtk_base_station_v2.py` の `_merge_config()` にautoモード処理を実装（L136-163）
  - `standalone_obs.py` の `auto_detect_port()` / `auto_observe_position()` に依存
  - 単独測位失敗時は `mode=manual` での再試行が必要
- **代替案**: manual固定（却下：運用の手間とヒューマンエラーリスクのため）

---

## 2026-07-07: RTCM false preamble バグ修正

- **決定内容**: RTCM v3 フレーム解析において、0xD3 preamble検出後に予約ビット（buffer[1]>>2）が非ゼロの場合、false preambleと判定してスキップする。
- **理由**:
  - RTCM v3 仕様では preamble の次の3ビットは予約ビット（must be zero）
  - ノイズやデータ破損により 0xD3 が偶然出現した場合、フレーム長計算が誤った値になり後続フレームが破壊される
  - 予約ビットチェックにより false preamble を 99.6% 以上の確率で排除可能
- **影響**:
  - `rtk_base_station_v2.py` L283-287 に reserved bits チェックを追加
  - フレーム検出の信頼性が向上
- **代替案**: CRC-24Q 検証のみに頼る（却下：破損フレームの誤検出確率が高く、後続フレームの連鎖破壊リスクがある）

---

## 2026-07-07: RTCM生ログ保存機能

- **決定内容**: 基地局が受信した全RTCMフレームを `logs/rtcm_raw_{timestamp}.bin` にバイナリ保存する。ログは基地局起動時に自動生成、停止時に自動クローズ。
- **理由**:
  - RTK品質の事後検証・トラブルシューティングにRTCM生データが必要
  - RTKLIB等の後処理ツールで再生・解析可能な形式で保存
  - バイナリ形式によりストレージ効率が高い
- **影響**:
  - `rtk_base_station_v2.py` L219-244（ファイルオープン/クローズ）、L305-310（フレーム書き込み）
  - `logs/` ディレクトリに `.bin` ファイルが蓄積される（現状ローテーションなし→今後の課題）
- **代替案**: フレーム解析後のテキストログのみ（却下：生データ再生が不可能になる）

---

## 2026-07-07: Raspberry Pi → Pixhawk シリアル高速化（1M baud + RTS/CTS）

- **決定内容**: RaspiとPixhawk間のシリアル通信を115200bps→1Mbpsに高速化し、RTS/CTSハードウェアフロー制御を有効化。
- **理由**:
  - MAVLinkテレメトリ + RTCM注入の同時通信では115200bpsでは帯域不足が懸念される
  - 1M baudはPixhawk TELEM1がサポートする最大レート
  - RTS/CTSにより高ボーレート時のバッファオーバーフローを防止
- **影響**:
  - `raspi/config.yml` : `serial_baudrate: 1000000`, `serial_rtscts: true`
  - `app/mavlink/connection.py` : `serial_rtscts` パラメータを `serial.Serial(rtscts=...)` に伝達
  - Pixhawk側 TELEM1 の SERIAL1_BAUD も 115（=115200bps）から適切な値に変更が必要な場合がある
- **代替案**: 115200bpsのまま（却下：帯域不足のリスク）

---

## 2026-07-07: Windows multiprocessing spawn モード対応

- **決定内容**: `rtk_base_station_v2.py` の `main()` エントリポイントに `multiprocessing.freeze_support()` を追加し、`__main__` ガード内で呼び出す。
- **理由**:
  - Windows の multiprocessing はデフォルトで `spawn` モード（Linux は `fork`）
  - spawn モードでは `freeze_support()` がないと子プロセス生成時に無限再帰が発生する
  - 実機テスト時に Windows で `RuntimeError: An attempt has been made to start a new process...` が発生したため修正
- **影響**:
  - `rtk_base_station_v2.py` L780: `multiprocessing.freeze_support()`
  - Windows/Linux 両方でマルチプロセスが正常動作
- **代替案**: マルチスレッド化（却下：Ctrl+C即停止の要件を満たせない）

---

## 2026-06-17: Web UI カード方式採用

- **決定内容**: Web UIのレイアウトをPySide6風のタブ構造から、ドローンカードグリッド方式に統一した。
- **理由**:
  - マルチドローン対応GCSでは、全機の状態を俯瞰できるカード表示が適切
  - PySide6風タブ（Dashboard/Graph/Raw Data）はWeb版では冗長
  - カードクリックによる直感的なドローン選択
- **影響**:
  - index.html から #panel-dashboard 削除、#multi-drone-grid をメインに
  - style.css は flex column に再構築、#sidebar 関連CSS削除
  - dashboard.js に selectCard() / getSelectedSystemId() 追加
  - controls.js の選択ロジックを #drone-list → .drone-card.selected に変更
  - 個別制御（Arm/Disarm/Takeoff/Land/Guided）は未実装（今後の課題）
- **代替案**: 旧タブ構造の維持（却下：レイアウト崩れの抜本的解決が必要）

---

## 2026-06: UV 移行（pip → UV）

- **決定内容**: Python パッケージマネージャーを pip から UV に移行。`pyproject.toml` を導入し、`uv venv && uv sync` を標準のセットアップ手順とする。
- **理由**:
  - UV は pip の 10-100 倍高速
  - `pyproject.toml` による依存管理の標準化（PEP 621）
  - `uv.lock` による再現可能なビルド
  - optional-dependencies で環境別の依存を宣言可能
- **影響**:
  - 開発環境構築手順が `uv venv && uv sync` に変更
  - GitHub リポジトリに `pyproject.toml`, `uv.lock` を追加
  - `requirements.txt`, `requirements_raspi.txt` は pip 互換用に維持
- **代替案**: pip の継続使用（却下：速度と再現性で UV が優位）

---

## 2026-06: Raspi 側は pip 維持

- **決定内容**: Raspberry Pi 側の依存管理は UV に移行せず、`requirements_raspi.txt` による pip インストールを維持する。
- **理由**:
  - Raspi の標準 Python が 3.11 系であり、`pyproject.toml` の `requires-python = ">=3.14"` を満たさない
  - Raspi 上で UV の追加インストールが運用負荷となる
  - Raspi は最小依存（pymavlink, PyYAML, pyserial, pytest）で十分
- **影響**:
  - `requirements_raspi.txt` を維持（`pyproject.toml` の `[project.optional-dependencies] raspi` にも定義済み）
  - Raspi 上のセットアップ手順は `pip install -r requirements_raspi.txt` のまま
  - 将来的に Raspi の Python が 3.14+ になったら UV 一本化を再検討
- **代替案**: Raspi にも UV を導入（却下：Python バージョン制約と運用負荷のため）

---

## 2026-05-29: マルチタブ UI 採用（3タブ構成）

- **決定内容**: メインウィンドウを QTabWidget による 3タブ構成（Dashboard / Graph / Raw Data）にリファクタリング。
- **理由**:
  - 情報量の増加に伴い、単一パネルでは表示しきれなくなった
  - ユーザーが必要な情報に素早くアクセスできる
  - 将来的な機能追加（カメラ映像など）を新しいタブとして追加可能
- **影響**:
  - `main_window.py` を大幅リファクタリング（`_create_dashboard_tab()`, `_create_graph_tab()`, `_create_raw_data_tab()` に分割）
  - ウィンドウサイズを 1200x800 に拡大
  - ScrollArea で各タブをスクロール対応
- **代替案**: ドッキングパネル方式（却下：実装の複雑さと現段階での必要性の低さ）

---

## 2026-05-29: コマンドリトライ機構（最大3回）

- **決定内容**: コマンド送信時に COMMAND_ACK を待機し、5秒のタイムアウトで最大3回の自動リトライを行う。
- **理由**:
  - UDP 通信は信頼性が低く、パケットロスが発生しうる
  - ミッションクリティカルなコマンド（ARM/DISARM）の到達保証が必要
  - 3回はネットワークジッターを吸収しつつ、無限リトライを防ぐ適切な閾値
- **影響**:
  - `command_dispatcher.py` に `_track_command()`, `_resend_command()`, `check_timeouts()` を追加
  - `message_router.py` に COMMAND_ACK 処理を追加
  - UI にリトライ回数表示を追加（色分け：緑/オレンジ/赤）
- **代替案**: リトライなしの単発送信（却下：信頼性不足）

---

## 2026-05-29: Exponential Backoff によるシリアル再接続

- **決定内容**: シリアル接続（Pixhawk 直結時）の切断時に exponential backoff（1.0→1.5→2.25→3.375→5.0秒、上限5秒）で再接続を試みる。
- **理由**:
  - 物理的な接続不良時に即時リトライを繰り返すと CPU を浪費する
  - 指数バックオフにより、一時的な切断と永続的な切断を区別できる
  - 上限5秒でユーザー体験を損なわない範囲に抑える
- **影響**:
  - `connection.py` の `_recv_loop_serial()` に exponential backoff ロジックを追加
  - `SERIAL_CRITICAL` エラーで UI に通知（`serial_max_errors=5` 超過時）
- **代替案**: 固定間隔リトライ（却下：再接続が成功するまでの無駄なリトライが多い）

---

## 2026-05-29: エラーコールバックアーキテクチャ

- **決定内容**: 接続エラー検出 → UI 通知をコールバックベースの非同期アーキテクチャで実装。
- **理由**:
  - MavlinkConnection はネットワーク I/O スレッドで動作しており、UI スレッドと分離されている
  - コールバックにより、MavlinkConnection が UI に直接依存しない疎結合を実現
  - 複数のエラーハンドラ（UI表示、ロギング、通知など）を登録可能
- **影響**:
  - `connection.py` に `register_error_callback()`, `_trigger_error_callback()` を追加
  - `main_window.py` でエラーコールバックを登録し、エラーダイアログを表示
  - `test_connection_errors.py` でコールバックの実行順序・一貫性をテスト
- **代替案**: ポーリング方式（却下：UI スレッドでのポーリングはパフォーマンス低下とコードの複雑化を招く）

---

## 2026-05-29: RTCM再接続（指数バックオフ）

- **決定内容**: RTCM TCP ストリーム切断時に exponential backoff で再接続を試みる。
- **理由**:
  - RTCM ストリームは長時間のフライト中に切断される可能性がある
  - RTK Fix の維持には継続的な RTCM 注入が不可欠
  - 指数バックオフにより再接続の成功率を高める
- **影響**:
  - `rtcm_reader.py` に TCP 再接続ループ、接続統計を追加
  - `test_rtk_integration.py` に切断後再接続のテストを追加
- **代替案**: 切断時は手動再起動（却下：自動化による運用負荷軽減のため）

---

## 2026-04-28: RTK基地局オールインワン化

- **決定内容**: RTCM 受信・配信を `rtk_base_station.py` に一元化。マルチスレッド構成（SerialReader + TcpServer + UdpBroadcaster）を採用。
- **理由**:
  - 従来は NTRIP受信・シリアル受信のスクリプトが分かれており、運用が煩雑
  - ublox からのシリアル受信を PC 側で一元化するスクリプトが不足していた
  - 1つのサービスで基地局データ取得からPC転送までをカバーする必要があった
- **影響**:
  - `rtk_base_station.py` を新規作成
  - `config/rtk_forwarder.yml` で設定を一元管理
- **代替案**: 複数スクリプトの組み合わせ（却下：運用の複雑さと障害復帰の困難さ）

---

## 2026-04-28: 設定ファイル優先順位の設計

- **決定内容**: 設定ファイルの解決順序を `$GCS_CONFIG_PATH` > `gcs.user.local.yml` > `gcs_local.yml` > `gcs.yml` とする。
- **理由**:
  - 環境変数による明示的な指定を最優先（CI/CD やデバッグ用）
  - Git 管理外のユーザー固有設定（`gcs.user.local.yml`）で個人の接続情報を保護
  - ローカル開発用と本番用で設定を分離可能
- **影響**:
  - `rtk_tools/config_loader.py` で優先順位に従った設定ファイル解決を実装
  - `.gitignore` に `config/gcs.user.local.yml` を追加
- **代替案**: 単一設定ファイル + 環境変数オーバーライド（却下：柔軟性不足）

---

## 2026-04-28: MAVLink v2 採用

- **決定内容**: MAVLink プロトコルバージョンとして v2 を採用。mavlink-router 設定でも `MavlinkVersion=2.0` を明示。
- **理由**:
  - MAVLink v2 は v1 と比較して拡張ヘッダ（送信元システム/コンポーネントID）、パケット署名、最大ペイロード拡大などの利点がある
  - pymavlink が v2 をフルサポート
  - ArduPilot の推奨プロトコルバージョン
- **影響**:
  - `connection.py` で `mavutil.mavlink.MAVLink(None)` を使用（v2 互換）
  - `message_router.py` で v2 メッセージのパースに対応
  - 手動フレーム構築（`SET_POSITION_TARGET_LOCAL_NED`）でも v2 形式（`0xFD` マジックバイト）を使用
- **代替案**: MAVLink v1（却下：拡張性・セキュリティ面で v2 が優位）

---

## 2026-04-27: Tailscale によるリモート接続

- **決定内容**: PC ↔ Raspi 間のリモート接続に Tailscale VPN を採用。
- **理由**:
  - 研究室 Wi-Fi とテザリング（モバイル回線）の両方で安定した接続を提供
  - SSH トンネルとの組み合わせで MAVLink 通信を暗号化
  - セットアップが容易（`tailscale up` のみ）
  - NAT 越えが自動で行われる
- **影響**:
  - `config/gcs_local.yml` で Tailscale IP（`100.123.158.105`）をエンドポイントに指定
  - `scripts/tailscale_setup_raspi.sh` を提供
  - README に Tailscale 経由の SSH トンネル構築手順を記載
- **代替案**: ポートフォワーディング + DDNS（却下：セキュリティリスクと不安定性）

---

## テンプレート

このファイルに新しい決定を追加する際は、以下のフォーマットを使用してください：

```markdown
## YYYY-MM-DD: [決定のタイトル]

- **決定内容**: [何を決めたか]
- **理由**: [なぜその決定をしたか]
- **影響**: [決定による影響範囲]
- **代替案**: [検討したが却下した代替案（省略可）]
```
