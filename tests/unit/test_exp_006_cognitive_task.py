"""実験 006: 思考的タスクベンチマークのテスト。

exp_006_cognitive_task_benchmark.py の各関数・パイプラインを検証する。

テスト対象:
    - 評価指標計算（diversity / depth / coverage / actionability / composite）
    - タスク生成（make_task）
    - 逐次実行パイプライン（run_sequential_cognitive_pipeline）
    - 並列実行パイプライン（run_parallel_cognitive_pipeline）
    - ベンチマーク実行（run_benchmark）
    - 逐次 vs 並列の特性比較（深さ/多様性の傾向）
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

# experiments/parallel-execution はハイフン含みのため sys.path 経由でインポート
_EXP_DIR = Path(__file__).resolve().parents[2] / "experiments" / "parallel-execution"
if str(_EXP_DIR) not in sys.path:
    sys.path.insert(0, str(_EXP_DIR))

exp_006 = importlib.import_module("exp_006_cognitive_task_benchmark")

# 公開 API
CognitiveTask = exp_006.CognitiveTask
CognitivePerspective = exp_006.CognitivePerspective
CognitiveEvalResult = exp_006.CognitiveEvalResult
TASK_TYPES = exp_006.TASK_TYPES
EXPECTED_KEYWORDS = exp_006.EXPECTED_KEYWORDS
CATEGORY_POOL = exp_006.CATEGORY_POOL
make_task = exp_006.make_task
compute_diversity = exp_006.compute_diversity
compute_depth = exp_006.compute_depth
compute_coverage = exp_006.compute_coverage
compute_actionability = exp_006.compute_actionability
compute_composite = exp_006.compute_composite
mock_analyze_sequential = exp_006.mock_analyze_sequential
mock_analyze_parallel = exp_006.mock_analyze_parallel
run_sequential_cognitive_pipeline = exp_006.run_sequential_cognitive_pipeline
run_parallel_cognitive_pipeline = exp_006.run_parallel_cognitive_pipeline
run_benchmark = exp_006.run_benchmark


# ============================================================
# ヘルパー
# ============================================================


def _make_perspective(
    perspective_id: str = "p-001",
    agent_id: str = "agent-1",
    category: str = "性能",
    detail_items: list[str] | None = None,
    is_actionable: bool = True,
    references_previous: bool = False,
) -> Any:
    """テスト用 CognitivePerspective を生成する。"""
    return CognitivePerspective(
        perspective_id=perspective_id,
        agent_id=agent_id,
        model_used="mock-model",
        category=category,
        content=f"{category}に関する分析",
        detail_items=detail_items if detail_items is not None else ["詳細1", "詳細2"],
        is_actionable=is_actionable,
        references_previous=references_previous,
    )


# ============================================================
# 評価指標計算テスト
# ============================================================


class TestComputeDiversity:
    """compute_diversity のテスト。"""

    def test_empty_returns_zero(self) -> None:
        """空リストは 0.0 を返すこと。"""
        assert compute_diversity([]) == 0.0

    def test_all_unique_returns_one(self) -> None:
        """全観点がユニークカテゴリなら 1.0 を返すこと。"""
        perspectives = [
            _make_perspective("p-1", category="性能"),
            _make_perspective("p-2", category="保守性"),
            _make_perspective("p-3", category="セキュリティ"),
        ]
        assert compute_diversity(perspectives) == pytest.approx(1.0)

    def test_all_same_category(self) -> None:
        """全観点が同一カテゴリなら 1/N を返すこと。"""
        perspectives = [_make_perspective(f"p-{i}", category="性能") for i in range(4)]
        assert compute_diversity(perspectives) == pytest.approx(1 / 4)

    def test_partial_uniqueness(self) -> None:
        """一部重複がある場合の多様性スコア。"""
        perspectives = [
            _make_perspective("p-1", category="性能"),
            _make_perspective("p-2", category="性能"),
            _make_perspective("p-3", category="保守性"),
        ]
        # ユニーク 2 / 総数 3
        assert compute_diversity(perspectives) == pytest.approx(2 / 3)


class TestComputeDepth:
    """compute_depth のテスト。"""

    def test_empty_returns_zero(self) -> None:
        """空リストは 0.0 を返すこと。"""
        assert compute_depth([]) == 0.0

    def test_single_no_details(self) -> None:
        """detail_items が空の場合、深さ 0.0 を返すこと。"""
        p = _make_perspective(detail_items=[])
        assert compute_depth([p]) == pytest.approx(0.0)

    def test_average_depth(self) -> None:
        """詳細項目数の平均が正しいこと。"""
        perspectives = [
            _make_perspective("p-1", detail_items=["a", "b", "c"]),
            _make_perspective("p-2", detail_items=["x"]),
        ]
        # (3 + 1) / 2 = 2.0
        assert compute_depth(perspectives) == pytest.approx(2.0)


class TestComputeCoverage:
    """compute_coverage のテスト。"""

    def test_empty_perspectives_returns_zero(self) -> None:
        """観点が空なら 0.0 を返すこと。"""
        assert compute_coverage([], ["パフォーマンス"]) == 0.0

    def test_empty_keywords_returns_zero(self) -> None:
        """期待キーワードが空なら 0.0 を返すこと。"""
        p = _make_perspective()
        assert compute_coverage([p], []) == 0.0

    def test_all_keywords_covered(self) -> None:
        """全キーワードが含まれる場合、1.0 を返すこと。"""
        p = CognitivePerspective(
            perspective_id="p-1",
            agent_id="agent-1",
            model_used="mock",
            category="性能",
            content="パフォーマンス スケーラビリティ",
            detail_items=["保守性について", "セキュリティに関する考察", "テスト容易性の検討"],
            is_actionable=True,
            references_previous=False,
        )
        keywords = ["パフォーマンス", "スケーラビリティ", "保守性", "セキュリティ", "テスト容易性"]
        assert compute_coverage([p], keywords) == pytest.approx(1.0)

    def test_partial_coverage(self) -> None:
        """一部のキーワードのみカバーされた場合。"""
        p = _make_perspective(detail_items=["パフォーマンス改善", "他の詳細"])
        keywords = ["パフォーマンス", "セキュリティ"]
        # 1 / 2 = 0.5
        assert compute_coverage([p], keywords) == pytest.approx(0.5)

    def test_case_insensitive(self) -> None:
        """キーワード照合は大文字小文字を無視すること。"""
        p = _make_perspective(detail_items=["PERFORMANCE issue"])
        assert compute_coverage([p], ["performance"]) == pytest.approx(1.0)


class TestComputeActionability:
    """compute_actionability のテスト。"""

    def test_empty_returns_zero(self) -> None:
        """空リストは 0.0 を返すこと。"""
        assert compute_actionability([]) == 0.0

    def test_all_actionable(self) -> None:
        """全観点が実装可能なら 1.0 を返すこと。"""
        perspectives = [_make_perspective(is_actionable=True) for _ in range(3)]
        assert compute_actionability(perspectives) == pytest.approx(1.0)

    def test_none_actionable(self) -> None:
        """実装可能な観点がゼロなら 0.0 を返すこと。"""
        perspectives = [_make_perspective(is_actionable=False) for _ in range(3)]
        assert compute_actionability(perspectives) == pytest.approx(0.0)

    def test_partial_actionable(self) -> None:
        """一部実装可能な場合の実用性スコア。"""
        perspectives = [
            _make_perspective(is_actionable=True),
            _make_perspective(is_actionable=False),
            _make_perspective(is_actionable=True),
        ]
        assert compute_actionability(perspectives) == pytest.approx(2 / 3)


class TestComputeComposite:
    """compute_composite のテスト。"""

    def test_all_perfect(self) -> None:
        """全指標が最高値なら 1.0 を返すこと（deep=6 を正規化の最大値とする）。"""
        score = compute_composite(1.0, 6.0, 1.0, 1.0)
        assert score == pytest.approx(1.0)

    def test_all_zero(self) -> None:
        """全指標がゼロなら 0.0 を返すこと。"""
        score = compute_composite(0.0, 0.0, 0.0, 0.0)
        assert score == pytest.approx(0.0)

    def test_depth_normalized(self) -> None:
        """深さスコアが 6 を超えても 1.0 でクリップされること。"""
        score_normal = compute_composite(1.0, 6.0, 1.0, 1.0)
        score_over = compute_composite(1.0, 100.0, 1.0, 1.0)
        assert score_normal == pytest.approx(score_over)

    def test_average_weights(self) -> None:
        """コンポジットが 4 指標の単純平均であること。"""
        # diversity=0.4, depth=3.0(→0.5), coverage=0.6, actionability=0.8
        # composite = (0.4 + 0.5 + 0.6 + 0.8) / 4 = 0.575
        score = compute_composite(0.4, 3.0, 0.6, 0.8)
        assert score == pytest.approx(0.575)


# ============================================================
# タスク生成テスト
# ============================================================


class TestMakeTask:
    """make_task のテスト。"""

    @pytest.mark.parametrize("task_type", TASK_TYPES)
    def test_returns_cognitive_task(self, task_type: str) -> None:
        """全タスク種別で CognitiveTask インスタンスが返ること。"""
        task = make_task(task_type)
        assert isinstance(task, CognitiveTask)
        assert task.task_type == task_type

    @pytest.mark.parametrize("task_type", TASK_TYPES)
    def test_has_expected_keywords(self, task_type: str) -> None:
        """全タスク種別で expected_keywords が設定されていること。"""
        task = make_task(task_type)
        assert len(task.expected_keywords) > 0

    @pytest.mark.parametrize("task_type", TASK_TYPES)
    def test_description_and_context_non_empty(self, task_type: str) -> None:
        """description / context が空でないこと。"""
        task = make_task(task_type)
        assert task.description.strip()
        assert task.context.strip()


# ============================================================
# 逐次実行パイプラインテスト
# ============================================================


class TestSequentialPipeline:
    """run_sequential_cognitive_pipeline のテスト。"""

    def test_result_keys(self) -> None:
        """結果辞書に必要なキーが含まれること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=2, seed=42)
        expected_keys = {
            "mode",
            "task_id",
            "task_type",
            "perspectives",
            "num_perspectives",
            "diversity",
            "depth",
            "coverage",
            "actionability",
            "composite_score",
            "duration_seconds",
            "total_tokens",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_mode_is_sequential(self) -> None:
        """mode フィールドが 'sequential' であること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=2, seed=42)
        assert result["mode"] == "sequential"

    def test_num_perspectives_equals_num_agents(self) -> None:
        """生成された観点数がエージェント数と一致すること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=3, seed=42)
        assert result["num_perspectives"] == 3
        assert len(result["perspectives"]) == 3

    def test_scores_in_valid_range(self) -> None:
        """全スコアが 0.0〜1.0 の範囲内であること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=3, seed=42)
        for key in ("diversity", "coverage", "actionability", "composite_score"):
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"

    def test_depth_is_non_negative(self) -> None:
        """depth スコアが非負であること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=3, seed=42)
        assert result["depth"] >= 0.0

    def test_reproducibility(self) -> None:
        """同一シードで再現性があること。"""
        task = make_task("issue_analysis")
        r1 = run_sequential_cognitive_pipeline(task, num_agents=3, seed=42)
        r2 = run_sequential_cognitive_pipeline(task, num_agents=3, seed=42)
        assert r1["diversity"] == pytest.approx(r2["diversity"])
        assert r1["depth"] == pytest.approx(r2["depth"])
        assert r1["composite_score"] == pytest.approx(r2["composite_score"])

    def test_later_perspectives_reference_previous(self) -> None:
        """後半の観点が前の観点を参照していること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=5, seed=42)
        perspectives: list[Any] = result["perspectives"]
        # 最初の観点は前の観点がない
        assert perspectives[0].references_previous is False
        # 2番目以降は前の観点を参照する可能性がある（確率的だが大半が参照）
        later_refs = [p.references_previous for p in perspectives[1:]]
        assert any(later_refs), "後続の観点のうち少なくとも1つが前の観点を参照すること"

    def test_duration_positive(self) -> None:
        """実行時間が正であること。"""
        task = make_task("issue_analysis")
        result = run_sequential_cognitive_pipeline(task, num_agents=2, seed=42)
        assert result["duration_seconds"] > 0.0


# ============================================================
# 並列実行パイプラインテスト
# ============================================================


class TestParallelPipeline:
    """run_parallel_cognitive_pipeline のテスト。"""

    def test_result_keys(self) -> None:
        """結果辞書に必要なキーが含まれること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        expected_keys = {
            "mode",
            "task_id",
            "task_type",
            "perspectives",
            "num_perspectives",
            "diversity",
            "depth",
            "coverage",
            "actionability",
            "composite_score",
            "duration_seconds",
            "total_tokens",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_mode_is_parallel(self) -> None:
        """mode フィールドが 'parallel' であること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        assert result["mode"] == "parallel"

    def test_num_perspectives_equals_num_agents_constant(self) -> None:
        """生成された観点数がモジュール定数 NUM_AGENTS と一致すること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        assert result["num_perspectives"] == exp_006.NUM_AGENTS

    def test_scores_in_valid_range(self) -> None:
        """全スコアが 0.0〜1.0 の範囲内であること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        for key in ("diversity", "coverage", "actionability", "composite_score"):
            assert 0.0 <= result[key] <= 1.0, f"{key} out of range: {result[key]}"

    def test_depth_is_non_negative(self) -> None:
        """depth スコアが非負であること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        assert result["depth"] >= 0.0

    def test_reproducibility(self) -> None:
        """同一シードで再現性があること。"""
        task = make_task("issue_analysis")
        r1 = run_parallel_cognitive_pipeline(task, seed=42)
        r2 = run_parallel_cognitive_pipeline(task, seed=42)
        assert r1["diversity"] == pytest.approx(r2["diversity"])
        assert r1["depth"] == pytest.approx(r2["depth"])
        assert r1["composite_score"] == pytest.approx(r2["composite_score"])

    def test_parallel_perspectives_do_not_reference_previous(self) -> None:
        """並列実行の全観点が前の観点を参照しないこと。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        for p in result["perspectives"]:
            assert p.references_previous is False, f"{p.agent_id} が前の観点を参照している"

    def test_duration_positive(self) -> None:
        """実行時間が正であること。"""
        task = make_task("issue_analysis")
        result = run_parallel_cognitive_pipeline(task, seed=42)
        assert result["duration_seconds"] > 0.0


# ============================================================
# 逐次 vs 並列の特性比較テスト
# ============================================================


class TestSequentialVsParallelCharacteristics:
    """逐次実行と並列実行の設計上の特性が現れることを検証する。

    モックの設計に基づく統計的傾向を検証する。
    確率的挙動のため複数シードの平均で比較する。
    """

    NUM_SEEDS = 10  # 統計的信頼性のための実行回数

    def _avg_metric(
        self,
        task: Any,
        mode: str,
        metric: str,
        seeds: int = 10,
    ) -> float:
        """指定指標の平均値を算出する。"""
        values: list[float] = []
        for i in range(seeds):
            if mode == "sequential":
                r = run_sequential_cognitive_pipeline(task, seed=100 + i)
            else:
                r = run_parallel_cognitive_pipeline(task, seed=100 + i)
            values.append(float(r[metric]))
        return sum(values) / len(values)

    def test_parallel_higher_diversity(self) -> None:
        """並列実行は逐次実行より多様性が高い傾向にあること。"""
        task = make_task("issue_analysis")
        seq_div = self._avg_metric(task, "sequential", "diversity")
        par_div = self._avg_metric(task, "parallel", "diversity")
        assert par_div > seq_div, (
            f"並列多様性 {par_div:.3f} が逐次多様性 {seq_div:.3f} を上回ること"
        )

    def test_sequential_higher_depth(self) -> None:
        """逐次実行は並列実行より深さが高い傾向にあること。"""
        task = make_task("issue_analysis")
        seq_depth = self._avg_metric(task, "sequential", "depth")
        par_depth = self._avg_metric(task, "parallel", "depth")
        assert seq_depth > par_depth, (
            f"逐次深さ {seq_depth:.3f} が並列深さ {par_depth:.3f} を上回ること"
        )

    def test_parallel_faster_execution(self) -> None:
        """並列実行は逐次実行より実行時間が短い傾向にあること。"""
        task = make_task("issue_analysis")
        seq_dur = self._avg_metric(task, "sequential", "duration_seconds")
        par_dur = self._avg_metric(task, "parallel", "duration_seconds")
        assert par_dur < seq_dur, (
            f"並列実行時間 {par_dur:.3f}s が逐次実行時間 {seq_dur:.3f}s より短いこと"
        )


# ============================================================
# ベンチマーク全体テスト
# ============================================================


class TestRunBenchmark:
    """run_benchmark のテスト。"""

    def test_result_structure(self) -> None:
        """ベンチマーク結果に必要なキーが含まれること。"""
        result = run_benchmark("issue_analysis")
        assert "task_type" in result
        assert "runs" in result
        assert "sequential" in result
        assert "parallel" in result

    def test_stats_keys_present(self) -> None:
        """各指標に mean / stdev / min / max が含まれること。"""
        result = run_benchmark("issue_analysis")
        for mode in ("sequential", "parallel"):
            for metric in (
                "duration",
                "diversity",
                "depth",
                "coverage",
                "actionability",
                "composite",
                "tokens",
            ):
                stats = result[mode][metric]
                assert "mean" in stats, f"{mode}.{metric} に mean がない"
                assert "stdev" in stats
                assert "min" in stats
                assert "max" in stats

    def test_runs_count_matches_constant(self) -> None:
        """runs フィールドがモジュール定数 BENCHMARK_RUNS と一致すること。"""
        result = run_benchmark("issue_analysis")
        assert result["runs"] == exp_006.BENCHMARK_RUNS

    @pytest.mark.parametrize("task_type", TASK_TYPES)
    def test_all_task_types_execute_without_error(self, task_type: str) -> None:
        """全タスク種別でエラーなく実行できること。"""
        result = run_benchmark(task_type)
        assert result["task_type"] == task_type
        assert result["sequential"]["composite"]["mean"] >= 0.0
        assert result["parallel"]["composite"]["mean"] >= 0.0

    def test_mean_scores_in_valid_range(self) -> None:
        """全ての mean スコアが妥当な範囲内であること。"""
        result = run_benchmark("issue_analysis")
        for mode in ("sequential", "parallel"):
            for metric in ("diversity", "coverage", "actionability", "composite"):
                mean = result[mode][metric]["mean"]
                assert 0.0 <= mean <= 1.0, f"{mode}.{metric}.mean = {mean} が範囲外"
