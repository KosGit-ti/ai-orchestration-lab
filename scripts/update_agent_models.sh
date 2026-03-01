#!/usr/bin/env bash
# エージェント定義のモデル設定を configs/ai_models.toml に合わせて更新する。
#
# 使い方:
#   bash scripts/update_agent_models.sh

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONFIG_FILE="${REPO_ROOT}/configs/ai_models.toml"
AGENTS_DIR="${REPO_ROOT}/agents"

if [[ ! -f "$CONFIG_FILE" ]]; then
    echo "ERROR: ${CONFIG_FILE} が見つかりません"
    exit 1
fi

if [[ ! -d "$AGENTS_DIR" ]]; then
    echo "ERROR: ${AGENTS_DIR} が見つかりません"
    exit 1
fi

echo "AI モデル設定を更新します..."

# overrides セクションから設定を読み取る
declare -A MODELS
while IFS='= ' read -r key value; do
    key=$(echo "$key" | xargs)
    value=$(echo "$value" | xargs | sed 's/^"//;s/"$//')
    if [[ -n "$key" && -n "$value" ]]; then
        MODELS[$key]="$value"
    fi
done < <(sed -n '/^\[overrides\]/,/^\[/p' "$CONFIG_FILE" | grep -E '^[a-z_]+ *=' | head -20)

for agent_file in "${AGENTS_DIR}"/*.agent.md; do
    if [[ ! -f "$agent_file" ]]; then
        continue
    fi
    basename=$(basename "$agent_file" .agent.md)
    model="${MODELS[$basename]:-}"
    if [[ -z "$model" ]]; then
        echo "  SKIP: ${basename} (設定なし)"
        continue
    fi
    # model: の行を置換
    if grep -q "^model:" "$agent_file"; then
        sed -i "s|^model:.*|model: ${model}|" "$agent_file"
        echo "  OK: ${basename} → ${model}"
    else
        echo "  SKIP: ${basename} (model: 行なし)"
    fi
done

echo "完了。"
