#!/usr/bin/env bash
# パッケージの初期セットアップスクリプト。
#
# 使い方:
#   bash scripts/init_packages.sh

set -euo pipefail

echo "=== パッケージ初期化 ==="

# uv がインストールされているか確認
if ! command -v uv &> /dev/null; then
    echo "uv が見つかりません。インストールしてください: https://docs.astral.sh/uv/"
    exit 1
fi

echo "依存関係をインストール..."
uv sync --all-extras

echo "完了。"
echo ""
echo "使い方:"
echo "  uv run pytest          # テスト実行"
echo "  uv run ruff check .    # リントチェック"
echo "  uv run mypy src/       # 型チェック"
