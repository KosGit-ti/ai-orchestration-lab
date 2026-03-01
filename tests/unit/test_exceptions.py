"""core.exceptions の単体テスト。"""

from __future__ import annotations

import pytest

from orchestration_lab.core.exceptions import (
    AgentError,
    ConfigError,
    ExperimentError,
    LabError,
    PipelineError,
    ValidationError,
)


class TestExceptionHierarchy:
    """例外階層のテスト。"""

    def test_lab_error_is_base(self) -> None:
        """LabError がすべてのカスタム例外の基底であることを確認する。"""
        assert issubclass(ExperimentError, LabError)
        assert issubclass(ValidationError, LabError)
        assert issubclass(ConfigError, LabError)
        assert issubclass(PipelineError, LabError)
        assert issubclass(AgentError, LabError)

    def test_agent_error_message(self) -> None:
        """AgentError のメッセージフォーマットを確認する。"""
        error = AgentError("implementer", "実装に失敗しました")
        assert str(error) == "[implementer] 実装に失敗しました"
        assert error.agent_name == "implementer"

    def test_agent_error_can_be_caught_as_lab_error(self) -> None:
        """AgentError が LabError として捕捉できることを確認する。"""
        with pytest.raises(LabError):
            raise AgentError("test-agent", "テストエラー")
