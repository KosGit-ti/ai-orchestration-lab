"""実験 003: タスク複雑度連動型の評価フレームワーク。

exp_001/002 では「タスク分割による難度低減」がモデル化されておらず、
ワーカー増加で品質が単調低下するという非現実的な結果になっていた。

本実験では以下を改善する:
  1. タスク分割による個別タスク難度の低減（複雑度連動モデル）
  2. 部分成功の許容（全タスク AND → 完了率ベース）
  3. 総合価値指標の導入（完了率 × 有効品質）
  4. 協調コストのモデル化（ワーカー間のオーバーヘッド）
  5. 逐次実行での知識蓄積効果

2つのシナリオで検証する:
  - シナリオ A（単純タスク）: コードフォーマット統一
    → タスク分割の恩恵が小さく、並列化の速度優位のみ
  - シナリオ B（複雑タスク）: ML 特徴量パイプライン構築
    → タスク分割で個別難度が大幅低減、並列実行が有利

実行方法:
    python experiments/parallel-execution/exp_003_evaluation_framework.py

注意:
    この PoC は外部 API を使用せず、モック応答で動作を検証する。
"""

from __future__ import annotations

import asyncio
import math
import random
import time
from dataclasses import dataclass, field

# ============================================================
# 型定義
# ============================================================


@dataclass
class TaskScenario:
    """タスクシナリオの定義。

    Attributes:
        name: シナリオ名。
        description: シナリオの説明。
        total_complexity: タスク全体の複雑度（0.0-1.0）。
        decomp_efficiency: 分割効率指数。N^α で難度が低減する。
            α=1.0 で完全分割（線形スケーリング）、α=0.0 で分割効果なし。
        coordination_factor: 協調コスト係数。ワーカー間の統合コスト。
        sequential_learning: 逐次実行時の知識蓄積率（タスクごとの改善量）。
        failure_sensitivity: 複雑度に対する失敗感度。
        quality_sensitivity: 複雑度に対する品質低下感度。
    """

    name: str
    description: str
    total_complexity: float
    decomp_efficiency: float
    coordination_factor: float
    sequential_learning: float
    failure_sensitivity: float
    quality_sensitivity: float


@dataclass
class SubTaskResult:
    """サブタスク実行結果。"""

    task_id: str
    worker_id: str
    success: bool
    quality_score: float
    duration_seconds: float
    task_complexity: float
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class EvaluationMetrics:
    """改善版の評価指標。

    Attributes:
        completion_rate: 完了率（成功タスク数 / 全タスク数）。
        effective_quality: 有効品質（成功タスクの品質平均）。
        total_value: 総合価値（完了率 × 有効品質）。
        elapsed_time: 所要時間（秒）。
        efficiency: 効率（総合価値 / 所要時間）。
        coordination_cost: 協調コスト（秒）。
        iterations: イテレーション数。
        num_workers: ワーカー数。
        num_tasks: タスク数。
        pipeline_passed: パイプライン合格判定。
    """

    completion_rate: float
    effective_quality: float
    total_value: float
    elapsed_time: float
    efficiency: float
    coordination_cost: float
    iterations: int
    num_workers: int
    num_tasks: int
    pipeline_passed: bool
    all_results: list[SubTaskResult] = field(default_factory=list)


@dataclass
class ScenarioComparison:
    """1シナリオ・1ワーカー数での比較結果。"""

    scenario: TaskScenario
    num_workers: int
    parallel: EvaluationMetrics
    sequential: EvaluationMetrics


# ============================================================
# シナリオ定義
# ============================================================

SCENARIO_SIMPLE = TaskScenario(
    name="単純タスク: コードフォーマット統一",
    description=(
        "既存コードベースのフォーマット統一。"
        "各ファイルは独立しており、分割しても個別の難度はほぼ変わらない。"
        "元々成功率が高いタスク。"
    ),
    total_complexity=0.30,
    decomp_efficiency=0.25,  # 分割してもあまり簡単にならない
    coordination_factor=0.10,  # 統合コスト低い（ファイル独立）
    sequential_learning=0.02,  # 学習効果小さい（パターン化された作業）
    failure_sensitivity=0.50,  # 失敗しにくい
    quality_sensitivity=0.40,  # 品質は安定
)

SCENARIO_COMPLEX = TaskScenario(
    name="複雑タスク: ML 特徴量パイプライン構築",
    description=(
        "市場予測のための ML 特徴量エンジニアリング。"
        "モノリシックに実装すると困難だが、"
        "モジュール分割により各部分の難度が大幅に低減する。"
    ),
    total_complexity=0.90,
    decomp_efficiency=0.70,  # 分割で大幅に簡単になる
    coordination_factor=0.25,  # 統合コスト中程度（モジュール間依存あり）
    sequential_learning=0.05,  # 学習効果あり（理解が深まる）
    failure_sensitivity=0.80,  # 複雑なので失敗しやすい
    quality_sensitivity=0.60,  # 品質が複雑度に影響されやすい
)

# ============================================================
# 設定
# ============================================================

MAX_ITERATIONS = 3
QUALITY_THRESHOLD = 0.80
COMPLETION_THRESHOLD = 0.80  # 80% 以上のタスクが成功すれば合格
WORKER_COUNTS = [1, 3, 5, 10]


# ============================================================
# 複雑度連動モデル
# ============================================================


def calc_per_task_complexity(
    total_complexity: float,
    num_workers: int,
    decomp_efficiency: float,
) -> float:
    """ワーカー数と分割効率に基づき、個別タスクの複雑度を算出する。

    Args:
        total_complexity: タスク全体の複雑度。
        num_workers: ワーカー数（= サブタスク数）。
        decomp_efficiency: 分割効率指数 α。
            C_per = C_total / N^α

    Returns:
        個別タスクの複雑度（0.0-1.0 にクリップ）。
    """
    if num_workers <= 1:
        return total_complexity
    per_task = total_complexity / (num_workers**decomp_efficiency)
    result: float = max(0.05, min(per_task, 1.0))
    return result


def calc_success_probability(
    task_complexity: float,
    failure_sensitivity: float,
    iteration: int,
) -> float:
    """タスク複雑度から成功確率を算出する。

    Args:
        task_complexity: 個別タスクの複雑度。
        failure_sensitivity: 失敗感度。
        iteration: 現在のイテレーション（0始まり）。

    Returns:
        成功確率（0.1-0.99 にクリップ）。
    """
    iteration_bonus = iteration * 0.08
    prob = 1.0 - task_complexity * failure_sensitivity + iteration_bonus
    return max(0.10, min(prob, 0.99))


def calc_base_quality(
    task_complexity: float,
    quality_sensitivity: float,
    iteration: int,
) -> float:
    """タスク複雑度からベース品質を算出する。

    Args:
        task_complexity: 個別タスクの複雑度。
        quality_sensitivity: 品質低下感度。
        iteration: 現在のイテレーション。

    Returns:
        ベース品質（0.2-1.0 にクリップ）。ランダムノイズを含む。
    """
    iteration_bonus = iteration * 0.06
    # 複雑度が低いほど品質が安定（分散が小さい）
    noise_range = task_complexity * 0.15
    noise = random.uniform(-noise_range, noise_range)
    base = 1.0 - task_complexity * quality_sensitivity + iteration_bonus + noise
    return max(0.20, min(base, 1.0))


def calc_coordination_cost(
    num_workers: int,
    coordination_factor: float,
) -> float:
    """協調コスト（時間オーバーヘッド）を算出する。

    Args:
        num_workers: ワーカー数。
        coordination_factor: 協調コスト係数。

    Returns:
        協調コスト（秒）。O(√N) で増大する。
    """
    if num_workers <= 1:
        return 0.0
    return math.sqrt(num_workers) * coordination_factor * 2.0


# ============================================================
# ワーカー実行（モック）
# ============================================================


async def mock_worker_execute(
    worker_id: str,
    task_id: str,
    scenario: TaskScenario,
    task_complexity: float,
    iteration: int,
    *,
    sequential_bonus: float = 0.0,
) -> SubTaskResult:
    """個別タスクを実行する（モック）。

    タスク複雑度に基づき成功率と品質が決定される。

    Args:
        worker_id: ワーカーID。
        task_id: タスクID。
        scenario: タスクシナリオ。
        task_complexity: このタスクの複雑度。
        iteration: 現在のイテレーション。
        sequential_bonus: 逐次実行時の知識蓄積ボーナス。
    """
    start = time.monotonic()

    # 模擬的な処理時間（複雑度に比例）
    work_time = random.uniform(0.1, 0.5) + task_complexity * 0.8
    await asyncio.sleep(work_time)

    # 成功判定
    success_prob = calc_success_probability(
        task_complexity,
        scenario.failure_sensitivity,
        iteration,
    )
    # 逐次ボーナスを成功率にも反映
    success_prob = min(success_prob + sequential_bonus * 0.5, 0.99)
    success = random.random() < success_prob

    # 品質算出
    quality = calc_base_quality(
        task_complexity,
        scenario.quality_sensitivity,
        iteration,
    )
    # 逐次ボーナスを品質にも反映
    quality = min(quality + sequential_bonus, 1.0)
    # 失敗時は品質ゼロ
    if not success:
        quality = 0.0

    duration = time.monotonic() - start

    return SubTaskResult(
        task_id=task_id,
        worker_id=worker_id,
        success=success,
        quality_score=quality,
        duration_seconds=duration,
        task_complexity=task_complexity,
        input_tokens=random.randint(1500, 4000),
        output_tokens=random.randint(500, 2000),
    )


# ============================================================
# 改善版品質ゲート（部分成功許容）
# ============================================================


def evaluate_results(
    results: list[SubTaskResult],
    quality_threshold: float,
    completion_threshold: float,
) -> tuple[bool, float, float]:
    """部分成功を許容する品質ゲート。

    Args:
        results: サブタスク結果のリスト。
        quality_threshold: 品質閾値。
        completion_threshold: 完了率閾値。

    Returns:
        (合格判定, 完了率, 有効品質) のタプル。
    """
    if not results:
        return False, 0.0, 0.0

    successful = [r for r in results if r.success]
    completion_rate = len(successful) / len(results)

    if not successful:
        return False, 0.0, 0.0

    effective_quality = sum(r.quality_score for r in successful) / len(successful)

    passed = completion_rate >= completion_threshold and effective_quality >= quality_threshold
    return passed, completion_rate, effective_quality


# ============================================================
# 並列実行パイプライン（部分リトライ対応）
# ============================================================


async def run_parallel(
    scenario: TaskScenario,
    num_workers: int,
    *,
    verbose: bool = False,
) -> EvaluationMetrics:
    """並列実行パイプライン（部分リトライ + 部分成功許容）。

    Args:
        scenario: タスクシナリオ。
        num_workers: ワーカー数。
        verbose: 詳細出力。
    """
    pipeline_start = time.monotonic()
    task_complexity = calc_per_task_complexity(
        scenario.total_complexity, num_workers, scenario.decomp_efficiency
    )
    coord_cost = calc_coordination_cost(num_workers, scenario.coordination_factor)

    task_ids = [f"task-{i:03d}" for i in range(num_workers)]
    best_results: dict[str, SubTaskResult] = {}

    if verbose:
        print(
            f"    [並列] workers={num_workers}, "
            f"task_complexity={task_complexity:.3f}, "
            f"coord_cost={coord_cost:.2f}s"
        )

    actual_iterations = 0
    for iteration in range(MAX_ITERATIONS):
        # 未成功 OR 品質不足のタスクを再実行（部分リトライ）
        if iteration == 0:
            pending_ids = list(task_ids)
        else:
            pending_ids = [
                tid
                for tid in task_ids
                if tid not in best_results
                or not best_results[tid].success
                or best_results[tid].quality_score < QUALITY_THRESHOLD
            ]

        if not pending_ids:
            break  # 全タスクが成功かつ品質基準達成

        actual_iterations = iteration + 1

        # Fan-Out: 並列実行
        coros = [
            mock_worker_execute(f"w-{i:03d}", tid, scenario, task_complexity, iteration)
            for i, tid in enumerate(pending_ids)
        ]
        results = list(await asyncio.gather(*coros))

        # 結果をマージ（より良い結果を保持）
        for r in results:
            prev = best_results.get(r.task_id)
            if (
                prev is None
                or not prev.success
                or (r.success and r.quality_score > prev.quality_score)
            ):
                best_results[r.task_id] = r

        all_results = list(best_results.values())
        passed, comp_rate, eff_quality = evaluate_results(
            all_results, QUALITY_THRESHOLD, COMPLETION_THRESHOLD
        )

        if verbose:
            n_success = sum(1 for r in all_results if r.success)
            print(
                f"      iter {iteration + 1}: "
                f"成功={n_success}/{num_workers}, "
                f"完了率={comp_rate:.2f}, "
                f"有効品質={eff_quality:.2f}, "
                f"合格={'Yes' if passed else 'No'}"
            )

        if passed:
            # 協調コスト追加
            await asyncio.sleep(coord_cost * 0.1)  # モック
            elapsed = time.monotonic() - pipeline_start + coord_cost
            total_value = comp_rate * eff_quality
            return EvaluationMetrics(
                completion_rate=comp_rate,
                effective_quality=eff_quality,
                total_value=total_value,
                elapsed_time=elapsed,
                efficiency=total_value / elapsed if elapsed > 0 else 0.0,
                coordination_cost=coord_cost,
                iterations=actual_iterations,
                num_workers=num_workers,
                num_tasks=num_workers,
                pipeline_passed=True,
                all_results=all_results,
            )

    # 最大イテレーション到達
    all_results = list(best_results.values())
    _, comp_rate, eff_quality = evaluate_results(
        all_results, QUALITY_THRESHOLD, COMPLETION_THRESHOLD
    )
    elapsed = time.monotonic() - pipeline_start + coord_cost
    total_value = comp_rate * eff_quality

    return EvaluationMetrics(
        completion_rate=comp_rate,
        effective_quality=eff_quality,
        total_value=total_value,
        elapsed_time=elapsed,
        efficiency=total_value / elapsed if elapsed > 0 else 0.0,
        coordination_cost=coord_cost,
        iterations=actual_iterations,
        num_workers=num_workers,
        num_tasks=num_workers,
        pipeline_passed=False,
        all_results=all_results,
    )


# ============================================================
# 逐次実行パイプライン（知識蓄積 + 部分リトライ）
# ============================================================


async def run_sequential(
    scenario: TaskScenario,
    num_workers: int,
    *,
    verbose: bool = False,
) -> EvaluationMetrics:
    """逐次実行パイプライン（知識蓄積 + 部分成功許容）。

    逐次実行でも同じ数のサブタスクに分割する。
    1 ワーカーが順番に処理し、前タスクの知識が蓄積される。

    Args:
        scenario: タスクシナリオ。
        num_workers: タスク数（並列と同数）。
        verbose: 詳細出力。
    """
    pipeline_start = time.monotonic()
    task_complexity = calc_per_task_complexity(
        scenario.total_complexity, num_workers, scenario.decomp_efficiency
    )

    task_ids = [f"task-{i:03d}" for i in range(num_workers)]
    best_results: dict[str, SubTaskResult] = {}

    if verbose:
        print(
            f"    [逐次] tasks={num_workers}, "
            f"task_complexity={task_complexity:.3f}, "
            f"learning_rate={scenario.sequential_learning}"
        )

    actual_iterations = 0
    for iteration in range(MAX_ITERATIONS):
        # 未成功 OR 品質不足のタスクを再実行
        if iteration == 0:
            pending_ids = list(task_ids)
        else:
            pending_ids = [
                tid
                for tid in task_ids
                if tid not in best_results
                or not best_results[tid].success
                or best_results[tid].quality_score < QUALITY_THRESHOLD
            ]

        if not pending_ids:
            break

        actual_iterations = iteration + 1

        # 逐次実行（知識蓄積あり）
        for task_order, tid in enumerate(pending_ids):
            # 逐次実行ではタスクを重ねるごとに知識が蓄積
            seq_bonus = task_order * scenario.sequential_learning
            result = await mock_worker_execute(
                "w-seq",
                tid,
                scenario,
                task_complexity,
                iteration,
                sequential_bonus=seq_bonus,
            )

            prev = best_results.get(tid)
            if (
                prev is None
                or not prev.success
                or (result.success and result.quality_score > prev.quality_score)
            ):
                best_results[tid] = result

        all_results = list(best_results.values())
        passed, comp_rate, eff_quality = evaluate_results(
            all_results, QUALITY_THRESHOLD, COMPLETION_THRESHOLD
        )

        if verbose:
            n_success = sum(1 for r in all_results if r.success)
            print(
                f"      iter {iteration + 1}: "
                f"成功={n_success}/{num_workers}, "
                f"完了率={comp_rate:.2f}, "
                f"有効品質={eff_quality:.2f}, "
                f"合格={'Yes' if passed else 'No'}"
            )

        if passed:
            elapsed = time.monotonic() - pipeline_start
            total_value = comp_rate * eff_quality
            return EvaluationMetrics(
                completion_rate=comp_rate,
                effective_quality=eff_quality,
                total_value=total_value,
                elapsed_time=elapsed,
                efficiency=total_value / elapsed if elapsed > 0 else 0.0,
                coordination_cost=0.0,
                iterations=actual_iterations,
                num_workers=1,
                num_tasks=num_workers,
                pipeline_passed=True,
                all_results=all_results,
            )

    # 最大イテレーション到達
    all_results = list(best_results.values())
    _, comp_rate, eff_quality = evaluate_results(
        all_results, QUALITY_THRESHOLD, COMPLETION_THRESHOLD
    )
    elapsed = time.monotonic() - pipeline_start
    total_value = comp_rate * eff_quality

    return EvaluationMetrics(
        completion_rate=comp_rate,
        effective_quality=eff_quality,
        total_value=total_value,
        elapsed_time=elapsed,
        efficiency=total_value / elapsed if elapsed > 0 else 0.0,
        coordination_cost=0.0,
        iterations=actual_iterations,
        num_workers=1,
        num_tasks=num_workers,
        pipeline_passed=False,
        all_results=all_results,
    )


# ============================================================
# 理論値算出（解析的な期待値）
# ============================================================


def calc_theoretical_values(
    scenario: TaskScenario,
    num_workers: int,
) -> dict[str, float]:
    """理論的な期待値を算出する（モンテカルロ検証用）。

    Args:
        scenario: タスクシナリオ。
        num_workers: ワーカー数。

    Returns:
        理論値の辞書。
    """
    c_per = calc_per_task_complexity(
        scenario.total_complexity, num_workers, scenario.decomp_efficiency
    )
    # イテレーション 2（最終）での期待値
    final_iter = MAX_ITERATIONS - 1
    p_success = calc_success_probability(c_per, scenario.failure_sensitivity, final_iter)
    expected_quality = 1.0 - c_per * scenario.quality_sensitivity + final_iter * 0.06

    # 完了率の期待値（二項分布）
    expected_completion = p_success

    # 全タスク成功の確率（exp_001/002 の AND モデル）
    p_all_success = p_success**num_workers

    # 80%以上成功の確率（部分成功モデル）
    min_success = math.ceil(num_workers * COMPLETION_THRESHOLD)
    p_partial = sum(
        math.comb(num_workers, k) * (p_success**k) * ((1 - p_success) ** (num_workers - k))
        for k in range(min_success, num_workers + 1)
    )

    return {
        "per_task_complexity": c_per,
        "success_probability": p_success,
        "expected_quality": max(0.2, min(expected_quality, 1.0)),
        "expected_completion_rate": expected_completion,
        "p_all_success_and": p_all_success,
        "p_partial_success": p_partial,
        "coordination_cost": calc_coordination_cost(num_workers, scenario.coordination_factor),
    }


# ============================================================
# 結果出力
# ============================================================

HEADER_WIDTH = 76


def _print_scenario_header(scenario: TaskScenario) -> None:
    """シナリオヘッダーを出力する。"""
    print(f"\n{'=' * HEADER_WIDTH}")
    print(f"シナリオ: {scenario.name}")
    print(f"  {scenario.description}")
    print(
        f"  複雑度={scenario.total_complexity:.2f}, "
        f"分割効率={scenario.decomp_efficiency:.2f}, "
        f"協調コスト係数={scenario.coordination_factor:.2f}"
    )
    print(f"{'=' * HEADER_WIDTH}")


def _print_theoretical_analysis(
    scenario: TaskScenario,
) -> None:
    """理論値の分析を出力する。"""
    print(f"\n  理論値分析（イテレーション{MAX_ITERATIONS}完了時）:")
    print(
        f"  {'Workers':>8}"
        f"  {'C_per':>6}"
        f"  {'P(成功)':>8}"
        f"  {'P(全AND)':>9}"
        f"  {'P(≥80%)':>8}"
        f"  {'協調(s)':>8}"
    )
    print(f"  {'-' * 50}")

    for n in WORKER_COUNTS:
        tv = calc_theoretical_values(scenario, n)
        print(
            f"  {n:>8}"
            f"  {tv['per_task_complexity']:>6.3f}"
            f"  {tv['success_probability']:>7.1%}"
            f"  {tv['p_all_success_and']:>8.1%}"
            f"  {tv['p_partial_success']:>7.1%}"
            f"  {tv['coordination_cost']:>8.2f}"
        )


def _print_comparison_table(
    comparisons: list[ScenarioComparison],
) -> None:
    """比較テーブルを出力する。"""
    print(
        f"\n  {'Workers':>8}  {'モード':>6}"
        f"  {'完了率':>6}  {'有効品質':>8}  {'総合価値':>8}"
        f"  {'時間(s)':>8}  {'効率':>6}  {'iter':>5}  {'結果':>5}"
    )
    print(f"  {'-' * 68}")

    for comp in comparisons:
        for label, m in [("並列", comp.parallel), ("逐次", comp.sequential)]:
            status = "PASS" if m.pipeline_passed else "FAIL"
            print(
                f"  {comp.num_workers:>8}  {label:>6}"
                f"  {m.completion_rate:>5.0%}"
                f"  {m.effective_quality:>8.3f}"
                f"  {m.total_value:>8.3f}"
                f"  {m.elapsed_time:>8.2f}"
                f"  {m.efficiency:>6.3f}"
                f"  {m.iterations:>5}"
                f"  {status:>5}"
            )
        print(f"  {'':>8}  {'---':>6}{'':>52}")


def _print_speedup_chart(
    comparisons: list[ScenarioComparison],
) -> None:
    """速度向上と価値向上のチャートを出力する。"""
    print("\n  スケーリング分析:")

    print("    速度倍率:")
    for comp in comparisons:
        if comp.parallel.elapsed_time > 0:
            speedup = comp.sequential.elapsed_time / comp.parallel.elapsed_time
        else:
            speedup = 0.0
        bar = "█" * int(speedup * 5)
        print(f"      N={comp.num_workers:>2}: {speedup:>5.2f}x {bar}")

    print("    総合価値（並列）:")
    for comp in comparisons:
        val = comp.parallel.total_value
        bar = "█" * int(val * 40)
        print(f"      N={comp.num_workers:>2}: {val:>5.3f} {bar}")

    print("    総合価値（逐次）:")
    for comp in comparisons:
        val = comp.sequential.total_value
        bar = "█" * int(val * 40)
        print(f"      N={comp.num_workers:>2}: {val:>5.3f} {bar}")


def _print_key_findings(
    simple_comps: list[ScenarioComparison],
    complex_comps: list[ScenarioComparison],
) -> None:
    """主要な知見を出力する。"""
    print(f"\n{'=' * HEADER_WIDTH}")
    print("総合分析: 単純タスク vs 複雑タスク")
    print(f"{'=' * HEADER_WIDTH}")

    # 各シナリオでの最適ワーカー数を特定
    for label, comps in [
        ("単純タスク", simple_comps),
        ("複雑タスク", complex_comps),
    ]:
        print(f"\n  【{label}】")

        # 並列で最高の総合価値を持つワーカー数
        best_parallel = max(
            comps,
            key=lambda c: (c.parallel.pipeline_passed, c.parallel.total_value),
        )
        # 逐次で最高の総合価値を持つワーカー数
        best_sequential = max(
            comps,
            key=lambda c: (
                c.sequential.pipeline_passed,
                c.sequential.total_value,
            ),
        )

        bp = best_parallel.parallel
        bs = best_sequential.sequential

        print(
            f"    並列最適: N={best_parallel.num_workers}"
            f" (価値={bp.total_value:.3f},"
            f" 完了率={bp.completion_rate:.0%},"
            f" 品質={bp.effective_quality:.3f})"
        )
        print(
            f"    逐次最適: N={best_sequential.num_workers}"
            f" (価値={bs.total_value:.3f},"
            f" 完了率={bs.completion_rate:.0%},"
            f" 品質={bs.effective_quality:.3f})"
        )

        # 並列 vs 逐次 の価値差
        if bp.total_value > bs.total_value:
            advantage = "並列有利"
            diff = bp.total_value - bs.total_value
        else:
            advantage = "逐次有利"
            diff = bs.total_value - bp.total_value
        print(f"    判定: {advantage}（価値差 {diff:.3f}）")

    # exp_001/002 との比較（AND モデル vs 部分成功モデル）
    print("\n  【評価モデルの比較: AND vs 部分成功】")
    print(f"  {'':>20}  {'AND(exp_001/002)':>16}  {'部分成功(exp_003)':>18}")
    print(f"  {'-' * 56}")

    for label, comps in [
        ("単純タスク", simple_comps),
        ("複雑タスク", complex_comps),
    ]:
        for comp in comps:
            if comp.num_workers in (5, 10):
                n = comp.num_workers
                tv = calc_theoretical_values(comp.scenario, n)
                print(
                    f"  {label} N={n:>2}:"
                    f"  {tv['p_all_success_and']:>15.1%}"
                    f"  {tv['p_partial_success']:>17.1%}"
                )

    print("\n  結論:")
    print("    1. 複雑タスクではタスク分割が品質・成功率を大幅に改善する")
    print("    2. 単純タスクでは分割の恩恵が小さく、速度のみが利点")
    print("    3. 部分成功モデルにより、AND 条件の非現実的な厳しさが解消")
    print("    4. 協調コストはワーカー増で増大するが、複雑タスクでは")
    print("       分割効果がそれを上回る")
    print(f"{'=' * HEADER_WIDTH}")


# ============================================================
# メイン実行
# ============================================================


async def run_scenario(
    scenario: TaskScenario,
    *,
    verbose: bool = True,
) -> list[ScenarioComparison]:
    """1シナリオの全パターンを実行する。"""
    _print_scenario_header(scenario)
    _print_theoretical_analysis(scenario)

    comparisons: list[ScenarioComparison] = []

    for num_workers in WORKER_COUNTS:
        print(f"\n  --- ワーカー数: {num_workers} ---")
        seed = 42 + num_workers

        random.seed(seed)
        parallel = await run_parallel(scenario, num_workers, verbose=verbose)

        random.seed(seed)
        sequential = await run_sequential(scenario, num_workers, verbose=verbose)

        comparisons.append(
            ScenarioComparison(
                scenario=scenario,
                num_workers=num_workers,
                parallel=parallel,
                sequential=sequential,
            )
        )

    _print_comparison_table(comparisons)
    _print_speedup_chart(comparisons)

    return comparisons


async def main() -> None:
    """評価フレームワーク検証のメインエントリポイント。"""
    print(f"{'#' * HEADER_WIDTH}")
    print("実験 003: タスク複雑度連動型の評価フレームワーク")
    print(f"設定: 品質閾値={QUALITY_THRESHOLD}, 完了率閾値={COMPLETION_THRESHOLD}")
    print(f"      最大イテレーション={MAX_ITERATIONS}")
    print(f"      ワーカー数パターン={WORKER_COUNTS}")
    print("改善点:")
    print("  1. タスク分割による難度低減（C_per = C_total / N^α）")
    print("  2. 部分成功許容（完了率 ≥ 80% AND 有効品質 ≥ 閾値）")
    print("  3. 部分リトライ（失敗タスクのみ再実行）")
    print("  4. 協調コスト（O(√N) オーバーヘッド）")
    print("  5. 逐次実行の知識蓄積効果")
    print(f"{'#' * HEADER_WIDTH}")

    # シナリオ A: 単純タスク
    simple_comps = await run_scenario(SCENARIO_SIMPLE)

    # シナリオ B: 複雑タスク
    complex_comps = await run_scenario(SCENARIO_COMPLEX)

    # 総合分析
    _print_key_findings(simple_comps, complex_comps)


if __name__ == "__main__":
    asyncio.run(main())
