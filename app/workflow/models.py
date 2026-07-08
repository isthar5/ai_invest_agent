"""
Workflow 数据模型 — M1 最小集。

TaskDefinition  = YAML 中一个 task 的不可变配置投影。
WorkflowDefinition = 整条 workflow 的不可变配置容器。
ExecutionPlan  = TaskBuilder 的产出，Runtime 的入参（封装 List[Task]）。

设计原则:
  - TaskDefinition / WorkflowDefinition 永远不可变（frozen dataclass）
  - ExecutionPlan 封装 tasks，未来扩展 context/artifacts 不影响 Runtime
  - depends_on 直接声明在 task 上，M1 不做 edges 解析
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


# ═══════════════════════════════════════════════════════════════
#  TaskDefinition
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True, frozen=True)
class TaskDefinition:
    """YAML 中一个 task 的不可变配置投影。

    Attributes:
        id: Workflow 内唯一标识（YAML key）。
        executor: 执行器名 — ExecutorRegistry 据此查找 Executor。
        depends_on: 依赖的 task id 列表（拓扑排序依据）。
        config: Executor 特定配置，直接传给 Executor.execute()。
    """

    id: str
    executor: str
    depends_on: Tuple[str, ...] = ()
    config: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
#  WorkflowDefinition
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True, frozen=True)
class WorkflowDefinition:
    """完整的 Workflow 配置定义（不可变）。

    由 WorkflowLoader 从 YAML 解析创建，仅用于 TaskBuilder 读取。

    Attributes:
        workflow_id: 唯一标识（YAML 文件名不含 .yaml）。
        version: 语义版本。
        tasks: 所有 task 定义。
    """

    workflow_id: str
    version: str = "1.0"
    tasks: Tuple[TaskDefinition, ...] = ()

    @property
    def task_ids(self) -> Tuple[str, ...]:
        """按定义顺序返回所有 task id。"""
        return tuple(t.id for t in self.tasks)

    @property
    def task_map(self) -> Dict[str, TaskDefinition]:
        """O(1) 查找: {task_id: TaskDefinition}。"""
        return {t.id: t for t in self.tasks}


# ═══════════════════════════════════════════════════════════════
#  ExecutionPlan
# ═══════════════════════════════════════════════════════════════

@dataclass(slots=True, frozen=True)
class ExecutionPlan:
    """TaskBuilder 的产出，Runtime.execute_dag() 的入参。

    封装 tasks 列表，确保未来加字段不影响 Runtime 接口。

    Attributes:
        workflow_id: 来源 workflow 标识。
        tasks: TaskBuilder 生产的 Task 列表（带 depends_on 的 DAG）。
        metadata: 扩展预留（M1 为空）。
    """

    workflow_id: str
    tasks: List[Any]  # List[app.runtime.task.Task]
    metadata: Dict[str, Any] = field(default_factory=dict)
