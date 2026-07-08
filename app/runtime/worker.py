"""
Worker — 领取 Task，管理生命周期，委托 TaskExecutor 执行 Skill。

Worker 不直接依赖 Skill。它通过 TaskExecutor 接口执行 Task。

SOLID：
  - Single Responsibility: 仅负责生命周期管理（status / event / timing）
  - Dependency Inversion: 依赖 TaskExecutor 接口，不依赖具体 Skill
  - Composition: 组合 EventBus + TaskExecutor，不继承
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from .interfaces import TaskExecutor
from .task import Task, TaskStatus
from .events import EventBus, EventType, RuntimeEvent

logger = logging.getLogger("runtime.worker")


class Worker:
    """
    Worker 执行器。

    Worker 不关心：
      - 任务是如何调度的（由 Scheduler 负责）
      - Skill 是如何执行的（由 TaskExecutor 负责）
      - 结果是如何聚合的（由 Aggregator 负责）

    Worker 只负责：
      - 管理 Task 生命周期状态
      - 记录时序（started_at / finished_at）
      - 发布 Event
      - 委托 TaskExecutor 执行
    """

    def __init__(
        self,
        executor: TaskExecutor,
        event_bus: Optional[EventBus] = None,
    ):
        self._executor = executor
        self._event_bus = event_bus or EventBus()

    async def execute(self, task: Task) -> Task:
        """
        执行单个 Task。

        生命周期：
          1. 状态 → RUNNING
          2. 发布 TaskStarted
          3. 委托 TaskExecutor.execute()
          4. 状态由 Executor 设置为 COMPLETED / FAILED / TIMEOUT
          5. 发布对应 Event
          6. 返回 Task
        """
        task.started_at = time.time()
        task.transition_to(TaskStatus.RUNNING)
        self._publish(EventType.TASK_STARTED, task)

        try:
            task = await self._executor.execute(task)
        except Exception as exc:
            task.transition_to(TaskStatus.FAILED)
            task.error = str(exc)
            logger.exception(f"Worker: unhandled error in task {task.task_id}")

        task.finished_at = time.time()

        # 发布完成事件
        event_map = {
            TaskStatus.COMPLETED: EventType.TASK_COMPLETED,
            TaskStatus.FAILED: EventType.TASK_FAILED,
            TaskStatus.TIMEOUT: EventType.TASK_TIMEOUT,
            TaskStatus.CANCELLED: EventType.TASK_CANCELLED,
        }
        event_type = event_map.get(task.status)
        if event_type:
            self._publish(event_type, task)

        return task

    def _publish(self, event_type: EventType, task: Task) -> None:
        try:
            self._event_bus.publish(RuntimeEvent(type=event_type, task=task))
        except Exception:
            logger.exception(f"Worker: failed to publish event {event_type.name}")
