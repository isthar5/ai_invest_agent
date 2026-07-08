"""
M3 — Workflow Prometheus 指标。

指标清单:
  workflow_executions_total   — Workflow 执行计数（按 workflow_id / status）
  workflow_duration_seconds   — Workflow 总耗时（按 workflow_id）
  task_executions_total       — Task 执行计数（按 workflow_id / task_id / executor / status）
  task_duration_seconds       — Task 执行耗时（按 workflow_id / task_id / executor）

Usage:
    from app.workflow.metrics import (
        record_workflow_start, record_workflow_end,
        record_task_end,
    )
"""

from __future__ import annotations

import time
from typing import Optional

from prometheus_client import Counter, Gauge, Histogram

# ── Workflow 级别指标 ───────────────────────────────────────

workflow_executions_total = Counter(
    "workflow_executions_total",
    "Total workflow executions",
    ["workflow_id", "status"],
)

workflow_duration_seconds = Histogram(
    "workflow_duration_seconds",
    "Workflow execution duration in seconds",
    ["workflow_id"],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0],
)

# ── Task 级别指标 ───────────────────────────────────────────

task_executions_total = Counter(
    "task_executions_total",
    "Total task executions",
    ["workflow_id", "task_id", "executor", "status"],
)

task_duration_seconds = Histogram(
    "task_duration_seconds",
    "Task execution duration in seconds",
    ["workflow_id", "task_id", "executor"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0, 10.0, 30.0],
)

# ── 当前运行数 ──────────────────────────────────────────────

workflow_active = Gauge(
    "workflow_active",
    "Currently running workflow count",
    ["workflow_id"],
)


# ═══════════════════════════════════════════════════════════════
#  记录辅助函数
# ═══════════════════════════════════════════════════════════════

_workflow_timers: dict = {}  # workflow_id → start_time


def record_workflow_start(workflow_id: str) -> None:
    """记录 Workflow 开始执行。"""
    workflow_active.labels(workflow_id=workflow_id).inc()
    _workflow_timers[workflow_id] = time.time()


def record_workflow_end(
    workflow_id: str, status: str, error: Optional[str] = None
) -> None:
    """记录 Workflow 执行结束。

    Args:
        workflow_id: Workflow 标识。
        status: "success" | "partial" | "failed"。
        error: 错误信息（可选）。
    """
    workflow_active.labels(workflow_id=workflow_id).dec()
    workflow_executions_total.labels(
        workflow_id=workflow_id, status=status
    ).inc()

    start = _workflow_timers.pop(workflow_id, None)
    if start is not None:
        duration = time.time() - start
        workflow_duration_seconds.labels(workflow_id=workflow_id).observe(duration)


def record_task_end(
    workflow_id: str,
    task_id: str,
    executor: str,
    status: str,
    latency_ms: float,
) -> None:
    """记录单个 Task 执行结束。

    Args:
        workflow_id: 所属 Workflow。
        task_id: Task 标识（YAML 中的 id，不含 _seq 后缀）。
        executor: Executor 类型名。
        status: "success" | "failed" | "skipped" | "timeout"。
        latency_ms: 执行耗时（毫秒）。
    """
    task_executions_total.labels(
        workflow_id=workflow_id,
        task_id=task_id,
        executor=executor,
        status=status,
    ).inc()
    task_duration_seconds.labels(
        workflow_id=workflow_id,
        task_id=task_id,
        executor=executor,
    ).observe(latency_ms / 1000.0)
