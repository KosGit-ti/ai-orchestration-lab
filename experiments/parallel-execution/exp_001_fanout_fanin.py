"""実験 001: Fan-Out/Fan-In パターンの検証。

司令塔（Commander）＋複数作業者（Worker）による
Fan-Out/Fan-In 型並列実行パターンの実現可能性を検証する。

実行方法:
    python experiments/parallel-execution/exp_001_fanout_fanin.py

注意:
    この PoC は外部 API を使用せず、モック応答で動作を検証する。
    実際の LLM 接続は N-003（最小実装）フェーズで統合する。
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

# ============================================================
# 型定義（実験用のローカル型。昇格版は src/orchestration_lab/parallel/types.py）
# ============================================================


@dataclass
class SubTask:
    """サブタスク定義。"""

    task_id: str
    description: str
    assigned_model: str
    context: str = ""


@dataclass
class SubTaskResult:
    """サブタスク実行結果。"""

    task_id: str
    worker_id: str
    model_used: str
    success: bool
    output: str
    quality_score: float
    duration_seconds: float
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class ReviewVerdict:
    """品質レビュー判定。"""

    passed: bool
    overall_score: float
    task_feedback: dict[str, str] = field(default_factory=dict)


@dataclass
class PipelineResult:
    """パイプライン全体の結果。"""

    success: bool
    iterations: int
    total_duration: float
    results: list[SubTaskResult] = field(default_factory=list)
    final_score: float = 0.0


# ============================================================
# 設定
# ============================================================

COMMANDER_MODEL = "claude-opus-4-20250514"
WORKER_MODELS = ["claude-sonnet-4-20250514", "codex-5.3"]
MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.80
NUM_WORKERS = 5


# ============================================================
# モック関数（外部 API なし）
# ============================================================


async def mock_commander_decompose(task_description: str) -> list[SubTask]:
    """司令塔がタスクを分解する（モック）。

    ML 特徴量エンジニアリングのタスクを独立したサブタスクに分解する。
    """
    # 模擬的な処理時間（司令塔の思考時間）
    await asyncio.sleep(0.1)

    subtasks = [
        SubTask(
            task_id="feat-price",
            description="価格ベースの特徴量を実装する（移動平均、ボリンジャーバンド、価格変動率）",
            assigned_model="claude-sonnet-4-20250514",
            context="src/features/price.py に実装",
        ),
        SubTask(
            task_id="feat-volume",
            description="出来高ベースの特徴量を実装する（VWAP、OBV、出来高移動平均）",
            assigned_model="codex-5.3",
            context="src/features/volume.py に実装",
        ),
        SubTask(
            task_id="feat-technical",
            description="テクニカル指標を実装する（RSI、MACD、ストキャスティクス）",
            assigned_model="claude-sonnet-4-20250514",
            context="src/features/technical.py に実装",
        ),
        SubTask(
            task_id="feat-stats",
            description="統計的特徴量を実装する（リターン分布、自己相関、ボラティリティ）",
            assigned_model="codex-5.3",
            context="src/features/stats.py に実装",
        ),
        SubTask(
            task_id="feat-pipeline",
            description="特徴量選択と前処理パイプラインを実装する",
            assigned_model="claude-sonnet-4-20250514",
            context="src/features/pipeline.py に実装。他の特徴量モジュールを統合する",
        ),
    ]

    print(f"  [Commander] タスクを {len(subtasks)} 個のサブタスクに分解しました")
    for st in subtasks:
        print(f"    - {st.task_id}: {st.description[:40]}... (model: {st.assigned_model})")

    return subtasks


async def mock_worker_execute(
    worker_id: str,
    task: SubTask,
    iteration: int,
) -> SubTaskResult:
    """ワーカーがサブタスクを実行する（モック）。

    モック応答として、ランダムな品質スコアと処理時間を生成する。
    イテレーションが進むほど品質が向上する傾向をシミュレートする。
    """
    start = time.monotonic()

    # 模擬的な処理時間（ワーカーのコード生成時間）
    work_time = random.uniform(0.5, 2.0)
    await asyncio.sleep(work_time)

    # イテレーションが進むほど品質が向上する（フィードバック反映の効果）
    base_quality = random.uniform(0.55, 0.85)
    iteration_bonus = iteration * 0.08
    quality = min(base_quality + iteration_bonus, 1.0)

    # 成功率もイテレーションで向上
    success = random.random() < (0.7 + iteration * 0.1)

    duration = time.monotonic() - start

    return SubTaskResult(
        task_id=task.task_id,
        worker_id=worker_id,
        model_used=task.assigned_model,
        success=success,
        output=f"# {task.task_id} の実装コード（モック）\n# 品質スコア: {quality:.2f}",
        quality_score=quality if success else 0.0,
        duration_seconds=duration,
        input_tokens=random.randint(1500, 4000),
        output_tokens=random.randint(500, 2000),
    )


async def mock_commander_review(
    results: list[SubTaskResult],
    threshold: float,
) -> ReviewVerdict:
    """司令塔が品質を判定する（モック）。"""
    await asyncio.sleep(0.1)

    scores = [r.quality_score for r in results]
    overall = sum(scores) / len(scores) if scores else 0.0

    feedback: dict[str, str] = {}
    for r in results:
        if r.quality_score < threshold:
            feedback[r.task_id] = f"品質スコア {r.quality_score:.2f} が閾値 {threshold} 未満"
        elif not r.success:
            feedback[r.task_id] = "実行に失敗。再試行が必要"

    passed = overall >= threshold and all(r.success for r in results)

    print(f"  [Commander] 品質判定: スコア={overall:.2f}, 合格={'Yes' if passed else 'No'}")
    if feedback:
        for tid, fb in feedback.items():
            print(f"    - {tid}: {fb}")

    return ReviewVerdict(passed=passed, overall_score=overall, task_feedback=feedback)


# ============================================================
# Fan-Out/Fan-In パイプライン
# ============================================================


async def run_fanout_fanin(task_description: str) -> PipelineResult:
    """Fan-Out/Fan-In パイプラインを実行する。

    1. 司令塔がタスクを分解する（Fan-Out）
    2. ワーカーが並列でサブタスクを実行する
    3. 司令塔が品質を判定する（Fan-In + Quality Gate）
    4. 品質不合格なら再指示して繰り返す

    Args:
        task_description: 実行するタスクの説明。

    Returns:
        パイプライン全体の実行結果。
    """
    pipeline_start = time.monotonic()
    all_results: list[SubTaskResult] = []

    print(f"\n{'=' * 60}")
    print("Fan-Out/Fan-In パイプライン開始")
    print(f"タスク: {task_description}")
    print(f"設定: ワーカー数={NUM_WORKERS}, 品質閾値={QUALITY_THRESHOLD}")
    print(f"       最大イテレーション={MAX_ITERATIONS}")
    print(f"{'=' * 60}")

    for iteration in range(MAX_ITERATIONS):
        print(f"\n--- イテレーション {iteration + 1}/{MAX_ITERATIONS} ---")

        # Step 1: Fan-Out（タスク分解）
        subtasks = await mock_commander_decompose(task_description)

        # Step 2: 並列実行
        print(f"\n  [Workers] {len(subtasks)} 個のサブタスクを並列実行中...")
        worker_tasks = [
            mock_worker_execute(f"worker-{i:03d}", subtask, iteration)
            for i, subtask in enumerate(subtasks)
        ]

        exec_start = time.monotonic()
        results = await asyncio.gather(*worker_tasks)
        exec_duration = time.monotonic() - exec_start
        all_results = list(results)

        print(f"  [Workers] 並列実行完了（{exec_duration:.2f}秒）")
        for r in results:
            status = "成功" if r.success else "失敗"
            print(
                f"    - {r.task_id}: {status}"
                f" (品質={r.quality_score:.2f},"
                f" {r.duration_seconds:.2f}秒,"
                f" tokens={r.input_tokens + r.output_tokens})"
            )

        # Step 3: Fan-In + Quality Gate
        print("\n  [Commander] 品質レビュー中...")
        verdict = await mock_commander_review(results, QUALITY_THRESHOLD)

        if verdict.passed:
            total_duration = time.monotonic() - pipeline_start
            print(f"\n{'=' * 60}")
            print("パイプライン完了！")
            print(f"  イテレーション数: {iteration + 1}")
            print(f"  最終品質スコア: {verdict.overall_score:.2f}")
            print(f"  総所要時間: {total_duration:.2f}秒")
            total_input = sum(r.input_tokens for r in all_results)
            total_output = sum(r.output_tokens for r in all_results)
            print(f"  総トークン: 入力={total_input}, 出力={total_output}")
            print(f"{'=' * 60}\n")

            return PipelineResult(
                success=True,
                iterations=iteration + 1,
                total_duration=total_duration,
                results=all_results,
                final_score=verdict.overall_score,
            )

        print("  [Commander] 品質基準未達。再指示してイテレーション継続...")

    # 最大イテレーション到達
    total_duration = time.monotonic() - pipeline_start
    final_score = (
        sum(r.quality_score for r in all_results) / len(all_results) if all_results else 0.0
    )

    print(f"\n{'=' * 60}")
    print("パイプライン終了（最大イテレーション到達）")
    print(f"  最終品質スコア: {final_score:.2f}")
    print(f"  総所要時間: {total_duration:.2f}秒")
    print(f"{'=' * 60}\n")

    return PipelineResult(
        success=False,
        iterations=MAX_ITERATIONS,
        total_duration=total_duration,
        results=all_results,
        final_score=final_score,
    )


# ============================================================
# 逐次実行との比較用
# ============================================================


async def run_sequential(task_description: str) -> PipelineResult:
    """逐次実行パイプライン（ベースライン比較用）。

    同じタスクを 1 つずつ逐次実行し、並列実行との比較基準とする。

    Args:
        task_description: 実行するタスクの説明。

    Returns:
        パイプライン全体の実行結果。
    """
    pipeline_start = time.monotonic()

    print(f"\n{'=' * 60}")
    print("逐次実行パイプライン開始（ベースライン比較）")
    print(f"{'=' * 60}")

    subtasks = await mock_commander_decompose(task_description)
    all_results: list[SubTaskResult] = []

    for i, subtask in enumerate(subtasks):
        print(f"\n  [Sequential] サブタスク {i + 1}/{len(subtasks)}: {subtask.task_id}")
        result = await mock_worker_execute(f"worker-seq-{i:03d}", subtask, iteration=1)
        all_results.append(result)

    total_duration = time.monotonic() - pipeline_start
    final_score = (
        sum(r.quality_score for r in all_results) / len(all_results) if all_results else 0.0
    )

    print(f"\n  逐次実行完了: {total_duration:.2f}秒, スコア={final_score:.2f}")

    return PipelineResult(
        success=final_score >= QUALITY_THRESHOLD,
        iterations=1,
        total_duration=total_duration,
        results=all_results,
        final_score=final_score,
    )


# ============================================================
# ヘルパー関数
# ============================================================


def _calc_improvement_rate(parallel: float, sequential: float) -> float:
    """所要時間の改善率を算出する。"""
    if sequential <= 0:
        return 0.0
    return (1 - parallel / sequential) * 100


def _calc_score_diff(parallel: float, sequential: float) -> float:
    """品質スコアの差分を算出する。"""
    if sequential <= 0:
        return 0.0
    return (parallel - sequential) * 100


# ============================================================
# メイン実行
# ============================================================


async def main() -> None:
    """PoC のメインエントリポイント。"""
    task = "市場予測のための ML 特徴量エンジニアリングを実装する"

    # シードを固定して再現性を確保
    random.seed(42)

    # Fan-Out/Fan-In 並列実行
    parallel_result = await run_fanout_fanin(task)

    # シードをリセットして同条件で逐次実行
    random.seed(42)
    sequential_result = await run_sequential(task)

    # 比較結果
    print(f"\n{'=' * 60}")
    print("比較結果")
    print(f"{'=' * 60}")
    print(f"{'指標':<20} {'並列実行':>12} {'逐次実行':>12} {'改善率':>10}")
    print(f"{'-' * 54}")
    print(
        f"{'所要時間（秒）':<20}"
        f" {parallel_result.total_duration:>12.2f}"
        f" {sequential_result.total_duration:>12.2f}"
        f" {
            _calc_improvement_rate(
                parallel_result.total_duration,
                sequential_result.total_duration,
            ):>9.1f}%"
    )
    print(
        f"{'品質スコア':<20}"
        f" {parallel_result.final_score:>12.2f}"
        f" {sequential_result.final_score:>12.2f}"
        f" {_calc_score_diff(parallel_result.final_score, sequential_result.final_score):>9.1f}%"
    )
    print(
        f"{'イテレーション数':<20}"
        f" {parallel_result.iterations:>12}"
        f" {sequential_result.iterations:>12}"
        f" {'N/A':>10}"
    )
    print(
        f"{'成功':<20}"
        f" {'Yes' if parallel_result.success else 'No':>12}"
        f" {'Yes' if sequential_result.success else 'No':>12}"
        f" {'N/A':>10}"
    )
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    asyncio.run(main())
