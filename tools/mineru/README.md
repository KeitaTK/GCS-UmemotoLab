# MinerU - PDF変換ツール

PDFをMarkdown形式に高精度変換するツールです。

## 環境

| 項目 | 内容 |
|------|------|
| ツール | [MinerU](https://github.com/opendatalab/MinerU) v3.4.0 |
| Python | 3.14 |
| PyTorch | 2.12.1 |
| 仮想環境 | `.venv` (プロジェクトルート) |
| プラットフォーム | macOS (Apple Silicon) |

## 動作確認

### PyTorch (2026-07-03 確認済み)

```
PyTorch version: 2.12.1
MPS available: True
MPS built: True
CPU OK
MPS device test: OK
```

macOS (Apple Silicon) では MPS (Metal Performance Shaders) が利用可能ですが、MinerU は公式には `pipeline` (CPU) バックエンドを推奨しています。

## 使い方

### 1. 仮想環境の有効化

```bash
cd /path/to/GCS-UmemotoLab
source .venv/bin/activate
```

### 2. 変換実行

#### ヘルパースクリプトを使用する場合（推奨）

```bash
# 基本的な使い方（pipeline / CPU モード）
./tools/mineru/run_mineru.sh input.pdf output_dir

# 出力ディレクトリを指定
./tools/mineru/run_mineru.sh app/roll_response.pdf tools/mineru/output

# ヘルプ表示
./tools/mineru/run_mineru.sh
```

#### 直接 mineru コマンドを使用する場合

```bash
# pipeline モード（CPU、最も安定／macOS推奨）
mineru -p "入力PDFのパス" -o "出力先フォルダ" -b pipeline

# 例
mineru -p "app/roll_response.pdf" -o "tools/mineru/output" -b pipeline
```

### 3. 出力確認

変換が成功すると、出力ディレクトリに以下のファイルが生成されます：

- `*.md` - Markdown形式の変換結果
- 画像ファイル（PDFに画像が含まれる場合）
- その他メタデータファイル

## バックエンドモード一覧

| モード | 説明 | macOS対応 |
|--------|------|-----------|
| `pipeline` | CPU汎用モード（安定・推奨） | ✅ 安定動作 |
| `hybrid-engine` | 次世代高精度（ローカルGPU） | ⚠️ MPS非対応の可能性あり |
| `vlm-engine` | 高精度（ローカルGPU） | ⚠️ MPS非対応の可能性あり |
| `hybrid-http-client` | 高精度（リモート推論） | ✅ サーバー要 |
| `vlm-http-client` | 高精度（リモート推論） | ✅ サーバー要 |

## 注意事項

- **初回実行時**：モデルのダウンロード（数GB）に時間がかかります。安定したネットワーク環境で実行してください。
- **MPS サポート**：PyTorch の MPS は利用可能ですが、MinerU が MPS を正式サポートしているかは未確認です。CPU モード (`-b pipeline`) を推奨します。
- **処理時間**：PDF のページ数や内容によって処理時間は変動します。

## トラブルシューティング

### mineru が見つからない場合

```bash
source .venv/bin/activate
pip install mineru
```

### モデルのダウンロードに失敗する場合

ネットワーク接続を確認し、必要に応じてプロキシを設定してください：

```bash
export HTTP_PROXY="http://proxy.example.com:8080"
export HTTPS_PROXY="http://proxy.example.com:8080"
```

### MPS 関連のエラーが発生する場合

環境変数で MPS を無効化して CPU モードに強制できます：

```bash
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
```
