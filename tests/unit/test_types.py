"""core.types の単体テスト。"""

from __future__ import annotations

from orchestration_lab.core.types import (
    AgentMetrics,
    AgentResult,
    AgentStatus,
    Finding,
    FindingSeverity,
    PipelineMetrics,
)


class TestFinding:
    """Finding データクラスのテスト。"""

    def test_finding_creation(self) -> None:
        """Finding が正しく作成されることを確認する。"""
        finding = Finding(
            severity=FindingSeverity.MUST,
            file="src/test.py",
            message="テスト指摘",
            line=42,
        )
        assert finding.severity == FindingSeverity.MUST
        assert finding.file == "src/test.py"
        assert finding.message == "テスト指摘"
        assert finding.line == 42

    def test_finding_without_line(self) -> None:
        """行番号なしの Finding が作成できることを確認する。"""
        finding = Finding(
            severity=FindingSeverity.SHOULD,
            file="src/test.py",
            message="テスト指摘",
        )
        assert finding.line is None


class TestAgentResult:
    """AgentResult データクラスのテスト。"""

    def test_agent_result_success(self) -> None:
        """成功状態の AgentResult が正しく作成されることを確認する。"""
        result = AgentResult(
            agent_name="implementer",
            status=AgentStatus.SUCCESS,
            summary="実装完了",
        )
        assert result.agent_name == "implementer"
        assert result.status == AgentStatus.SUCCESS
        assert result.summary == "実装完了"
        assert result.findings == []
        assert result.metrics is None
        assert not result.has_must_findings()

    def test_has_must_findings_true(self) -> None:
        """Must 指摘がある場合に True が返ることを確認する。"""
        result = AgentResult(
            agent_name="auditor-spec",
            status=AgentStatus.PARTIAL,
            summary="監査完了、Must指摘あり",
            findings=[
                Finding(
                    severity=FindingSeverity.MUST,
                    file="src/test.py",
                    message="必須修正",
                ),
            ],
        )
        assert result.has_must_findings()

    def test_has_must_findings_false(self) -> None:
        """Must 指摘がない場合に False が返ることを確認する。"""
        result = AgentResult(
            agent_name="auditor-spec",
            status=AgentStatus.SUCCESS,
            summary="監査完了",
            findings=[
                Finding(
                    severity=FindingSeverity.SHOULD,
                    file="src/test.py",
                    message="推奨修正",
                ),
            ],
        )
        assert not result.has_must_findings()

    def test_agent_result_with_metrics(self) -> None:
        """メトリクス付きの AgentResult が正しく作成されることを確認する。"""
        metrics = AgentMetrics(
            files_changed=3,
            lines_added=100,
            lines_removed=20,
        )
        result = AgentResult(
            agent_name="implementer",
            status=AgentStatus.SUCCESS,
            summary="実装完了",
            metrics=metrics,
        )
        assert result.metrics is not None
        assert result.metrics.files_changed == 3
        assert result.metrics.lines_added == 100


class TestPipelineMetrics:
    """PipelineMetrics データクラスのテスト。"""

    def test_default_values(self) -> None:
        """デフォルト値が正しいことを確認する。"""
        metrics = PipelineMetrics()
        assert metrics.ci_pass_rate == 0.0
        assert metrics.audit_must_count == 0
        assert metrics.audit_should_count == 0
        assert metrics.fix_loop_count == 0
        assert metrics.total_duration_seconds == 0.0

    def test_custom_values(self) -> None:
        """カスタム値が正しく設定されることを確認する。"""
        metrics = PipelineMetrics(
            ci_pass_rate=0.85,
            audit_must_count=1,
            audit_should_count=3,
            fix_loop_count=2,
            total_duration_seconds=120.5,
        )
        assert metrics.ci_pass_rate == 0.85
        assert metrics.audit_must_count == 1
