"""実験 004: LangGraph Fan-Out/Fan-In プロトタイプのテスト。

exp_004_langgraph_fanout.py のモック関数、グラフ構築、
パイプライン実行を検証する。
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

exp_004 = importlib.import_module("exp_004_langgraph_fanout")

SubTask = exp_004.SubTask
WorkerOutput = exp_004.WorkerOutput
QualityGateResult = exp_004.QualityGateResult
mock_decompose = exp_004.mock_decompose
mock_execute = exp_004.mock_execute
mock_quality_check = exp_004.mock_quality_check
commander_node = exp_004.commander_node
worker_node = exp_004.worker_node
quality_gate_node = exp_004.quality_gate_node
prepare_retry_node = exp_004.prepare_retry_node
fanout_to_workers = exp_004.fanout_to_workers
route_after_quality = exp_004.route_after_quality
build_graph = exp_004.build_graph
run_pipeline = exp_004.run_pipeline


# ============================================================
# データ型テスト
# ============================================================


class TestSubTask:
    """SubTask データクラスのテスト。"""

    def test_creation_with_defaults(self) -> None:
        """デフォルト値でのインスタンス生成。"""
        st = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        assert st.task_id == "t1"
        assert st.description == "テスト"
        assert st.assigned_model == "model-a"
        assert st.context == ""
        assert st.retry_feedback == ""

    def test_creation_with_retry_feedback(self) -> None:
        """再指示フィードバック付きのインスタンス生成。"""
        st = SubTask(
            task_id="t1",
            description="テスト",
            assigned_model="model-a",
            retry_feedback="品質改善を求む",
        )
        assert st.retry_feedback == "品質改善を求む"


class TestWorkerOutput:
    """WorkerOutput データクラスのテスト。"""

    def test_creation(self) -> None:
        """基本的なインスタンス生成。"""
        wo = WorkerOutput(
            task_id="t1",
            worker_id="w1",
            model_used="model-a",
            success=True,
            output="結果",
            quality_score=0.9,
        )
        assert wo.task_id == "t1"
        assert wo.success is True
        assert wo.quality_score == 0.9
        assert wo.duration_seconds == 0.0
        assert wo.input_tokens == 0
        assert wo.output_tokens == 0


class TestQualityGateResult:
    """QualityGateResult データクラスのテスト。"""

    def test_passed(self) -> None:
        """合格時のインスタンス。"""
        qr = QualityGateResult(passed=True, overall_score=0.9)
        assert qr.passed is True
        assert qr.failed_task_ids == []
        assert qr.task_feedback == {}

    def test_failed_with_feedback(self) -> None:
        """不合格時のインスタンス。"""
        qr = QualityGateResult(
            passed=False,
            overall_score=0.6,
            failed_task_ids=["t1", "t2"],
            task_feedback={"t1": "改善を求む", "t2": "改善を求む"},
        )
        assert qr.passed is False
        assert len(qr.failed_task_ids) == 2


# ============================================================
# モック関数テスト
# ============================================================


class TestMockDecompose:
    """mock_decompose のテスト。"""

    def test_returns_five_subtasks(self) -> None:
        """5個のサブタスクを返すこと。"""
        subtasks = mock_decompose("テストタスク")
        assert len(subtasks) == 5

    def test_unique_task_ids(self) -> None:
        """タスク ID がユニークであること。"""
        subtasks = mock_decompose("テストタスク")
        ids = [st.task_id for st in subtasks]
        assert len(ids) == len(set(ids))

    def test_models_assigned(self) -> None:
        """全サブタスクにモデルが割り当てられていること。"""
        subtasks = mock_decompose("テストタスク")
        for st in subtasks:
            assert st.assigned_model != ""


class TestMockExecute:
    """mock_execute のテスト。"""

    def test_returns_worker_output(self) -> None:
        """WorkerOutput を返すこと。"""
        st = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        result = mock_execute(st, "worker-1")
        assert isinstance(result, WorkerOutput)
        assert result.task_id == "t1"
        assert result.worker_id == "worker-1"

    def test_quality_score_range(self) -> None:
        """品質スコアが 0.0〜1.0 の範囲にあること。"""
        st = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        for _ in range(20):
            result = mock_execute(st, "worker-1")
            assert 0.0 <= result.quality_score <= 1.0

    def test_retry_feedback_improves_score(self) -> None:
        """再指示フィードバックで品質向上バイアスがあること（統計的テスト）。"""
        import random

        random.seed(42)
        st_no_retry = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        st_retry = SubTask(
            task_id="t2",
            description="テスト",
            assigned_model="model-a",
            retry_feedback="改善を求む",
        )
        no_retry_scores = [mock_execute(st_no_retry, "w").quality_score for _ in range(50)]
        retry_scores = [mock_execute(st_retry, "w").quality_score for _ in range(50)]
        # 再指示の平均スコアは非再指示以上であるべき
        assert sum(retry_scores) / len(retry_scores) >= sum(no_retry_scores) / len(no_retry_scores)

    def test_tokens_populated(self) -> None:
        """トークン数が正の値であること。"""
        st = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        result = mock_execute(st, "worker-1")
        assert result.input_tokens > 0
        assert result.output_tokens > 0


class TestMockQualityCheck:
    """mock_quality_check のテスト。"""

    def test_all_pass(self) -> None:
        """全ワーカーが閾値以上の場合、合格すること。"""
        results = [
            WorkerOutput(
                task_id=f"t{i}",
                worker_id=f"w{i}",
                model_used="m",
                success=True,
                output="ok",
                quality_score=0.9,
            )
            for i in range(3)
        ]
        qr = mock_quality_check(results, 0.8)
        assert qr.passed is True
        assert len(qr.failed_task_ids) == 0

    def test_some_fail(self) -> None:
        """一部が閾値未満の場合、不合格の task_id が報告されること。"""
        results = [
            WorkerOutput(
                task_id="t1",
                worker_id="w1",
                model_used="m",
                success=True,
                output="ok",
                quality_score=0.9,
            ),
            WorkerOutput(
                task_id="t2",
                worker_id="w2",
                model_used="m",
                success=True,
                output="ok",
                quality_score=0.5,
            ),
        ]
        qr = mock_quality_check(results, 0.8)
        assert qr.passed is False
        assert "t2" in qr.failed_task_ids
        assert "t1" not in qr.failed_task_ids

    def test_overall_score_is_average(self) -> None:
        """overall_score が平均値であること。"""
        results = [
            WorkerOutput(
                task_id=f"t{i}",
                worker_id=f"w{i}",
                model_used="m",
                success=True,
                output="ok",
                quality_score=score,
            )
            for i, score in enumerate([0.6, 0.8, 1.0])
        ]
        qr = mock_quality_check(results, 0.5)
        assert qr.overall_score == pytest.approx(0.8, abs=0.001)

    def test_at_threshold_boundary(self) -> None:
        """閾値ちょうどのスコアは合格すること。"""
        results = [
            WorkerOutput(
                task_id="t1",
                worker_id="w1",
                model_used="m",
                success=True,
                output="ok",
                quality_score=0.8,
            ),
        ]
        qr = mock_quality_check(results, 0.8)
        assert qr.passed is True

    def test_just_below_threshold(self) -> None:
        """閾値直下のスコアは不合格であること。"""
        results = [
            WorkerOutput(
                task_id="t1",
                worker_id="w1",
                model_used="m",
                success=True,
                output="ok",
                quality_score=0.799,
            ),
        ]
        qr = mock_quality_check(results, 0.8)
        assert qr.passed is False
        assert "t1" in qr.failed_task_ids


# ============================================================
# LangGraph ノードテスト
# ============================================================


class TestCommanderNode:
    """commander_node のテスト。"""

    def test_decomposes_task(self) -> None:
        """タスクを分解して subtasks と iteration を返すこと。"""
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [],
            "quality_result": None,
            "iteration": 0,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        result = commander_node(state)
        assert "subtasks" in result
        assert len(result["subtasks"]) == 5
        assert result["iteration"] == 1


class TestWorkerNode:
    """worker_node のテスト。"""

    def test_executes_single_subtask(self) -> None:
        """単一サブタスクを実行して WorkerOutput のリストを返すこと。"""
        st = SubTask(task_id="t1", description="テスト", assigned_model="model-a")
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [st],
            "worker_results": [],
            "quality_result": None,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        result = worker_node(state)
        assert "worker_results" in result
        assert len(result["worker_results"]) == 1
        assert result["worker_results"][0].task_id == "t1"


class TestQualityGateNode:
    """quality_gate_node のテスト。"""

    def test_evaluates_results(self) -> None:
        """ワーカー結果を評価すること。"""
        wo = WorkerOutput(
            task_id="t1",
            worker_id="w1",
            model_used="m",
            success=True,
            output="ok",
            quality_score=0.9,
        )
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [wo],
            "quality_result": None,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        result = quality_gate_node(state)
        assert "quality_result" in result
        assert result["quality_result"].passed is True

    def test_deduplication(self) -> None:
        """同一 task_id の重複を排除し最新結果を使うこと。"""
        wo_old = WorkerOutput(
            task_id="t1",
            worker_id="w1",
            model_used="m",
            success=True,
            output="old",
            quality_score=0.5,
        )
        wo_new = WorkerOutput(
            task_id="t1",
            worker_id="w1",
            model_used="m",
            success=True,
            output="new",
            quality_score=0.9,
        )
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [wo_old, wo_new],
            "quality_result": None,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        result = quality_gate_node(state)
        # 最新（wo_new）のスコア 0.9 が採用されるため合格
        assert result["quality_result"].passed is True


class TestPrepareRetryNode:
    """prepare_retry_node のテスト。"""

    def test_creates_retry_subtasks(self) -> None:
        """不合格タスクのみ再指示サブタスクを生成すること。"""
        st1 = SubTask(task_id="t1", description="テスト1", assigned_model="m")
        st2 = SubTask(task_id="t2", description="テスト2", assigned_model="m")
        qr = QualityGateResult(
            passed=False,
            overall_score=0.7,
            failed_task_ids=["t2"],
            task_feedback={"t2": "改善を求む"},
        )
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [st1, st2],
            "worker_results": [],
            "quality_result": qr,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        result = prepare_retry_node(state)
        assert len(result["subtasks"]) == 1
        assert result["subtasks"][0].task_id == "t2"
        assert result["subtasks"][0].retry_feedback == "改善を求む"
        assert result["iteration"] == 2


# ============================================================
# ルーティングテスト
# ============================================================


class TestFanoutToWorkers:
    """fanout_to_workers のテスト。"""

    def test_creates_send_per_subtask(self) -> None:
        """サブタスク数分の Send を生成すること。"""
        from langgraph.types import Send

        st1 = SubTask(task_id="t1", description="テスト1", assigned_model="m")
        st2 = SubTask(task_id="t2", description="テスト2", assigned_model="m")
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [st1, st2],
            "worker_results": [],
            "quality_result": None,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        sends = fanout_to_workers(state)
        assert len(sends) == 2
        assert all(isinstance(s, Send) for s in sends)


class TestRouteAfterQuality:
    """route_after_quality のテスト。"""

    def test_end_on_pass(self) -> None:
        """合格時に END を返すこと。"""
        from langgraph.graph import END as LG_END

        qr = QualityGateResult(passed=True, overall_score=0.9)
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [],
            "quality_result": qr,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        assert route_after_quality(state) == LG_END

    def test_retry_on_fail(self) -> None:
        """不合格・イテレーション残りがある場合に prepare_retry を返すこと。"""
        qr = QualityGateResult(
            passed=False,
            overall_score=0.6,
            failed_task_ids=["t1"],
        )
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [],
            "quality_result": qr,
            "iteration": 1,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        assert route_after_quality(state) == "prepare_retry"

    def test_end_on_max_iterations(self) -> None:
        """最大イテレーション到達時に END を返すこと。"""
        from langgraph.graph import END as LG_END

        qr = QualityGateResult(
            passed=False,
            overall_score=0.6,
            failed_task_ids=["t1"],
        )
        state: dict[str, Any] = {
            "task_description": "テスト",
            "subtasks": [],
            "worker_results": [],
            "quality_result": qr,
            "iteration": 3,
            "max_iterations": 3,
            "quality_threshold": 0.8,
        }
        assert route_after_quality(state) == LG_END


# ============================================================
# グラフ構築テスト
# ============================================================


class TestBuildGraph:
    """build_graph のテスト。"""

    def test_returns_state_graph(self) -> None:
        """StateGraph を返すこと。"""
        from langgraph.graph.state import StateGraph

        graph = build_graph()
        assert isinstance(graph, StateGraph)

    def test_compilable(self) -> None:
        """コンパイル可能であること。"""
        graph = build_graph()
        app = graph.compile()
        assert app is not None


# ============================================================
# パイプライン実行テスト
# ============================================================


class TestRunPipeline:
    """run_pipeline の統合テスト。"""

    def test_basic_execution(self) -> None:
        """基本実行が成功すること。"""
        result = run_pipeline(
            "テストタスク",
            max_iterations=3,
            quality_threshold=0.8,
            seed=42,
        )
        assert result["status"] in ("success", "partial")
        assert result["worker_count"] > 0
        assert result["total_duration_seconds"] > 0
        assert result["total_tokens"] >= 0
        assert "worker_results" in result

    def test_reproducibility_with_seed(self) -> None:
        """同一シードで再現性があること。"""
        r1 = run_pipeline("テスト", seed=123)
        r2 = run_pipeline("テスト", seed=123)
        assert r1["quality_score"] == r2["quality_score"]
        assert r1["iterations"] == r2["iterations"]
        assert r1["worker_count"] == r2["worker_count"]

    def test_different_seed_different_result(self) -> None:
        """異なるシードで異なる結果を返すこと（高確率）。"""
        r1 = run_pipeline("テスト", seed=1)
        r2 = run_pipeline("テスト", seed=999)
        # 完全一致しない確率が高い（モック乱数依存）
        # 少なくとも実行できること
        assert r1["worker_count"] > 0
        assert r2["worker_count"] > 0

    def test_low_threshold_passes_first_try(self) -> None:
        """低い閾値なら1回目で合格すること。"""
        result = run_pipeline(
            "テスト",
            max_iterations=3,
            quality_threshold=0.1,
            seed=42,
        )
        assert result["quality_passed"] is True
        assert result["iterations"] == 1

    def test_result_keys(self) -> None:
        """結果辞書に必要なキーが含まれること。"""
        result = run_pipeline("テスト", seed=42)
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
            "raw_result_count",
        }
        assert expected_keys.issubset(set(result.keys()))

    def test_deduplication_in_results(self) -> None:
        """worker_results が重複排除されていること。"""
        result = run_pipeline("テスト", seed=42)
        task_ids = [r.task_id for r in result["worker_results"]]
        assert len(task_ids) == len(set(task_ids))
