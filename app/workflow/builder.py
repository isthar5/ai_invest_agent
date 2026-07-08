"""
TaskBuilder — WorkflowDefinition → ExecutionPlan。

M1 职责:
  1. TaskDefinition → app.runtime.task.Task
  2. __FROM_RUNTIME__ 占位符替换
  3. 注入 __executor__ 到 payload
  4. BFS 计算拓扑 stage

M1 不做:
  - VariableResolver
  - RetryBuilder / TimeoutBuilder
  - Condition / Branch
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any, Dict, List

from app.runtime.task import Task

from .models import ExecutionPlan, TaskDefinition, WorkflowDefinition

logger = logging.getLogger("workflow.builder")

_RUNTIME_PLACEHOLDER = "__FROM_RUNTIME__"


class TaskBuilder:
    """WorkflowDefinition → ExecutionPlan 翻译器。"""

    def build(
        self,
        definition: WorkflowDefinition,
        **runtime_params: Any,
    ) -> ExecutionPlan:
        """将 WorkflowDefinition 翻译为 ExecutionPlan。

        Args:
            definition: 已加载的 Workflow 配置。
            **runtime_params: 替换 __FROM_RUNTIME__ 的运行时值。

        Returns:
            ExecutionPlan — 包含按拓扑顺序排列的 Task 列表。
        """
        # Step 1: 为每个 TaskDefinition 创建 Task
        task_map: Dict[str, Task] = {}
        for task_def in definition.tasks:
            task_map[task_def.id] = self._build_task(task_def, runtime_params)

        # Step 2: 计算拓扑 stage
        self._compute_stages(task_map)

        # Step 3: 按 stage → task_id 排序
        tasks = sorted(task_map.values(), key=lambda t: (t.stage, t.task_id))

        logger.info(
            f"TaskBuilder: built '{definition.workflow_id}' "
            f"({len(tasks)} tasks)"
        )

        return ExecutionPlan(
            workflow_id=definition.workflow_id,
            tasks=tasks,
        )

    # ── 单 Task 构造 ──────────────────────────────────────

    def _build_task(
        self,
        task_def: TaskDefinition,
        runtime_params: Dict[str, Any],
    ) -> Task:
        """TaskDefinition → Task。

        替换 __FROM_RUNTIME__ 占位符，注入 __executor__。
        """
        config = dict(task_def.config)
        for key, value in list(config.items()):
            if value == _RUNTIME_PLACEHOLDER and key in runtime_params:
                config[key] = runtime_params[key]

        return Task(
            task_id=task_def.id,
            skill="workflow_executor",
            payload={"__executor__": task_def.executor, **config},
            depends_on=list(task_def.depends_on),
        )

    # ── 拓扑排序 ──────────────────────────────────────────

    @staticmethod
    def _compute_stages(task_map: Dict[str, Task]) -> None:
        """BFS 计算每个 Task 的拓扑 stage。

        stage 0 = 无依赖的根 task。
        有循环依赖时未分配 task 兜底 stage="999"。
        """
        in_degree: Dict[str, int] = {}
        dependents: Dict[str, List[str]] = {}

        for tid in task_map:
            in_degree[tid] = 0
            dependents[tid] = []

        for tid, task in task_map.items():
            in_degree[tid] = len(task.depends_on)
            for dep in task.depends_on:
                if dep in dependents:
                    dependents[dep].append(tid)

        queue: deque = deque()
        for tid, deg in in_degree.items():
            if deg == 0:
                queue.append((tid, 0))

        assigned = 0
        while queue:
            tid, stage = queue.popleft()
            task_map[tid].stage = str(stage)
            assigned += 1
            for dep in dependents.get(tid, []):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append((dep, stage + 1))

        if assigned < len(task_map):
            unassigned = [t for t, d in in_degree.items() if d > 0]
            logger.warning(f"TaskBuilder: possible cycle — {unassigned}")
            for tid in unassigned:
                task_map[tid].stage = "999"
