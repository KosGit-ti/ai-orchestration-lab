# 運用手順（Runbook）

## 1. ローカル開発

### 1.1 環境セットアップ

```bash
# リポジトリのクローン
git clone https://github.com/KosGit-ti/ai-orchestration-lab.git
cd ai-orchestration-lab

# 依存インストール（開発用）
uv sync --dev

# 全研究依存を含む場合
uv sync --extra all
```

### 1.2 CI チェック（ローカル実行）

```bash
# Lint
uv run ruff check .

# フォーマットチェック
uv run ruff format --check .

# 型チェック
uv run mypy src/ tests/ ci/

# テスト
uv run pytest -q --tb=short

# ポリシーチェック
uv run python ci/policy_check.py
```

### 1.3 フォーマット適用

```bash
uv run ruff format .
uv run ruff check --fix .
```

## 2. 実験の実行

### 2.1 新規実験の開始

1. `experiments/<テーマ>/` にディレクトリを作成
2. `README.md` に実験の目的・手法・期待結果を記載
3. 実験コードを配置
4. 結果を `docs/research/<テーマ>/` に記録

### 2.2 実験コードの src/ への昇格

1. experiments/ のコードが安定したことを確認
2. C-002（昇格品質基準）を満たすようにリファクタリング
3. テストを追加（tests/unit/）
4. mypy strict を通過させる
5. PR を作成してレビュー

## 3. dev-orchestration-template へのフィードバック

### 3.1 フィードバック手順

1. 研究成果の文書化が完了していることを確認（C-003）
2. ベンチマーク結果が有効性を示していることを確認
3. dev-orchestration-template リポジトリにブランチを作成
4. 変更を段階的に適用
5. テンプレートの既存テストが通ることを確認
6. PR を作成

## 4. トラブルシューティング

### 4.1 CI 失敗時

- ruff: `uv run ruff check --fix .` で自動修正
- mypy: エラーメッセージに従い型アノテーションを修正
- pytest: テストの失敗原因を調査し修正
- policy_check: 秘密情報や禁止パターンを除去

### 4.2 依存の追加

```bash
# 開発依存に追加
uv add --dev <package>

# 研究テーマ別に追加（optional-dependencies）
# pyproject.toml を直接編集後に uv sync
```
