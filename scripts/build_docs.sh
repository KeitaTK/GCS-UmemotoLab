#!/bin/bash
# ドキュメント自動ビルドスクリプト
# 用途: sphinx-buildコマンドのラッパー（PATH設定不要）

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DOCS_DIR="$PROJECT_ROOT/docs_sphinx"
PYTHON_BIN="/Users/taitai0123/Library/Python/3.9/bin"

echo "==================================="
echo "GCS-UmemotoLab ドキュメント生成"
echo "==================================="

# sphinxがインストールされているか確認
if ! command -v "$PYTHON_BIN/sphinx-build" &> /dev/null; then
    echo "❌ Sphinxがインストールされていません。以下を実行してください:"
    echo "   pip3 install sphinx sphinx-autodoc-typehints"
    exit 1
fi

# ドキュメント書き直しを強制的に行う場合は -r フラグを使用
if [ "$1" == "-r" ] || [ "$1" == "--rebuild" ]; then
    echo "🔄 既存のビルドをクリアしています..."
    rm -rf "$DOCS_DIR/build"
    rm -rf "$DOCS_DIR/.doctrees"
fi

# APIドキュメントを再生成
echo "📝 APIドキュメントを生成しています..."
cd "$DOCS_DIR"
"$PYTHON_BIN/sphinx-apidoc" -f -o source ../app

# HTMLドキュメントをビルド
echo "🔨 HTMLドキュメントをビルドしています..."
"$PYTHON_BIN/sphinx-build" -b html source build/html

echo ""
echo "✅ ドキュメント生成完了！"
echo ""
echo "📖 ブラウザで表示:"
echo "   open $DOCS_DIR/build/html/index.html"
echo ""
