"""並列実行フレームワークの型定義テスト。

parallel モジュールの型定義が正しく機能することを検証する。
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from orchestration_lab.core.types import AgentStatus
from orchestration_lab.parallel.types import (
    ModelConfig,
    ModelRole,
    ParallelExecutionConfig,
    ParallelExecutionResult,
    QualityVerdict,
    TokenUsage,
    WorkerResult,
    WorkerTask,
)


class TestModelRole:
    """ModelRole 列挙型のテスト。"""

    def test_commander_value(self) -> None:
        """COMMANDER の値が正しいこと。"""
        assert ModelRole.COMMANDER.value == "commander"

    def test_worker_value(self) -> None:
        """WORKER の値が正しいこと。"""
        assert ModelRole.WORKER.value == "worker"


class TestModelConfig:
    """ModelConfig のテスト。"""

    def test_creation_with_defaults(self) -> None:
        """デフォルト値でのインスタンス生成。"""
        config = ModelConfig(model_id="claude-opus-4-20250514", role=ModelRole.COMMANDER)
        assert config.model_id == "claude-opus-4-20250514"
        assert config.role == ModelRole.COMMANDER
        assert config.max_tokens == 4096
        assert config.temperature == 0.0

    def test_creation_with_custom_values(self) -> None:
        """カスタム値でのインスタンス生成。"""
        config = ModelConfig(
            model_id="claude-sonnet-4-20250514",
            role=ModelRole.WORKER,
            max_tokens=8192,
            temperature=0.3,
        )
        assert config.model_id == "claude-sonnet-4-20250514"
        assert config.role == ModelRole.WORKER
        assert config.max_tokens == 8192
        assert config.temperature == 0.3


class TestTokenUsage:
    """TokenUsage のテスト。"""

    def test_default_values(self) -> None:
        """デフォルト値が 0 であること。"""
        usage = TokenUsage()
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.total_tokens == 0

    def test_total_tokens_calculation(self) -> None:
        """合計トークン数の計算が正しいこと。"""
        usage = TokenUsage(input_tokens=1000, output_tokens=500)
        assert usage.total_tokens == 1500

    def test_frozen(self) -> None:
        """frozen dataclass のため属性変更不可であること。"""
        usage = TokenUsage(input_tokens=100, output_tokens=50)
        with pytest.raises(FrozenInstanceError):
            usage.input_tokens = 200  # type: ignore[misc]


class TestWorkerTask:
    """WorkerTask のテスト。"""

    def test_creation_minimal(self) -> None:
        """必須フィールドのみでのインスタンス生成。"""
        task = WorkerTask(task_id="task-001", description="移動平均を計算する関数を実装")
        assert task.task_id == "task-001"
        assert task.description == "移動平均を計算する関数を実装"
        assert task.context == ""
        assert task.assigned_model == ""
        assert task.priority == 0

    def test_creation_full(self) -> None:
        """全フィールド指定でのインスタンス生成。"""
        task = WorkerTask(
            task_id="task-002",
            description="RSI を計算する関数を実装",
            context="既存の indicators.py に追加する",
            assigned_model="claude-sonnet-4-20250514",
            priority=1,
        )
        assert task.task_id == "task-002"
        assert task.assigned_model == "claude-sonnet-4-20250514"
        assert task.priority == 1


class TestWorkerResult:
    """WorkerResult のテスト。"""

    def test_creation_success(self) -> None:
        """成功結果のインスタンス生成。"""
        result = WorkerResult(
            task_id="task-001",
            worker_id="worker-001",
            model_used="claude-sonnet-4-20250514",
            status=AgentStatus.SUCCESS,
            output="def moving_average(data, window): ...",
            files_changed=["src/features/price.py"],
            duration_seconds=45.2,
            token_usage=TokenUsage(input_tokens=2000, output_tokens=800),
        )
        assert result.task_id == "task-001"
        assert result.status == AgentStatus.SUCCESS
        assert result.files_changed == ["src/features/price.py"]
        assert result.token_usage.total_tokens == 2800

    def test_creation_failure(self) -> None:
        """失敗結果のインスタンス生成。"""
        result = WorkerResult(
            task_id="task-002",
            worker_id="worker-002",
            model_used="codex-5.3",
            status=AgentStatus.FAILURE,
            output="Error: ...",
        )
        assert result.status == AgentStatus.FAILURE
        assert result.files_changed == []
        assert result.duration_seconds == 0.0


class TestQualityVerdict:
    """QualityVerdict のテスト。"""

    def test_passed_verdict(self) -> None:
        """品質通過の判定。"""
        verdict = QualityVerdict(passed=True, score=0.92, iteration=2)
        assert verdict.passed is True
        assert verdict.score == 0.92
        assert verdict.iteration == 2

    def test_failed_verdict_with_feedback(self) -> None:
        """品質不合格のフィードバック付き判定。"""
        verdict = QualityVerdict(
            passed=False,
            score=0.65,
            feedback={
                "task-001": "テストが不足している",
                "task-003": "型アノテーションが欠けている",
            },
            iteration=1,
        )
        assert verdict.passed is False
        assert len(verdict.feedback) == 2
        assert "task-001" in verdict.feedback


class TestParallelExecutionConfig:
    """ParallelExecutionConfig のテスト。"""

    def test_default_values(self) -> None:
        """デフォルト設定値の検証。"""
        config = ParallelExecutionConfig()
        assert config.min_workers == 3
        assert config.max_workers == 10
        assert config.default_workers == 5
        assert config.quality_threshold == 0.8
        assert config.max_iterations == 5
        assert config.worker_timeout_seconds == 600.0
        assert config.pipeline_timeout_seconds == 3600.0

    def test_determine_worker_count_within_range(self) -> None:
        """ワーカー数がレンジ内の場合。"""
        config = ParallelExecutionConfig(min_workers=3, max_workers=10)
        assert config.determine_worker_count(5) == 5

    def test_determine_worker_count_below_min(self) -> None:
        """サブタスク数が最小値未満の場合、最小値を返す。"""
        config = ParallelExecutionConfig(min_workers=3, max_workers=10)
        assert config.determine_worker_count(1) == 3

    def test_determine_worker_count_above_max(self) -> None:
        """サブタスク数が最大値超過の場合、最大値を返す。"""
        config = ParallelExecutionConfig(min_workers=3, max_workers=10)
        assert config.determine_worker_count(15) == 10

    def test_determine_worker_count_exact_min(self) -> None:
        """サブタスク数が最小値と同じ場合。"""
        config = ParallelExecutionConfig(min_workers=3, max_workers=10)
        assert config.determine_worker_count(3) == 3

    def test_determine_worker_count_exact_max(self) -> None:
        """サブタスク数が最大値と同じ場合。"""
        config = ParallelExecutionConfig(min_workers=3, max_workers=10)
        assert config.determine_worker_count(10) == 10


class TestParallelExecutionResult:
    """ParallelExecutionResult のテスト。"""

    def test_creation_success(self) -> None:
        """成功結果の生成。"""
        worker_result = WorkerResult(
            task_id="task-001",
            worker_id="worker-001",
            model_used="claude-sonnet-4-20250514",
            status=AgentStatus.SUCCESS,
            output="実装コード",
            duration_seconds=30.0,
            token_usage=TokenUsage(input_tokens=1000, output_tokens=500),
        )
        verdict = QualityVerdict(passed=True, score=0.95)
        result = ParallelExecutionResult(
            status=AgentStatus.SUCCESS,
            iterations=2,
            total_duration_seconds=120.5,
            worker_results=[worker_result],
            final_verdict=verdict,
            total_token_usage=TokenUsage(input_tokens=5000, output_tokens=2000),
        )
        assert result.status == AgentStatus.SUCCESS
        assert result.iterations == 2
        assert len(result.worker_results) == 1
        assert result.final_verdict.passed is True
        assert result.total_token_usage.total_tokens == 7000

    def test_creation_defaults(self) -> None:
        """デフォルト値での生成。"""
        result = ParallelExecutionResult(
            status=AgentStatus.FAILURE,
            iterations=0,
            total_duration_seconds=0.0,
        )
        assert result.worker_results == []
        assert result.final_verdict.passed is False
        assert result.total_token_usage.total_tokens == 0
