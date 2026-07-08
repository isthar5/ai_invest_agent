"""
Workflow Framework — 配置驱动的 Task 编排 (M1)。

组件:
  models.py    — WorkflowDefinition / TaskDefinition / ExecutionPlan
  executors.py — ExecutorRegistry + 4 Executor + WorkflowExecutorSkill
  loader.py    — WorkflowLoader (YAML → Definition)
  registry.py  — WorkflowRegistry (单例 + 热更新)
  builder.py   — TaskBuilder (Definition → ExecutionPlan)
"""

from .models import WorkflowDefinition, TaskDefinition, ExecutionPlan
from .registry import WorkflowRegistry, get_registry, reset_registry
from .loader import WorkflowLoader
from .builder import TaskBuilder
from .service import WorkflowService
from .result import WorkflowResult
from .executors import ExecutorRegistry, WorkflowExecutorSkill  # noqa: F401

__all__ = [
    "WorkflowDefinition",
    "TaskDefinition",
    "ExecutionPlan",
    "WorkflowRegistry",
    "get_registry",
    "reset_registry",
    "WorkflowLoader",
    "TaskBuilder",
    "WorkflowService",
    "WorkflowResult",
    "ExecutorRegistry",
]
