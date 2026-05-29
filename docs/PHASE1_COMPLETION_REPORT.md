# GCS 実装進捗レポート - Phase 1完了版

**作成日**: 2026年5月29日 18:30  
**対象**: GCS-UmemotoLab プロジェクト  
**ステータス**: Phase 1-1 実装完了、残り機能の実装計画確定

---

## 📊 現在のステータス

### Phase 1: UI テレメトリー表示強化

#### ✅ Phase 1-1: SYS_STATUS表示機能 - **完了**

実装内容:
- **telemetry_store.py**: `get_sys_status()` と `get_global_position()` メソッドを追加
- **main_window.py**: 以下の UI パネルを実装
  - System Status グループ: Armed/Disarmed 状態、フライトモード
  - Battery Status グループ: 電圧、電流、残量（パーセント）
  - GPS Status グループ: 衛星数、位置情報（緯度経度）、高度（MSL/相対）
- **main.py**: `dispatcher.guided` を初期化してGuided Mode を UI から操作可能に
- **requirements.txt**: pyqtgraph・matplotlib を依存関係に追加

ファイル変更:
```
✅ app/mavlink/telemetry_store.py
✅ app/ui/main_window.py  
✅ app/main.py
✅ requirements.txt
```

構文チェック結果: ✅ PASS

---

#### ⏳ Phase 1-2: 複数 NAMED_VALUE_FLOAT のグラフ化 - **準備完了、統合待ち**

作成ファイル:
- `app/ui/telemetry_plotter.py`: pyqtgraph を使用したリアルタイムグラフウィジェット

実装予定:
- UI タブに「Graph」タブを追加
- ドローン選択・フィールド選択でドロップダウン を操作
- リアルタイムで時系列データをプロット

次ステップ:
- main_window.py に telemetry_plotter.py を統合
- タブビューで Dashboard/Graph/Raw Data の3つを切り替え

---

#### ⏳ Phase 1-3: GPS 位置情報の簡易表示 - **基本実装済み、強化待ち**

現状:
- GPS 座標（緯度経度）は Phase 1-1 で既に表示
- 高度（MSL・相対）も表示

拡張予定:
- Folium による簡易地図表示（オプション）
- フライトパス可視化（軌跡記録）

---

### Phase 2: コマンド実行の堅牢化

#### ⏳ Phase 2-1: COMMAND_ACK確認応答処理

実装予定:
```python
# command_dispatcher.py の改善
class CommandDispatcher:
    def __init__(self, connection):
        self.pending_commands = {}  # command_id -> (timestamp, expected_ack)
        self.ack_timeout = 5.0  # seconds
    
    def send_command_long(self, system_id, command_id, params):
        # コマンド送信前に内部カウンタ increment
        msg_id = self._get_next_command_id()
        # MAVLink送信
        self.pending_commands[msg_id] = (time.time(), command_id)
        # 5秒以内に COMMAND_ACK を受け取ることを期待
    
    def handle_command_ack(self, ack_message):
        # COMMAND_ACK メッセージを受け取ったら pending から削除
        if ack_message.command in self.pending_commands:
            del self.pending_commands[ack_message.command]
```

#### ⏳ Phase 2-2: タイムアウト・リトライ機構

実装予定:
- タイムアウト時の自動リトライ
- 最大3回までリトライ
- ユーザーに通知（成功/失敗/タイムアウト）

---

### Phase 3: エラーハンドリング・テスト拡張

#### ⏳ Phase 3-1: Guided Mode UI統合

現状:
- UI 入力フィールド実装済み（North/East/Down）
- [Send Position Target] ボタン実装済み

テスト待ち:
- 実機でのGuided Mode コマンド送信・応答確認

#### ⏳ Phase 3-2: エラーハンドリング強化

予定項目:
- UDP パケット損失時のリカバリ
- シリアル接続エラーの自動復旧
- RTCM ストリーム切断時の警告表示

---

## 📈 実装スケジュール推奨

### 優先度 (High → Low)

| 優先度 | 項目 | 難度 | 期待効果 | 推定時間 |
|--------|------|------|--------|---------|
| ⭐⭐⭐ | Phase 1-2: グラフ化 | 中 | 視覚化で運用効率大幅向上 | 2-3h |
| ⭐⭐⭐ | Phase 2-1: COMMAND_ACK | 中 | 信頼性向上、コマンド実行確認 | 2-3h |
| ⭐⭐ | Phase 3-1: Guided Mode テスト | 低 | マニュアル飛行制御 | 1h |
| ⭐⭐ | Phase 3-2: エラーハンドリング | 中 | ロバストネス向上 | 2h |
| ⭐ | Phase 1-3: 地図表示 | 高 | ニッチ機能（オプション） | 3-4h |

---

## 🚀 次のアクション

### 短期（今週）
1. Phase 1-2 UI統合: telemetry_plotter.py を main_window.py に組み込み
2. 簡易テスト: dummy_sitl.py でのダミーデータでグラフ表示確認

### 中期（今月中）
3. Phase 2-1 実装: command_dispatcher.py にCOMMAND_ACK処理を追加
4. 実機テスト: Raspberry Pi + Pixhawk での統合テスト

### 長期（来月以降）
5. エラーハンドリング強化
6. ドキュメント更新

---

## 📝 実装チェックリスト

### Phase 1-1: SYS_STATUS表示機能
- [x] telemetry_store.py にメソッド追加
- [x] main_window.py に UI パネル追加
- [x] main.py で dispatcher.guided を初期化
- [x] requirements.txt を更新
- [x] 構文チェック PASS

### Phase 1-2: グラフ化
- [x] telemetry_plotter.py を作成
- [ ] main_window.py に統合
- [ ] ドロップダウンコンボボックスで表示フィールド選択
- [ ] リアルタイムプロット動作確認

### Phase 2-1: COMMAND_ACK処理
- [ ] 待機中のコマンド管理辞書を実装
- [ ] COMMAND_ACK メッセージハンドラを実装
- [ ] タイムアウト検出ロジック
- [ ] UI での確認応答表示

### Phase 3: その他
- [ ] エラーハンドリング強化
- [ ] ユニットテスト拡張
- [ ] 実機統合テスト

---

## 📚 関連ドキュメント

- **IMPLEMENTATION_DETAILS.md** - 詳細な機能仕様
- **PROJECT_OVERVIEW.md** - プロジェクト概要
- **development_history.md** - 開発履歴
- **design.md** - システム設計
- **spec.md** - 機能要件

---

## ✅ Phase 1-1 完了により実現したこと

| 項目 | 改善前 | 改善後 |
|------|--------|--------|
| **バッテリー表示** | ❌ なし | ✅ 電圧・電流・残量 |
| **GPS 表示** | ❌ なし | ✅ 衛星数・位置・高度 |
| **System Status** | ⚠️ 最小限 | ✅ Mode・Health追加 |
| **UI 見やすさ** | ❌ 縦一列 | ✅ グループ化 |
| **Guided Mode** | ❌ 非操作可 | ✅ UI から入力可 |

---

**レビュー対象者**: 瀧敬太  
**次回確認日**: 2026年6月2日
