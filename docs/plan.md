# 計画（Plan）

## 運用ルール

- この文書は「現在の計画」を表す。過去ログを増やさない。
- 変更履歴は直近10件までとし、重要判断は ADR に移す。
- 自動実行の対象は「Next」のみとする。Backlog は自動で着手しない。

## 現状（Status）

- フェーズ：**Foundation**（Phase 0 進行中）
- ブロッカー：なし
- 直近の重要決定：リポジトリ初期構築

## ロードマップ（概略）

| Phase | 名称 | 目標 | 期間目安 |
|---|---|---|---|
| 0 | Foundation | リポジトリ基盤整備、CI 品質ゲート確立 | 1 週間 |
| 1 | Parallel Execution | エージェント並列実行の研究・実装・検証 | 2〜4 週間 |
| 2 | Typed Orchestration | LangGraph + Pydantic AI による型安全オーケストレーション | 2〜4 週間 |
| 3 | Eval & Observability | パイプライン品質評価・AI Gateway 統合 | 2〜3 週間 |
| 4 | A2A & Advanced | A2A プロトコル実装、高度な研究 | 継続 |

※ 期間目安は目標であり、検証結果に基づき随時見直す。

## 今月のゴール

- G1 リポジトリ基盤と CI を確立する
- G2 エージェント並列実行の調査・設計を完了する
- G3 並列実行の最小実装を検証する

## Next（自動実行対象：最大3件）

### N-001 リポジトリ基盤整備

- 目的：CI 品質ゲートと正本ドキュメント体系を確立する
- 受入条件：
  - CI（ruff / mypy / pytest / policy_check）が動作する
  - 正本ドキュメント（requirements / policies / architecture / plan）が整備されている
  - GitHub Actions ワークフローが設定されている
- 依存：なし
- 触る領域：ci/, docs/, .github/workflows/

### N-002 エージェント並列実行の調査・設計

- 目的：並列実行のアプローチを調査し、設計方針を策定する
- 受入条件：
  - 並列実行の候補アプローチが3つ以上比較されている
  - 設計方針が docs/research/parallel-execution/ に文書化されている
  - ADR に採用アプローチの判断が記録されている
- 依存：N-001
- 触る領域：docs/research/parallel-execution/, docs/adr/

### N-003 並列実行の最小実装

- 目的：設計方針に基づくプロトタイプを実装・検証する
- 受入条件：
  - experiments/parallel-execution/ にプロトタイプが実装されている
  - 逐次実行 vs 並列実行の品質比較ベンチマークが実行できる
  - 結果が docs/research/parallel-execution/ に記録されている
- 依存：N-002
- 触る領域：experiments/parallel-execution/, src/orchestration_lab/parallel/

## Backlog

### B-001 型安全オーケストレーションの調査

- 目的：LangGraph + Pydantic AI の適合性を調査する
- Phase: 2

### B-002 Eval フレームワークの調査

- 目的：パイプライン品質の定量評価手法を調査する
- Phase: 3

### B-003 AI Gateway の調査

- 目的：LiteLLM によるコスト管理・可観測性を調査する
- Phase: 3

### B-004 A2A プロトコル実装検証

- 目的：Agent2Agent 標準プロトコルの実装可能性を検証する
- Phase: 4

### B-005 TDD 並列フローの研究

- 目的：テストファースト × エージェント並列の有効性を研究する
- Phase: 4

### B-006 dev-orchestration-template へのフィードバック

- 目的：研究成果をテンプレートに反映する
- Phase: 各研究テーマ完了後に随時

## Issue 対応表

| タスク | Issue # | 状態 |
|---|---|---|
| N-001 リポジトリ基盤整備 | #1 | Open |
| N-002 並列実行の調査・設計 | — | 未作成 |
| N-003 並列実行の最小実装 | — | 未作成 |

## Done（今期完了）

（なし）

## 変更履歴

| 日付 | 内容 |
|---|---|
| 2026-03-01 | 初版作成。Phase 0〜4 のロードマップ策定。 |
