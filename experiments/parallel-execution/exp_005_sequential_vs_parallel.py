"""実験 005: 逐次実行 vs 並列実行のベンチマーク比較。

exp_004 の LangGraph Fan-Out/Fan-In パイプラインと
逐次実行パイプラインの品質・パフォーマンスを比較する。

比較指標:
    - 実行時間（Wall-clock）
    - 品質スコア（平均・最小・最大）
    - イテレーション数（品質ゲート通過までの回数）
    - トークン使用量
    - 品質ゲート合格率

実行方法:
    python experiments/parallel-execution/exp_005_sequential_vs_parallel.py

注意:
    モック応答で動作を検証する。外部 LLM API は使用しない。
    乱数シードにより再現性を確保している。
"""

from __future__ import annotations

import importlib
import random
import statistics
import sys
import time
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# 実験ディレクトリはハイフン含みのため、sys.path 経由でインポートする

_exp_dir = Path(__file__).resolve().parent
if str(_exp_dir) not in sys.path:
    sys.path.insert(0, str(_exp_dir))

exp_004 = importlib.import_module("exp_004_langgraph_fanout")
SubTask = exp_004.SubTask
WorkerOutput = exp_004.WorkerOutput
QualityGateResult = exp_004.QualityGateResult
mock_decompose = exp_004.mock_decompose
mock_execute = exp_004.mock_execute
mock_quality_check = exp_004.mock_quality_check
run_parallel_pipeline = exp_004.run_pipeline

# ============================================================
# 設定
# ============================================================

QUALITY_THRESHOLD = 0.80
MAX_ITERATIONS = 3
BENCHMARK_RUNS = 10  # ベンチマーク実行回数
SEED_BASE = 100  # シードの基準値


# ============================================================
# 逐次実行パイプライン
# ============================================================


def run_sequential_pipeline(
    task_description: str,
    *,
    max_iterations: int = MAX_ITERATIONS,
    quality_threshold: float = QUALITY_THRESHOLD,
    seed: int = 42,
) -> dict[str, Any]:
    """逐次実行パイプラインを実行する。

    全サブタスクを1つずつ順番に実行する。
    品質ゲートでの不合格タスクは次イテレーションで再実行する。

    Args:
        task_description: 実行するタスクの説明。
        max_iterations: 品質ゲートの最大イテレーション数。
        quality_threshold: 品質閾値。
        seed: 乱数シード。

    Returns:
        実行結果の辞書。
    """
    random.seed(seed)
    start_time = time.time()

    # タスク分解
    subtasks = mock_decompose(task_description)
    results: dict[str, WorkerOutput] = {}
    quality: QualityGateResult | None = None
    iteration = 0

    for iteration in range(1, max_iterations + 1):  # noqa: B007
        # 逐次実行: タスクを1つずつ処理
        for subtask in subtasks:
            worker_id = f"seq-worker-{subtask.task_id}"
            result = mock_execute(subtask, worker_id)
            results[subtask.task_id] = result

        # 品質ゲート
        all_results = list(results.values())
        quality = mock_quality_check(all_results, quality_threshold)

        if quality.passed:
            break

        # 不合格タスクに再指示フィードバックを付与
        failed_ids = set(quality.failed_task_ids)
        retry_subtasks: list[SubTask] = []
        for st in subtasks:
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
        subtasks = retry_subtasks

    elapsed = time.time() - start_time
    final_results = list(results.values())
    total_input = sum(r.input_tokens for r in final_results)
    total_output = sum(r.output_tokens for r in final_results)

    return {
        "status": "success" if (quality and quality.passed) else "partial",
        "iterations": iteration,
        "total_duration_seconds": round(elapsed, 3),
        "quality_score": quality.overall_score if quality else 0.0,
        "quality_passed": quality.passed if quality else False,
        "worker_count": len(final_results),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "worker_results": final_results,
    }


# ============================================================
# ベンチマーク実行
# ============================================================


@dataclass
class BenchmarkMetrics:
    """ベンチマーク集計メトリクス。"""

    mode: str
    runs: int
    avg_duration: float
    min_duration: float
    max_duration: float
    std_duration: float
    avg_quality: float
    min_quality: float
    max_quality: float
    avg_iterations: float
    pass_rate: float
    avg_tokens: float
    total_tokens: int


def run_benchmark(
    task_description: str,
    runs: int = BENCHMARK_RUNS,
    seed_base: int = SEED_BASE,
) -> tuple[BenchmarkMetrics, BenchmarkMetrics]:
    """逐次 vs 並列のベンチマークを実行する。

    Args:
        task_description: ベンチマーク対象のタスク説明。
        runs: 実行回数。
        seed_base: シードの基準値。

    Returns:
        (逐次メトリクス, 並列メトリクス) のタプル。
    """
    seq_results: list[dict[str, Any]] = []
    par_results: list[dict[str, Any]] = []

    print(f"\nベンチマーク実行中... ({runs} runs)")
    print("-" * 50)

    for i in range(runs):
        seed = seed_base + i

        # 逐次実行
        seq = run_sequential_pipeline(
            task_description,
            max_iterations=MAX_ITERATIONS,
            quality_threshold=QUALITY_THRESHOLD,
            seed=seed,
        )
        seq_results.append(seq)

        # 並列実行（LangGraph）
        par = run_parallel_pipeline(
            task_description,
            max_iterations=MAX_ITERATIONS,
            quality_threshold=QUALITY_THRESHOLD,
            seed=seed,
        )
        par_results.append(par)

        seq_mark = "✓" if seq["quality_passed"] else "✗"
        par_mark = "✓" if par["quality_passed"] else "✗"
        print(
            f"  Run {i + 1:2d}: "
            f"Seq={seq['total_duration_seconds']:.3f}s [{seq_mark}] "
            f"Par={par['total_duration_seconds']:.3f}s [{par_mark}]"
        )

    # メトリクス集計
    seq_metrics = _compute_metrics("sequential", seq_results)
    par_metrics = _compute_metrics("parallel", par_results)

    return seq_metrics, par_metrics


def _compute_metrics(mode: str, results: list[dict[str, Any]]) -> BenchmarkMetrics:
    """結果リストからメトリクスを集計する。"""
    durations = [r["total_duration_seconds"] for r in results]
    qualities = [r["quality_score"] for r in results]
    iterations = [r["iterations"] for r in results]
    tokens = [r["total_tokens"] for r in results]
    passed = [1 if r["quality_passed"] else 0 for r in results]

    return BenchmarkMetrics(
        mode=mode,
        runs=len(results),
        avg_duration=statistics.mean(durations),
        min_duration=min(durations),
        max_duration=max(durations),
        std_duration=statistics.stdev(durations) if len(durations) > 1 else 0.0,
        avg_quality=statistics.mean(qualities),
        min_quality=min(qualities),
        max_quality=max(qualities),
        avg_iterations=statistics.mean(iterations),
        pass_rate=statistics.mean(passed),
        avg_tokens=statistics.mean(tokens),
        total_tokens=sum(tokens),
    )


# ============================================================
# 結果出力
# ============================================================


def print_comparison(seq: BenchmarkMetrics, par: BenchmarkMetrics) -> None:
    """比較結果を整形出力する。"""
    print("\n" + "=" * 70)
    print("実験 005: 逐次実行 vs 並列実行 ベンチマーク比較")
    print("=" * 70)

    print(f"\n実行回数: {seq.runs}")
    print(f"品質閾値: {QUALITY_THRESHOLD}")
    print(f"最大イテレーション: {MAX_ITERATIONS}")

    print("\n--- パフォーマンス比較 ---")
    print(f"{'指標':20s} {'逐次':>15s} {'並列':>15s} {'差分':>15s}")
    print("-" * 70)

    # 実行時間
    dur_diff = par.avg_duration - seq.avg_duration
    dur_pct = (dur_diff / seq.avg_duration * 100) if seq.avg_duration > 0 else 0
    print(
        f"{'平均実行時間':20s} "
        f"{seq.avg_duration:>14.3f}s "
        f"{par.avg_duration:>14.3f}s "
        f"{dur_diff:>+14.3f}s ({dur_pct:+.1f}%)"
    )

    # 品質スコア
    q_diff = par.avg_quality - seq.avg_quality
    print(
        f"{'平均品質スコア':20s} {seq.avg_quality:>15.3f} {par.avg_quality:>15.3f} {q_diff:>+15.3f}"
    )
    print(
        f"{'最小品質スコア':20s} "
        f"{seq.min_quality:>15.3f} "
        f"{par.min_quality:>15.3f} "
        f"{par.min_quality - seq.min_quality:>+15.3f}"
    )

    # イテレーション
    iter_diff = par.avg_iterations - seq.avg_iterations
    print(
        f"{'平均イテレーション':20s} "
        f"{seq.avg_iterations:>15.1f} "
        f"{par.avg_iterations:>15.1f} "
        f"{iter_diff:>+15.1f}"
    )

    # 合格率
    print(
        f"{'品質ゲート合格率':20s} "
        f"{seq.pass_rate:>14.0%}  "
        f"{par.pass_rate:>14.0%}  "
        f"{par.pass_rate - seq.pass_rate:>+14.0%} "
    )

    # トークン
    tok_diff = par.avg_tokens - seq.avg_tokens
    tok_pct = (tok_diff / seq.avg_tokens * 100) if seq.avg_tokens > 0 else 0
    print(
        f"{'平均トークン数':20s} "
        f"{seq.avg_tokens:>14,.0f}  "
        f"{par.avg_tokens:>14,.0f}  "
        f"{tok_diff:>+14,.0f} ({tok_pct:+.1f}%)"
    )

    print("\n" + "=" * 70)


def generate_markdown_report(seq: BenchmarkMetrics, par: BenchmarkMetrics) -> str:
    """Markdown 形式のレポートを生成する。"""
    dur_diff_pct = (
        (par.avg_duration - seq.avg_duration) / seq.avg_duration * 100
        if seq.avg_duration > 0
        else 0
    )
    tok_diff_pct = (
        (par.avg_tokens - seq.avg_tokens) / seq.avg_tokens * 100 if seq.avg_tokens > 0 else 0
    )

    # 差分値を事前計算（テンプレートの行長制限対応）
    q_avg_diff = par.avg_quality - seq.avg_quality
    q_min_diff = par.min_quality - seq.min_quality
    q_max_diff = par.max_quality - seq.max_quality
    iter_diff = par.avg_iterations - seq.avg_iterations
    pr_diff = par.pass_rate - seq.pass_rate

    report = f"""## ベンチマーク結果

### 実行条件

| パラメータ | 値 |
|---|---|
| 実行回数 | {seq.runs} |
| 品質閾値 | {QUALITY_THRESHOLD} |
| 最大イテレーション | {MAX_ITERATIONS} |
| ワーカー数 | 5 |
| モデル | claude-sonnet-4-20250514, codex-5.3 |

### パフォーマンス比較

| 指標 | 逐次 | 並列 | 差分 |
|---|---|---|---|
| 平均実行時間 | {seq.avg_duration:.3f}s | {par.avg_duration:.3f}s | {dur_diff_pct:+.1f}% |
| 実行時間 σ | {seq.std_duration:.3f}s | {par.std_duration:.3f}s | — |
| 平均品質 | {seq.avg_quality:.3f} | {par.avg_quality:.3f} | {q_avg_diff:+.3f} |
| 最小品質 | {seq.min_quality:.3f} | {par.min_quality:.3f} | {q_min_diff:+.3f} |
| 最大品質 | {seq.max_quality:.3f} | {par.max_quality:.3f} | {q_max_diff:+.3f} |
| 平均イテレーション | {seq.avg_iterations:.1f} | {par.avg_iterations:.1f} | {iter_diff:+.1f} |
| 合格率 | {seq.pass_rate:.0%} | {par.pass_rate:.0%} | {pr_diff:+.0%} |
| 平均トークン | {seq.avg_tokens:,.0f} | {par.avg_tokens:,.0f} | {tok_diff_pct:+.1f}% |
| 累計トークン | {seq.total_tokens:,} | {par.total_tokens:,} | — |
"""
    return report


# ============================================================
# メイン
# ============================================================


def main() -> None:
    """メインエントリポイント。"""
    task = (
        "ML 特徴量エンジニアリング: 株式データから価格・出来高・モメンタム・"
        "ボラティリティ・クロスセクションの5カテゴリの特徴量を実装する"
    )

    print("逐次 vs 並列 ベンチマーク比較")
    print(f"タスク: {task}")

    seq_metrics, par_metrics = run_benchmark(task, runs=BENCHMARK_RUNS)

    print_comparison(seq_metrics, par_metrics)

    # Markdown レポート生成
    report = generate_markdown_report(seq_metrics, par_metrics)
    print("\n--- Markdown レポート（docs 用）---")
    print(report)


if __name__ == "__main__":
    # Pydantic v1 互換警告を抑制（CLI 実行時のみ。テスト環境は pyproject.toml で制御）
    import warnings

    warnings.filterwarnings("ignore", message="Core Pydantic V1")
    main()
