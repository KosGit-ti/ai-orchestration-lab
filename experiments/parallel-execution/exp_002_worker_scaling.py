"""実験 002: ワーカー数スケーリングの検証。

並列実行における最適ワーカー数を検証する。
ワーカー数 3 / 5 / 10 のパターンで並列実行・逐次実行を比較し、
スケーリング特性と品質ゲートループの効果を分析する。

実行方法:
    python experiments/parallel-execution/exp_002_worker_scaling.py

注意:
    この PoC は外部 API を使用せず、モック応答で動作を検証する。
    並列・逐次の両方で品質ゲートループ（最大3イテレーション）を適用し、
    公平な比較を行う。
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field

# ============================================================
# 型定義
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
    num_workers: int
    num_tasks: int
    results: list[SubTaskResult] = field(default_factory=list)
    final_score: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0


@dataclass
class ScalingComparison:
    """スケーリング比較結果。"""

    num_workers: int
    parallel_result: PipelineResult
    sequential_result: PipelineResult


# ============================================================
# 設定
# ============================================================

COMMANDER_MODEL = "claude-opus-4-20250514"
WORKER_MODELS = ["claude-sonnet-4-20250514", "codex-5.3"]
MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.80
WORKER_COUNTS = [3, 5, 10]

# ワーカー数に対応するサブタスクテンプレート
SUBTASK_TEMPLATES: dict[str, tuple[str, str]] = {
    # task_id: (description, context)
    "feat-price": (
        "価格ベースの特徴量を実装する（移動平均、ボリンジャーバンド、価格変動率）",
        "src/features/price.py に実装",
    ),
    "feat-volume": (
        "出来高ベースの特徴量を実装する（VWAP、OBV、出来高移動平均）",
        "src/features/volume.py に実装",
    ),
    "feat-technical": (
        "テクニカル指標を実装する（RSI、MACD、ストキャスティクス）",
        "src/features/technical.py に実装",
    ),
    "feat-stats": (
        "統計的特徴量を実装する（リターン分布、自己相関、ボラティリティ）",
        "src/features/stats.py に実装",
    ),
    "feat-pipeline": (
        "特徴量選択と前処理パイプラインを実装する",
        "src/features/pipeline.py に実装。他の特徴量モジュールを統合する",
    ),
    "feat-momentum": (
        "モメンタム指標を実装する（ROC、Williams %R、MFI）",
        "src/features/momentum.py に実装",
    ),
    "feat-volatility": (
        "ボラティリティ指標を実装する（ATR、ケルトナーチャネル、歴史的 vol）",
        "src/features/volatility.py に実装",
    ),
    "feat-pattern": (
        "チャートパターン認識を実装する（ダブルトップ、ヘッドアンドショルダー）",
        "src/features/pattern.py に実装",
    ),
    "feat-sentiment": (
        "センチメント特徴量を実装する（出来高比率、価格加速度）",
        "src/features/sentiment.py に実装",
    ),
    "feat-cross": (
        "クロスアセット特徴量を実装する（相関行列、セクター相対強度）",
        "src/features/cross.py に実装",
    ),
}

# ワーカー数別に使用するサブタスク ID
WORKER_TASK_MAP: dict[int, list[str]] = {
    3: ["feat-price", "feat-volume", "feat-technical"],
    5: [
        "feat-price",
        "feat-volume",
        "feat-technical",
        "feat-stats",
        "feat-pipeline",
    ],
    10: list(SUBTASK_TEMPLATES.keys()),
}


# ============================================================
# モック関数
# ============================================================


def _build_subtasks(num_workers: int) -> list[SubTask]:
    """ワーカー数に応じたサブタスクリストを構築する。"""
    task_ids = WORKER_TASK_MAP[num_workers]
    subtasks = []
    for i, task_id in enumerate(task_ids):
        desc, ctx = SUBTASK_TEMPLATES[task_id]
        model = WORKER_MODELS[i % len(WORKER_MODELS)]
        subtasks.append(
            SubTask(
                task_id=task_id,
                description=desc,
                assigned_model=model,
                context=ctx,
            )
        )
    return subtasks


async def mock_worker_execute(
    worker_id: str,
    task: SubTask,
    iteration: int,
) -> SubTaskResult:
    """ワーカーがサブタスクを実行する（モック）。

    イテレーションが進むほど品質が向上する。
    並列・逐次で同じ関数を使うことで公平性を確保する。
    """
    start = time.monotonic()

    # 模擬的な処理時間
    work_time = random.uniform(0.3, 1.5)
    await asyncio.sleep(work_time)

    # イテレーションによる品質向上
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
        output=f"# {task.task_id} の実装コード（モック）",
        quality_score=quality if success else 0.0,
        duration_seconds=duration,
        input_tokens=random.randint(1500, 4000),
        output_tokens=random.randint(500, 2000),
    )


def _review_results(
    results: list[SubTaskResult],
    threshold: float,
) -> ReviewVerdict:
    """品質を判定する（同期版）。"""
    scores = [r.quality_score for r in results]
    overall = sum(scores) / len(scores) if scores else 0.0

    feedback: dict[str, str] = {}
    for r in results:
        if not r.success:
            feedback[r.task_id] = "実行に失敗。再試行が必要"
        elif r.quality_score < threshold:
            feedback[r.task_id] = f"品質スコア {r.quality_score:.2f} が閾値 {threshold} 未満"

    passed = overall >= threshold and all(r.success for r in results)
    return ReviewVerdict(passed=passed, overall_score=overall, task_feedback=feedback)


# ============================================================
# 並列実行パイプライン
# ============================================================


async def run_parallel(
    num_workers: int,
    *,
    verbose: bool = False,
) -> PipelineResult:
    """並列実行パイプラインを実行する。

    Args:
        num_workers: ワーカー数（サブタスク数に対応）。
        verbose: 詳細出力を有効にする。

    Returns:
        パイプライン全体の実行結果。
    """
    pipeline_start = time.monotonic()
    subtasks = _build_subtasks(num_workers)
    all_results: list[SubTaskResult] = []

    if verbose:
        print(f"\n  [並列] ワーカー数={num_workers}, タスク数={len(subtasks)}")

    for iteration in range(MAX_ITERATIONS):
        # Fan-Out: 並列実行
        worker_tasks = [
            mock_worker_execute(f"worker-{i:03d}", subtask, iteration)
            for i, subtask in enumerate(subtasks)
        ]
        results = list(await asyncio.gather(*worker_tasks))
        all_results = results

        # Fan-In: 品質判定
        verdict = _review_results(results, QUALITY_THRESHOLD)

        if verbose:
            print(
                f"    イテレーション {iteration + 1}: "
                f"スコア={verdict.overall_score:.2f}, "
                f"合格={'Yes' if verdict.passed else 'No'}"
            )

        if verdict.passed:
            total_duration = time.monotonic() - pipeline_start
            total_input = sum(r.input_tokens for r in all_results)
            total_output = sum(r.output_tokens for r in all_results)
            return PipelineResult(
                success=True,
                iterations=iteration + 1,
                total_duration=total_duration,
                num_workers=num_workers,
                num_tasks=len(subtasks),
                results=all_results,
                final_score=verdict.overall_score,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
            )

    # 最大イテレーション到達
    total_duration = time.monotonic() - pipeline_start
    final_score = (
        sum(r.quality_score for r in all_results) / len(all_results) if all_results else 0.0
    )
    total_input = sum(r.input_tokens for r in all_results)
    total_output = sum(r.output_tokens for r in all_results)

    return PipelineResult(
        success=False,
        iterations=MAX_ITERATIONS,
        total_duration=total_duration,
        num_workers=num_workers,
        num_tasks=len(subtasks),
        results=all_results,
        final_score=final_score,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


# ============================================================
# 逐次実行パイプライン（品質ゲートループ付き）
# ============================================================


async def run_sequential(
    num_workers: int,
    *,
    verbose: bool = False,
) -> PipelineResult:
    """逐次実行パイプラインを実行する（品質ゲートループ付き）。

    並列実行との公平な比較のため、逐次実行でも
    品質ゲートループ（最大3イテレーション）を適用する。

    Args:
        num_workers: タスク数（並列実行と同じ数のサブタスクを処理）。
        verbose: 詳細出力を有効にする。

    Returns:
        パイプライン全体の実行結果。
    """
    pipeline_start = time.monotonic()
    subtasks = _build_subtasks(num_workers)
    all_results: list[SubTaskResult] = []

    if verbose:
        print(f"\n  [逐次] タスク数={len(subtasks)}")

    for iteration in range(MAX_ITERATIONS):
        results: list[SubTaskResult] = []
        for i, subtask in enumerate(subtasks):
            result = await mock_worker_execute(f"worker-seq-{i:03d}", subtask, iteration)
            results.append(result)
        all_results = results

        # 品質判定
        verdict = _review_results(results, QUALITY_THRESHOLD)

        if verbose:
            print(
                f"    イテレーション {iteration + 1}: "
                f"スコア={verdict.overall_score:.2f}, "
                f"合格={'Yes' if verdict.passed else 'No'}"
            )

        if verdict.passed:
            total_duration = time.monotonic() - pipeline_start
            total_input = sum(r.input_tokens for r in all_results)
            total_output = sum(r.output_tokens for r in all_results)
            return PipelineResult(
                success=True,
                iterations=iteration + 1,
                total_duration=total_duration,
                num_workers=num_workers,
                num_tasks=len(subtasks),
                results=all_results,
                final_score=verdict.overall_score,
                total_input_tokens=total_input,
                total_output_tokens=total_output,
            )

    # 最大イテレーション到達
    total_duration = time.monotonic() - pipeline_start
    final_score = (
        sum(r.quality_score for r in all_results) / len(all_results) if all_results else 0.0
    )
    total_input = sum(r.input_tokens for r in all_results)
    total_output = sum(r.output_tokens for r in all_results)

    return PipelineResult(
        success=False,
        iterations=MAX_ITERATIONS,
        total_duration=total_duration,
        num_workers=num_workers,
        num_tasks=len(subtasks),
        results=all_results,
        final_score=final_score,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
    )


# ============================================================
# 結果出力
# ============================================================


def _calc_speedup(parallel_time: float, sequential_time: float) -> float:
    """速度向上倍率を算出する。"""
    if parallel_time <= 0:
        return 0.0
    return sequential_time / parallel_time


def _print_pattern_result(comp: ScalingComparison) -> None:
    """1パターンの結果を出力する。"""
    p = comp.parallel_result
    s = comp.sequential_result
    speedup = _calc_speedup(p.total_duration, s.total_duration)

    print(f"\n--- ワーカー数: {comp.num_workers} （タスク数: {p.num_tasks}）---")
    print(f"{'':>20} {'並列':>10} {'逐次':>10} {'比較':>12}")
    print(f"{'-' * 52}")
    print(
        f"{'所要時間（秒）':>20} {p.total_duration:>9.2f} {s.total_duration:>9.2f} {speedup:>9.2f}x"
    )
    print(
        f"{'品質スコア':>20}"
        f" {p.final_score:>9.2f}"
        f" {s.final_score:>9.2f}"
        f" {p.final_score - s.final_score:>+9.2f}"
    )
    print(f"{'イテレーション数':>20} {p.iterations:>9} {s.iterations:>9} {'':>12}")
    p_status = "成功" if p.success else "失敗"
    s_status = "成功" if s.success else "失敗"
    print(f"{'結果':>20} {p_status:>9} {s_status:>9} {'':>12}")
    p_tokens = p.total_input_tokens + p.total_output_tokens
    s_tokens = s.total_input_tokens + s.total_output_tokens
    print(f"{'総トークン数':>20} {p_tokens:>9,} {s_tokens:>9,} {'':>12}")


def _print_summary_table(comparisons: list[ScalingComparison]) -> None:
    """全パターンのサマリーテーブルを出力する。"""
    print(f"\n{'=' * 72}")
    print("スケーリング比較サマリー")
    print(f"{'=' * 72}")
    print(
        f"{'Workers':>8}"
        f" {'Tasks':>6}"
        f" {'並列(秒)':>9}"
        f" {'逐次(秒)':>9}"
        f" {'速度倍率':>9}"
        f" {'並列品質':>9}"
        f" {'逐次品質':>9}"
        f" {'並列結果':>9}"
    )
    print(f"{'-' * 68}")

    for comp in comparisons:
        p = comp.parallel_result
        s = comp.sequential_result
        speedup = _calc_speedup(p.total_duration, s.total_duration)
        p_status = "PASS" if p.success else "FAIL"
        print(
            f"{comp.num_workers:>8}"
            f" {p.num_tasks:>6}"
            f" {p.total_duration:>9.2f}"
            f" {s.total_duration:>9.2f}"
            f" {speedup:>8.2f}x"
            f" {p.final_score:>9.2f}"
            f" {s.final_score:>9.2f}"
            f" {p_status:>9}"
        )

    print(f"{'=' * 72}")


def _print_analysis(comparisons: list[ScalingComparison]) -> None:
    """分析結果を出力する。"""
    print("\n分析:")

    # 速度向上の傾向
    speedups = []
    for comp in comparisons:
        p = comp.parallel_result
        s = comp.sequential_result
        speedup = _calc_speedup(p.total_duration, s.total_duration)
        speedups.append((comp.num_workers, speedup))

    print("\n  速度向上倍率の傾向:")
    for workers, speedup in speedups:
        bar = "█" * int(speedup * 10)
        print(f"    ワーカー数 {workers:>2}: {speedup:.2f}x {bar}")

    # 品質ゲートループの効果
    print("\n  品質ゲートループの効果:")
    for comp in comparisons:
        p = comp.parallel_result
        s = comp.sequential_result
        print(
            f"    ワーカー数 {comp.num_workers:>2}: "
            f"並列 {p.iterations} iter → {p.final_score:.2f}, "
            f"逐次 {s.iterations} iter → {s.final_score:.2f}"
        )

    # 結論
    all_parallel_pass = all(c.parallel_result.success for c in comparisons)
    all_sequential_pass = all(c.sequential_result.success for c in comparisons)

    print("\n  結論:")
    if all_parallel_pass and not all_sequential_pass:
        print("    → 並列実行は全パターンで品質基準を達成。")
        print("      品質ゲートループによるイテレーション改善が有効に機能。")
    elif all_parallel_pass and all_sequential_pass:
        print("    → 並列・逐次とも全パターンで品質基準を達成。")
        print("      並列実行の優位性は実行速度の向上にある。")
    else:
        print("    → 一部パターンで品質基準未達。")
        print("      モックのランダム性による影響の可能性あり。")

    # 最適ワーカー数の推定
    best = max(
        comparisons,
        key=lambda c: (
            c.parallel_result.success,
            _calc_speedup(
                c.parallel_result.total_duration,
                c.sequential_result.total_duration,
            ),
        ),
    )
    best_speedup = _calc_speedup(
        best.parallel_result.total_duration,
        best.sequential_result.total_duration,
    )
    best_quality = best.parallel_result.final_score
    print(
        f"\n    推奨ワーカー数: {best.num_workers}"
        f" （速度倍率={best_speedup:.2f}x,"
        f" 品質={best_quality:.2f}）"
    )


# ============================================================
# メイン実行
# ============================================================


async def main() -> None:
    """スケーリング検証のメインエントリポイント。"""
    print("=" * 72)
    print("実験 002: ワーカー数スケーリング検証")
    print(f"設定: 品質閾値={QUALITY_THRESHOLD}, 最大イテレーション={MAX_ITERATIONS}")
    print(f"パターン: ワーカー数 = {WORKER_COUNTS}")
    print("条件: 並列・逐次ともに品質ゲートループを適用（公平比較）")
    print("=" * 72)

    comparisons: list[ScalingComparison] = []

    for num_workers in WORKER_COUNTS:
        print(f"\n{'#' * 60}")
        print(f"# パターン: ワーカー数 = {num_workers}")
        print(f"{'#' * 60}")

        # 同一シードで並列・逐次を比較
        seed = 42 + num_workers  # ワーカー数ごとに異なるシードで独立性を確保

        # 並列実行
        random.seed(seed)
        parallel_result = await run_parallel(num_workers, verbose=True)

        # 逐次実行
        random.seed(seed)
        sequential_result = await run_sequential(num_workers, verbose=True)

        comp = ScalingComparison(
            num_workers=num_workers,
            parallel_result=parallel_result,
            sequential_result=sequential_result,
        )
        comparisons.append(comp)
        _print_pattern_result(comp)

    # サマリー
    _print_summary_table(comparisons)
    _print_analysis(comparisons)


if __name__ == "__main__":
    asyncio.run(main())
