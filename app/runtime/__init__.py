"""
Execution Runtime — 统一 AI Agent 执行运行时。

架构：
  LangGraph (Planning)
    ↓
  ExecutionRuntime (Execution)
    ↓
  Scheduler (Dispatching) → PythonScheduler | GoScheduler (未来)
    ↓
  Worker (Lifecycle)
    ↓
  TaskExecutor (Skill Invocation)
    ↓
  Skill (Business Logic)

公开 API：
  - ExecutionRuntime: 运行时门面（工厂方法 create() 或手动 DI）
  - Task / TaskStatus: 统一任务对象与生命周期
  - ExecutionHandle: 执行句柄（不暴露 asyncio.Future）
  - RetryPolicy / TimeoutPolicy: 可配置策略
  - Scheduler / TaskExecutor / ResultAggregator: 抽象接口
"""

from .task import Task, TaskStatus
from .interfaces import (
    Scheduler,
    TaskExecutor,
    ExecutionHandle,
    ResultAggregator,
    AggregatedResult,
)
from .handle import PythonExecutionHandle
from .executor import DefaultTaskExecutor
from .worker import Worker
from .python_scheduler import PythonScheduler
from .aggregator import DefaultResultAggregator
from .retry import RetryPolicy
from .timeout import TimeoutPolicy
from .events import EventBus, EventType, RuntimeEvent
from .hooks import (
    BeforeExecuteHook,
    AfterExecuteHook,
    RetryHook,
    TimeoutHook,
    ErrorHook,
    ObservabilityBeforeHook,
    ObservabilityAfterHook,
    default_hooks,
)
from .runtime import ExecutionRuntime
from .go_scheduler import GoScheduler
from .go_handle import GoExecutionHandle

__all__ = [
    # Runtime
    "ExecutionRuntime",
    # Task
    "Task",
    "TaskStatus",
    # Interfaces
    "Scheduler",
    "TaskExecutor",
    "ExecutionHandle",
    "ResultAggregator",
    "AggregatedResult",
    # Implementations
    "PythonExecutionHandle",
    "GoExecutionHandle",
    "GoScheduler",
    "DefaultTaskExecutor",
    "Worker",
    "PythonScheduler",
    "DefaultResultAggregator",
    # Policies
    "RetryPolicy",
    "TimeoutPolicy",
    # Events & Hooks
    "EventBus",
    "EventType",
    "RuntimeEvent",
    "BeforeExecuteHook",
    "AfterExecuteHook",
    "RetryHook",
    "TimeoutHook",
    "ErrorHook",
    "ObservabilityBeforeHook",
    "ObservabilityAfterHook",
    "default_hooks",
]
