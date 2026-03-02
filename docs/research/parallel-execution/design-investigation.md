# エージェント並列実行 — 設計調査報告

## 1. 背景と目的

現行の dev-orchestration-template パイプラインでは、エージェントは基本的に逐次実行される。
特に実装フェーズ（implementer → test-engineer → CI → 監査）は 1 タスクずつ処理するため、
複雑な実装タスク（例：ML 特徴量エンジニアリング）では全体の所要時間が長い。

本調査では、**実装工程の作業を並列実行化** するアーキテクチャを調査し、
最適なアプローチを選定する。

## 2. ターゲットアーキテクチャ

ユーザーが要求する具体的なアーキテクチャ：

```text
┌─────────────────────────────────────────────────────┐
│                       Pipeline                       │
│                                                      │
│  ┌──────────────┐    Fan-Out     ┌──────────────┐   │
│  │  Commander    │──────┬───────▶│  Worker 1     │   │
│  │  (Opus 4.6)  │      │        │  (Sonnet 4.6) │   │
│  │              │      │        └──────┬─────────┘   │
│  │  ・タスク分解 │      │               │             │
│  │  ・品質判定  │      │        ┌──────┴─────────┐   │
│  │  ・再指示    │      ├───────▶│  Worker 2     │   │
│  │              │      │        │  (Codex 5.3)  │   │
│  └──────┬───────┘      │        └──────┬─────────┘   │
│         ▲              │               │             │
│         │              │        ┌──────┴─────────┐   │
│         │    Fan-In    ├───────▶│  Worker 3     │   │
│         │◀─────────────┤        │  (Sonnet 4.6) │   │
│         │              │        └──────┬─────────┘   │
│         │              │               │             │
│  ┌──────┴───────┐      │        ┌──────┴─────────┐   │
│  │ Quality Gate │      └───────▶│  Worker N     │   │
│  │              │               │  (Codex 5.3)  │   │
│  │ pass? ─Yes─▶ 次工程          └───────────────┘   │
│  │       └No──▶ 再指示ループ                         │
│  └──────────────┘                                    │
└─────────────────────────────────────────────────────┘
```

### 要件整理

| 要件 | 内容 |
|---|---|
| 司令塔モデル | Opus 4.6（コンテキスト理解 + 技術的卓越性） |
| 作業者モデル | Sonnet 4.6 / Codex 5.3（コスト効率の高いコーディング特化） |
| 実行パターン | Fan-Out / Fan-In |
| 品質ゲート | 司令塔による検証・再指示ループ（パフォーマンス最大化） |
| ワーカー数 | 可変 3〜10（困難なら 5 固定） |
| 実行時間 | 長時間実行を許容 |
| ユースケース | 複雑な実装タスク（ML 特徴量エンジニアリング等） |

## 3. 候補アプローチ

### A1: asyncio + LiteLLM マルチモデル直接オーケストレーション

**概要:** Python `asyncio.gather()` で複数の LLM API 呼び出しを並列実行する。
LiteLLM の統一インターフェースにより、異種モデル（Opus / Sonnet / Codex）を透過的に扱う。

**アーキテクチャ:**

```python
async def run_pipeline(task: str, config: Config) -> Result:
    iteration = 0
    while iteration < config.max_iterations:
        # Fan-Out: 司令塔がタスク分解
        subtasks = await commander.decompose(task)

        # 並列実行: asyncio.gather で全ワーカーを同時実行
        results = await asyncio.gather(*[
            worker.execute(subtask) for subtask in subtasks
        ])

        # Fan-In + Quality Gate: 司令塔が品質判定
        verdict = await commander.review(results)
        if verdict.passed:
            return aggregate(results, verdict)
        task = verdict.revised_task  # 再指示
        iteration += 1
```

**メリット:**

- 実装が最もシンプル（標準ライブラリ + LiteLLM のみ）
- ワーカー数の動的制御が容易（`asyncio.Semaphore` で上限制御可能）
- 品質ゲートループの制御が直感的
- 長時間実行にも適している（`asyncio.wait_for` でタイムアウト制御）
- LiteLLM は既に `pyproject.toml` の optional deps に含まれている

**デメリット:**

- 状態管理を手動で実装する必要がある
- ワークフローの可視化手段がない（ロギングに依存）
- エラーリカバリやリトライの仕組みを自前で実装する必要がある
- コンテキスト共有の仕組みが標準では提供されない

**適合度:** ★★★★☆ — 要件に直接対応。プロトタイプに最適。

### A2: LangGraph Fan-Out/Fan-In

**概要:** LangGraph の `StateGraph` と `Send` API を使い、
構造化されたワークフローとして Fan-Out / Fan-In パターンを実装する。

**アーキテクチャ:**

```python
from langgraph.graph import StateGraph, Send

def commander_decompose(state: PipelineState) -> list[Send]:
    """司令塔がタスクを分解し、ワーカーに Send で配信する。"""
    subtasks = decompose(state.task)
    return [
        Send("worker_execute", {"task": t, "model": select_model(t)})
        for t in subtasks
    ]

graph = StateGraph(PipelineState)
graph.add_node("commander_decompose", commander_decompose)
graph.add_node("worker_execute", worker_execute)
graph.add_node("commander_review", commander_review)
graph.add_conditional_edges(
    "commander_review",
    quality_check,
    {"pass": END, "fail": "commander_decompose"},
)
```

**メリット:**

- Fan-Out / Fan-In が第一級パターンとして組み込まれている（`Send` API）
- Pydantic モデルによる型安全な状態管理
- 条件付きエッジで品質ゲートループを宣言的に定義可能
- グラフの可視化と実行トレースが標準で利用可能
- Phase 2（型安全オーケストレーション）との相乗効果
- `pyproject.toml` の optional deps に含まれている

**デメリット:**

- LangGraph の学習コストがある
- LangGraph API がまだ発展途上（破壊的変更のリスク）
- オーバーヘッドがある（シンプルなケースでは過剰）
- LangGraph 固有の制約に縛られる（カスタマイズの限界）

**適合度:** ★★★★★ — 要件に最も適合。本格実装に推奨。

### A3: Task Queue + Worker Pool（Celery / Redis 等）

**概要:** メッセージキューベースの非同期ワーカープール。
各ワーカーが独立プロセスとして LLM 呼び出しを実行する。

**アーキテクチャ:**

```python
# Producer（Commander）
for subtask in decomposed_tasks:
    celery_app.send_task("worker.execute", args=[subtask])

# Consumer（Worker）
@celery_app.task
def execute(subtask: dict) -> dict:
    result = litellm.completion(model=subtask["model"], ...)
    return result
```

**メリット:**

- 水平スケーリングが容易（ワーカーを別マシンに分散可能）
- 耐障害性が高い（ワーカー障害時の自動リトライ）
- 長時間タスクに適している（バックグラウンド実行）

**デメリット:**

- インフラコストが非常に高い（Redis / RabbitMQ の運用が必要）
- 研究フェーズには過剰なアーキテクチャ
- デプロイ・運用の複雑さが研究の焦点から外れる
- コンテキスト共有が困難（プロセス間通信）

**適合度:** ★★☆☆☆ — スケーラビリティは高いが、研究フェーズには不適。

### A4: A2A プロトコルによる分散エージェント

**概要:** Google の Agent-to-Agent（A2A）プロトコルに準拠した
エージェントサービスを構築し、HTTP/JSON-RPC で通信する。

**アーキテクチャ:**

```text
Commander Agent (A2A Server)
    ↕ HTTP/JSON-RPC
Worker Agent 1 (A2A Server)
Worker Agent 2 (A2A Server)
Worker Agent N (A2A Server)
```

**メリット:**

- 標準プロトコルによる相互運用性
- 言語・フレームワーク非依存
- マイクロサービス的なスケーラビリティ
- 外部エージェントとの連携が可能

**デメリット:**

- インフラ構築コストが極めて高い
- 各エージェントの HTTP サーバー運用が必要
- 研究フェーズでは ROI が低い
- オーバーエンジニアリングのリスク

**適合度:** ★☆☆☆☆ — Phase 4 以降の検討課題。現時点では不適。

## 4. 評価基準と比較

### 評価基準

| 基準 | 重み | 説明 |
|---|---|---|
| 要件適合度 | 高 | ユーザー要件（Fan-Out/Fan-In、品質ゲート、異種モデル）への適合 |
| 実装容易性 | 高 | プロトタイプの作成コスト |
| 型安全性 | 中 | mypy strict 対応、Pydantic 統合 |
| 拡張性 | 中 | ワーカー数変更、新モデル追加の容易さ |
| 可観測性 | 低 | 実行トレース、可視化の充実度 |
| インフラコスト | 低 | 追加インフラの必要性 |

### 比較表

| 基準 | A1: asyncio | A2: LangGraph | A3: Task Queue | A4: A2A |
|---|---|---|---|---|
| Fan-Out/Fan-In | ○ 手動実装 | ◎ Send API | ○ キューで分散 | ○ HTTP 通信 |
| 品質ゲート | ◎ while ループ | ◎ 条件付きエッジ | △ コールバック | △ リクエスト/応答 |
| 異種モデル | ◎ LiteLLM | ◎ LiteLLM | ◎ LiteLLM | ○ 各サービスで設定 |
| 可変ワーカー数 | ◎ 動的タスク生成 | ◎ Send で動的配信 | ◎ キュー投入数 | ○ サービス数 |
| 長時間実行 | ◎ asyncio | ◎ 非同期対応 | ◎ バックグラウンド | ◎ 非同期通信 |
| 実装コスト | ◎ 低い | ○ 中程度 | △ 高い | × 極めて高い |
| 型安全性 | ○ dataclass | ◎ Pydantic | ○ Pydantic | △ JSON schema |
| 可視化 | △ ログのみ | ◎ グラフ可視化 | ○ Flower 等 | △ ダッシュボード |
| Phase 2 相乗効果 | △ なし | ◎ 高い | △ なし | △ Phase 4 向け |
| インフラ追加 | ◎ 不要 | ◎ 不要 | × Redis 必要 | × HTTP サーバー |

## 5. 推奨アプローチ

### 一次推奨：A2（LangGraph Fan-Out/Fan-In）

**理由:**

1. **Fan-Out / Fan-In が第一級パターン** — `Send` API により、司令塔から可変数の
   ワーカーへの動的タスク配信が宣言的に記述できる
2. **品質ゲートループが自然** — 条件付きエッジにより、品質判定 → 再指示のループが
   グラフ構造として表現できる
3. **型安全性** — Pydantic モデルによる状態管理が Phase 2（型安全オーケストレーション）と
   直接的な相乗効果を持つ
4. **可観測性** — 実行グラフの可視化、ステップごとのトレースが標準で利用可能
5. **依存関係** — 既に `pyproject.toml` の optional deps に含まれている

### 補完アプローチ：A1（asyncio + LiteLLM）

**理由:**

1. **プロトタイプの迅速な検証** — LangGraph の学習コストなしに即座にパターンを検証できる
2. **フォールバック** — LangGraph の API 変更や不具合時の代替手段として機能する
3. **シンプルなユースケース** — タスク分解が不要な単純な並列呼び出しに適している

### 段階的導入戦略

```text
Phase 1（N-002 / N-003）:
  PoC は A1（asyncio モック）で概念実証
        ↓
Phase 1 後半:
  A2（LangGraph）で本格実装
        ↓
Phase 2:
  型安全オーケストレーションと統合
        ↓
Phase 4（長期）:
  A4（A2A）での分散化を検討
```

## 6. 設計方針

### 6.1 異種モデル混成（ヘテロジニアス・マルチモデル）

各モデルの特性に基づく役割分担：

| モデル | 役割 | 特性 | コスト効率 |
|---|---|---|---|
| Opus 4.6 | 司令塔 | コンテキスト理解、タスク分解、品質判定に優れる | 低（高品質だが高コスト） |
| Sonnet 4.6 | 作業者（汎用） | コーディング品質と速度のバランス | 高 |
| Codex 5.3 | 作業者（コード特化） | コード生成に特化、高速 | 高 |

**モデル選択戦略:**

- 司令塔は常に Opus 4.6（品質を最優先）
- 作業者のモデルは、タスクの性質に応じて動的に選択可能
  - テスト生成 → Sonnet 4.6（テスト設計のバランス感覚）
  - コード実装 → Codex 5.3（高速なコード生成）
  - ドキュメント → Sonnet 4.6（自然言語品質）

### 6.2 品質ゲートループ

```text
commander.review(worker_results)
    │
    ├─ score >= threshold → PASS → 次工程へ
    │
    └─ score < threshold → FAIL
         │
         ├─ iteration < max_iterations → 再指示（フィードバック付き）
         │
         └─ iteration >= max_iterations → 部分成功 or 人間にエスカレーション
```

**品質スコアの構成要素（案）:**

- コード品質（lint / 型チェック通過率）: 30%
- テスト通過率: 30%
- 要件充足度（司令塔の主観評価）: 25%
- コード統合性（ファイル間の整合性）: 15%

### 6.3 ワーカー数の可変制御

```python
# 動的ワーカー数決定
def determine_worker_count(
    subtasks: list[WorkerTask],
    config: ParallelExecutionConfig,
) -> int:
    """サブタスク数と設定に基づきワーカー数を決定する。"""
    desired = len(subtasks)
    return max(config.min_workers, min(desired, config.max_workers))
```

- **最小値:** 3（並列化の効果が出る最小数）
- **最大値:** 10（API レート制限とコスト制約）
- **デフォルト:** 5（コストと速度のバランス）
- **決定ロジック:** サブタスク数に応じて自動調整（min/max でクリップ）

### 6.4 長時間実行の許容設計

- ワーカーごとのタイムアウト: 設定可能（デフォルト 600 秒）
- パイプライン全体のタイムアウト: 設定可能（デフォルト 3600 秒）
- 中間結果の保存: 各イテレーション後に結果を永続化
- 進捗報告: 定期的なステータス更新

### 6.5 タスク分解戦略（ML 特徴量エンジニアリングの例）

```text
入力: 「市場予測のための ML 特徴量エンジニアリングを実装する」

司令塔の分解結果（例）:
  ├── Worker 1: 価格ベースの特徴量（移動平均、ボリンジャーバンド等）
  ├── Worker 2: 出来高ベースの特徴量（VWAP、OBV 等）
  ├── Worker 3: テクニカル指標（RSI、MACD 等）
  ├── Worker 4: 統計的特徴量（リターン分布、自己相関等）
  └── Worker 5: 特徴量選択・前処理パイプライン

各ワーカーは独立したモジュールとして実装するため、
ファイル競合のリスクが低い。
```

## 7. 技術的リスクと対策

| リスク | 影響度 | 対策 |
|---|---|---|
| ワーカー間のファイル競合 | 高 | タスク分解時にファイル排他を考慮。独立モジュールへの分割を司令塔が保証 |
| コンテキスト不足による品質低下 | 中 | 共有コンテキスト（ディレクトリ構造、既存コード）をワーカーに事前配布 |
| API レート制限 | 中 | asyncio.Semaphore でワーカー数を制限。バックオフ戦略 |
| 品質ゲートの無限ループ | 低 | max_iterations で制限。閾値の適切な設定 |
| LangGraph API の破壊的変更 | 低 | バージョン固定 + A1（asyncio）をフォールバックとして維持 |

## 8. 次のステップ

1. **N-002（本タスク）**: PoC で Fan-Out/Fan-In + 品質ゲートパターンを検証する
2. **N-003**: LangGraph で本格実装を行い、モック → 実 LLM 呼び出しに段階的に移行する
3. **ベンチマーク**: 逐次実行 vs 並列実行の品質・時間・コスト比較を実施する
4. **フィードバック**: 成果を dev-orchestration-template に反映する

## 参考情報

- [LangGraph Send API ドキュメント](https://langchain-ai.github.io/langgraph/)
- [LiteLLM モデルプロバイダー](https://docs.litellm.ai/)
- [A2A プロトコル仕様](https://github.com/google/A2A)
- [RQ-1〜RQ-3 研究課題](./README.md)
