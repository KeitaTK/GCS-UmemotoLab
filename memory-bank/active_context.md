# Active Context — GCS-UmemotoLab

## 現在取り組んでいること

### UV 移行（✅ 完了）
- `pyproject.toml` を導入し、UV による依存管理に完全移行済み
- `uv venv && uv sync` で環境構築（従来の `pip install -r requirements.txt` 互換も維持）
- Raspi 向けは `requirements_raspi.txt` で最小依存を維持（UV の optional-dependencies `raspi` としても定義済み）
- `.python-version` で Python 3.14 を指定

### 開発環境の整備
- `.clinerules`（Cline ルールファイル）の作成・整備
- Memory Bank ディレクトリ構造の作成（本作業）
- Sphinx ドキュメント生成の整備（`docs_sphinx/`）

## 最近の変更

| 日付 | 変更内容 | 影響範囲 |
|------|----------|----------|
| 2026-06 | `pyproject.toml` 導入、UV 移行完了 | プロジェクト全体の依存管理 |
| 2026-06 | `.clinerules` 作成 | Cline の挙動制御 |
| 2026-06 | Memory Bank ディレクトリ作成 | プロジェクト知識の体系化 |
| 2026-05-29 | 未実装機能の実装拡張（UI表示、ガイドモード、コマンド制御、複数フィールド表示、RTK状態監視） | `main_window.py`, `telemetry_store.py`, `connection.py`, `command_dispatcher.py` |
| 2026-05-29 | COMMAND_ACK追跡・タイムアウト・リトライ機構実装（Phase 2-1, 2-2） | `command_dispatcher.py`, `message_router.py`, `main_window.py` |
| 2026-05-29 | エラーハンドリング実装（Phase 3-2）：UDP/Serial 接続エラー検出・回復 | `connection.py`, `main_window.py`, `test_connection_errors.py` |
| 2026-05-29 | グラフ化機能実装（Phase 1-2）：3タブUI、pyqtgraph リアルタイムグラフ | `main_window.py`, `telemetry_plotter.py` |
| 2026-05-29 | RTCM切断復帰の再接続実装 | `rtcm_reader.py` |
| 2026-04-28 | RTK基地局オールインワン化（Phase A）、ドキュメント統合 | `rtk_base_station.py`, `docs/` |

## 次のステップ

### 優先度: 高
- [ ] **実機テスト検証**: Raspberry Pi 経由での実機接続テスト（コマンド送信、RTCM注入、接続エラー回復）
- [ ] **長時間運用テスト**: Phase 7 の生産テスト継続（CPU使用率・メモリリーク監視）
- [ ] **NTRIP再取得**: RTCMストリーム切断時の NTRIP 再接続・認証再取得の強化

### 優先度: 中
- [ ] **UIの自由レイアウト編集**: 複数パネルのドラッグ＆ドロップ再配置
- [ ] **高度な複数コマンド制御**: 厳密なグループ同期制御（複数機同時テイクオフ等）
- [ ] **GPS拡張（Phase 1-3）**: GPS_DOP 表示、衛星コンステレーション可視化

### 優先度: 低
- [ ] **Sphinx ドキュメントの全モジュールカバレッジ**: `docs_sphinx/` の `.rst` ファイル拡充
- [ ] **CI/CD パイプライン**: GitHub Actions での自動テスト・ビルド

## アクティブな課題・検討事項

### 技術的課題
1. **Raspi 側の依存管理**: UV の optional-dependencies と `requirements_raspi.txt` の二重管理状態。将来的に UV 一本化するか検討が必要。
2. **Python 3.14 要件**: `pyproject.toml` で `>=3.14` としているが、Raspi の標準 Python は 3.11 系。Raspi 側では `pyproject.toml` を参照せず `requirements_raspi.txt` を使用する運用で回避中。
3. **MAVLink メッセージパースの互換性**: `message_router.py` で pymavlink の新旧 API（`parse_buffer` / `parse_char_array` / `decode`）のフォールバック対応をしているが、pymavlink のバージョンアップで破壊的変更が入る可能性。
4. **SITL テストの自動化**: 現在のテストは主にユニットテスト。SITL を使った統合テストの自動化が未整備。

### 設計上の検討事項
1. **設定ファイルの優先順位**: `$GCS_CONFIG_PATH` > `gcs.user.local.yml` > `gcs_local.yml` > `gcs.yml`。ユーザー固有設定とGit管理下設定の分離は適切か。
2. **マルチドローン対応の深化**: 現在は System ID による識別のみ。ドローンごとの個別設定（パラメータ違い等）への対応が必要か。
3. **RTCMインジェクションのブロードキャスト**: 現在は全ドローン（System ID 1, 2）にブロードキャストしているが、選択的注入が必要なケースがあるか。
4. **ログローテーション**: 現在 5MB x 5世代。長時間フライトでログ消失のリスクはないか。

### 運用上の注意点
- **Force Arm は屋内テスト専用**: 実飛行では絶対に使用しない。テスト後は `dispatcher.restore_arm_params()` でデフォルトに戻す。
- **RTCM ホスト設定**: Windows/u-center と Raspberry Pi/GCS が別ホストの場合は `rtcm_host` を配信元 IP に変更する。
- **SSH トンネル**: 方式Aでは GCS 起動前に別ターミナルで SSH トンネルを確立しておく必要がある。
