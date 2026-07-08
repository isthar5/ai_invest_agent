"""
Runtime Hooks — Hook 接口定义。

TaskExecutor 在执行生命周期的关键节点调用 Hook。
Observability / Metrics / Tracing / Audit 通过 Hook 接入。

SOLID：
  - Interface Segregation: 每个 Hook 是一个独立接口
  - Open/Closed: 新增 Hook 无需修改 TaskExecutor
  - Dependency Injection: Hook 列表通过构造函数注入
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from .task import Task


class BeforeExecuteHook(ABC):
    """Task 执行前调用。可修改 Task（如注入 context）。"""

    @abstractmethod
    async def on_before_execute(self, task: Task) -> Task:
        ...


class AfterExecuteHook(ABC):
    """Task 执行后调用（无论成功/失败/超时）。用于记录日志、更新 metrics。"""

    @abstractmethod
    async def on_after_execute(self, task: Task) -> None:
        ...


class RetryHook(ABC):
    """每次重试时调用。"""

    @abstractmethod
    async def on_retry(self, task: Task, attempt: int, exception: BaseException) -> None:
        ...


class TimeoutHook(ABC):
    """超时时调用。"""

    @abstractmethod
    async def on_timeout(self, task: Task) -> None:
        ...


class ErrorHook(ABC):
    """执行异常时调用。"""

    @abstractmethod
    async def on_error(self, task: Task, exception: BaseException) -> None:
        ...


# ═══════════════════════════════════════════════════════════════
#  内置 Hook 实现（通过 DI 注入到 TaskExecutor）
# ═══════════════════════════════════════════════════════════════

class ObservabilityBeforeHook(BeforeExecuteHook):
    """将 Task 信息注入 RequestContext，确保日志/追踪自动关联"""

    async def on_before_execute(self, task: Task) -> Task:
        try:
            from app.observability.context import request_context
            ctx = request_context()
            ctx.skill = task.skill
            if task.request_id:
                ctx.request_id = task.request_id
            if task.trace_id:
                ctx.trace_id = task.trace_id
        except ImportError:
            pass
        return task


class ObservabilityAfterHook(AfterExecuteHook):
    """记录 Task 完成后的 metrics 和 usage"""

    async def on_after_execute(self, task: Task) -> None:
        try:
            from app.observability.metrics import tool_latency_seconds
            tool_latency_seconds.labels(tool_name=task.skill).observe(
                task.duration_ms / 1000.0
            )
        except ImportError:
            pass


def default_hooks() -> List:
    """返回默认 Hook 列表（DI 友好）"""
    hooks: List = []
    try:
        hooks.append(ObservabilityBeforeHook())
        hooks.append(ObservabilityAfterHook())
    except Exception:
        pass
    return hooks
