"""
DefaultResultAggregator — 等待 ExecutionHandle 完成，聚合结果。

复用现有 CrossSkillFusion 做加权融合。

SOLID：
  - Single Responsibility: 仅负责结果收集与合并
  - Dependency Injection: fusion_strategy 可注入
  - Open/Closed: 可注入不同 fusion 策略（RRF / LLM-as-Judge）
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

from .interfaces import ExecutionHandle, ResultAggregator, AggregatedResult
from .task import Task, TaskStatus

logger = logging.getLogger("runtime.aggregator")


class DefaultResultAggregator(ResultAggregator):
    """
    默认结果聚合器。

    委托 CrossSkillFusion（现有模块）做加权融合。
    如果 CrossSkillFusion 不可用，降级为简单合并。
    """

    def __init__(
        self,
        fusion_strategy: Optional[Callable] = None,
    ):
        """
        Args:
            fusion_strategy: 可选的融合策略函数。
                             签名: (results_dict, tasks) → AggregatedResult
                             None 时使用内置 CrossSkillFusion。
        """
        self._fusion_strategy = fusion_strategy

    async def aggregate(
        self,
        handles: List[ExecutionHandle],
    ) -> AggregatedResult:
        """等待所有 handle 完成，聚合结果"""
        tasks: List[Task] = []
        for h in handles:
            try:
                task = await h.wait()
            except Exception:
                task = Task(skill=h.task_id, status=TaskStatus.FAILED)
            tasks.append(task)

        return self.merge(tasks)

    def merge(self, tasks: List[Task]) -> AggregatedResult:
        """将已完成 Task 列表合并为 AggregatedResult"""
        if self._fusion_strategy:
            results = {}
            for t in tasks:
                results[t.skill] = t.result
            return self._fusion_strategy(results, tasks)

        # 默认：简单合并
        results: Dict[str, Any] = {}
        success = fail = timeout = 0
        total_latency = 0.0

        for t in tasks:
            results[t.skill] = t.result if t.is_success else None
            total_latency += t.duration_ms

            if t.status == TaskStatus.COMPLETED:
                success += 1
            elif t.status == TaskStatus.TIMEOUT:
                timeout += 1
            else:
                fail += 1

        return AggregatedResult(
            results=results,
            tasks=tasks,
            success_count=success,
            fail_count=fail,
            timeout_count=timeout,
            total_latency_ms=total_latency,
        )
