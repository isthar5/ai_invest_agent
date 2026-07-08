"""
ExecutionRuntime — 统一执行运行时门面。

职责：
  - Task 提交（返回 ExecutionHandle）
  - 并行执行（execute_parallel）
  - DAG 执行（execute_dag，根据 depends_on 自动拓扑排序）
  - 结果聚合
  - 优雅关闭

不负责：
  - 业务逻辑（Skill 负责）
  - 调度细节（Scheduler 负责）
  - 规划决策（LangGraph Planner 负责）

SOLID：
  - Dependency Inversion: 依赖 Scheduler/ResultAggregator/EventBus 接口
  - Dependency Injection: 所有组件通过构造函数注入
  - 不 import asyncio.Future / asyncio.Task
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Set

from .interfaces import (
    Scheduler,
    ExecutionHandle,
    ResultAggregator,
    AggregatedResult,
)
from .task import Task, TaskStatus
from .events import (
    EventBus,
    EventType,
    RuntimeEvent,
    _create_logging_subscriber,
    _create_metrics_subscriber,
)

logger = logging.getLogger("runtime")


class ExecutionRuntime:
    """
    统一执行运行时。

    用法：
        # 1. 工厂方法（默认 PythonScheduler）
        runtime = ExecutionRuntime.create(max_workers=4)

        # 2. 手动 DI（GoScheduler 等自定义组合）
        runtime = ExecutionRuntime(
            scheduler=my_scheduler,
            aggregator=my_aggregator,
            event_bus=my_event_bus,
        )

        # 执行
        result = await runtime.execute_parallel(tasks)
        await runtime.shutdown()
    """

    def __init__(
        self,
        scheduler: Scheduler,
        aggregator: Optional[ResultAggregator] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._scheduler = scheduler
        self._aggregator = aggregator
        self._event_bus = event_bus or EventBus()

        # 注册内置 subscriber（仅当 EventBus 是新创建时）
        if event_bus is None:
            self._event_bus.subscribe(
                EventType.TASK_STARTED, _create_logging_subscriber()
            )
            self._event_bus.subscribe(
                EventType.TASK_COMPLETED, _create_metrics_subscriber()
            )
            self._event_bus.subscribe(
                EventType.TASK_FAILED, _create_metrics_subscriber()
            )
            self._event_bus.subscribe(
                EventType.TASK_TIMEOUT, _create_metrics_subscriber()
            )

    # ── 工厂方法 ──────────────────────────────────────────

    @classmethod
    def create(
        cls,
        max_workers: int = 4,
        aggregator: Optional[ResultAggregator] = None,
    ) -> "ExecutionRuntime":
        """
        工厂方法：创建默认配置的 ExecutionRuntime（PythonScheduler）。

        Args:
            max_workers: 最大并发 Worker 数
            aggregator: 结果聚合器（None 则使用 DefaultResultAggregator）
        """
        from .python_scheduler import PythonScheduler
        from .executor import DefaultTaskExecutor
        from .hooks import default_hooks

        event_bus = EventBus()
        executor = DefaultTaskExecutor(
            hooks=default_hooks(),
            event_bus=event_bus,
        )
        scheduler = PythonScheduler(
            executor=executor,
            max_workers=max_workers,
            event_bus=event_bus,
        )
        if aggregator is None:
            from .aggregator import DefaultResultAggregator
            aggregator = DefaultResultAggregator()

        return cls(
            scheduler=scheduler,
            aggregator=aggregator,
            event_bus=event_bus,
        )

    # ── 公共 API ──────────────────────────────────────────

    async def submit(self, task: Task) -> ExecutionHandle:
        """提交单个 Task，返回 ExecutionHandle"""
        return await self._scheduler.submit(task)

    async def execute_parallel(
        self,
        tasks: List[Task],
    ) -> AggregatedResult:
        """
        并行执行一组 Task（无依赖关系）。

        所有 Task 同时提交，等待全部完成，聚合结果。
        """
        if not tasks:
            return AggregatedResult(results={}, tasks=[])

        # 提交全部
        handles = []
        for task in tasks:
            h = await self._scheduler.submit(task)
            handles.append(h)

        # 等待完成
        await self._scheduler.wait(handles)

        # 聚合
        if self._aggregator:
            return await self._aggregator.aggregate(handles)

        # 降级：简单合并
        from .aggregator import DefaultResultAggregator
        agg = DefaultResultAggregator()
        return await agg.aggregate(handles)

    async def execute_dag(
        self,
        tasks: List[Task],
    ) -> AggregatedResult:
        """
        DAG 执行：根据 depends_on 自动拓扑排序并分阶段执行。

        Stage 内的 Task 并行执行。
        Stage 之间串行（后续 Stage 等待依赖 Stage 完成）。
        """
        if not tasks:
            return AggregatedResult(results={}, tasks=[])

        task_map = {t.task_id: t for t in tasks}
        completed: Set[str] = set()
        handles_map: Dict[str, ExecutionHandle] = {}

        while len(completed) < len(tasks):
            # 找出所有依赖已满足的 Task
            ready = [
                t for t in tasks
                if t.task_id not in handles_map
                and all(dep in completed for dep in t.depends_on)
            ]

            if not ready:
                # 可能有循环依赖或全部 task 已失败
                pending = [t.task_id for t in tasks if t.task_id not in completed]
                logger.error(f"DAG: no ready tasks, pending={pending}")
                break

            # 并行提交当前 stage
            batch_handles = []
            for task in ready:
                h = await self._scheduler.submit(task)
                handles_map[task.task_id] = h
                batch_handles.append(h)

            # 等待这批全部完成
            await self._scheduler.wait(batch_handles)
            for h in batch_handles:
                completed.add(h.task_id)

        # 聚合所有结果
        all_handles = list(handles_map.values())
        if self._aggregator:
            return await self._aggregator.aggregate(all_handles)

        from .aggregator import DefaultResultAggregator
        agg = DefaultResultAggregator()
        return await agg.aggregate(all_handles)

    async def shutdown(self) -> None:
        """优雅关闭 Runtime"""
        await self._scheduler.shutdown()
        self._event_bus.publish(
            RuntimeEvent(
                type=EventType.RUNTIME_SHUTDOWN,
                task=Task(skill="__shutdown__"),
            )
        )
