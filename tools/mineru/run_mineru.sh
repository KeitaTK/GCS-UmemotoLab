#!/bin/bash
# ==============================================================================
# MinerU PDF変換 ヘルパースクリプト (macOS / Apple Silicon 最適化版)
# ==============================================================================
# 用途: PDFをMarkdownに変換する mineru コマンドのラッパー
#
# 【基本使い方】
#   ./run_mineru.sh input.pdf output_dir                      # 標準変換
#   ./run_mineru.sh input.pdf output_dir --fast               # 高速モード（数式・テーブル解析スキップ）
#   ./run_mineru.sh input.pdf output_dir --txt                # テキスト抽出のみ（OCRスキップ、最速）
#   ./run_mineru.sh input.pdf output_dir --fast --txt         # 高速テキスト抽出（最速）
#   ./run_mineru.sh input.pdf output_dir -b hybrid-engine     # バックエンド指定
#   ./run_mineru.sh input.pdf output_dir -l japanese          # 言語指定
#
# 【オプション】
#   --fast          高速モード (数式: -f false, テーブル: -t false)
#   --txt           テキスト抽出モード (OCRスキップ: -m txt)
#   --force-ocr     OCR強制モード (-m ocr)
#   -b <backend>    バックエンド指定 (pipeline|hybrid-engine|vlm-engine)
#   -l <lang>       OCR言語指定 (ch|japanese|korean|arabic|east_slavic|cyrillic|devanagari)
#   -s <start>      開始ページ (0-based)
#   -e <end>        終了ページ (0-based)
#   -h, --help      このヘルプを表示
#
# 【高速化のポイント】
#   1. --fast : 数式・テーブル解析をスキップ → 約30-50%高速化
#   2. --txt  : OCRを完全スキップ (text PDF限定) → 約60-80%高速化
#   3. --fast --txt : 上記両方を適用 → 最大80-90%高速化
#
# 【推奨バックエンド】
#   - pipeline (デフォルト): 最も安定。Apple Silicon では MPS が自動利用される
#   - hybrid-engine: 次世代高精度。MPS 未検証のため注意
# ==============================================================================

set -e

# ============================================================
# 設定
# ============================================================
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
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
# デフォルト値
# ============================================================
BACKEND="pipeline"
LANG="ch"
FAST_MODE=false
TXT_MODE=false
FORCE_OCR=false
START_PAGE=""
END_PAGE=""

# ============================================================
# ヘルプ表示
# ============================================================
show_help() {
    echo "========================================="
    echo "  MinerU PDF変換ツール v3.4.0"
    echo "  macOS / Apple Silicon 最適化版"
    echo "========================================="
    echo ""
    echo "【使い方】"
    echo "  $0 <入力PDF> <出力ディレクトリ> [オプション...]"
    echo ""
    echo "【引数】"
    echo "  入力PDF          : 変換するPDFファイルのパス（必須）"
    echo "  出力ディレクトリ   : 変換結果の出力先ディレクトリ（必須）"
    echo ""
    echo "【オプション】"
    echo "  --fast            高速モード（数式・テーブル解析スキップ、約30-50%高速化）"
    echo "  --txt             テキスト抽出モード（OCRスキップ、text PDF限定、約60-80%高速化）"
    echo "  --force-ocr       OCR強制モード（画像ベースPDF用）"
    echo "  -b, --backend <b> バックエンド指定 (pipeline|hybrid-engine|vlm-engine)"
    echo "                     デフォルト: pipeline（最も安定、MPS自動利用）"
    echo "  -l, --lang <l>    OCR言語指定 (ch|japanese|korean|arabic|east_slavic|cyrillic|devanagari)"
    echo "                     デフォルト: ch"
    echo "  -s, --start <n>   開始ページ (0-based)"
    echo "  -e, --end <n>     終了ページ (0-based)"
    echo "  -h, --help        このヘルプを表示"
    echo ""
    echo "【使用例】"
    echo "  $0 sample.pdf ./output                           # 標準変換（pipeline, OCRあり）"
    echo "  $0 sample.pdf ./output --fast                    # 高速モード（数式・テーブルスキップ）"
    echo "  $0 sample.pdf ./output --txt                     # テキスト抽出のみ（OCRスキップ、最速）"
    echo "  $0 sample.pdf ./output --fast --txt              # 最速モード（全オプション併用）"
    echo "  $0 sample.pdf ./output -b hybrid-engine          # 別バックエンド指定"
    echo "  $0 sample.pdf ./output -l japanese               # 日本語OCR"
    echo "  $0 sample.pdf ./output -s 0 -e 5                 # ページ範囲指定"
    echo ""
    echo "【高速化Tips】"
    echo "  ・テキスト抽出可能なPDF → --txt オプションでOCRをスキップ（最速）"
    echo "  ・数式・テーブル不要 → --fast オプションで解析をスキップ"
    echo "  ・モデル事前DL → mineru-models-download -m pipeline"
    echo "  ・Apple Silicon → pipeline バックエンドで MPS が自動利用される"
    echo ""
    exit 0
}

# ============================================================
# 引数パース
# ============================================================
ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        -h|--help)
            show_help
            ;;
        --fast)
            FAST_MODE=true
            shift
            ;;
        --txt)
            TXT_MODE=true
            shift
            ;;
        --force-ocr)
            FORCE_OCR=true
            shift
            ;;
        -b|--backend)
            BACKEND="$2"
            shift 2
            ;;
        -l|--lang)
            LANG="$2"
            shift 2
            ;;
        -s|--start)
            START_PAGE="$2"
            shift 2
            ;;
        -e|--end)
            END_PAGE="$2"
            shift 2
            ;;
        -*)
            echo "❌ エラー: 不明なオプション: $1"
            echo "  ヘルプ: $0 -h"
            exit 1
            ;;
        *)
            ARGS+=("$1")
            shift
            ;;
    esac
done

# 位置引数チェック
if [ ${#ARGS[@]} -lt 2 ]; then
    echo "❌ エラー: 入力PDF と 出力ディレクトリ を指定してください"
    echo ""
    show_help
    exit 1
fi

INPUT_PDF="${ARGS[0]}"
OUTPUT_DIR="${ARGS[1]}"

# ============================================================
# --txt と --force-ocr の競合チェック
# ============================================================
if [ "$TXT_MODE" = true ] && [ "$FORCE_OCR" = true ]; then
    echo "❌ エラー: --txt と --force-ocr は同時に指定できません"
    exit 1
fi

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
# 環境情報の表示
# ============================================================
echo "========================================="
echo "  MinerU PDF変換 実行"
echo "========================================="

# mineru バージョン
MINERU_VER=$("$MINERU_BIN" --version 2>&1 | head -1)
echo "  MinerU        : $MINERU_VER"

# PyTorch / MPS 状態
"$PYTHON_BIN" -c "
import torch
print(f'  PyTorch       : {torch.__version__}')
print(f'  MPS available : {torch.backends.mps.is_available()}')
device = 'mps' if torch.backends.mps.is_available() else 'cpu'
print(f'  Auto device   : {device}')
" 2>/dev/null || echo "  PyTorch       : N/A"

# PDF情報
PDF_SIZE=$(ls -lh "$INPUT_PDF" | awk '{print $5}')
echo "  入力ファイル  : $INPUT_PDF ($PDF_SIZE)"

# PDFページ数（pdfinfo があれば表示）
if command -v pdfinfo &> /dev/null; then
    PDF_PAGES=$(pdfinfo "$INPUT_PDF" 2>/dev/null | grep "Pages:" | awk '{print $2}')
    if [ -n "$PDF_PAGES" ]; then
        echo "  PDFページ数   : $PDF_PAGES"
    fi
fi

echo "  出力ディレクトリ: $OUTPUT_DIR"
echo "  バックエンド   : $BACKEND"

# OCR言語表示（-m txt 時は OCR 不要）
if [ "$TXT_MODE" = true ]; then
    echo "  OCR           : スキップ（テキスト抽出モード）"
else
    echo "  OCR言語       : $LANG"
fi

# モード表示
MODE_PARTS=()
if [ "$FAST_MODE" = true ]; then
    MODE_PARTS+=("高速(数式/テーブルOFF)")
fi
if [ "$TXT_MODE" = true ]; then
    MODE_PARTS+=("テキスト抽出(OCR OFF)")
fi
if [ "$FORCE_OCR" = true ]; then
    MODE_PARTS+=("OCR強制")
fi
if [ ${#MODE_PARTS[@]} -gt 0 ]; then
    echo "  モード         : ${MODE_PARTS[*]}"
else
    echo "  モード         : 標準（数式/テーブル/OCR すべて有効）"
fi

if [ -n "$START_PAGE" ]; then
    echo "  ページ範囲     : $START_PAGE - ${END_PAGE:-最後}"
fi

echo "  MPS自動利用    : $(if [ "$BACKEND" = "pipeline" ]; then echo '✅ 有効 (pipeline バックエンド)'; else echo '⚠️ 未確認 (非pipeline バックエンド)'; fi)"
echo "========================================="
echo ""

# ============================================================
# MinerU 実行オプションの構築
# ============================================================
MINERU_OPTS=(
    -p "$INPUT_PDF"
    -o "$OUTPUT_DIR"
    -b "$BACKEND"
)

# メソッドオプション
if [ "$TXT_MODE" = true ]; then
    MINERU_OPTS+=(-m txt)
elif [ "$FORCE_OCR" = true ]; then
    MINERU_OPTS+=(-m ocr)
fi

# OCR言語（-m txt 時は不要だが、pipelineモードでは明示的に渡す）
if [ "$TXT_MODE" != true ]; then
    MINERU_OPTS+=(-l "$LANG")
fi

# 高速モード: 数式・テーブル解析をスキップ
if [ "$FAST_MODE" = true ]; then
    MINERU_OPTS+=(-f false)
    MINERU_OPTS+=(-t false)
fi

# ページ範囲
if [ -n "$START_PAGE" ]; then
    MINERU_OPTS+=(-s "$START_PAGE")
fi
if [ -n "$END_PAGE" ]; then
    MINERU_OPTS+=(-e "$END_PAGE")
fi

# デバッグ: 実行コマンドを表示
echo "【実行コマンド】"
echo "  $MINERU_BIN ${MINERU_OPTS[*]}"
echo ""

# ============================================================
# MinerU 実行
# ============================================================
START_TIME=$(date +%s)

"$MINERU_BIN" "${MINERU_OPTS[@]}"

END_TIME=$(date +%s)
ELAPSED=$((END_TIME - START_TIME))

# ============================================================
# 完了確認
# ============================================================
echo ""
echo "========================================="
echo "  変換完了"
echo "========================================="

ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))
echo "  処理時間       : ${ELAPSED}秒 (${ELAPSED_MIN}分${ELAPSED_SEC}秒)"

# ページ数がわかっていれば速度も表示
if [ -n "$PDF_PAGES" ] && [ "$PDF_PAGES" -gt 0 ] && [ "$ELAPSED" -gt 0 ]; then
    SPEED=$(echo "scale=2; $PDF_PAGES / $ELAPSED" | bc 2>/dev/null)
    if [ -n "$SPEED" ]; then
        echo "  処理速度       : ${SPEED} pages/sec"
    fi
fi

# 出力ディレクトリの内容を表示
if [ -d "$OUTPUT_DIR" ]; then
    echo ""
    echo "【生成ファイル一覧】"
    FILE_COUNT=0
    TOTAL_SIZE=0
    while IFS= read -r f; do
        if [ -f "$f" ]; then
            size=$(wc -c < "$f" 2>/dev/null | tr -d ' ')
            echo "  $(basename "$f") (${size} bytes)"
            FILE_COUNT=$((FILE_COUNT + 1))
            TOTAL_SIZE=$((TOTAL_SIZE + size))
        fi
    done < <(find "$OUTPUT_DIR" -type f 2>/dev/null | sort)

    if [ $FILE_COUNT -gt 0 ]; then
        echo ""
        echo "  合計: ${FILE_COUNT}ファイル, $(echo "scale=1; $TOTAL_SIZE/1024" | bc 2>/dev/null || echo "$((TOTAL_SIZE/1024))") KB"
    fi

    echo ""

    # Markdownファイルが見つかった場合、先頭行を表示
    MD_FILE=$(find "$OUTPUT_DIR" -name "*.md" -type f 2>/dev/null | head -1)
    if [ -n "$MD_FILE" ]; then
        echo "【Markdownプレビュー（先頭10行）】"
        head -10 "$MD_FILE"
        echo "..."
        echo ""
    fi
fi

echo "✅ 正常に完了しました。"
