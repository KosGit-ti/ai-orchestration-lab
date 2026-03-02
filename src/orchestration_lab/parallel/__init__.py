"""parallel モジュール — エージェント並列実行フレームワーク。

Fan-Out/Fan-In 型並列実行パターンの型定義とユーティリティを提供する。
"""

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

__all__ = [
    "ModelConfig",
    "ModelRole",
    "ParallelExecutionConfig",
    "ParallelExecutionResult",
    "QualityVerdict",
    "TokenUsage",
    "WorkerResult",
    "WorkerTask",
]
