# Phase 5: RTK/RTCM 検証テスト - 実行手順

現在のプロジェクト進捗: **75%** ✅  
次のマイルストーン: **RTK/RTCM インジェクション確認** → 80%

---

## 📋 実行チェックリスト

### ✅ 準備完了状況
- [x] Pixhawk6C が Raspberry Pi に USB 接続（`/dev/ttyACM0`）
- [x] Backend が正常に動作（ハートビート受信確認）
- [x] 本番運用ドキュメント整備完了
- [x] u-center セットアップガイド作成完了
- [ ] Windows PC に u-center インストール（**ユーザー実施**）

---

## 🚀 次のステップ（4 ステップで完了）

### ステップ 1: Windows PC で u-center をインストール

**対象者**: Windows PC ユーザー  
**所要時間**: 10 分

1. [u-center ダウンロードページ](https://www.u-blox.com/en/product/u-center) にアクセス
2. u-center 最新版をダウンロード（OS: Windows 10/11）
3. インストーラーを実行してインストール
4. u-center を起動

**確認**: u-center が起動してメニューが表示されていることを確認

---

### ステップ 2: u-center で NTRIP サーバーを設定

**対象者**: Windows PC（u-center）  
**所要時間**: 5 分

#### Option A: **NTRIP キャスターから RTCM を取得する場合**

1. u-center メニュー → **Tools** → **NTRIP Client**
2. キャスターアドレス入力（例: 国土地理院 GNSS サービス）
   - ホスト: `ntrip.gsi.go.jp`
   - ポート: `2101`
   - マウントポイント: 地域別マウントポイント選択
3. **Add Stream** → ストリーム接続開始

#### Option B: **ローカル RTCM ストリームを作成する場合**

```bash
# Raspberry Pi で RTCM ダミーサーバー起動
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && timeout 120 python3 app/dummy_rtcm_server.py"
```

---

### ステップ 3: u-center で TCP サーバーを起動

**対象者**: Windows PC（u-center）  
**所要時間**: 2 分

1. u-center メニュー → **Tools** → **TCP Server**
2. 設定:
   - **Host**: `127.0.0.1`（ローカルホスト）
   - **Port**: `2101`
   - **Format**: `RTCM3` を選択
3. **Start** をクリック

**確認**: ステータスが「Running」に変わることを確認

---

### ステップ 4: Raspberry Pi で Backend を起動（RTCM 有効化）

**対象者**: Raspberry Pi  
**所要時間**: 5 分

#### 4-1: 設定ファイルを RTCM 有効化で作成

```bash
ssh taki@192.168.11.19 "cat > ~/GCS-UmemotoLab/config/gcs_local.yml << 'EOF'
connection_type: serial
serial_port: /dev/ttyACM0
serial_baudrate: 115200
rtcm_enabled: true
rtcm_host: 127.0.0.1
rtcm_tcp_port: 2101
udp_listen_port: 14550
drones:
  drone1:
    system_id: 1
    endpoint: 127.0.0.1:14550
EOF
"
```

#### 4-2: Backend を起動して RTCM インジェクションを監視

```bash
ssh taki@192.168.11.19 "cd ~/GCS-UmemotoLab && source .venv/bin/activate && timeout 60 python3 app/backend_server.py 2>&1"
```

**期待する出力**:
```
[INFO] Connected to RTCM source: 127.0.0.1:2101
[INFO] RTCM data injected: XXX bytes in Y frame(s)
[INFO] Active drones: [1]
[INFO]   Drone 1: heartbeat received (bytes)
```

---

## ✨ 成功の指標

### ✅ RTK インジェクション成功
```
[INFO] RTCM data injected: 128 bytes in 2 frame(s)  # ← これが表示されたら成功
```

### ✅ Pixhawk GPS 信号改善
- GPS Fix Type が向上（2D/3D → RTK Fixed）
- QGroundControl で「RTK」ステータス表示

---

## 🔍 トラブルシューティング

| 症状 | 原因 | 対処法 |
|------|------|--------|
| `Connection refused: 127.0.0.1:2101` | u-center 起動していない | u-center を起動して TCP Server を Start |
| `RTCM data injected` ログなし | Pixhawk が GPS_RTCM_DATA 未対応 | ファームウェアバージョン確認（Pixhawk6C は対応） |
| ハートビート途絶 | シリアル接続断 | USB ケーブル再接続 |

**詳細**: [docs/troubleshooting_guide.md](./troubleshooting_guide.md) カテゴリ 3 を参照

---

## 📊 進捗目標

| マイルストーン | 状態 | 達成条件 |
|--------|------|--------|
| Phase 4: 運用ドキュメント完成 | ✅ 完了 | 運用マニュアル・トラブルシューティング作成 |
| **Phase 5: RTK 検証テスト** | 🟡 進行中 | RTCM インジェクション確認 + GPS 改善 |
| Phase 6: マルチドローン検証 | ⏳ 次予定 | 2 台以上のドローン同時管理テスト |
| Phase 7: 本番環境テスト | ⏳ 予定 | 24-48 時間連続稼働確認 |

---

## 📞 サポート情報

### ドキュメント参照
- **RTK 統合ガイド**: [docs/rtk_integration_guide.md](./rtk_integration_guide.md)
- **u-center セットアップ**: [docs/rtk_setup_guide.md](./rtk_setup_guide.md)
- **トラブルシューティング**: [docs/troubleshooting_guide.md](./troubleshooting_guide.md)
- **運用マニュアル**: [docs/operations_manual.md](./operations_manual.md)

### 問い合わせ
GitHub Issues: [KeitaTK/GCS-UmemotoLab](https://github.com/KeitaTK/GCS-UmemotoLab/issues)

---

**Last Updated**: 2026-04-24  
**Next Steps**: u-center セットアップ → ステップ 1-4 実行 → 進捗 80% へ
