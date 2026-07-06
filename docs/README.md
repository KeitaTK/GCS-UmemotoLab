# GCS-UmemotoLab ドキュメント

このディレクトリは、GCS-UmemotoLab プロジェクトの全ドキュメントを管理します。

## ディレクトリ構成

```
docs/
├── README.md                    # このファイル（ドキュメントインデックス）
├── DOCUMENTATION_GUIDE.md       # docstring 記述規約
│
├── 01-specification/            # 仕様・設計
│   ├── spec.md                  # 機能要件・非機能要件
│   ├── design.md                # システムアーキテクチャ設計
│   ├── communication-architecture.md  # MAVLink通信経路・トポロジ
│   ├── flight_roadmap.md        # 飛行試験ロードマップ
│   ├── web-ui-spec.md           # Web UI 仕様
│   └── multi-drone-dashboard-design.md  # マルチドローンUI設計
│
├── 02-development/              # 開発ガイド・履歴
│   ├── dev_guide.md             # 開発環境構築ガイド
│   └── development_history.md   # 全開発履歴（時系列）
│
├── 03-operations/               # 運用マニュアル
│   ├── operations_manual.md     # 全体運用手順
│   ├── multidrone_operations_guide.md  # マルチドローン運用手順
│   ├── raspi-connection-setup.md  # Raspberry Pi 接続設定
│   ├── rtk_setup_guide.md       # RTK セットアップガイド
│   ├── rtk_integration_guide.md # RTK 統合ガイド
│   └── troubleshooting_guide.md # トラブルシューティング
│
├── 04-testing/                  # テスト関連
│   ├── test_cases.md            # テストケース一覧
│   ├── 2026-07-03_test_report.md  # テストレポート
│   └── test_rtcm_injection_20260424.md  # RTCM注入テスト
│
├── 05-implementation/           # 実装詳細
│   ├── IMPLEMENTATION_DETAILS.md         # Observer/EKF 実装詳細
│   ├── RTK_BASE_STATION_IMPLEMENTATION.md  # RTK基地局実装詳細
│   ├── gps_comparison_sample1.md         # GPS比較分析
│   └── sample5_rtk_fixed.png             # RTK FIX 画像
│
└── archive/                     # アーカイブ（陳腐化したレポート）
    ├── PHASE1_COMPLETION_REPORT.md
    ├── PHASE5_RTK_NEXT_STEPS.md
    ├── PHASE7_PRODUCTION_TEST_START.md
    ├── RTK_BASE_STATION_FINAL_REPORT.md
    ├── progress_report_20260624.md
    ├── troubleshooting_20260616_uart_udp_fix.md
    └── project_presentation.md
```

## 各カテゴリの説明

| カテゴリ | 内容 |
|----------|------|
| **01-specification** | システムの要件定義、アーキテクチャ設計、通信仕様など |
| **02-development** | 開発環境のセットアップ手順、全開発履歴 |
| **03-operations** | 実機の運用方法、RTK設定、トラブルシューティング |
| **04-testing** | テストケース定義、テスト実行レポート |
| **05-implementation** | 特定機能の詳細な実装ドキュメント |
| **archive** | 過去の進捗レポート・完了報告（参照用、メンテナンス対象外） |

## 関連ドキュメント

- [プロジェクト README](../README.md)
- [Sphinx API ドキュメント](../docs_sphinx/)