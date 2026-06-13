# Decision Log — GCS-UmemotoLab

> このファイルはプロジェクトの重要なアーキテクチャ・技術判断を記録します。
> 各エントリは日付降順（新しい決定が上）。

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
