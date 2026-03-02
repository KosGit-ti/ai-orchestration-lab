"""実験 005: 逐次 vs 並列ベンチマークのテスト。

exp_005_sequential_vs_parallel.py の逐次パイプライン、
ベンチマーク集計、レポート生成を検証する。
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

exp_005 = importlib.import_module("exp_005_sequential_vs_parallel")

run_sequential_pipeline = exp_005.run_sequential_pipeline
run_benchmark = exp_005.run_benchmark
_compute_metrics = exp_005._compute_metrics
generate_markdown_report = exp_005.generate_markdown_report
BenchmarkMetrics = exp_005.BenchmarkMetrics


# ============================================================
# 逐次パイプラインテスト
# ============================================================


class TestRunSequentialPipeline:
    """run_sequential_pipeline のテスト。"""

    def test_basic_execution(self) -> None:
        """基本実行が成功すること。"""
        result = run_sequential_pipeline("テストタスク", seed=42)
        assert result["status"] in ("success", "partial")
        assert result["worker_count"] > 0
        assert result["total_duration_seconds"] > 0
        assert result["total_tokens"] >= 0

    def test_result_keys(self) -> None:
        """結果辞書に必要なキーが含まれること。"""
        result = run_sequential_pipeline("テスト", seed=42)
        expected_keys = {
            "status",
            "iterations",
            "total_duration_seconds",
            "quality_score",
            "quality_passed",
            "worker_count",
            "total_input_tokens",
            "total_output_tokens",
            "total_tokens",
            "worker_results",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_reproducibility_with_seed(self) -> None:
        """同一シードで再現性があること。"""
        r1 = run_sequential_pipeline("テスト", seed=42)
        r2 = run_sequential_pipeline("テスト", seed=42)
        assert r1["quality_score"] == r2["quality_score"]
        assert r1["iterations"] == r2["iterations"]
        assert r1["worker_count"] == r2["worker_count"]

    def test_low_threshold_passes(self) -> None:
        """低い閾値なら合格すること。"""
        result = run_sequential_pipeline(
            "テスト",
            quality_threshold=0.1,
            seed=42,
        )
        assert result["quality_passed"] is True

    def test_max_iterations_respected(self) -> None:
        """最大イテレーション数が守られること。"""
        result = run_sequential_pipeline(
            "テスト",
            max_iterations=1,
            quality_threshold=0.99,
            seed=42,
        )
        assert result["iterations"] <= 1


# ============================================================
# メトリクス集計テスト
# ============================================================


class TestComputeMetrics:
    """_compute_metrics のテスト。"""

    def test_basic_computation(self) -> None:
        """基本的なメトリクス集計。"""
        results = [
            {
                "total_duration_seconds": 1.0,
                "quality_score": 0.8,
                "iterations": 2,
                "total_tokens": 1000,
                "quality_passed": True,
            },
            {
                "total_duration_seconds": 2.0,
                "quality_score": 0.9,
                "iterations": 1,
                "total_tokens": 1500,
                "quality_passed": True,
            },
        ]
        metrics = _compute_metrics("test", results)
        assert metrics.mode == "test"
        assert metrics.runs == 2
        assert metrics.avg_duration == pytest.approx(1.5)
        assert metrics.min_duration == pytest.approx(1.0)
        assert metrics.max_duration == pytest.approx(2.0)
        assert metrics.avg_quality == pytest.approx(0.85)
        assert metrics.pass_rate == pytest.approx(1.0)
        assert metrics.total_tokens == 2500

    def test_mixed_pass_rate(self) -> None:
        """合格/不合格混在時の合格率。"""
        results = [
            {
                "total_duration_seconds": 1.0,
                "quality_score": 0.9,
                "iterations": 1,
                "total_tokens": 1000,
                "quality_passed": True,
            },
            {
                "total_duration_seconds": 2.0,
                "quality_score": 0.5,
                "iterations": 3,
                "total_tokens": 2000,
                "quality_passed": False,
            },
        ]
        metrics = _compute_metrics("test", results)
        assert metrics.pass_rate == pytest.approx(0.5)

    def test_single_result(self) -> None:
        """1件のみでも集計できること。"""
        results = [
            {
                "total_duration_seconds": 1.5,
                "quality_score": 0.85,
                "iterations": 2,
                "total_tokens": 1200,
                "quality_passed": True,
            },
        ]
        metrics = _compute_metrics("single", results)
        assert metrics.runs == 1
        assert metrics.std_duration == 0.0
        assert metrics.avg_quality == pytest.approx(0.85)


# ============================================================
# ベンチマーク実行テスト
# ============================================================


class TestRunBenchmark:
    """run_benchmark のテスト。"""

    def test_returns_two_metrics(self) -> None:
        """逐次・並列の2つのメトリクスを返すこと。"""
        seq, par = run_benchmark("テスト", runs=2, seed_base=200)
        assert isinstance(seq, BenchmarkMetrics)
        assert isinstance(par, BenchmarkMetrics)
        assert seq.mode == "sequential"
        assert par.mode == "parallel"
        assert seq.runs == 2
        assert par.runs == 2

    def test_metrics_populated(self) -> None:
        """メトリクスの値が妥当であること。"""
        seq, par = run_benchmark("テスト", runs=3, seed_base=300)
        assert seq.avg_duration > 0
        assert par.avg_duration > 0
        assert 0.0 <= seq.avg_quality <= 1.0
        assert 0.0 <= par.avg_quality <= 1.0
        assert seq.total_tokens > 0
        assert par.total_tokens > 0


# ============================================================
# レポート生成テスト
# ============================================================


class TestGenerateMarkdownReport:
    """generate_markdown_report のテスト。"""

    @pytest.fixture
    def sample_metrics(self) -> tuple[Any, Any]:
        """テスト用メトリクスペア。"""
        seq = BenchmarkMetrics(
            mode="sequential",
            runs=10,
            avg_duration=0.5,
            min_duration=0.3,
            max_duration=0.7,
            std_duration=0.1,
            avg_quality=0.85,
            min_quality=0.7,
            max_quality=0.95,
            avg_iterations=1.5,
            pass_rate=0.9,
            avg_tokens=5000.0,
            total_tokens=50000,
        )
        par = BenchmarkMetrics(
            mode="parallel",
            runs=10,
            avg_duration=0.15,
            min_duration=0.1,
            max_duration=0.2,
            std_duration=0.03,
            avg_quality=0.88,
            min_quality=0.75,
            max_quality=0.97,
            avg_iterations=1.3,
            pass_rate=1.0,
            avg_tokens=5200.0,
            total_tokens=52000,
        )
        return seq, par

    def test_contains_markdown_headers(self, sample_metrics: tuple[Any, Any]) -> None:
        """Markdown ヘッダーが含まれること。"""
        seq, par = sample_metrics
        report = generate_markdown_report(seq, par)
        assert "## ベンチマーク結果" in report
        assert "### 実行条件" in report
        assert "### パフォーマンス比較" in report

    def test_contains_table(self, sample_metrics: tuple[Any, Any]) -> None:
        """テーブルが含まれること。"""
        seq, par = sample_metrics
        report = generate_markdown_report(seq, par)
        assert "| 指標 |" in report
        assert "平均実行時間" in report
        assert "合格率" in report

    def test_is_valid_string(self, sample_metrics: tuple[Any, Any]) -> None:
        """文字列として妥当であること。"""
        seq, par = sample_metrics
        report = generate_markdown_report(seq, par)
        assert isinstance(report, str)
        assert len(report) > 100
