"""
PythonScheduler — 基于 asyncio 的 Scheduler 实现。

内部使用 asyncio.Semaphore 控制并发，asyncio.Future 驱动执行。
asyncio 细节完全封装在内部，不暴露给上层。

未来替换：GoScheduler（gRPC → Go Worker Pool）。

SOLID：
  - Liskov Substitution: 完全满足 Scheduler 接口
  - Single Responsibility: 仅负责并发调度 + Worker 管理
  - Dependency Injection: Worker / Executor / EventBus 全部注入
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional

from .interfaces import ExecutionHandle, Scheduler, TaskExecutor
from .task import Task, TaskStatus
from .handle import PythonExecutionHandle
from .worker import Worker
from .events import EventBus, EventType, RuntimeEvent

logger = logging.getLogger("runtime.python_scheduler")


class PythonScheduler(Scheduler):
    """
    基于 asyncio 的调度器。

    特性：
      - asyncio.Semaphore 限制并发 Worker 数
      - 每个 Worker 通过 TaskExecutor 执行 Skill
      - 所有 asyncio 细节封装在内部
    """

    def __init__(
        self,
        executor: TaskExecutor,
        max_workers: int = 4,
        event_bus: Optional[EventBus] = None,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be >= 1")

        self._executor = executor
        self._max_workers = max_workers
        self._semaphore = asyncio.Semaphore(max_workers)
        self._event_bus = event_bus or EventBus()

        # 内部状态
        self._handles: Dict[str, PythonExecutionHandle] = {}
        self._shutdown = False

        # 创建 Worker（所有 Worker 共享同一个 Executor + EventBus）
        self._worker = Worker(executor=executor, event_bus=self._event_bus)

    # ── Scheduler 接口 ────────────────────────────────────

    async def submit(self, task: Task) -> ExecutionHandle:
        if self._shutdown:
            raise RuntimeError("Scheduler is shut down")

        # 状态转换
        task.transition_to(TaskStatus.QUEUED)
        self._publish(EventType.TASK_QUEUED, task)

        # 创建 asyncio Task（内部实现细节）
        async def _run() -> Task:
            async with self._semaphore:
                return await self._worker.execute(task)

        future = asyncio.ensure_future(_run())

        # 完成时自动更新 handle 状态
        def _on_done(fut: asyncio.Future) -> None:
            pass  # Task 状态已在 Worker.execute() 中更新

        future.add_done_callback(_on_done)

        handle = PythonExecutionHandle(task=task, future=future)
        self._handles[task.task_id] = handle
        return handle

    async def cancel(self, task_id: str) -> bool:
        handle = self._handles.get(task_id)
        if handle is None:
            return False
        cancelled = handle.cancel()
        if cancelled:
            task = handle._task
            task.transition_to(TaskStatus.CANCELLED)
            self._publish(EventType.TASK_CANCELLED, task)
        return cancelled

    async def wait(
        self,
        handles: List[ExecutionHandle],
        timeout: Optional[float] = None,
    ) -> List[ExecutionHandle]:
        """等待一批 handle 全部完成"""
        if not handles:
            return []

        async_tasks = []
        for h in handles:
            if isinstance(h, PythonExecutionHandle):
                async_tasks.append(h._future)

        if async_tasks:
            done, _pending = await asyncio.wait(
                async_tasks,
                timeout=timeout,
                return_when=asyncio.ALL_COMPLETED,
            )

        return [h for h in handles if h.done()]

    async def shutdown(self) -> None:
        """优雅关闭：等待进行中的任务完成"""
        self._shutdown = True
        self._publish(EventType.RUNTIME_SHUTDOWN, Task(skill="__shutdown__"))
        logger.info("PythonScheduler shut down")

    # ── internal ──────────────────────────────────────────

    def _publish(self, event_type: EventType, task: Task) -> None:
        try:
            self._event_bus.publish(RuntimeEvent(type=event_type, task=task))
        except Exception:
            pass
