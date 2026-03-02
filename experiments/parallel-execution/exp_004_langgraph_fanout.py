"""実験 004: LangGraph による Fan-Out/Fan-In パターンの実装。

ADR-0001 の決定に基づき、LangGraph の Send API を用いた
Fan-Out/Fan-In 型並列実行パターンのプロトタイプを実装する。

司令塔（Commander）がタスクを分解し、Send API で複数ワーカーに
Fan-Out。ワーカー結果を集約後、品質ゲートで判定する。
不合格の場合は再指示ループを実行する。

アーキテクチャ:
    Commander → Send(Worker) × N → Aggregator → QualityGate
                                                    ↓ (不合格)
                                              Send(Worker) × M（再指示）

実行方法:
    python experiments/parallel-execution/exp_004_langgraph_fanout.py

注意:
    モック応答で動作を検証する。外部 LLM API は使用しない。
    Python 3.14 では langchain_core の Pydantic v1 互換警告が出るが動作に影響なし。
"""

from __future__ import annotations

import operator
import random
import time
import warnings
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import END
from langgraph.graph.state import StateGraph
from langgraph.types import Send

# Pydantic v1 互換警告を抑制（Python 3.14 環境）
warnings.filterwarnings("ignore", message="Core Pydantic V1")


# ============================================================
# 型定義（実験用ローカル型）
# ============================================================


@dataclass
class SubTask:
    """サブタスク定義。"""

    task_id: str
    description: str
    assigned_model: str
    context: str = ""
    retry_feedback: str = ""


@dataclass
class WorkerOutput:
    """ワーカー実行結果。"""

    task_id: str
    worker_id: str
    model_used: str
    success: bool
    output: str
    quality_score: float
    duration_seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class QualityGateResult:
    """品質ゲート結果。"""

    passed: bool
    overall_score: float
    task_feedback: dict[str, str] = field(default_factory=dict)
    failed_task_ids: list[str] = field(default_factory=list)


# ============================================================
# LangGraph 状態定義
# ============================================================


class PipelineState(TypedDict):
    """Fan-Out/Fan-In パイプラインのグラフ状態。

    worker_results は Annotated + operator.add で
    各ワーカーノードからの結果を自動的にリストに集約する。
    """

    task_description: str
    subtasks: list[SubTask]
    worker_results: Annotated[list[WorkerOutput], operator.add]
    quality_result: QualityGateResult | None
    iteration: int
    max_iterations: int
    quality_threshold: float


# ============================================================
# 設定
# ============================================================

COMMANDER_MODEL = "claude-opus-4-20250514"
WORKER_MODELS = ["claude-sonnet-4-20250514", "codex-5.3"]
MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.80


# ============================================================
# モック関数
# ============================================================


def mock_decompose(task_description: str) -> list[SubTask]:
    """司令塔がタスクを分解する（モック）。"""
    definitions = [
        ("feat-price", "価格ベースの特徴量を実装する（移動平均、ボリンジャーバンド）"),
        ("feat-volume", "出来高ベースの特徴量を実装する（出来高MA、VWAP）"),
        ("feat-momentum", "モメンタム系の特徴量を実装する（RSI、MACD）"),
        ("feat-volatility", "ボラティリティ特徴量を実装する（ATR、HV）"),
        ("feat-cross", "クロスセクション特徴量を実装する（セクター乖離率）"),
    ]
    subtasks: list[SubTask] = []
    for i, (tid, desc) in enumerate(definitions):
        subtasks.append(
            SubTask(
                task_id=tid,
                description=desc,
                assigned_model=WORKER_MODELS[i % len(WORKER_MODELS)],
                context=f"src/features/{tid.split('-')[1]}.py に実装",
            )
        )
    return subtasks


def mock_execute(subtask: SubTask, worker_id: str) -> WorkerOutput:
    """ワーカーがサブタスクを実行する（モック）。

    再指示フィードバックがある場合は品質スコアが向上する。
    """
    duration = random.uniform(0.01, 0.05)
    time.sleep(duration)

    base_score = random.uniform(0.65, 0.95)
    if subtask.retry_feedback:
        base_score = min(1.0, base_score + random.uniform(0.05, 0.15))

    return WorkerOutput(
        task_id=subtask.task_id,
        worker_id=worker_id,
        model_used=subtask.assigned_model,
        success=base_score > 0.5,
        output=f"# {subtask.description}\nclass Feature:\n    pass",
        quality_score=round(base_score, 3),
        duration_seconds=round(duration, 3),
        input_tokens=random.randint(500, 2000),
        output_tokens=random.randint(200, 1500),
    )


def mock_quality_check(results: list[WorkerOutput], threshold: float) -> QualityGateResult:
    """品質ゲート判定（モック）。"""
    scores = [r.quality_score for r in results]
    overall = sum(scores) / len(scores) if scores else 0.0

    failed: list[str] = []
    feedback: dict[str, str] = {}
    for r in results:
        if r.quality_score < threshold:
            failed.append(r.task_id)
            feedback[r.task_id] = f"品質 {r.quality_score:.3f} < 閾値 {threshold}。改善を求む。"

    return QualityGateResult(
        passed=len(failed) == 0,
        overall_score=round(overall, 3),
        task_feedback=feedback,
        failed_task_ids=failed,
    )


# ============================================================
# LangGraph ノード
# ============================================================


def commander_node(state: PipelineState) -> dict[str, Any]:
    """司令塔ノード: タスクを分解する。"""
    subtasks = mock_decompose(state["task_description"])
    print(f"  [Commander] タスクを {len(subtasks)} 個のサブタスクに分解")
    return {"subtasks": subtasks, "iteration": 1}


def worker_node(state: PipelineState) -> dict[str, Any]:
    """ワーカーノード: 個別サブタスクを実行する。

    Send API により、state["subtasks"] にはこのワーカー用の
    1個のサブタスクのみが入っている。
    """
    subtask = state["subtasks"][0]
    worker_id = f"worker-{subtask.task_id}"
    result = mock_execute(subtask, worker_id)
    retry_mark = " (再実行)" if subtask.retry_feedback else ""
    print(f"  [Worker] {subtask.task_id:20s} → score={result.quality_score:.3f}{retry_mark}")
    return {"worker_results": [result]}


def quality_gate_node(state: PipelineState) -> dict[str, Any]:
    """品質ゲートノード: ワーカー結果を評価する。

    operator.add による累積結果から、各 task_id の最新結果のみを評価する。
    """
    all_results = state["worker_results"]
    threshold = state.get("quality_threshold", QUALITY_THRESHOLD)
    iteration = state.get("iteration", 1)

    # 重複排除: 各 task_id の最新（最後）の結果を採用
    seen: dict[str, WorkerOutput] = {}
    for r in all_results:
        seen[r.task_id] = r
    latest_results = list(seen.values())

    quality = mock_quality_check(latest_results, threshold)

    status = "PASS" if quality.passed else "FAIL"
    print(
        f"  [QualityGate] iter={iteration} score={quality.overall_score:.3f} "
        f"→ {status} (failed={len(quality.failed_task_ids)})"
    )

    return {
        "quality_result": quality,
        "iteration": iteration,
    }


def prepare_retry_node(state: PipelineState) -> dict[str, Any]:
    """再指示準備ノード: 不合格タスクにフィードバックを付与する。"""
    quality = state["quality_result"]
    if quality is None:
        return {"subtasks": [], "iteration": state.get("iteration", 1) + 1}

    original_subtasks = state["subtasks"]
    failed_ids = set(quality.failed_task_ids)

    retry_subtasks: list[SubTask] = []
    for st in original_subtasks:
        if st.task_id in failed_ids:
            fb = quality.task_feedback.get(st.task_id, "品質改善を求む")
            retry_subtasks.append(
                SubTask(
                    task_id=st.task_id,
                    description=st.description,
                    assigned_model=st.assigned_model,
                    context=st.context,
                    retry_feedback=fb,
                )
            )

    new_iter = state.get("iteration", 1) + 1
    print(f"  [Retry] {len(retry_subtasks)} タスクを再指示 (iter→{new_iter})")
    return {
        "subtasks": retry_subtasks,
        "iteration": new_iter,
    }


# ============================================================
# 条件分岐（ルーティング）
# ============================================================


def fanout_to_workers(state: PipelineState) -> list[Send]:
    """Commander/Retry → Worker への Fan-Out を Send API で実行する。"""
    sends: list[Send] = []
    for subtask in state["subtasks"]:
        worker_state: PipelineState = {
            "task_description": state["task_description"],
            "subtasks": [subtask],
            "worker_results": [],
            "quality_result": None,
            "iteration": state.get("iteration", 0),
            "max_iterations": state.get("max_iterations", MAX_ITERATIONS),
            "quality_threshold": state.get("quality_threshold", QUALITY_THRESHOLD),
        }
        sends.append(Send("worker", worker_state))
    return sends


def route_after_quality(state: PipelineState) -> str:
    """品質ゲート後のルーティング。"""
    quality = state.get("quality_result")
    iteration = state.get("iteration", 0)
    max_iter = state.get("max_iterations", MAX_ITERATIONS)

    if quality is None or quality.passed:
        return END

    if iteration >= max_iter:
        print(f"  [QualityGate] 最大イテレーション {max_iter} に到達。終了。")
        return END

    return "prepare_retry"


# ============================================================
# グラフ構築
# ============================================================


def build_graph() -> StateGraph:
    """Fan-Out/Fan-In LangGraph グラフを構築する。

    構造:
        commander → Send(worker) × N → quality_gate
                                            ↓ (不合格)
                                       prepare_retry → Send(worker) × M → quality_gate
    """
    graph = StateGraph(PipelineState)

    # ノード登録
    graph.add_node("commander", commander_node)
    graph.add_node("worker", worker_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("prepare_retry", prepare_retry_node)

    # エントリポイント
    graph.set_entry_point("commander")

    # Commander → Worker（Fan-Out via Send）
    graph.add_conditional_edges("commander", fanout_to_workers, ["worker"])

    # Worker → QualityGate（Fan-In: すべてのワーカー完了後）
    graph.add_edge("worker", "quality_gate")

    # QualityGate → END or Retry
    graph.add_conditional_edges(
        "quality_gate",
        route_after_quality,
        {END: END, "prepare_retry": "prepare_retry"},
    )

    # Retry → Worker（再指示 Fan-Out via Send）
    graph.add_conditional_edges("prepare_retry", fanout_to_workers, ["worker"])

    return graph


# ============================================================
# 実行
# ============================================================


def run_pipeline(
    task_description: str,
    *,
    max_iterations: int = MAX_ITERATIONS,
    quality_threshold: float = QUALITY_THRESHOLD,
    seed: int = 42,
) -> dict[str, Any]:
    """Fan-Out/Fan-In パイプラインを実行する。

    Args:
        task_description: 実行するタスクの説明。
        max_iterations: 品質ゲートの最大イテレーション数。
        quality_threshold: 品質閾値。
        seed: 乱数シード（再現性確保）。

    Returns:
        実行結果の辞書。
    """
    random.seed(seed)

    graph = build_graph()
    app = graph.compile()

    initial_state: PipelineState = {
        "task_description": task_description,
        "subtasks": [],
        "worker_results": [],
        "quality_result": None,
        "iteration": 0,
        "max_iterations": max_iterations,
        "quality_threshold": quality_threshold,
    }

    start_time = time.time()
    final_state = app.invoke(initial_state)
    elapsed = time.time() - start_time

    quality = final_state.get("quality_result")
    all_results: list[WorkerOutput] = final_state.get("worker_results", [])

    # 重複排除: 各 task_id の最新結果を採用
    seen: dict[str, WorkerOutput] = {}
    for r in all_results:
        seen[r.task_id] = r
    deduped = list(seen.values())

    total_input = sum(r.input_tokens for r in deduped)
    total_output = sum(r.output_tokens for r in deduped)

    return {
        "status": "success" if (quality and quality.passed) else "partial",
        "iterations": final_state.get("iteration", 0),
        "total_duration_seconds": round(elapsed, 3),
        "quality_score": quality.overall_score if quality else 0.0,
        "quality_passed": quality.passed if quality else False,
        "worker_count": len(deduped),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "worker_results": deduped,
        "raw_result_count": len(all_results),
    }


# ============================================================
# 出力
# ============================================================


def print_results(results: dict[str, Any]) -> None:
    """結果を整形出力する。"""
    print("\n" + "=" * 70)
    print("実験 004: LangGraph Fan-Out/Fan-In パイプライン結果")
    print("=" * 70)

    print(f"\nステータス     : {results['status']}")
    print(f"イテレーション : {results['iterations']}")
    print(f"所要時間       : {results['total_duration_seconds']:.3f}秒")
    print(f"品質スコア     : {results['quality_score']:.3f}")
    print(f"品質合格       : {'✓' if results['quality_passed'] else '✗'}")
    print(f"ワーカー結果数 : {results['worker_count']}（生: {results['raw_result_count']}）")
    print(f"トークン合計   : {results['total_tokens']:,}")

    print("\n--- ワーカー別結果（重複排除後）---")
    for r in results["worker_results"]:
        mark = "✓" if r.success else "✗"
        print(
            f"  [{mark}] {r.task_id:20s} "
            f"score={r.quality_score:.3f} "
            f"model={r.model_used:30s} "
            f"time={r.duration_seconds:.3f}s"
        )

    print("\n" + "=" * 70)


# ============================================================
# メイン
# ============================================================


def main() -> None:
    """メインエントリポイント。"""
    task = (
        "ML 特徴量エンジニアリング: 株式データから価格・出来高・モメンタム・"
        "ボラティリティ・クロスセクションの5カテゴリの特徴量を実装する"
    )

    print("LangGraph Fan-Out/Fan-In パイプラインを実行中...")
    print(f"タスク: {task}")
    print(f"品質閾値: {QUALITY_THRESHOLD}")
    print(f"最大イテレーション: {MAX_ITERATIONS}")
    print()

    results = run_pipeline(
        task,
        max_iterations=MAX_ITERATIONS,
        quality_threshold=QUALITY_THRESHOLD,
        seed=42,
    )

    print_results(results)


if __name__ == "__main__":
    main()
