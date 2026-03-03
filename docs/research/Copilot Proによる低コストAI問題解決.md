# Copilot Pro による低コスト AI 問題解決 — 調査報告

> 本文書は、最新の AI オーケストレーション手法を調査し、GitHub 環境で求められる要素・ファイルを特定した上で、
> 本リポジトリ（ai-orchestration-lab）での実現に必要な要素をまとめたものである。

## 目次

1. [調査概要](#1-調査概要)
2. [最新 AI オーケストレーション手法の動向（2025〜2026）](#2-最新-ai-オーケストレーション手法の動向20252026)
3. [GitHub 環境で求められる設定ファイル一覧](#3-github-環境で求められる設定ファイル一覧)
4. [本リポジトリの現状分析（ギャップ分析）](#4-本リポジトリの現状分析ギャップ分析)
5. [実現に必要な要素と推奨アクション](#5-実現に必要な要素と推奨アクション)
6. [低コスト AI 問題解決戦略](#6-低コスト-ai-問題解決戦略)
7. [結論と次のステップ](#7-結論と次のステップ)

---

## 1. 調査概要

### 1.1 調査目的

Copilot Pro（GitHub Copilot Coding Agent）を中心に、複数の AI コーディングツールを活用した低コストかつ高品質な AI オーケストレーションの実現方法を調査する。具体的には以下を明らかにする：

- 各 AI ツールが GitHub リポジトリ上で参照する設定ファイルの種類と役割
- ツール横断の標準規格（AGENTS.md）の現状と採用状況
- 本リポジトリに不足している要素と、段階的に導入すべき施策

### 1.2 調査対象ツール

| ツール | 提供元 | 主な用途 |
|---|---|---|
| GitHub Copilot Pro / Coding Agent | GitHub (Microsoft) | コード生成・PR 自動作成・コードレビュー |
| Claude Code | Anthropic | CLI ベースの自律エージェント開発 |
| Cursor | Cursor Inc. | AI ネイティブ IDE |
| Windsurf | Codeium | AI ファーストIDE |
| Gemini CLI | Google | CLI ベースの AI コーディング |
| Aider | Open Source | CLI ベースのペアプログラミング |

### 1.3 調査日

2026-03-03

---

## 2. 最新 AI オーケストレーション手法の動向（2025〜2026）

### 2.1 AGENTS.md — ツール横断のオープン標準

2025 年 8 月に OpenAI が提唱し、同年 12 月に **Agentic AI Foundation (AAIF)** として Linux Foundation 傘下に移管されたオープン標準。創設メンバーに Anthropic、OpenAI、Google、Microsoft、Amazon が名を連ねる。

**現状:**
- 60,000 以上の OSS プロジェクトが採用
- 対応ツール：Claude Code、GitHub Copilot Coding Agent、Cursor、Gemini CLI、OpenAI Codex、Windsurf、Aider、Zed、Warp、RooCode

**形式:** 純粋な Markdown。YAML フロントマター不要。ディレクトリごとに配置可能（最も近い `AGENTS.md` が優先）。

**README.md との使い分け:**
- `README.md` — 人間向け（プロジェクト紹介、クイックスタート）
- `AGENTS.md` — AI エージェント向け（ビルドコマンド、コーディング規約、アーキテクチャ詳細）

### 2.2 GitHub Copilot Coding Agent

Microsoft Build 2025 で発表。GitHub Actions ランナー上でサンドボックス実行される自律エージェント。

**主要機能:**
- Issue をアサインすると自動的にクローン → 分析 → 実装 → ドラフト PR を作成
- リアルタイムのセッションログで進捗を監視可能
- 実行中の途中介入（ステアリング）に対応

**設定ファイル体系（2025〜2026 年の進化）:**

| 時期 | ファイル | 機能 |
|---|---|---|
| 2025 初頭 | `.github/copilot-instructions.md` | リポジトリ全体のグローバル指示 |
| 2025-07 | `.github/instructions/*.instructions.md` | パス別スコープ指示（`applyTo` glob） |
| 2025-08 | `AGENTS.md` | Coding Agent が AGENTS.md を公式サポート |
| 2025-10 | CodeQL/ESLint 統合 | コードレビューに静的解析結果を統合 |
| 2025-11 | `excludeAgent` プロパティ | `"code-review"` / `"coding-agent"` 別に指示を出し分け |
| 2025-12 | `.github/agents/*.agent.md` | カスタムエージェントプロファイル |
| 2025-12 | Agent Skills（`.github/skills/`） | ライフサイクル自動化スクリプト |
| 2026-01 | Copilot SDK (技術プレビュー) | Node.js/Python/Go/.NET 対応の SDK |

**重要な制限:**
- Copilot コードレビューは指示ファイルの先頭 **4,000 文字** のみ読み取る（Coding Agent や Chat には制限なし）
- API 経由での再レビュー依頼は技術的に不可能（本リポジトリ `docs/orchestration.md` §6.2 で検証済み）

### 2.3 Claude Code

Anthropic の CLI ベース自律エージェント。Claude Agent SDK として汎用エージェントフレームワークに発展。

**設定ファイル体系:**

| ファイル | 配置場所 | 用途 |
|---|---|---|
| `CLAUDE.md` | プロジェクトルート | プロジェクトコンテキスト（セッション開始時に自動読み込み） |
| `CLAUDE.local.md` | プロジェクトルート（.gitignore 対象） | 個人用オーバーライド |
| `~/.claude/CLAUDE.md` | ホームディレクトリ | グローバル指示 |
| `.claude/settings.json` | プロジェクト内 | フック設定・権限・ツール制御 |
| `.claude/settings.local.json` | プロジェクト内（.gitignore 対象） | 個人用設定 |
| `.claude/agents/*.md` | プロジェクト内 | サブエージェント定義（YAML フロントマター付き） |

**フックシステム（2025-06 リリース）:**
- `SessionStart`, `PreToolUse`, `PostToolUse`, `SubagentStart`, `SubagentStop`, `Stop` 等のライフサイクルイベント
- シェルコマンド、HTTP POST、Claude プロンプト、エージェント起動の 4 種類
- `.claude/settings.json` で設定

**サブエージェント定義:**

```markdown
---
name: security-auditor
description: セキュリティ分析を行う。認証関連ファイルの変更時に自動起動。
tools: Read, Grep, Glob
model: haiku
---
セキュリティ脆弱性の特定に特化した監査エージェント。
```

- `model` でエージェントごとにモデルを指定可能（`opus`/`sonnet`/`haiku`）→ **コスト最適化の鍵**
- サブエージェントはさらにサブエージェントをネストできない（1 階層のみ）
- 各サブエージェントは独立したコンテキストウィンドウで実行

### 2.4 Cursor

**設定ファイル体系:**

| ファイル | 状態 | 用途 |
|---|---|---|
| `.cursorrules` | 非推奨（後方互換で動作） | プロジェクトルートの単一ファイル |
| `.cursor/rules/*.mdc` | **推奨（現行）** | MDC（Markdown Config）形式、パス別スコープ |

**MDC ファイルのフロントマター:**

```markdown
---
description: Python ファイル向けコーディング規約
globs: "**/*.py"
alwaysApply: false
---
```

活性化モード：Always（常時）、Auto Attached（glob 一致時）、Agent Requested（AI 判断）、Manual（手動 @mention）

### 2.5 Windsurf

| ファイル | 状態 | 用途 |
|---|---|---|
| `.windsurfrules` | レガシー | プロジェクトルートの単一ファイル |
| `.windsurf/rules/*.md` | **推奨（Wave 8+）** | ディレクトリ型、glob/Always On 等の活性化モード |

### 2.6 その他のツール

| ツール | 設定ファイル | 補足 |
|---|---|---|
| Cline | `.clinerules` / `.clinerules/*.md` | v3.13+ でルール ON/OFF の UI |
| Roo Code | `.roo/rules/`, `.roo/rules-{mode}/` | モード別ルール（architect, code 等） |
| Aider | `.aider.conf.yml` | YAML。`read: CONVENTIONS.md` で規約ファイル参照 |
| Gemini CLI | `GEMINI.md` / `AGENT.md` | 階層構造。`@file.md` でインポート可能 |

---

## 3. GitHub 環境で求められる設定ファイル一覧

### 3.1 全体マップ

2026 年時点で、AI 対応の GitHub リポジトリに求められる設定ファイルの全体像：

```
project-root/
│
│  ── AI エージェント共通指示 ──
├── AGENTS.md                              # [必須] 全ツール共通オープン標準
│
│  ── GitHub Copilot ──
├── .github/
│   ├── copilot-instructions.md            # [必須] Copilot グローバル指示
│   ├── instructions/                      # [推奨] パス別スコープ指示
│   │   └── *.instructions.md
│   ├── agents/                            # [任意] Copilot カスタムエージェント
│   │   └── *.agent.md
│   ├── prompts/                           # [任意] 再利用可能プロンプト
│   │   └── *.prompt.md
│   ├── workflows/                         # [必須] CI/CD ワークフロー
│   ├── PULL_REQUEST_TEMPLATE.md           # [推奨] PR テンプレート
│   └── hooks/                             # [任意] Coding Agent フック
│
│  ── Claude Code ──
├── CLAUDE.md                              # [推奨] プロジェクトコンテキスト
├── .claude/
│   ├── settings.json                      # [任意] フック・権限設定
│   └── agents/                            # [任意] サブエージェント定義
│       └── *.md
│
│  ── Cursor ──
├── .cursor/
│   └── rules/                             # [任意] MDC ルールファイル
│       └── *.mdc
│
│  ── Windsurf ──
├── .windsurf/
│   └── rules/                             # [任意] プロジェクトルール
│       └── *.md
│
│  ── プロジェクト固有 ──
├── agents/                                # [任意] エージェント定義（本リポジトリ独自）
│   └── *.agent.md
└── configs/
    └── ai_models.toml                     # [任意] モデル割り当て設定
```

### 3.2 優先度別の分類

| 優先度 | ファイル | 理由 |
|---|---|---|
| **必須** | `AGENTS.md` | 全ツール共通標準。60,000+ プロジェクトが採用。ツール非依存 |
| **必須** | `.github/copilot-instructions.md` | 本リポジトリの中核。既に運用中 |
| **必須** | `.github/workflows/ci.yml` | 品質ゲート。既に運用中 |
| **推奨** | `CLAUDE.md` | Claude Code 対応。copilot-instructions.md からの抽出で作成可能 |
| **推奨** | `.github/instructions/*.instructions.md` | パス別スコープ指示。experiments/ と src/ で品質基準を分離可能 |
| **任意** | `.claude/agents/*.md` | Claude Code サブエージェント。既存 agents/ と対応 |
| **任意** | `.cursor/rules/*.mdc` | Cursor 対応。MDC 形式のルールファイル |
| **任意** | `.github/agents/*.agent.md` | Copilot カスタムエージェント。既存 agents/ の Copilot 正式形式版 |

---

## 4. 本リポジトリの現状分析（ギャップ分析）

### 4.1 既存の設定ファイル

| ファイル | 状態 | 評価 |
|---|---|---|
| `.github/copilot-instructions.md` | **運用中** | 12 ステップの自動実行パイプラインを詳細に定義。非常に充実 |
| `.github/workflows/ci.yml` | **運用中** | lint → format → type check → test → policy check の品質ゲート |
| `.github/workflows/issue-lifecycle.yml` | **運用中** | PR マージ時の Issue 自動 Close |
| `.github/PULL_REQUEST_TEMPLATE.md` | **運用中** | チェックリスト付き PR テンプレート |
| `agents/*.agent.md` | **運用中** | 7 エージェント定義（orchestrator 含む） |
| `configs/ai_models.toml` | **運用中** | Opus / Sonnet のモデル割り当て |
| `.vscode/settings.json` | **運用中** | Copilot エージェント設定 |
| `project-config.yml` | **運用中** | プロジェクトメタデータ |

### 4.2 不足している要素

| ファイル | 重要度 | 不足の影響 |
|---|---|---|
| `AGENTS.md` | **高** | Claude Code、Cursor、Gemini CLI、Aider 等からプロジェクト規約が参照されない |
| `CLAUDE.md` | **中** | Claude Code セッションでプロジェクトコンテキストが自動読み込みされない |
| `.github/instructions/*.instructions.md` | **中** | `experiments/` と `src/` で異なる品質基準を Copilot に伝達できない |
| `.claude/agents/*.md` | **低** | Claude Code のサブエージェント機能が活用できない |
| `.cursor/rules/*.mdc` | **低** | Cursor IDE でのプロジェクト固有ルールが適用されない |
| `.github/agents/*.agent.md` | **低** | Copilot Coding Agent のカスタムエージェント機能が活用できない |

### 4.3 重複・非効率の懸念

現在 `copilot-instructions.md` に **全情報が集約** されている（163 行）。これは Copilot 単独運用では適切だが、以下の問題がある：

1. **4,000 文字制限**: Copilot コードレビューは先頭 4,000 文字のみ読み取る → 重要な情報が切り捨てられるリスク
2. **ツールロック**: 他のツール（Claude Code, Cursor）からは参照されない
3. **スコープ不足**: `experiments/` と `src/` で異なる品質基準を適用できない

---

## 5. 実現に必要な要素と推奨アクション

### 5.1 Phase A: 即座に導入すべき要素（高優先度）

#### A-1. AGENTS.md の作成

**目的:** ツール横断のプロジェクト指示を提供する。

**内容構成（案）:**
- プロジェクト概要（AI オーケストレーション研究ラボ）
- ビルド・テスト・lint コマンド（`uv run pytest`, `uv run ruff check .` 等）
- コーディング規約（Python 3.11+、mypy strict、英語識別子 / 日本語コメント）
- ディレクトリ構造と責務（`experiments/` vs `src/` の品質基準の違い）
- Conventional Commit フォーマット
- 正本ドキュメントの参照先

**配置:** プロジェクトルート `AGENTS.md`

**期待効果:** Claude Code、Cursor、Gemini CLI、Aider 等すべてのツールがプロジェクト規約を参照可能に。

#### A-2. CLAUDE.md の作成

**目的:** Claude Code セッションでのプロジェクトコンテキスト自動読み込み。

**内容構成（案）:**
- AGENTS.md の内容をベースに、Claude Code 固有の指示を追加
- 正本参照ルール（docs/ 配下の SSOT）
- エージェント定義の参照先（`agents/*.agent.md`）
- CI 実行コマンド一覧
- 本リポジトリ固有の制約（P-001〜P-003）

**設計原則:** copilot-instructions.md の **全文コピーではなく**、共通部分は AGENTS.md に抽出し、CLAUDE.md は Claude Code 固有の差分のみを記述する。

### 5.2 Phase B: 短期的に導入すべき要素（中優先度）

#### B-1. `.github/instructions/` パス別スコープ指示

**目的:** `experiments/` と `src/` で異なる品質基準を Copilot に自動適用する。

```markdown
# .github/instructions/experiments.instructions.md
---
applyTo: "experiments/**/*.py"
---
# 実験コード品質基準（C-001）
- ruff check は必須、mypy / テストは推奨
- 外部 API モック使用を推奨
- README.md に実験の目的・手法・期待結果を記載すること
```

```markdown
# .github/instructions/src.instructions.md
---
applyTo: "src/**/*.py"
---
# 昇格コード品質基準（C-002）
- mypy strict 必須
- テスト必須（tests/unit/ に配置）
- docstring 必須
- ruff check 必須
```

#### B-2. copilot-instructions.md の構造最適化

**目的:** Copilot コードレビューの 4,000 文字制限に対応する。

**対策:**
- 最重要情報（Language、Scope & Safety、Code Style）を先頭 4,000 文字以内に配置
- 詳細なパイプライン手順は `.github/instructions/` へ分離を検討
- `excludeAgent: "code-review"` を活用して、レビュー不要な詳細を除外

### 5.3 Phase C: 中長期的に導入を検討する要素（低優先度）

#### C-1. `.claude/agents/*.md` サブエージェント定義

既存の `agents/*.agent.md` を Claude Code 形式に変換。モデル指定（`model: haiku` / `model: sonnet`）によるコスト最適化を実現。

#### C-2. `.cursor/rules/*.mdc` ルールファイル

Cursor IDE ユーザー向け。AGENTS.md の内容を MDC 形式に変換。

#### C-3. `.github/agents/*.agent.md` Copilot カスタムエージェント

Copilot Coding Agent のカスタムエージェント機能。既存 `agents/` のファイルを `.github/agents/` に移行または二重配置。`handoffs` フィールドでエージェント間のハンドオフチェーンを定義可能。

---

## 6. 低コスト AI 問題解決戦略

### 6.1 モデルルーティングによるコスト最適化

本リポジトリの `configs/ai_models.toml` は既にモデルルーティングを実装している：

| 役割 | 現在のモデル | コスト特性 |
|---|---|---|
| orchestrator | Opus 4.6 | 高コスト・高品質（タスク分解・品質判定） |
| release_manager | Opus 4.6 | 高コスト・高品質（最終判定） |
| implementer | Sonnet 4.6 | 中コスト・中品質（コード実装） |
| test_engineer | Sonnet 4.6 | 中コスト・中品質（テスト作成） |
| auditor_* (3種) | Sonnet 4.6 | 中コスト・中品質（監査） |

**改善案:** Claude Code のサブエージェントでは `model: haiku` が指定可能。以下のタスクに Haiku を活用することで更なるコスト削減が可能：

| タスク | 推奨モデル | 理由 |
|---|---|---|
| コードベース検索・ファイル探索 | Haiku | 単純な検索タスクに Opus/Sonnet は過剰 |
| フォーマットチェック・lint 結果の分類 | Haiku | パターンマッチング主体 |
| コミットメッセージ生成 | Haiku | テンプレートベースの生成 |
| コード実装 | Sonnet / Codex | コーディング品質と速度のバランス |
| タスク分解・品質判定 | Opus | 高度な推論が必要 |
| 最終リリース判定 | Opus | 多面的な判断が必要 |

### 6.2 トークンコスト削減手法

| 手法 | 削減率 | 本リポジトリでの適用可能性 |
|---|---|---|
| **プロンプトキャッシュ** | 60〜95% | 静的システムプロンプト（copilot-instructions.md）のキャッシュ |
| **モデルカスケード** | 最大 87% | 単純タスクに Haiku、複雑タスクに Opus を動的選択 |
| **RAG（関連コンテキストのみ取得）** | 70%+ | サブエージェントの独立コンテキストウィンドウが自然に実現 |
| **プロンプト圧縮** | 30〜50% | 冗長な指示の削減、AGENTS.md への共通化 |
| **バッチ処理** | 約 50% | 並列監査（3 エージェント同時実行）での API バッチ |

### 6.3 サブエージェントアーキテクチャによるコスト構造

並列サブエージェントアーキテクチャは、コスト最適化の構造的優位性を持つ：

1. **コンテキスト分離**: 各サブエージェントが独立したコンテキストウィンドウを持つため、不要な情報でトークンを消費しない
2. **並列実行**: 逐次実行と比較してウォールクロック時間を 71.6% 削減（N-003 実証済み）
3. **モデル混成**: タスク特性に応じたモデル選択により、品質を維持しつつコストを最小化

### 6.4 Copilot Pro の Premium Request 制限への対応

| プラン | Premium requests/月 |
|---|---|
| Copilot Business | 300 |
| Copilot Enterprise | 1,000 |

**対策:**
- 高頻度のルーティンタスク（lint 修正、フォーマット）は Copilot 外で処理
- Copilot コードレビューは初回のみ（API 制限で再レビュー不可）→ 以降は CI + get_errors で品質担保
- 複雑なタスクのみ Copilot Coding Agent に委譲

---

## 7. 結論と次のステップ

### 7.1 調査結論

1. **AGENTS.md はデファクト標準になりつつある**: Linux Foundation 傘下の AAIF で標準化。全主要ツールが対応。本リポジトリへの導入は必須。
2. **設定ファイルの階層化が進んでいる**: 全ツールが「グローバル指示 → パス別スコープ → エージェント定義」の階層構造に収斂。
3. **モデルルーティングが低コスト化の鍵**: 本リポジトリは既に Opus / Sonnet の二層構造を実装済み。Haiku 層の追加で更なるコスト削減が可能。
4. **本リポジトリは Copilot 中心の設計が成熟している**: copilot-instructions.md、agents/、CI ワークフローは高品質。不足しているのはツール横断の対応（AGENTS.md、CLAUDE.md）。

### 7.2 推奨アクション一覧

| # | アクション | 優先度 | 工数目安 | 効果 |
|---|---|---|---|---|
| 1 | `AGENTS.md` 作成 | 高 | 小 | 全 AI ツールからのプロジェクト規約参照 |
| 2 | `CLAUDE.md` 作成 | 中 | 小 | Claude Code セッションの品質向上 |
| 3 | `.github/instructions/` 導入 | 中 | 小 | experiments/ と src/ の品質基準自動適用 |
| 4 | `copilot-instructions.md` 構造最適化 | 中 | 中 | コードレビュー 4,000 文字制限への対応 |
| 5 | `.claude/agents/` 作成 | 低 | 中 | Claude Code サブエージェントのコスト最適化 |
| 6 | `.cursor/rules/` 作成 | 低 | 小 | Cursor IDE 対応 |
| 7 | Haiku モデル層の追加 | 低 | 小 | ルーティンタスクのコスト削減 |

### 7.3 設計原則

設定ファイル間の **情報重複を最小化** するため、以下の階層構造を推奨する：

```
AGENTS.md          ← 全ツール共通の規約（Single Source of Truth）
  ├── copilot-instructions.md  ← Copilot 固有のパイプライン・ワークフロー
  ├── CLAUDE.md                ← Claude Code 固有の指示（差分のみ）
  └── .cursor/rules/*.mdc     ← Cursor 固有のルール（差分のみ）
```

各ツール固有のファイルは AGENTS.md を **補完する差分** として設計し、共通部分の二重管理を避ける。

---

## 変更履歴

| 日付 | 内容 |
|---|---|
| 2026-03-03 | 初版作成。AI オーケストレーション手法の調査、GitHub 環境要素の特定、ギャップ分析、推奨アクションを記載。 |
