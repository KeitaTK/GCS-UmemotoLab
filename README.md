# ArduPilot用カスタムGCS（地上管制局）

Windows上で複数のArduPilotドローンを制御・監視するマルチドローン対応の地上管制局システムです。

## 概要

- **通信方式**: MAVLink v2 over UDP/Wi-Fi
- **ハードウェア**: Windows PC + Raspberry Pi 5（通信ブリッジ）
- **言語**: Python 3.10+
- **UI**: PySide6（Qt）
- **特徴**: カスタムMAVLinkメッセージ、RTKインジェクション、マルチドローン対応

### 主な機能

| 機能 | 説明 |
|------|------|
| **テレメトリー受信** | HEARTBEAT、SYS_STATUS、位置情報、カスタムメッセージ |
| **機体制御** | アーム/ディスアーム、離陸/着陸、ガイド制御（Guided mode） |
| **RTK補正** | u-center経由のRTCM配信により、地上局からドローンへのRTK Fixを実現 |
| **マルチドローン** | System IDによる複数ドローンの識別・制御 |
| **ロギング** | 全MAVLinkメッセージの記録 |

## システムアーキテクチャ

```
┌─────────────────────┐
│  Windows PC (GCS)   │
│  ┌───────────────┐  │
│  │  Python App   │  │
│  │  (PySide6)    │  │
│  │  pymavlink    │  │
│  └───────────────┘  │
└──────────┬──────────┘
           │ UDP/TCP
      Wi-Fi Network
           │
┌──────────┴──────────┐
│  Raspberry Pi 5     │
│  mavlink-router     │
│  (通信ブリッジ)      │
└──────────┬──────────┘
           │ Serial
    ┌──────┴──────┐
    │   ArduPilot │
    │   (Pixhawk) │
    └─────────────┘
```

## セットアップ

### 前提条件

- Python 3.10 以上
- Windows 10/11
- Raspberry Pi 5 + mavlink-router（ドローン側）
- u-center（オプション、RTK使用時）

### インストール

```bash
# リポジトリのクローン
git clone https://github.com/your-repo/gcs-system.git
cd gcs-system

# 仮想環境の作成
python -m venv venv
venv\Scripts\activate

# 依存パッケージのインストール
pip install -r requirements.txt
```

### 設定

`config/gcs.yml` を編集し、ドローンのIPアドレスとSystem IDを設定します：

```yaml
udp_listen_port: 14550
drones:
  drone1:
    system_id: 1
    endpoint: "192.168.1.100:14550"
rtcm_tcp_port: 5000
```

## GitHub Copilotを使った開発ワークフロー

このプロジェクトは、GitHub Issueとpull requestsを通じた段階的な開発フローをサポートしています。

### 開発フロー図

```
1. Issue作成
   ↓
2. Copilotに実装委譲
   ↓
3. Pull Request作成
   ↓
4. ローカルテスト・検証
   ↓
5. 動作確認後、Merge
```

### ステップバイステップ

#### 1️⃣ Issue の作成

目的のタスクを以下の形式でIssueとして作成します：

**例：** 「SYS_STATUSメッセージの受信とUI表示機能を実装」

```markdown
## 概要
ドローンのバッテリー状態やシステムヘルスを表示するため、
SYS_STATUSメッセージをパースしてUIに表示する機能を実装します。

## 受け入れ基準
- [ ] SYS_STATUSメッセージの受信ロジック実装
- [ ] バッテリー電圧をステータスパネルに表示
- [ ] システムエラーフラグの可視化
- [ ] ユニットテストの作成

## 参考資料
- MAVLink仕様: https://mavlink.io/en/messages/common.html#SYS_STATUS
```

#### 2️⃣ Copilotへの実装委譲

以下のコマンドをターミナルで実行：

```bash
# フィーチャーブランチの作成
git checkout -b feature/sys-status-display

# Copilotに実装を指示（VS Codeのチャットで）
# 「このIssueを実装してください」
```

**VS Code Copilot Chat での指示例：**

```
Issue #XX: SYS_STATUSメッセージの受信とUI表示機能を実装してください。
受け入れ基準：
- SYS_STATUSメッセージの受信ロジック実装
- バッテリー電圧をステータスパネルに表示
- システムエラーフラグの可視化
- ユニットテストの作成

前提条件：
- 既存の MavlinkConnection クラスを使用
- TelemetryStore に SYS_STATUS データを保存
```

#### 3️⃣ Pull Request の作成

Copilotが実装完了後、PR を作成します：

```bash
git add .
git commit -m "feat: Implement SYS_STATUS message reception and UI display (#XX)"
git push origin feature/sys-status-display
```

**PR テンプレート（自動）:**

```markdown
## Issue
Closes #XX

## 変更内容
- SYS_STATUSメッセージの受信ロジック実装
- バッテリー電圧をステータスパネルに表示
- システムエラーフラグの可視化
- ユニットテストの作成（テストカバレッジ: 85%以上）

## テスト方法
1. ドローンを接続
2. GCSアプリを起動
3. ステータスパネルにバッテリー情報が表示されることを確認
4. pytest で自動テストを実行
```

#### 4️⃣ 検証（Verification）

**ローカル環境での動作確認：**

```bash
# ブランチをチェックアウト
git checkout feature/sys-status-display
git pull origin feature/sys-status-display

# テスト実行
pytest tests/ -v

# GCS アプリの起動と動作確認
python app/main.py
```

**確認項目：**
- ✅ テストがすべてパス
- ✅ ドローンと通信でき、SYS_STATUSが表示される
- ✅ エラーハンドリングが機能する
- ✅ ログに異常が出ていない

**検証完了後、コメントで報告：**

```markdown
## 検証結果

- ✅ テスト成功（5/5 cases passed）
- ✅ 実ドローンで動作確認完了
- ✅ コード品質：問題なし
- 📌 別途確認不要

Approved! 準備完了。
```

#### 5️⃣ Merge

検証が完了したら、PR をマージします：

```bash
# main ブランチへ切り替え
git checkout main

# フィーチャーブランチをマージ
git merge --no-ff feature/sys-status-display

# リモートにプッシュ
git push origin main

# フィーチャーブランチの削除
git branch -d feature/sys-status-display
git push origin --delete feature/sys-status-display
```

GitHub UI からのマージ（推奨）:
1. PR ページの "Merge pull request" ボタンをクリック
2. Commit message: デフォルト（Issue #XX の参照を自動挿入）
3. "Confirm merge" をクリック
4. "Delete branch" をクリック

## ワークフロー推奨事項

| 段階 | 責任 | ツール |
|------|------|--------|
| Issue 作成 | 開発者（デザイナー） | GitHub Issues |
| 実装 | GitHub Copilot | VS Code + Copilot |
| テスト | GitHub Copilot | pytest |
| 検証 | 開発者（人間） | ローカル環境 |
| Merge | 開発者 | GitHub |

## プロジェクト構造

```
gcs-system/
├── README.md                 # このファイル
├── requirements.txt          # Python 依存パッケージ
├── config/
│   └── gcs.yml              # GCS 設定ファイル
├── app/
│   ├── main.py              # アプリケーション入口
│   ├── ui/
│   │   ├── main_window.py    # メインUI
│   │   └── panels/           # 各パネルコンポーネント
│   ├── mavlink/
│   │   ├── connection.py     # UDP 接続管理
│   │   ├── router.py         # メッセージルーター
│   │   └── commands.py       # コマンド送信
│   ├── rtk/
│   │   └── injector.py       # RTK 補正配信
│   └── telemetry/
│       └── store.py          # テレメトリーデータ
├── tests/
│   ├── test_connection.py    # 接続テスト
│   ├── test_router.py        # ルーターテスト
│   └── test_commands.py      # コマンドテスト
└── docs/
    ├── spec.md               # 詳細仕様
    ├── dev_guide.md          # 開発ガイド
    └── design.md             # アーキテクチャ設計
```

## MVPで実装する機能

1. **リポジトリセットアップ**：フォルダー構造、基本設定
2. **MAVLink コア**：UDP入出力、メッセージルーター、状態管理
3. **RTK インジェクション**：RTCM リーダー、データ配信
4. **コマンド制御**：アーム/ディスアーム、離陸/着陸
5. **UI**：ドローンリスト、テレメトリー表示、制御パネル
6. **統合テスト**：シングル・マルチドローン検証

## 受け入れ基準（成功の定義）

- ✅ 少なくとも1台のドローンのHEARTBEATが表示される
- ✅ NAMED_VALUE_FLOAT 値がリアルタイム更新される
- ✅ アーム/ディスアームが成功する
- ✅ RTCMストリームが転送され、ログに記録される
- ✅ 複数ドローン（2台以上）で動作確認完了
- ✅ 全テストがパス、カバレッジ 80% 以上

## 参考資料

- [MAVLink Protocol Specification](https://mavlink.io/en/)
- [ArduPilot Documentation](https://ardupilot.org/dev/)
- [pymavlink Guide](https://github.com/ArduPilot/pymavlink)
- [PySide6 Documentation](https://doc.qt.io/qtforpython/)
- [GitHub Issues & Pull Requests](https://docs.github.com/en/issues)

## ライセンス

[MIT License](LICENSE)

## 問い合わせ

質問や機能提案は GitHub Issues で受け付けています。
