"""
ExecutionHandle 实现。

PythonExecutionHandle: 内部包装 asyncio.Future，不暴露给 Runtime。
GoExecutionHandle:   未来实现，内部包装 gRPC Stream。

SOLID：
  - Liskov Substitution: PythonExecutionHandle 完全满足 ExecutionHandle 接口
  - Dependency Inversion: Runtime 只依赖 ExecutionHandle 接口
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from .interfaces import ExecutionHandle
from .task import Task, TaskStatus


class PythonExecutionHandle(ExecutionHandle):
    """
    基于 asyncio.Future 的 ExecutionHandle。
    asyncio.Future 完全封装在内部，不对外暴露。
    """

    def __init__(self, task: Task, future: asyncio.Future):
        self._task = task
        self._future = future

    @property
    def task_id(self) -> str:
        return self._task.task_id

    def status(self) -> TaskStatus:
        return self._task.status

    def result(self) -> Any:
        if self._future.exception():
            raise self._future.exception()  # type: ignore[misc]
        return self._future.result()

    def exception(self) -> Optional[Exception]:
        return self._future.exception()

    def done(self) -> bool:
        return self._future.done()

    async def wait(self, timeout: Optional[float] = None) -> Task:
        try:
            await asyncio.wait_for(
                asyncio.shield(self._future),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            if self._task.can_transition_to(TaskStatus.TIMEOUT):
                self._task.transition_to(TaskStatus.TIMEOUT)
            self._task.error = f"Timeout after {timeout}s"
        except asyncio.CancelledError:
            if self._task.can_transition_to(TaskStatus.CANCELLED):
                self._task.transition_to(TaskStatus.CANCELLED)
        return self._task

    def cancel(self) -> bool:
        if not self._future.done():
            return self._future.cancel()
        return False
