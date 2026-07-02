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

### PyTorch / MPS (2026-07-03 確認済み)

```
PyTorch version: 2.12.1
MPS available: True
MPS built: True
CPU OK
MPS device test: OK
```

**重要**: macOS (Apple Silicon) では、`pipeline` バックエンド使用時に **MPS (Metal Performance Shaders) が自動的に利用されます**。
MinerU v3.4.0 の `get_device()` は CUDA → MPS → NPU → CPU の順で自動検出するため、
Apple Silicon Mac では追加設定なしで MPS による高速化が適用されます。

## 使い方

### 0. モデルの事前ダウンロード（初回のみ・推奨）

初回実行時にモデルダウンロード（約2〜5GB）で待たされないよう、事前ダウンロードを推奨します：

```bash
cd /path/to/GCS-UmemotoLab
source .venv/bin/activate

# pipeline モデルのみ（約2GB）
mineru-models-download -m pipeline -s auto

# すべてのモデル（pipeline + VLM、約5GB）
mineru-models-download -m all -s auto
```

ダウンロード元は `auto`（自動選択）、`huggingface`、`modelscope` から選択できます。

### 1. 仮想環境の有効化

```bash
cd /path/to/GCS-UmemotoLab
source .venv/bin/activate
```

### 2. 変換実行

#### ヘルパースクリプトを使用する場合（推奨）

```bash
# 基本的な使い方（pipeline / MPS自動利用）
./tools/mineru/run_mineru.sh input.pdf output_dir

# 出力ディレクトリを指定
./tools/mineru/run_mineru.sh app/roll_response.pdf tools/mineru/output

# 高速モード（数式・テーブル解析スキップ、約30-50%高速化）
./tools/mineru/run_mineru.sh input.pdf output_dir --fast

# テキスト抽出モード（OCRスキップ、text PDF限定、約60-80%高速化）
./tools/mineru/run_mineru.sh input.pdf output_dir --txt

# 最速モード（全オプション併用、約80-90%高速化）
./tools/mineru/run_mineru.sh input.pdf output_dir --fast --txt

# 日本語OCR
./tools/mineru/run_mineru.sh input.pdf output_dir -l japanese

# ヘルプ表示
./tools/mineru/run_mineru.sh -h
```

#### 直接 mineru コマンドを使用する場合

```bash
# pipeline モード（MPS自動利用）
mineru -p "入力PDFのパス" -o "出力先フォルダ" -b pipeline

# 高速モード（数式・テーブル解析スキップ）
mineru -p "入力PDFのパス" -o "出力先フォルダ" -b pipeline -f false -t false

# テキスト抽出モード（OCRスキップ、text PDF限定）
mineru -p "入力PDFのパス" -o "出力先フォルダ" -b pipeline -m txt

# 例
mineru -p "app/roll_response.pdf" -o "tools/mineru/output" -b pipeline
```

### 3. 出力確認

変換が成功すると、出力ディレクトリに以下のファイルが生成されます：

- `*.md` - Markdown形式の変換結果
- 画像ファイル（PDFに画像が含まれる場合）
- その他メタデータファイル

## 高速化オプション一覧

| オプション | mineru 引数 | 効果 | 推定速度向上 | ユースケース |
|-----------|------------|------|-------------|------------|
| `--fast` | `-f false -t false` | 数式解析・テーブル解析をスキップ | **30-50%** | 数式・テーブル不要の文書 |
| `--txt` | `-m txt` | OCRを完全スキップ（text PDF限定） | **60-80%** | テキスト抽出可能なPDF |
| `--fast --txt` | 上記の組み合わせ | 全最適化を適用 | **80-90%** | シンプルなtext PDF |
| `--force-ocr` | `-m ocr` | OCRを強制 | なし（むしろ遅くなる） | 画像ベースPDF |

> **注意**: `-m txt` は PDF から直接テキストを抽出するモードです。スキャンPDF（画像ベース）では使用できません。
> MinerU の `-m auto`（デフォルト）は自動判別で OCR 要否を判断します。

### 処理時間の目安

| PDFタイプ | ページ数 | 標準モード | --fast | --txt | 備考 |
|----------|---------|-----------|--------|-------|------|
| 軽量テキストPDF | 1-10p | 5-15秒 | 3-8秒 | 1-3秒 | OCR不要のテキストPDF |
| 標準レポート | 10-50p | 30秒-3分 | 15秒-1.5分 | 5-30秒 | 図表・数式なし |
| 複雑なPDF | 10-50p | 1-5分 | 30秒-3分 | N/A | 数式・表・図あり |
| 大型PDF | 100p+ | 5-15分 | 3-8分 | 1-3分 | ページ数に比例 |

> 処理時間は Apple Silicon (M1/M2/M3) での目安です。初回実行時はモデルダウンロードによりさらに時間がかかります。

## バックエンドモード一覧

| モード | 説明 | macOS MPS対応 |
|--------|------|--------------|
| `pipeline` | CPU汎用モード（安定・推奨） | ✅ **MPS自動利用** |
| `hybrid-engine` | 次世代高精度（ローカルGPU） | ⚠️ MPS未検証、MLX使用可 |
| `vlm-engine` | 高精度（ローカルGPU） | ⚠️ MPS未検証、MLX使用可 |
| `hybrid-http-client` | 高精度（リモート推論） | ✅ サーバー要 |
| `vlm-http-client` | 高精度（リモート推論） | ✅ サーバー要 |

> **MPS 対応状況 (2026-07-03 更新)**: MinerU v3.4.0 のコード解析により、`get_device()` が
> CUDA → MPS → NPU → CPU の順で自動検出することを確認しました。
> `pipeline` バックエンドでは MPS が自動利用され、`PYTORCH_ENABLE_MPS_FALLBACK=1` も設定されます。

## 注意事項

- **初回実行時**：モデルのダウンロード（2〜5GB）に時間がかかります。
  事前に `mineru-models-download -m pipeline` でダウンロードしておくことを推奨します。
- **MPS サポート**：`pipeline` バックエンドでは MPS が自動利用されます。
  `hybrid-engine` / `vlm-engine` の MPS 対応は未確認です。
- **処理時間**：PDF のページ数や内容によって処理時間は大きく変動します。
  不要な解析をスキップするオプション（`--fast` / `--txt`）で大幅な高速化が可能です。

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

# またはダウンロード元を明示的に指定
mineru-models-download -m pipeline -s modelscope
```

### MPS 関連のエラーが発生する場合

環境変数で MPS を無効化して CPU モードに強制できます：

```bash
export PYTORCH_MPS_HIGH_WATERMARK_RATIO=0.0
# または
export MINERU_DEVICE_MODE=cpu
```

### モデルキャッシュの場所

デフォルトでは以下の場所にキャッシュされます：

- **HuggingFace**: `~/.cache/huggingface/hub/models--opendatalab--PDF-Extract-Kit-1.0/`
- **ModelScope**: `~/.cache/modelscope/hub/models/OpenDataLab/PDF-Extract-Kit-1.0/`
- **設定ファイル**: `~/mineru.json`
