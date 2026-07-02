#!/bin/bash
# MinerU PDF変換 ヘルパースクリプト (macOS版)
# 用途: PDFをMarkdownに変換するmineruコマンドのラッパー
#
# 使用例:
#   ./run_mineru.sh input.pdf output_dir
#   ./run_mineru.sh input.pdf output_dir pipeline
#   ./run_mineru.sh input.pdf output_dir pipeline ch
#
# 引数:
#   $1: 入力PDFのパス (必須)
#   $2: 出力先ディレクトリ (必須)
#   $3: バックエンドモード (任意, デフォルト: pipeline)
#       - pipeline: CPUモード（最も安定、macOS推奨）
#       - hybrid-engine: 高精度（ローカルGPU使用）
#       - vlm-engine: 高精度（ローカルGPU使用）
#   $4: OCR言語 (任意, デフォルト: ch)
#       - ch, korean, japanese, arabic, east_slavic, cyrillic, devanagari など

set -e

# ============================================================
# 設定
# ============================================================
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
MINERU_BIN="$VENV_DIR/bin/mineru"

# ============================================================
# プロキシ設定（必要に応じてコメント解除）
# ============================================================
# export HTTP_PROXY="http://proxy.example.com:8080"
# export HTTPS_PROXY="http://proxy.example.com:8080"
# export NO_PROXY="localhost,127.0.0.1"

# ============================================================
# 引数チェック
# ============================================================
if [ $# -lt 2 ]; then
    echo "========================================="
    echo "  MinerU PDF変換ツール"
    echo "========================================="
    echo ""
    echo "【使い方】"
    echo "  $0 <入力PDF> <出力ディレクトリ> [バックエンド] [OCR言語]"
    echo ""
    echo "【引数】"
    echo "  入力PDF          : 変換するPDFファイルのパス"
    echo "  出力ディレクトリ   : 変換結果の出力先ディレクトリ"
    echo "  バックエンド       : pipeline | hybrid-engine | vlm-engine (デフォルト: pipeline)"
    echo "  OCR言語          : ch | korean | japanese | arabic など (デフォルト: ch)"
    echo ""
    echo "【使用例】"
    echo "  $0 sample.pdf ./output"
    echo "  $0 sample.pdf ./output pipeline"
    echo "  $0 sample.pdf ./output pipeline ch"
    echo ""
    echo "【注意】"
    echo "  - macOSでは MPS (Metal Performance Shaders) が利用可能ですが、"
    echo "    MinerU は pipeline (CPU) モードを推奨します。"
    echo "  - 初回実行時はモデルのダウンロードに時間がかかる場合があります。"
    echo ""
    exit 1
fi

INPUT_PDF="$1"
OUTPUT_DIR="$2"
BACKEND="${3:-pipeline}"
LANG="${4:-ch}"

# ============================================================
# 入力チェック
# ============================================================
if [ ! -f "$INPUT_PDF" ]; then
    echo "❌ エラー: 入力ファイルが見つかりません: $INPUT_PDF"
    exit 1
fi

# 出力ディレクトリを作成
mkdir -p "$OUTPUT_DIR"

# ============================================================
# 仮想環境チェック
# ============================================================
if [ ! -f "$PYTHON_BIN" ]; then
    echo "❌ エラー: 仮想環境が見つかりません: $VENV_DIR"
    echo "   以下のコマンドで仮想環境を作成してください:"
    echo "   python3 -m venv $VENV_DIR"
    exit 1
fi

if [ ! -f "$MINERU_BIN" ]; then
    echo "❌ エラー: mineru が見つかりません。仮想環境にインストールしてください:"
    echo "   source $VENV_DIR/bin/activate"
    echo "   pip install mineru"
    exit 1
fi

# ============================================================
# 実行前の情報表示
# ============================================================
echo "========================================="
echo "  MinerU PDF変換 実行"
echo "========================================="
echo "  入力ファイル  : $INPUT_PDF"
echo "  出力ディレクトリ: $OUTPUT_DIR"
echo "  バックエンド   : $BACKEND"
echo "  OCR言語       : $LANG"
echo "  仮想環境       : $VENV_DIR"
echo "========================================="
echo ""

# ============================================================
# MinerU 実行
# ============================================================
"$MINERU_BIN" \
    -p "$INPUT_PDF" \
    -o "$OUTPUT_DIR" \
    -b "$BACKEND" \
    -l "$LANG"

# ============================================================
# 完了確認
# ============================================================
echo ""
echo "========================================="
echo "  変換完了"
echo "========================================="

# 出力ディレクトリの内容を表示
if [ -d "$OUTPUT_DIR" ]; then
    echo ""
    echo "【生成ファイル一覧】"
    find "$OUTPUT_DIR" -type f | sort | while read -r f; do
        size=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
        echo "  $(basename "$f") (${size} bytes)"
    done
    echo ""

    # Markdownファイルが見つかった場合、先頭行を表示
    MD_FILE=$(find "$OUTPUT_DIR" -name "*.md" -type f | head -1)
    if [ -n "$MD_FILE" ]; then
        echo "【Markdownプレビュー（先頭10行）】"
        head -10 "$MD_FILE"
        echo "..."
        echo ""
    fi
fi

echo "✅ 正常に完了しました。"
