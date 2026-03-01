"""型定義モジュール。

オーケストレーションラボ全体で使用する共通の型を定義する。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


class AgentStatus(Enum):
    """エージェントの実行状態。"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


class FindingSeverity(Enum):
    """指摘の深刻度。"""

    MUST = "Must"
    SHOULD = "Should"
    NICE = "Nice"


@dataclass(frozen=True)
class Finding:
    """監査指摘。

    Args:
        severity: 指摘の深刻度。
        file: 対象ファイルの相対パス。
        message: 指摘内容の説明。
        line: 対象行番号（特定できない場合は None）。
    """

    severity: FindingSeverity
    file: str
    message: str
    line: int | None = None


@dataclass(frozen=True)
class AgentMetrics:
    """エージェント実行メトリクス。

    Args:
        files_changed: 変更されたファイル数。
        lines_added: 追加行数。
        lines_removed: 削除行数。
        tests_added: 追加されたテスト数。
        tests_passed: 通過したテスト数。
        tests_failed: 失敗したテスト数。
        coverage: テストカバレッジ（%）。
    """

    files_changed: int = 0
    lines_added: int = 0
    lines_removed: int = 0
    tests_added: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    coverage: float | None = None


@dataclass(frozen=True)
class AgentResult:
    """エージェント実行結果。

    Args:
        agent_name: エージェント名。
        status: 実行状態。
        summary: 結果の自然言語要約。
        findings: 指摘事項のリスト。
        metrics: 定量的な指標。
        timestamp: 結果生成時刻（UTC）。
    """

    agent_name: str
    status: AgentStatus
    summary: str
    findings: list[Finding] = field(default_factory=list)
    metrics: AgentMetrics | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def has_must_findings(self) -> bool:
        """Must 指摘が含まれるか判定する。"""
        return any(f.severity == FindingSeverity.MUST for f in self.findings)


@dataclass(frozen=True)
class PipelineMetrics:
    """パイプライン全体のメトリクス。

    Args:
        ci_pass_rate: CI 初回通過率。
        audit_must_count: Must 指摘の合計数。
        audit_should_count: Should 指摘の合計数。
        fix_loop_count: 修正ループ回数。
        total_duration_seconds: パイプライン全体の所要時間（秒）。
    """

    ci_pass_rate: float = 0.0
    audit_must_count: int = 0
    audit_should_count: int = 0
    fix_loop_count: int = 0
    total_duration_seconds: float = 0.0
