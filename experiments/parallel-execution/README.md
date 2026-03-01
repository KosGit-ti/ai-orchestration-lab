# エージェント並列実行 — 実験

このディレクトリには、エージェント並列実行に関する実験コードを格納する。

## 構成

```
parallel-execution/
├── README.md           # この文書
├── exp_001_*.py        # 実験 001: Copilot Chat 擬似並列
├── exp_002_*.py        # 実験 002: LangGraph による並列
└── exp_003_*.py        # 実験 003: A2A 分散並列
```

## 研究テーマ

- **RQ-1**: 監査エージェントの並列実行で品質はどの程度向上するか？
- **RQ-2**: 並列実行の実行時間削減効果はどの程度か？
- **RQ-3**: 並列実行時のコンテキスト共有はどうあるべきか？

## 対応ドキュメント

- [研究ノート](../../docs/research/parallel-execution/README.md)
- [要件 FR-001](../../docs/requirements.md)
