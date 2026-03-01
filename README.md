# AI Orchestration Lab

AI エージェントオーケストレーションの研究・検証・実装ラボ。

[dev-orchestration-template](https://github.com/KosGit-ti/dev-orchestration-template) のオーケストレーション設計を進化させるための研究リポジトリ。成果は dev-orchestration-template や他のプロジェクトリポジトリに段階的にフィードバックする。

## 研究テーマ

| Phase | テーマ | 内容 | 状態 |
|---|---|---|---|
| 1 | **エージェント並列実行** | 実装エージェントの並列実行による品質向上の研究・検証 | 🔜 Next |
| 2 | **型安全オーケストレーション** | LangGraph + Pydantic AI によるプログラマティック API 化 | 📋 Backlog |
| 3 | **Eval フレームワーク** | パイプライン品質の定量評価（Promptfoo 等） | 📋 Backlog |
| 3 | **AI Gateway 統合** | LiteLLM によるコスト管理・可観測性 | 📋 Backlog |
| 4 | **A2A プロトコル** | Agent2Agent 標準プロトコルの実装検証 | 📋 Backlog |
| 4 | **TDD 並列フロー** | テストファースト × エージェント並列の研究 | 📋 Backlog |

## リポジトリ構成

```
ai-orchestration-lab/
├── agents/              # エージェント定義（.agent.md）
├── ci/                  # CI / ポリシーチェック
├── configs/             # 設定ファイル
├── docs/                # 正本ドキュメント（SSOT）
│   ├── research/        # 研究テーマ別のノート・知見
│   └── adr/             # アーキテクチャ判断記録
├── experiments/         # 実験コード（テーマ別）
│   ├── parallel-execution/
│   ├── typed-orchestration/
│   ├── eval-framework/
│   ├── a2a-protocol/
│   └── ai-gateway/
├── src/                 # 検証済みの実装コード
│   └── orchestration_lab/
│       ├── core/        # 型定義・例外・共通
│       ├── parallel/    # 並列実行フレームワーク
│       └── eval/        # 品質評価フレームワーク
├── tests/               # テスト
│   ├── unit/
│   └── integration/
├── benchmarks/          # パフォーマンスベンチマーク
├── notebooks/           # 分析・可視化
├── outputs/             # 実験結果出力（.gitignore 対象）
└── scripts/             # ユーティリティスクリプト
```

## クイックスタート

```bash
# 依存インストール
uv sync --dev

# CI チェック実行
uv run ruff check .
uv run ruff format --check .
uv run mypy src/ tests/
uv run pytest -q --tb=short

# ポリシーチェック
uv run python ci/policy_check.py
```

## フィードバックフロー

```
ai-orchestration-lab（研究・検証）
        │
        │ 成果が安定したら
        ▼
dev-orchestration-template（テンプレート更新）
        │
        │ テンプレート適用
        ▼
stock-trading-system 等（各プロジェクト）
```

## 正本ドキュメント

| 正本 | ファイル |
|---|---|
| 要件 | `docs/requirements.md` |
| ポリシー | `docs/policies.md` |
| 制約仕様 | `docs/constraints.md` |
| アーキテクチャ | `docs/architecture.md` |
| オーケストレーション | `docs/orchestration.md` |
| 計画 | `docs/plan.md` |
| 運用手順 | `docs/runbook.md` |
| 重要判断 | `docs/adr/` |

## ライセンス

MIT License
