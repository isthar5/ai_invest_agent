"""
Task — 统一执行单元。

纯数据类，无任何外部依赖。支持 DAG（有向无环图）依赖声明。

生命周期状态：
  CREATED → QUEUED → RUNNING → COMPLETED | FAILED | TIMEOUT | CANCELLED
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class TaskStatus(Enum):
    CREATED = auto()
    QUEUED = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    TIMEOUT = auto()
    CANCELLED = auto()

    @property
    def is_terminal(self) -> bool:
        return self in {
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.TIMEOUT,
            TaskStatus.CANCELLED,
        }

    @property
    def is_success(self) -> bool:
        return self == TaskStatus.COMPLETED


# 合法状态转换
_ALLOWED_TRANSITIONS: Dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.CREATED:   frozenset({TaskStatus.QUEUED, TaskStatus.TIMEOUT, TaskStatus.CANCELLED}),
    TaskStatus.QUEUED:    frozenset({TaskStatus.RUNNING, TaskStatus.TIMEOUT, TaskStatus.CANCELLED}),
    TaskStatus.RUNNING:   frozenset({
        TaskStatus.COMPLETED, TaskStatus.FAILED,
        TaskStatus.TIMEOUT, TaskStatus.CANCELLED,
    }),
    TaskStatus.FAILED:    frozenset({TaskStatus.QUEUED}),  # 重试时重新入队
    TaskStatus.COMPLETED: frozenset(),
    TaskStatus.TIMEOUT:   frozenset(),
    TaskStatus.CANCELLED: frozenset(),
}


@dataclass
class Task:
    """
    统一 Task 对象。Planner 创建，Runtime 执行。

    DAG 字段：
      - depends_on: 当前 Task 依赖的 task_id 列表（必须全部完成才调度）
      - children: 依赖当前 Task 的 task_id 列表（自动填充）
      - stage: 阶段名（同一 stage 的 Task 可并行）
      - group: 逻辑分组（用于聚合/展示）
    """

    skill: str
    payload: Dict[str, Any] = field(default_factory=dict)

    # 身份
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    parent_task: Optional[str] = None

    # DAG
    depends_on: List[str] = field(default_factory=list)
    children: List[str] = field(default_factory=list)
    stage: str = "default"
    group: str = "default"

    # 调度
    priority: int = 0

    # 生命周期
    status: TaskStatus = TaskStatus.CREATED
    retry_count: int = 0

    # 策略（可选，None 则使用 Runtime 默认）
    retry_policy: Optional["RetryPolicy"] = None
    timeout_policy: Optional["TimeoutPolicy"] = None
    timeout: float = 30.0

    # 追踪
    request_id: str = ""
    trace_id: str = ""

    # 结果
    result: Optional[Any] = None
    error: Optional[str] = None

    # 时间戳
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    # Hook 列表（可注入，None 则使用 Runtime 默认）
    hooks: List[Any] = field(default_factory=list)

    @property
    def duration_ms(self) -> float:
        if self.started_at is None:
            return 0.0
        end = self.finished_at or time.time()
        return (end - self.started_at) * 1000

    @property
    def is_terminal(self) -> bool:
        return self.status.is_terminal

    @property
    def is_success(self) -> bool:
        return self.status.is_success

    def can_transition_to(self, target: TaskStatus) -> bool:
        return target in _ALLOWED_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, target: TaskStatus) -> None:
        if not self.can_transition_to(target):
            raise ValueError(
                f"Invalid task state transition: {self.status.name} → {target.name}"
            )
        self.status = target

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "parent_task": self.parent_task,
            "skill": self.skill,
            "stage": self.stage,
            "group": self.group,
            "priority": self.priority,
            "status": self.status.name,
            "depends_on": self.depends_on,
            "children": self.children,
            "retry_count": self.retry_count,
            "timeout": self.timeout,
            "request_id": self.request_id,
            "trace_id": self.trace_id,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }
