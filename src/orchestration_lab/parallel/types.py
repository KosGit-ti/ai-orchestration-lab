"""並列実行フレームワークの型定義モジュール。

Fan-Out/Fan-In 型並列実行パターンに必要な型を定義する。
司令塔（Commander）＋作業者（Worker）構成における
タスク、結果、品質判定、設定の型を提供する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestration_lab.core.types import AgentStatus


class ModelRole(Enum):
    """モデルの役割。

    並列実行パイプラインにおけるモデルの役割を定義する。
    """

    COMMANDER = "commander"
    WORKER = "worker"


@dataclass(frozen=True)
class ModelConfig:
    """モデル設定。

    LLM モデルの識別子と実行パラメータを保持する。

    Args:
        model_id: モデル識別子（例: "claude-opus-4-20250514"）。
        role: パイプラインにおける役割。
        max_tokens: 最大出力トークン数。
        temperature: 生成温度（0.0 = 決定的）。
    """

    model_id: str
    role: ModelRole
    max_tokens: int = 4096
    temperature: float = 0.0


@dataclass(frozen=True)
class TokenUsage:
    """トークン使用量。

    LLM API 呼び出しにおけるトークン消費量を記録する。

    Args:
        input_tokens: 入力トークン数。
        output_tokens: 出力トークン数。
    """

    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        """合計トークン数を返す。"""
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class WorkerTask:
    """ワーカーに割り当てるサブタスク。

    司令塔がタスクを分解した結果の個別サブタスクを表現する。

    Args:
        task_id: サブタスクの一意識別子。
        description: サブタスクの説明。
        context: 共有コンテキスト（ディレクトリ構造、既存コード等）。
        assigned_model: 割り当てるモデルの識別子。
        priority: 優先度（0 が最高）。
    """

    task_id: str
    description: str
    context: str = ""
    assigned_model: str = ""
    priority: int = 0


@dataclass(frozen=True)
class WorkerResult:
    """ワーカーの実行結果。

    個別ワーカーの実行完了後の結果データを保持する。

    Args:
        task_id: 対応するサブタスクの識別子。
        worker_id: ワーカーの識別子。
        model_used: 使用したモデルの識別子。
        status: 実行状態。
        output: 生成されたコードまたはテキスト。
        files_changed: 変更されたファイルパスのリスト。
        duration_seconds: 実行時間（秒）。
        token_usage: トークン使用量。
    """

    task_id: str
    worker_id: str
    model_used: str
    status: AgentStatus
    output: str
    files_changed: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    token_usage: TokenUsage = field(default_factory=TokenUsage)


@dataclass(frozen=True)
class QualityVerdict:
    """司令塔による品質判定。

    司令塔がワーカー結果を評価した判定結果を保持する。

    Args:
        passed: 品質基準を満たしたか。
        score: 品質スコア（0.0〜1.0）。
        feedback: タスク ID → フィードバックの対応。
        iteration: 現在のイテレーション番号。
    """

    passed: bool
    score: float
    feedback: dict[str, str] = field(default_factory=dict)
    iteration: int = 0


@dataclass(frozen=True)
class ParallelExecutionConfig:
    """並列実行の設定。

    Fan-Out/Fan-In パイプラインの実行パラメータを定義する。

    Args:
        min_workers: 最小ワーカー数。
        max_workers: 最大ワーカー数。
        default_workers: デフォルトワーカー数。
        quality_threshold: 品質閾値（0.0〜1.0）。
        max_iterations: 最大品質ゲートイテレーション数。
        worker_timeout_seconds: ワーカーごとのタイムアウト（秒）。
        pipeline_timeout_seconds: パイプライン全体のタイムアウト（秒）。
        commander_model: 司令塔のモデル識別子。
        worker_models: 作業者のモデル識別子リスト。
    """

    min_workers: int = 3
    max_workers: int = 10
    default_workers: int = 5
    quality_threshold: float = 0.8
    max_iterations: int = 5
    worker_timeout_seconds: float = 600.0
    pipeline_timeout_seconds: float = 3600.0
    commander_model: str = ""
    worker_models: list[str] = field(default_factory=list)

    def determine_worker_count(self, subtask_count: int) -> int:
        """サブタスク数に基づきワーカー数を決定する。

        Args:
            subtask_count: 分解されたサブタスクの数。

        Returns:
            実際に使用するワーカー数。
        """
        return max(self.min_workers, min(subtask_count, self.max_workers))


@dataclass(frozen=True)
class ParallelExecutionResult:
    """並列実行全体の結果。

    Fan-Out/Fan-In パイプラインの最終結果を保持する。

    Args:
        status: パイプライン全体の実行状態。
        iterations: 実行したイテレーション数。
        total_duration_seconds: 全体の所要時間（秒）。
        worker_results: 各ワーカーの結果リスト。
        final_verdict: 最終の品質判定。
        total_token_usage: 全体のトークン使用量。
    """

    status: AgentStatus
    iterations: int
    total_duration_seconds: float
    worker_results: list[WorkerResult] = field(default_factory=list)
    final_verdict: QualityVerdict = field(
        default_factory=lambda: QualityVerdict(passed=False, score=0.0)
    )
    total_token_usage: TokenUsage = field(default_factory=TokenUsage)
