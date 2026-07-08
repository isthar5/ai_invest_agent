"""
WorkflowService — Node 层的统一 Workflow 执行入口。

Node 只通过 WorkflowService.run(workflow_id, **params) 触发执行，
通过 WorkflowResult.outputs["task_id"] 获取结果。
不直接调用 Registry / TaskBuilder / Runtime。

职责边界:
  WorkflowService: Registry → TaskBuilder → ExecutionPlan → Runtime → WorkflowResult
  Node:            构建 params（messages / context），调用 service.run()
"""

from __future__ import annotations

import itertools
import logging
from typing import Any, Dict

from app.runtime import ExecutionRuntime
from .registry import get_registry
from .builder import TaskBuilder
from .result import WorkflowResult

logger = logging.getLogger("workflow.service")

_seq = itertools.count(1)


class WorkflowService:
    """Workflow 执行服务。Node 的唯一 Workflow 入口。"""

    def __init__(self, runtime: ExecutionRuntime):
        self._runtime = runtime

    async def run(
        self,
        workflow_id: str,
        **params: Any,
    ) -> WorkflowResult:
        """加载 Workflow → 构建 Plan → 顺序执行 → WorkflowResult。

        M1: 顺序执行，手动数据传递。
        M2+: 升级为 execute_dag + VariableResolver，Node 调用方无需改动。
        """
        definition = get_registry().get(workflow_id)
        plan = TaskBuilder().build(definition, **params)

        outputs: Dict[str, Any] = {}
        for task in plan.tasks:
            task.payload = {**task.payload, **params}
            task.task_id = f"{task.task_id}_{next(_seq)}"
            logger.debug(f"WorkflowService: executing '{task.task_id}'")

            handle = await self._runtime.submit(task)
            await handle.wait()

            if handle.status().is_success:
                outputs[task.task_id.rsplit("_", 1)[0]] = handle.result()
            else:
                err = handle.exception()
                raise RuntimeError(
                    f"Task '{task.task_id}' failed: {err or handle.result()}"
                )

        return WorkflowResult(workflow_id=workflow_id, outputs=outputs)
