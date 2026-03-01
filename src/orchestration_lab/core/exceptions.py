"""例外定義モジュール。

オーケストレーションラボ全体で使用する例外階層を定義する。
"""

from __future__ import annotations


class LabError(Exception):
    """ラボ全体の基底例外。"""


class ExperimentError(LabError):
    """実験実行時のエラー。"""


class ValidationError(LabError):
    """バリデーションエラー。"""


class ConfigError(LabError):
    """設定エラー。"""


class PipelineError(LabError):
    """パイプライン実行エラー。"""


class AgentError(LabError):
    """エージェント実行エラー。"""

    def __init__(self, agent_name: str, message: str) -> None:
        """エージェントエラーを初期化する。

        Args:
            agent_name: エラーが発生したエージェント名。
            message: エラーメッセージ。
        """
        self.agent_name = agent_name
        super().__init__(f"[{agent_name}] {message}")
