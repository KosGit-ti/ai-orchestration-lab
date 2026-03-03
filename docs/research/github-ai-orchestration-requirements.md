# GitHub環境におけるAIオーケストレーション実現要素の調査・検証報告

## 概要

本ドキュメントは「Copilot Proによる低コストAI問題解決.md」の調査結果をもとに、GitHub環境でマルチエージェント・オーケストレーションを実現するために求められる構成要素・ファイルを調査・検証し、本リポジトリ（ai-orchestration-lab）での実現に必要な要素を整理したものである。

調査対象:
- GitHub Copilot カスタムエージェント構成（`.github/agents/`、agents.md）
- GitHub Agentic Workflows（gh-aw）
- Model Context Protocol（MCP）サーバー構成
- カスタムインストラクション（copilot-instructions.md）
- CLAUDE.md / AGENTS.md（クロスツール互換フォーマット）
- Mission Control / Agent Sessions（VS Code統合）

---

## 1. 調査結果から抽出されたGitHub環境の構成要素

調査報告書が提示するマルチエージェント・オーケストレーションの実現には、以下の6つの技術領域がGitHub環境上のファイル・設定として具体化される必要がある。

### 1.1 エージェントペルソナの宣言的定義（agents.md）

**調査報告の記述:**
> `.github/agents/` ディレクトリに各エージェントのペルソナと制約を宣言的に記述したマークダウンファイルを配置する（引用12）

**GitHub環境での実体:**

| 項目 | 内容 |
|------|------|
| ファイル配置 | `.github/agents/<AGENT-NAME>.agent.md` |
| フォーマット | YAMLフロントマター + Markdownボディ |
| フロントマター属性 | `name`, `description`, `tools`, `model`, `mcp-servers` |
| ファイル名制約 | `.`, `-`, `_`, `a-z`, `A-Z`, `0-9` のみ使用可 |
| スコープ | リポジトリレベル（`.github/agents/`）またはOrg/Enterpriseレベル（`.github-private/agents/`） |

**フロントマターの例:**
```yaml
---
name: "security-auditor"
description: "セキュリティ監査を行う読み取り専用エージェント"
model: "claude-sonnet-4.6"
tools: ["read", "search", "get_errors"]
---
```

**6つの核となる定義領域:**
1. **Commands** — エージェントが実行可能なコマンド
2. **Testing** — テスト実行手順と期待結果
3. **Project Structure** — プロジェクト構造の理解
4. **Code Style** — コーディング規約と制約
5. **Git Workflow** — ブランチ戦略・コミット規約
6. **Boundaries** — 明確な禁止事項

### 1.2 動的モデルルーティング（2モデルワークフロー）

**調査報告の記述:**
> 高度な推論モデルをメインエージェントとして起動し、計画書を作成。その後、軽量モデルに切り替えて実装する（引用14）

**GitHub環境での実体:**

| 要素 | 実現方法 |
|------|----------|
| モデル指定 | `.agent.md` フロントマターの `model:` プロパティ |
| 計画モデル | Claude Opus 4.6 / OpenAI o3（高推論・高コスト） |
| 実装モデル | Claude Sonnet 4.6 / GPT-4.1（高速・低コスト） |
| 計画の永続化 | `/docs/spec.md` 等のマークダウンファイル |
| 切り替え制御 | Orchestratorエージェントがフェーズに応じてサブエージェントを委譲 |

### 1.3 サブエージェントによるレビュー・検証ループ

**調査報告の記述:**
> Specialist → Reviewer → フィードバックループによる自己修復サイクル。異なるAIモデルを割り当てることで盲点を補う（引用12）

**GitHub環境での実体:**

| 要素 | 実現方法 |
|------|----------|
| サブエージェント呼び出し | `#runSubagent` ツールコール（VS Code Copilot Chat） |
| コンテキスト分離 | 各サブエージェントが独立したコンテキストウィンドウで実行 |
| 結果返却 | 簡潔なJSON/Markdownレポートのみをメインに返却 |
| ループ制御 | 品質スコア閾値による反復/終了判定 |
| VS Code設定 | `github.copilot.chat.agent.subAgent.enabled: true` |

### 1.4 GitHub Agentic Workflows（自律的CI/CD）

**調査報告の記述:**
> `.github/workflows` ディレクトリにマークダウンファイルを作成し、自然言語でタスクの意図を記述する。`gh aw compile` で `.lock.yml` に変換（引用28）

**GitHub環境での実体:**

| 項目 | 内容 |
|------|------|
| ファイル配置 | `.github/workflows/<workflow-name>.md` |
| フォーマット | YAMLフロントマター + 自然言語Markdownボディ |
| コンパイル | `gh aw compile` → `.lock.yml` 生成 |
| エンジン選択 | Copilot CLI / Claude Code / OpenAI Codex |
| 権限モデル | デフォルト読み取り専用 + `safe-outputs` による書き込み制御 |
| ステータス | テクニカルプレビュー（2026年2月13日〜） |

**フロントマター構造:**
```yaml
---
name: daily-repo-status
on:
  schedule:
    - cron: "0 9 * * *"
engine: copilot
permissions:
  contents: read
  issues: write
safe-outputs:
  - type: issue
    action: create
tools:
  - github
---
```

### 1.5 MCP（Model Context Protocol）統合

**調査報告の記述:**
> MCPサーバーを構築・導入することで、エージェントに無数の「スキル」を付与。Slack、Linear、Azure Boards等との連携が可能（引用31）

**GitHub環境での実体:**

| 項目 | 内容 |
|------|------|
| 構成ファイル | `.vscode/mcp.json`（ワークスペース共有）または `~/mcp.json`（ユーザー個人） |
| サーバー種別 | Remote（HTTP）/ Local（コマンドベース） |
| GitHub公式MCP | `https://api.githubcopilot.com/mcp`（リモート） |
| ローカルMCP | `github/github-mcp-server`（npmパッケージ） |
| エージェント連携 | `.agent.md` フロントマターの `mcp-servers:` プロパティ |

**mcp.json の例:**
```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp"
    }
  }
}
```

### 1.6 クロスツール互換インストラクション

**調査報告の記述（包括）:**
> AIエージェントを用いた自動化が失敗する最大の原因は「システム構造（Structure）の欠如」にある（引用9）

**GitHub環境での実体:**

| ファイル | 用途 | 対象ツール |
|----------|------|------------|
| `.github/copilot-instructions.md` | Copilot全般のカスタムインストラクション | GitHub Copilot |
| `.github/instructions/*.instructions.md` | パス固有インストラクション | GitHub Copilot |
| `CLAUDE.md` | Claude Codeセッション全体への永続的指示 | Claude Code |
| `AGENTS.md` | エージェント向けオープン標準（Linux Foundation管理） | 複数ツール共通 |
| `.cursorrules` | Cursor IDE向け指示 | Cursor |

---

## 2. 本リポジトリの現状マッピング

### 2.1 実装状況の一覧

| # | 構成要素 | 調査報告での位置づけ | 現在の状態 | 判定 |
|---|----------|---------------------|-----------|------|
| 1 | エージェントペルソナ定義 | `.github/agents/*.agent.md` | `agents/*.agent.md`（ルート直下） | **△ 配置場所が異なる** |
| 2 | 2モデルワークフロー（Plan & Execute） | Opus → 計画、Sonnet → 実装 | `configs/ai_models.toml` で定義済み | **○ 概念実装済み** |
| 3 | サブエージェント・レビューループ | Specialist → Reviewer → フィードバック | orchestrator.agent.md の12ステップパイプラインで実装 | **◎ 先行実装済み** |
| 4 | GitHub Agentic Workflows | `.github/workflows/*.md` → `.lock.yml` | 従来型YAML（ci.yml, issue-lifecycle.yml）のみ | **× 未実装** |
| 5 | MCP統合 | `.vscode/mcp.json` | 未配置 | **× 未実装** |
| 6 | カスタムインストラクション | `.github/copilot-instructions.md` | 163行の包括的指示書が存在 | **◎ 先行実装済み** |
| 7 | VS Code Agent Sessions | `github.copilot.chat.agent.subAgent.enabled` | `.vscode/settings.json` で有効化済み | **○ 実装済み** |
| 8 | CLAUDE.md | Claude Codeセッション指示 | 未配置 | **× 未実装** |
| 9 | AGENTS.md（オープン標準） | クロスツール共通指示 | 未配置 | **× 未実装** |
| 10 | エージェント用YAMLフロントマター | `.agent.md` に `model:`, `tools:`, `mcp-servers:` | 現在のagent.mdにフロントマターなし | **△ 未対応** |
| 11 | 型付きインターフェース（出力スキーマ） | サブエージェント結果のJSON構造強制 | 各agent.mdにレスポンススキーマ定義あり | **◎ 先行実装済み** |
| 12 | ポリシーによるアクション制御 | エージェント操作権限の明示的制限 | policies.md + policy_check.py で実現 | **◎ 先行実装済み** |

### 2.2 強み（調査結果に先行して実現済みの要素）

本リポジトリは、調査報告が提唱する多くのパターンを独自に先行実装している。

1. **7エージェント体制と12ステップパイプライン** — 調査報告の「Specialist → Reviewer → フィードバックループ」を、orchestrator → implementer/test_engineer → 3 auditors → release_manager という明確な責務分離で実現
2. **型付き出力スキーマ** — 各エージェントのレスポンスがJSON構造（status, summary, findings[], metrics）で定義済み
3. **モデル役割分離** — `configs/ai_models.toml` で Opus 4.6（判断系）と Sonnet 4.6（実行系）の明確な分離
4. **ポリシーエンフォースメント** — P-001〜P-042の42ポリシー + 自動チェック（policy_check.py）
5. **SSOT（Single Source of Truth）設計** — docs/ 配下の5文書を正規の情報源とする宣言的設計

### 2.3 ギャップ（調査結果との乖離点）

| 優先度 | ギャップ | 影響 | 対応方針 |
|--------|---------|------|----------|
| **高** | エージェント配置場所が `agents/` であり `.github/agents/` でない | Copilot Coding Agent がカスタムエージェントを自動認識しない | 移行検討（後述） |
| **高** | `.agent.md` にYAMLフロントマターがない | `model:`, `tools:`, `mcp-servers:` の宣言的制御が効かない | フロントマター追加（後述） |
| **中** | GitHub Agentic Workflows 未導入 | 自律的CI/CD（夜間トリアージ、CI障害分析等）が実現できない | テクニカルプレビュー評価（後述） |
| **中** | MCP統合なし | 外部ツール（Slack、Linear等）との連携不可 | `.vscode/mcp.json` 追加（後述） |
| **低** | CLAUDE.md 未配置 | Claude Code利用時のセッション指示が効かない | 作成検討 |
| **低** | AGENTS.md（オープン標準）未配置 | 他ツール（Codex、Cursor、Jules等）との互換性なし | 作成検討 |

---

## 3. 実現に必要な要素の詳細分析

### 3.1 【高優先】エージェント配置の `.github/agents/` 移行

#### 現状
```
ai-orchestration-lab/
├── agents/                          ← 現在の配置（ルート直下）
│   ├── orchestrator.agent.md
│   ├── implementer.agent.md
│   ├── test_engineer.agent.md
│   ├── auditor_spec.agent.md
│   ├── auditor_security.agent.md
│   ├── auditor_reliability.agent.md
│   └── release_manager.agent.md
```

#### GitHub Copilot が期待する配置
```
ai-orchestration-lab/
├── .github/
│   └── agents/                      ← Copilot が自動認識するパス
│       ├── orchestrator.agent.md
│       ├── implementer.agent.md
│       ├── test-engineer.agent.md   ← アンダースコアはハイフンに
│       ├── auditor-spec.agent.md
│       ├── auditor-security.agent.md
│       ├── auditor-reliability.agent.md
│       └── release-manager.agent.md
```

#### 移行時の考慮事項
- **ファイル名**: GitHub Copilot はファイル名の `_` を許容するが、慣例的に `-` が推奨される
- **フロントマター追加**: 各エージェントに `name`, `description`, `model`, `tools` を追加
- **既存参照の更新**: `.github/copilot-instructions.md`、`docs/orchestration.md` 等の参照パス更新
- **後方互換**: 移行期間中は `agents/` にシンボリックリンクまたは参照ガイドを残すことも可能

#### 影響範囲
- `.github/copilot-instructions.md` 内のエージェント参照パス
- `docs/orchestration.md` のエージェント一覧
- `docs/architecture.md` のモジュール構成図
- `project-config.yml` のエージェント定義

### 3.2 【高優先】YAMLフロントマターの追加

#### 現在の形式（フロントマターなし）
```markdown
# orchestrator（司令塔）

あなたは orchestrator（司令塔）です。
...
```

#### 目標形式（GitHub Copilot カスタムエージェント準拠）
```markdown
---
name: "orchestrator"
description: "タスク分解・進捗管理・サブエージェント委譲を行う司令塔エージェント"
model: "claude-opus-4.6"
tools: ["*"]
---

# orchestrator（司令塔）

あなたは orchestrator（司令塔）です。
...
```

#### 各エージェントのフロントマター設計

| エージェント | model | tools | mcp-servers |
|-------------|-------|-------|-------------|
| orchestrator | claude-opus-4.6 | `["*"]` | （必要に応じて） |
| implementer | claude-sonnet-4.6 | `["read", "edit", "write", "search", "terminal"]` | — |
| test-engineer | claude-sonnet-4.6 | `["read", "edit", "write", "search", "terminal"]` | — |
| auditor-spec | claude-sonnet-4.6 | `["read", "search", "get_errors"]` | — |
| auditor-security | claude-sonnet-4.6 | `["read", "search", "get_errors"]` | — |
| auditor-reliability | claude-sonnet-4.6 | `["read", "search", "get_errors"]` | — |
| release-manager | claude-opus-4.6 | `["read", "search", "get_errors"]` | — |

#### `configs/ai_models.toml` との整合
現在の `configs/ai_models.toml` で定義されているモデル割り当てを `.agent.md` のフロントマターに転記する。`ai_models.toml` はバックアップ/リファレンスとして残し、フロントマターを正規の定義源（SSOT）とする。

### 3.3 【中優先】GitHub Agentic Workflows 導入

#### 導入候補ワークフロー

調査報告の「AIエージェントの工場（Agent Factory）」を実現するために、以下のワークフローが候補となる。

**1. 自動Issue分析（issue-analysis.md）**
```yaml
---
name: issue-analysis
on:
  issues:
    types: [opened]
engine: copilot
permissions:
  contents: read
  issues: write
safe-outputs:
  - type: issue_comment
    action: create
tools:
  - github
---
```
```markdown
新しいIssueが作成されたとき:
1. Issueの内容を分析し、docs/requirements.md との関連性を特定する
2. 影響を受ける可能性のあるファイルを一覧化する
3. 分析結果をIssueコメントとして投稿する
```

**2. CI障害分析（ci-failure-analysis.md）**
```yaml
---
name: ci-failure-analysis
on:
  workflow_run:
    workflows: ["CI"]
    types: [completed]
    conclusions: [failure]
engine: copilot
permissions:
  contents: read
  issues: write
safe-outputs:
  - type: issue
    action: create
tools:
  - github
---
```
```markdown
CIが失敗したとき:
1. 失敗したジョブのログを取得・解析する
2. 根本原因を特定し、修正案を提示する
3. 分析結果をIssueとして作成する
```

#### 導入前提条件
- `gh` CLI のインストールと `gh aw` 拡張の導入
- テクニカルプレビューへのアクセス権限
- コンパイル結果（`.lock.yml`）のリポジトリへのコミット

#### 本リポジトリへの適用判断
GitHub Agentic Workflows は2026年2月時点でテクニカルプレビュー段階にある。本リポジトリが研究目的であることを考慮すると、**実験的導入として `experiments/` 配下でのPoC評価**が適切と考えられる。正式導入はGA（一般提供）を待つべきである。

### 3.4 【中優先】MCP サーバー構成

#### 推奨構成ファイル

`.vscode/mcp.json` をワークスペースに追加し、チーム共有可能にする。

```json
{
  "servers": {
    "github": {
      "type": "http",
      "url": "https://api.githubcopilot.com/mcp"
    }
  }
}
```

#### 拡張候補
研究フェーズの進行に応じて以下のMCPサーバーを追加候補とする:

| MCPサーバー | 用途 | 導入時期 |
|------------|------|----------|
| GitHub MCP | GitHub API操作（Issue、PR、コード検索） | 即時導入可 |
| Playwright MCP | ブラウザ自動テスト | Phase 2以降 |
| File System MCP | ローカルファイル操作拡張 | 必要に応じて |

#### ポリシーとの整合
- P-001（意図しない外部API接続の禁止）により、MCPサーバーの追加にはADR作成が必要
- リモートMCPサーバーの利用はGitHub公式のみに限定し、サードパーティMCPはローカル実行を原則とする

### 3.5 【低優先】CLAUDE.md の作成

Claude Code でのセッション指示として、以下の構成で作成する。

```markdown
# AI Orchestration Lab

## プロジェクト概要
AIエージェントオーケストレーションの研究・検証リポジトリ。

## 技術スタック
- Python 3.11+, パッケージマネージャ: uv
- 型チェック: mypy strict, リンター: ruff, テスト: pytest

## 開発ルール
- docs/ 配下がSSOT（Single Source of Truth）
- ポリシー: docs/policies.md（P-001〜P-042）
- 実験コード: experiments/ に配置（src/ と混在禁止）
- src/ 昇格基準: mypy strict + tests必須 + ruff + docstring

## CI コマンド
- ruff check src/ tests/ ci/ experiments/
- ruff format --check .
- mypy src/ tests/ ci/ --strict
- pytest tests/
- python ci/policy_check.py

## エージェント構成
7エージェント体制（agents/*.agent.md）
- orchestrator: 司令塔（Opus 4.6）
- implementer: 実装担当（Sonnet 4.6）
- test_engineer: テスト担当（Sonnet 4.6）
- auditor_spec/security/reliability: 監査担当（Sonnet 4.6）
- release_manager: リリース判断（Opus 4.6）

## コミット規約
Conventional Commits: feat:, fix:, docs:, test:, ci:, refactor:, chore:, research:
```

#### 既存 copilot-instructions.md との役割分担
- `copilot-instructions.md`: Copilot に特化した詳細な実行パイプライン・品質ゲート定義
- `CLAUDE.md`: Claude Code に特化したプロジェクト概要・開発コマンド・基本ルール
- 共通事項（ポリシー、技術スタック等）は重複を最小化し、docs/ への参照で統一

### 3.6 【低優先】AGENTS.md（オープン標準）の作成

AGENTS.md は Linux Foundation の Agentic AI Foundation が管理するオープンフォーマットであり、GitHub Copilot、OpenAI Codex、Google Jules、Cursor、Amp 等の複数ツールで共通利用できる。

#### 本リポジトリでの位置づけ
- 本リポジトリの `.github/agents/` に配置された `.agent.md` ファイルはGitHub Copilot専用
- AGENTS.md はリポジトリルートに配置し、ツール非依存の共通指示として機能
- 両者は補完関係にあり、矛盾しないよう設計する必要がある

---

## 4. 実現に必要な要素の優先度マトリクス

### 4.1 分類基準

- **ROI**: 導入コスト対効果（調査報告の「経済的アービトラージ」観点）
- **即効性**: 導入後すぐに効果が出るか
- **リスク**: 導入時の破壊的変更リスク
- **依存度**: 他の要素への前提条件となるか

### 4.2 優先度マトリクス

| 優先度 | 要素 | ROI | 即効性 | リスク | 対応内容 |
|--------|------|-----|--------|--------|----------|
| **P1** | `.agent.md` フロントマター追加 | 高 | 高 | 低 | 既存ファイルへのYAMLヘッダー追記のみ |
| **P2** | `.github/agents/` への移行 | 高 | 高 | 中 | ファイル移動 + 参照パス更新 |
| **P3** | `.vscode/mcp.json` 追加 | 中 | 高 | 低 | 新規ファイル追加のみ |
| **P4** | CLAUDE.md 作成 | 中 | 中 | 低 | 新規ファイル追加のみ |
| **P5** | AGENTS.md 作成 | 低 | 中 | 低 | 新規ファイル追加のみ |
| **P6** | GitHub Agentic Workflows 導入 | 高 | 低 | 中 | テクニカルプレビュー依存、GA待ち推奨 |

### 4.3 推奨実施順序

```
Phase A（即時実施可能）:
  P1: フロントマター追加 → P2: .github/agents/ 移行 → P3: mcp.json 追加

Phase B（短期）:
  P4: CLAUDE.md 作成 → P5: AGENTS.md 作成

Phase C（GA後）:
  P6: GitHub Agentic Workflows 正式導入
```

---

## 5. 本リポジトリの構成要素と調査報告のアーキテクチャパターンの対応表

| 調査報告のパターン | 本リポジトリでの対応要素 | 状態 |
|-------------------|------------------------|------|
| **動的モデルルーティング（Plan & Execute）** | configs/ai_models.toml（Opus=計画、Sonnet=実装） | 実装済み |
| **サブエージェント委譲** | orchestrator.agent.md → implementer/test_engineer | 実装済み |
| **コンテキスト分離** | 各エージェントが独立コンテキストで実行 + JSON応答スキーマ | 実装済み |
| **フィードバック・自己反省ループ** | 12ステップパイプラインの修正ループ（最大3回） | 実装済み |
| **異なるモデルによるレビュー** | auditor（Sonnet）がimplementer（Sonnet）出力を監査 | 部分実装（同一モデル） |
| **agents.md ペルソナ制御** | agents/*.agent.md（7エージェント定義） | 実装済み（配置場所要移行） |
| **型付きインターフェース** | 各エージェントのレスポンススキーマ（JSON） | 実装済み |
| **アクションスキーマ** | policies.md + policy_check.py | 実装済み |
| **Agentic Workflows** | ci.yml + issue-lifecycle.yml（従来型YAML） | 未実装（従来型で代替中） |
| **MCP統合** | — | 未実装 |
| **Mission Control** | .vscode/settings.json（subAgent有効化） | 設定済み |
| **プレミアムリクエスト最適化** | 2モデル構成による消費最適化 | 設計済み |

---

## 6. 結論

### 6.1 本リポジトリの評価

調査報告が提唱する「低コストAIオーケストレーション」の実現に必要な**核心的要素の約70%は既に本リポジトリに実装済み**である。特に以下の点は調査報告の推奨事項を先取りしている:

- 7エージェント体制と責務分離
- 12ステップ自律実行パイプライン
- 型付き出力スキーマ
- ポリシーエンフォースメント
- SSOT設計

### 6.2 残りの30%（ギャップ）

未実装の要素は主にGitHub Copilotプラットフォームとの**統合インターフェース層**に集中している:

1. `.github/agents/` への配置移行とフロントマター対応（Copilot カスタムエージェント認識）
2. MCP統合による外部ツール連携
3. GitHub Agentic Workflows による自律CI/CD

### 6.3 次のアクション

上記「4.3 推奨実施順序」に従い、Phase A（フロントマター追加 → 配置移行 → MCP設定）を即時実施可能な改善として着手することを推奨する。これにより、本リポジトリの既存のオーケストレーション設計が、GitHub Copilotプラットフォームのネイティブ機能と直接連携し、調査報告が描く「経済的アービトラージ」を最大限に活用できる状態となる。

---

## 参考資料

- [How to write a great agents.md — GitHub Blog](https://github.blog/ai-and-ml/github-copilot/how-to-write-a-great-agents-md-lessons-from-over-2500-repositories/)
- [Creating custom agents for Copilot coding agent — GitHub Docs](https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/create-custom-agents)
- [Custom agents configuration — GitHub Docs](https://docs.github.com/en/copilot/reference/custom-agents-configuration)
- [GitHub Agentic Workflows — Technical Preview](https://github.blog/changelog/2026-02-13-github-agentic-workflows-are-now-in-technical-preview/)
- [Automate repository tasks with GitHub Agentic Workflows — GitHub Blog](https://github.blog/ai-and-ml/automate-repository-tasks-with-github-agentic-workflows/)
- [GitHub Agentic Workflows Documentation](https://github.github.com/gh-aw/)
- [Add and manage MCP servers in VS Code](https://code.visualstudio.com/docs/copilot/customization/mcp-servers)
- [GitHub MCP Server](https://github.com/github/github-mcp-server)
- [AGENTS.md — Open Standard](https://agents.md/)
- [How to orchestrate agents using mission control — GitHub Blog](https://github.blog/ai-and-ml/github-copilot/how-to-orchestrate-agents-using-mission-control/)
