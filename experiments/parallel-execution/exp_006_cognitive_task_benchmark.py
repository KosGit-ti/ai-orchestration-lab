"""実験 006: 思考的タスクでの逐次実行 vs 並列実行のベンチマーク比較。

N-003 では実装タスク（コーディング）で逐次 vs 並列を比較した。
本実験では**思考的タスク**（課題分析・解決策考案・トレードオフ評価など）での
比較を行い、タスク特性による並列実行の適用パターンを明らかにする。

逐次実行の特性:
    - 前のエージェントの観点を参照できる（文脈の連続性）
    - 深掘りやすい → depth（深さ）が増す傾向
    - 前の観点に引きずられる → diversity（多様性）が落ちる傾向

並列実行の特性:
    - 各エージェントが独立して分析（文脈なし）
    - 多様な視点が生まれる → diversity（多様性）が高い傾向
    - それぞれの深さは浅い → depth は逐次より低い傾向
    - 複数の方向から分析 → coverage（網羅性）が高い傾向

比較指標:
    - diversity (多様性): ユニークカテゴリ数 / 総観点数
    - depth (深さ): 観点あたりの詳細項目数の平均
    - coverage (網羅性): 期待キーワードのカバー率
    - actionability (実用性): 実装可能フラグの割合
    - composite_score: 4 指標の加重平均（各 0.25）
    - duration (実行時間): Wall-clock 時間

実行方法:
    python experiments/parallel-execution/exp_006_cognitive_task_benchmark.py

注意:
    モック応答で動作を検証する。外部 LLM API は使用しない。
    乱数シードにより再現性を確保している。
"""

from __future__ import annotations

import operator
import random
import statistics
import time
import warnings
from dataclasses import dataclass, field
from typing import Annotated, Any, NotRequired, TypedDict

from langgraph.graph import END
from langgraph.graph.state import StateGraph
from langgraph.types import Send

# ============================================================
# 定数
# ============================================================

#: タスク種別の一覧
TASK_TYPES: list[str] = [
    "issue_analysis",  # 課題分析
    "solution_design",  # 解決策考案
    "tradeoff",  # トレードオフ分析
    "architecture",  # アーキテクチャ設計
    "risk_assessment",  # リスク評価
]

#: タスク種別ごとの期待キーワード（網羅性チェック用）
EXPECTED_KEYWORDS: dict[str, list[str]] = {
    "issue_analysis": [
        "パフォーマンス",
        "スケーラビリティ",
        "保守性",
        "セキュリティ",
        "テスト容易性",
    ],
    "solution_design": [
        "キャッシュ",
        "非同期",
        "バッチ処理",
        "インデックス",
        "水平スケール",
    ],
    "tradeoff": [
        "コスト",
        "複雑性",
        "速度",
        "信頼性",
        "開発工数",
    ],
    "architecture": [
        "レイヤー",
        "依存関係",
        "コンポーネント",
        "インターフェース",
        "データフロー",
    ],
    "risk_assessment": [
        "障害",
        "セキュリティリスク",
        "依存リスク",
        "コスト超過",
        "スケジュール遅延",
    ],
}

#: カテゴリプール（多様性を測定するための観点カテゴリ候補）
CATEGORY_POOL: dict[str, list[str]] = {
    "issue_analysis": [
        "性能",
        "保守性",
        "セキュリティ",
        "可用性",
        "UX",
        "コスト",
        "拡張性",
        "テスト",
    ],
    "solution_design": [
        "キャッシュ",
        "非同期化",
        "分散処理",
        "インデックス",
        "CDN",
        "負荷分散",
        "圧縮",
        "プリフェッチ",
    ],
    "tradeoff": [
        "一貫性",
        "可用性",
        "分断耐性",
        "レイテンシ",
        "スループット",
        "コスト",
        "複雑性",
        "移行コスト",
    ],
    "architecture": [
        "マイクロサービス",
        "モノリス",
        "イベント駆動",
        "CQRS",
        "レイヤード",
        "ヘキサゴナル",
        "パイプライン",
        "プラグイン",
    ],
    "risk_assessment": [
        "技術的負債",
        "ベンダーロックイン",
        "セキュリティ脆弱性",
        "スケール限界",
        "データ損失",
        "人的リスク",
        "規制リスク",
        "コスト超過",
    ],
}

#: エージェントが使用するモデル名一覧（モック用）
AGENT_MODELS: list[str] = [
    "claude-sonnet-4-20250514",
    "codex-5.3",
    "gemini-2.0-pro",
    "gpt-5-mini",
    "claude-haiku-4",
]

NUM_AGENTS: int = 5  # エージェント数
BENCHMARK_RUNS: int = 10  # ベンチマーク実行回数
SEED_BASE: int = 200  # ベンチマーク用乱数シードの基準値


# ============================================================
# データ型定義
# ============================================================


@dataclass
class CognitiveTask:
    """思考的タスクの定義。"""

    task_id: str
    task_type: str
    description: str
    context: str
    expected_keywords: list[str] = field(default_factory=list)


@dataclass
class CognitivePerspective:
    """エージェントが生成した一つの観点（Perspective）。"""

    perspective_id: str
    agent_id: str
    model_used: str
    category: str
    content: str
    detail_items: list[str]
    is_actionable: bool
    references_previous: bool
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class CognitiveEvalResult:
    """思考的タスクの評価結果（4指標）。"""

    diversity: float  # ユニークカテゴリ数 / 総観点数
    depth: float  # 観点あたり詳細項目数の平均
    coverage: float  # 期待キーワードのカバー率
    actionability: float  # 実装可能観点の割合
    composite_score: float  # 4 指標の加重平均


# ============================================================
# LangGraph 状態定義
# ============================================================


class CognitivePipelineState(TypedDict):
    """思考的タスク並列パイプラインのグラフ状態。

    perspectives は Annotated + operator.add で各エージェントの
    結果を自動的にリストに集約する（Fan-In）。

    agent_id / model は Send API でエージェントへの Fan-Out 時に
    ワーカーステートとして使用する（coordinator と agent_node 間のみ）。
    """

    task: CognitiveTask
    perspectives: Annotated[list[CognitivePerspective], operator.add]
    eval_result: NotRequired[CognitiveEvalResult]
    # Fan-Out 時にワーカー状態として使用するフィールド
    agent_id: NotRequired[str]
    model: NotRequired[str]


# ============================================================
# タスク生成
# ============================================================


def make_task(task_type: str) -> CognitiveTask:
    """タスク種別に応じたベンチマーク用思考的タスクを生成する。

    Args:
        task_type: タスク種別。TASK_TYPES のいずれかを指定する。

    Returns:
        CognitiveTask インスタンス。
    """
    descriptions: dict[str, str] = {
        "issue_analysis": (
            "大規模 EC サイトの検索パフォーマンス低下問題を分析し、原因と改善点を特定する"
        ),
        "solution_design": ("検索 API のレイテンシ削減に向けた改善策を設計する"),
        "tradeoff": (
            "全文検索エンジン（Elasticsearch）導入 vs DB インデックス最適化のトレードオフを評価する"
        ),
        "architecture": ("スケーラブルな検索基盤のアーキテクチャを設計する"),
        "risk_assessment": ("検索システムリプレースプロジェクトのリスクを評価する"),
    }
    contexts: dict[str, str] = {
        "issue_analysis": (
            "月間1000万 PV、検索 API の P99 レイテンシが 5000ms を超過。DB クエリが複雑化している。"
        ),
        "solution_design": (
            "現在は PostgreSQL の LIKE クエリ。インデックスは部分適用。"
            "読み取り負荷が書き込み負荷の10倍。"
        ),
        "tradeoff": (
            "Elasticsearch 導入コスト：インフラ月額20万円、初期構築3ヶ月。"
            "DB 最適化コスト：エンジニア2名・2週間。"
        ),
        "architecture": (
            "現在はモノリシックなバックエンド。将来的にはマイクロサービス化を検討中。"
        ),
        "risk_assessment": (
            "現行 DB は PostgreSQL 14。Elasticsearch は社内に知見なし。移行データ量は 5 億件。"
        ),
    }
    return CognitiveTask(
        task_id=f"task-{task_type}-001",
        task_type=task_type,
        description=descriptions.get(task_type, descriptions["issue_analysis"]),
        context=contexts.get(task_type, contexts["issue_analysis"]),
        expected_keywords=EXPECTED_KEYWORDS.get(task_type, EXPECTED_KEYWORDS["issue_analysis"]),
    )


# ============================================================
# 評価指標計算
# ============================================================


def compute_diversity(perspectives: list[CognitivePerspective]) -> float:
    """多様性を算出する。ユニークカテゴリ数 / 総観点数。

    Args:
        perspectives: 観点のリスト。

    Returns:
        0.0〜1.0 の多様性スコア。
    """
    if not perspectives:
        return 0.0
    categories = {p.category for p in perspectives}
    return len(categories) / len(perspectives)


def compute_depth(perspectives: list[CognitivePerspective]) -> float:
    """深さを算出する。観点あたりの詳細項目数の平均。

    Args:
        perspectives: 観点のリスト。

    Returns:
        0 以上の深さスコア（詳細項目数の平均）。
    """
    if not perspectives:
        return 0.0
    return sum(len(p.detail_items) for p in perspectives) / len(perspectives)


def compute_coverage(
    perspectives: list[CognitivePerspective], expected_keywords: list[str]
) -> float:
    """網羅性を算出する。期待キーワードのカバー率。

    Args:
        perspectives: 観点のリスト。
        expected_keywords: 期待されるキーワードの一覧。

    Returns:
        0.0〜1.0 の網羅性スコア。
    """
    if not expected_keywords or not perspectives:
        return 0.0
    all_content = " ".join(p.content + " " + " ".join(p.detail_items) for p in perspectives).lower()
    covered = sum(1 for kw in expected_keywords if kw.lower() in all_content)
    return covered / len(expected_keywords)


def compute_actionability(perspectives: list[CognitivePerspective]) -> float:
    """実用性を算出する。実装可能フラグを持つ観点の割合。

    Args:
        perspectives: 観点のリスト。

    Returns:
        0.0〜1.0 の実用性スコア。
    """
    if not perspectives:
        return 0.0
    return sum(1 for p in perspectives if p.is_actionable) / len(perspectives)


def compute_composite(
    diversity: float,
    depth_score: float,
    coverage: float,
    actionability: float,
) -> float:
    """4 指標の加重平均でコンポジットスコアを算出する。

    深さは最大 6 detail_items を 1.0 として正規化する。

    Args:
        diversity: 多様性スコア（0.0〜1.0）。
        depth_score: 深さスコア（観点あたり詳細項目数）。
        coverage: 網羅性スコア（0.0〜1.0）。
        actionability: 実用性スコア（0.0〜1.0）。

    Returns:
        0.0〜1.0 のコンポジットスコア。
    """
    normalized_depth = min(depth_score / 6.0, 1.0)
    return (diversity + normalized_depth + coverage + actionability) / 4.0


# ============================================================
# モック関数
# ============================================================


def mock_analyze_sequential(
    task: CognitiveTask,
    agent_id: str,
    model: str,
    previous_perspectives: list[CognitivePerspective],
) -> CognitivePerspective:
    """逐次実行でエージェントが観点を生成する（モック）。

    前の観点を参照できる（文脈の連続性）。
    - 前の観点のカテゴリと被りやすい（多様性低下）
    - 前の観点が多いほど detail_items が増加（深さ増加）

    Args:
        task: 実行する思考的タスク。
        agent_id: エージェント識別子。
        model: 使用モデル名。
        previous_perspectives: 前のエージェントが生成した観点のリスト。

    Returns:
        CognitivePerspective インスタンス。
    """
    start = time.time()
    time.sleep(random.uniform(0.01, 0.05))

    task_type = task.task_type
    categories = CATEGORY_POOL.get(task_type, CATEGORY_POOL["issue_analysis"])
    keyword_pool = EXPECTED_KEYWORDS.get(task_type, [])

    # 逐次の特性: 前の観点のカテゴリと被りやすい（確率70%で既存カテゴリから選ぶ）
    used_categories = [p.category for p in previous_perspectives]
    if used_categories and random.random() < 0.70:
        category = random.choice(used_categories)
    else:
        category = random.choice(categories)

    # 逐次の特性: 前の観点が多いほど detail_items が増加（深さ増加）
    base_detail_count = 2
    depth_bonus = min(len(previous_perspectives), 4)
    detail_count = base_detail_count + depth_bonus + random.randint(0, 2)

    detail_items = [
        (
            f"{category}観点の詳細{i + 1}: "
            f"{random.choice(keyword_pool) if keyword_pool else '詳細事項'}に関する考察"
        )
        for i in range(detail_count)
    ]

    # 前の観点を参照した場合はアクション可能性がやや高い
    is_actionable = random.random() < (0.55 + 0.05 * len(previous_perspectives))

    content = f"{task.description}について、{category}の観点から分析。"
    if previous_perspectives:
        content += f"（前{len(previous_perspectives)}観点を踏まえた深掘り考察）"

    duration = time.time() - start
    tokens = 200 + len(detail_items) * 30 + len(previous_perspectives) * 20

    return CognitivePerspective(
        perspective_id=f"{agent_id}-perspective",
        agent_id=agent_id,
        model_used=model,
        category=category,
        content=content,
        detail_items=detail_items,
        is_actionable=is_actionable,
        references_previous=bool(previous_perspectives),
        duration_seconds=round(duration, 3),
        input_tokens=tokens,
        output_tokens=tokens // 2,
    )


def mock_analyze_parallel(
    task: CognitiveTask,
    agent_id: str,
    model: str,
) -> CognitivePerspective:
    """並列実行でエージェントが観点を生成する（モック）。

    前の観点を参照しない（独立分析）。
    - カテゴリをランダムに選択（多様性高）
    - detail_items は短め（深さ低）

    Args:
        task: 実行する思考的タスク。
        agent_id: エージェント識別子。
        model: 使用モデル名。

    Returns:
        CognitivePerspective インスタンス。
    """
    start = time.time()
    time.sleep(random.uniform(0.005, 0.02))  # 並列では各エージェントが短時間実行

    task_type = task.task_type
    categories = CATEGORY_POOL.get(task_type, CATEGORY_POOL["issue_analysis"])
    keyword_pool = EXPECTED_KEYWORDS.get(task_type, [])

    # 並列の特性: 独立してカテゴリを選択（多様性高）
    category = random.choice(categories)

    # 並列の特性: detail_items は短め（深さ低）
    detail_count = random.randint(1, 4)

    detail_items = [
        (
            f"{category}観点の詳細{i + 1}: "
            f"{random.choice(keyword_pool) if keyword_pool else '詳細事項'}に関する独立分析"
        )
        for i in range(detail_count)
    ]

    is_actionable = random.random() < 0.60

    content = f"{task.description}について、{category}の観点から独立分析。"

    duration = time.time() - start
    tokens = 150 + len(detail_items) * 25

    return CognitivePerspective(
        perspective_id=f"{agent_id}-perspective",
        agent_id=agent_id,
        model_used=model,
        category=category,
        content=content,
        detail_items=detail_items,
        is_actionable=is_actionable,
        references_previous=False,
        duration_seconds=round(duration, 3),
        input_tokens=tokens,
        output_tokens=tokens // 2,
    )


# ============================================================
# 逐次実行パイプライン
# ============================================================


def run_sequential_cognitive_pipeline(
    task: CognitiveTask,
    num_agents: int = NUM_AGENTS,
    seed: int = 42,
) -> dict[str, Any]:
    """思考的タスクの逐次実行パイプライン。

    各エージェントが前のエージェントの観点を参照しながら順番に分析する。

    Args:
        task: 実行する思考的タスク。
        num_agents: エージェント数。
        seed: 乱数シード（再現性確保）。

    Returns:
        diversity / depth / coverage / actionability / composite_score 等を含む結果辞書。
    """
    random.seed(seed)
    start_time = time.time()

    perspectives: list[CognitivePerspective] = []

    for i in range(num_agents):
        agent_id = f"seq-agent-{i + 1}"
        model = AGENT_MODELS[i % len(AGENT_MODELS)]
        p = mock_analyze_sequential(task, agent_id, model, perspectives)
        perspectives.append(p)

    total_duration = time.time() - start_time

    diversity = compute_diversity(perspectives)
    depth = compute_depth(perspectives)
    coverage = compute_coverage(perspectives, task.expected_keywords)
    actionability = compute_actionability(perspectives)
    composite = compute_composite(diversity, depth, coverage, actionability)

    total_input = sum(p.input_tokens for p in perspectives)
    total_output = sum(p.output_tokens for p in perspectives)

    return {
        "mode": "sequential",
        "task_id": task.task_id,
        "task_type": task.task_type,
        "perspectives": perspectives,
        "num_perspectives": len(perspectives),
        "diversity": diversity,
        "depth": depth,
        "coverage": coverage,
        "actionability": actionability,
        "composite_score": composite,
        "duration_seconds": total_duration,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
    }


# ============================================================
# 並列実行パイプライン（LangGraph Fan-Out/Fan-In）
# ============================================================


def fanout_to_agents(state: CognitivePipelineState) -> list[Send]:
    """コーディネーター → エージェントへの Fan-Out を Send API で実行する。

    Args:
        state: パイプライン状態（task を含む）。

    Returns:
        各エージェントへの Send リスト。
    """
    sends: list[Send] = []
    for i in range(NUM_AGENTS):
        agent_id = f"par-agent-{i + 1}"
        model = AGENT_MODELS[i % len(AGENT_MODELS)]
        worker_state: CognitivePipelineState = {
            "task": state["task"],
            "perspectives": [],
            "agent_id": agent_id,
            "model": model,
        }
        sends.append(Send("agent_node", worker_state))
    return sends


def agent_node(state: CognitivePipelineState) -> dict[str, Any]:
    """個々のエージェントが独立して観点を生成するノード。

    Args:
        state: エージェントワーカー状態（task / agent_id / model を含む）。

    Returns:
        perspectives に生成した観点を1件追加した辞書。
    """
    task = state["task"]
    agent_id = state.get("agent_id", "par-agent-unknown")
    model = state.get("model", AGENT_MODELS[0])
    p = mock_analyze_parallel(task, agent_id, model)
    return {"perspectives": [p]}


def evaluator_node(state: CognitivePipelineState) -> dict[str, Any]:
    """集約された観点を4指標で評価するノード。

    Args:
        state: 全エージェントの観点が集約されたパイプライン状態。

    Returns:
        eval_result を含む辞書。
    """
    perspectives = state["perspectives"]
    task = state["task"]

    diversity = compute_diversity(perspectives)
    depth = compute_depth(perspectives)
    coverage = compute_coverage(perspectives, task.expected_keywords)
    actionability = compute_actionability(perspectives)
    composite = compute_composite(diversity, depth, coverage, actionability)

    return {
        "eval_result": CognitiveEvalResult(
            diversity=diversity,
            depth=depth,
            coverage=coverage,
            actionability=actionability,
            composite_score=composite,
        )
    }


def build_cognitive_graph() -> Any:
    """思考的タスク用の LangGraph Fan-Out/Fan-In グラフを構築する。

    構造:
        coordinator → Send(agent_node) × N → evaluator → END

    Returns:
        コンパイル済み LangGraph アプリケーション。
    """
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        graph = StateGraph(CognitivePipelineState)

        # ノード登録（coordinator は条件付きエッジで Fan-Out するため、
        # ノードして登録せずエントリポイント直後の条件分岐として扱う）
        graph.add_node("agent_node", agent_node)
        graph.add_node("evaluator", evaluator_node)

        # エントリポイントからダイレクトに Fan-Out
        graph.set_entry_point("coordinator_fanout")
        graph.add_node(
            "coordinator_fanout",
            lambda state: {},  # 状態変更なし。Fan-Out は条件付きエッジで実施
        )
        graph.add_conditional_edges("coordinator_fanout", fanout_to_agents, ["agent_node"])
        graph.add_edge("agent_node", "evaluator")
        graph.add_edge("evaluator", END)

        return graph.compile()


def run_parallel_cognitive_pipeline(
    task: CognitiveTask,
    seed: int = 42,
) -> dict[str, Any]:
    """思考的タスクの並列実行パイプライン（LangGraph Fan-Out/Fan-In）。

    Args:
        task: 実行する思考的タスク。
        seed: 乱数シード（再現性確保）。

    Returns:
        diversity / depth / coverage / actionability / composite_score 等を含む結果辞書。
    """
    random.seed(seed)
    app = build_cognitive_graph()

    start_time = time.time()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore")
        final_state = app.invoke({"task": task, "perspectives": []})
    total_duration = time.time() - start_time

    perspectives: list[CognitivePerspective] = final_state["perspectives"]
    eval_result: CognitiveEvalResult = final_state["eval_result"]

    total_input = sum(p.input_tokens for p in perspectives)
    total_output = sum(p.output_tokens for p in perspectives)

    return {
        "mode": "parallel",
        "task_id": task.task_id,
        "task_type": task.task_type,
        "perspectives": perspectives,
        "num_perspectives": len(perspectives),
        "diversity": eval_result.diversity,
        "depth": eval_result.depth,
        "coverage": eval_result.coverage,
        "actionability": eval_result.actionability,
        "composite_score": eval_result.composite_score,
        "duration_seconds": total_duration,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
    }


# ============================================================
# ベンチマーク実行
# ============================================================


def run_benchmark(task_type: str = "issue_analysis") -> dict[str, Any]:
    """指定タスク種別のベンチマークを実行し、逐次 vs 並列の比較結果を返す。

    Args:
        task_type: ベンチマークするタスク種別。TASK_TYPES のいずれかを指定する。

    Returns:
        sequential / parallel の各指標統計を含む辞書。
    """
    task = make_task(task_type)
    seq_results: list[dict[str, Any]] = []
    par_results: list[dict[str, Any]] = []

    for i in range(BENCHMARK_RUNS):
        seed = SEED_BASE + i
        seq_results.append(run_sequential_cognitive_pipeline(task, seed=seed))
        par_results.append(run_parallel_cognitive_pipeline(task, seed=seed))

    def stats(values: list[float]) -> dict[str, float]:
        """基本統計を算出する。"""
        return {
            "mean": statistics.mean(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
        }

    return {
        "task_type": task_type,
        "runs": BENCHMARK_RUNS,
        "sequential": {
            "duration": stats([r["duration_seconds"] for r in seq_results]),
            "diversity": stats([r["diversity"] for r in seq_results]),
            "depth": stats([r["depth"] for r in seq_results]),
            "coverage": stats([r["coverage"] for r in seq_results]),
            "actionability": stats([r["actionability"] for r in seq_results]),
            "composite": stats([r["composite_score"] for r in seq_results]),
            "tokens": stats([r["total_tokens"] for r in seq_results]),
        },
        "parallel": {
            "duration": stats([r["duration_seconds"] for r in par_results]),
            "diversity": stats([r["diversity"] for r in par_results]),
            "depth": stats([r["depth"] for r in par_results]),
            "coverage": stats([r["coverage"] for r in par_results]),
            "actionability": stats([r["actionability"] for r in par_results]),
            "composite": stats([r["composite_score"] for r in par_results]),
            "tokens": stats([r["total_tokens"] for r in par_results]),
        },
    }


def print_benchmark_report(result: dict[str, Any]) -> None:
    """ベンチマーク結果をコンソールに表示する。

    Args:
        result: run_benchmark が返した辞書。
    """
    task_type = result["task_type"]
    seq = result["sequential"]
    par = result["parallel"]

    print(f"\n{'=' * 70}")
    print(f"思考的タスクベンチマーク: {task_type}（{result['runs']}回実行）")
    print(f"{'=' * 70}")

    rows: list[tuple[str, str, str]] = [
        ("実行時間 (s)", "duration", ".3f"),
        ("多様性", "diversity", ".3f"),
        ("深さ (detail/観点)", "depth", ".2f"),
        ("網羅性", "coverage", ".3f"),
        ("実用性", "actionability", ".3f"),
        ("コンポジット", "composite", ".3f"),
        ("トークン数", "tokens", ".0f"),
    ]

    print(f"{'指標':<24} {'逐次 (mean±σ)':<24} {'並列 (mean±σ)':<24} {'差分'}")
    print("-" * 90)

    for label, key, fmt in rows:
        s = seq[key]
        p = par[key]
        s_str = f"{s['mean']:{fmt}} ± {s['stdev']:{fmt}}"
        p_str = f"{p['mean']:{fmt}} ± {p['stdev']:{fmt}}"
        diff = p["mean"] - s["mean"]
        diff_pct = (diff / s["mean"] * 100) if s["mean"] != 0 else 0.0
        sign = "+" if diff >= 0 else ""
        print(f"{label:<24} {s_str:<24} {p_str:<24} {sign}{diff_pct:.1f}%")

    print(f"\n並列実行の特性評価（タスク種別: {task_type}）:")
    par_div_win = par["diversity"]["mean"] > seq["diversity"]["mean"]
    seq_dep_win = seq["depth"]["mean"] > par["depth"]["mean"]
    par_cov_win = par["coverage"]["mean"] >= seq["coverage"]["mean"]
    comp_diff_pct = (
        (par["composite"]["mean"] - seq["composite"]["mean"]) / seq["composite"]["mean"] * 100
        if seq["composite"]["mean"]
        else 0.0
    )
    sign = "+" if comp_diff_pct >= 0 else ""
    print(f"  多様性:         {'並列優位 ✓' if par_div_win else '逐次優位 ✓'}")
    print(f"  深さ:           {'逐次優位 ✓' if seq_dep_win else '並列優位 ✓'}")
    print(f"  網羅性:         {'並列優位 ✓' if par_cov_win else '逐次優位 ✓'}")
    print(f"  コンポジット差: {sign}{comp_diff_pct:.1f}%")


# ============================================================
# エントリポイント
# ============================================================


if __name__ == "__main__":
    print("=" * 70)
    print("実験 006: 思考的タスクでの逐次実行 vs 並列実行ベンチマーク")
    print("（モック LLM 環境）")
    print("=" * 70)

    all_results: dict[str, Any] = {}
    for task_type in TASK_TYPES:
        result = run_benchmark(task_type)
        all_results[task_type] = result
        print_benchmark_report(result)

    print(f"\n{'=' * 70}")
    print("全タスク種別サマリー")
    print(f"{'=' * 70}")
    print(f"{'タスク種別':<24} {'逐次コンポジット':<18} {'並列コンポジット':<18} {'差分'}")
    print("-" * 72)
    for task_type, result in all_results.items():
        s_mean = result["sequential"]["composite"]["mean"]
        p_mean = result["parallel"]["composite"]["mean"]
        diff_pct = (p_mean - s_mean) / s_mean * 100 if s_mean else 0.0
        sign = "+" if diff_pct >= 0 else ""
        print(f"{task_type:<24} {s_mean:<18.3f} {p_mean:<18.3f} {sign}{diff_pct:.1f}%")
