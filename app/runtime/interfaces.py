"""
Runtime Interfaces — 所有抽象接口集中定义。

依赖方向：所有 Runtime 模块依赖此文件中的接口，而非具体实现。
这保证了 Scheduler / TaskExecutor / ExecutionHandle / ResultAggregator
的可替换性（Python → Go）。

SOLID：
  - Interface Segregation: 小而专注的接口
  - Dependency Inversion: 高层模块依赖接口，不依赖实现
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .task import Task, TaskStatus


# ═══════════════════════════════════════════════════════════════
#  ExecutionHandle
# ═══════════════════════════════════════════════════════════════

class ExecutionHandle(ABC):
    """
    Task 执行句柄。不暴露底层并发原语（asyncio.Future / gRPC Stream）。

    PythonExecutionHandle: 内部包装 asyncio.Future
    GoExecutionHandle:     内部包装 gRPC Stream
    """

    @property
    @abstractmethod
    def task_id(self) -> str:
        ...

    @abstractmethod
    def status(self) -> TaskStatus:
        ...

    @abstractmethod
    def result(self) -> Any:
        """阻塞获取结果，若失败则抛出异常"""
        ...

    @abstractmethod
    def exception(self) -> Optional[Exception]:
        ...

    @abstractmethod
    def done(self) -> bool:
        ...

    @abstractmethod
    async def wait(self, timeout: Optional[float] = None) -> Task:
        ...

    @abstractmethod
    def cancel(self) -> bool:
        ...


# ═══════════════════════════════════════════════════════════════
#  Scheduler
# ═══════════════════════════════════════════════════════════════

class Scheduler(ABC):
    """
    任务调度器抽象。

    PythonScheduler: asyncio + Worker Pool
    GoScheduler:     gRPC → Go Worker Pool（未来）
    """

    @abstractmethod
    async def submit(self, task: Task) -> ExecutionHandle:
        ...

    @abstractmethod
    async def cancel(self, task_id: str) -> bool:
        ...

    @abstractmethod
    async def wait(
        self,
        handles: List[ExecutionHandle],
        timeout: Optional[float] = None,
    ) -> List[ExecutionHandle]:
        ...

    @abstractmethod
    async def shutdown(self) -> None:
        ...


# ═══════════════════════════════════════════════════════════════
#  TaskExecutor
# ═══════════════════════════════════════════════════════════════

class TaskExecutor(ABC):
    """
    Skill 执行器抽象。Worker 通过它执行 Skill，不直接依赖 Skill。

    DefaultTaskExecutor: 通过 SkillRegistry 查找 Skill，应用 Retry/Timeout/Hook
    """

    @abstractmethod
    async def execute(self, task: Task) -> Task:
        ...

    @abstractmethod
    def resolve(self, skill_name: str) -> Any:
        """根据 skill name 返回 Skill 实例"""
        ...


# ═══════════════════════════════════════════════════════════════
#  ResultAggregator
# ═══════════════════════════════════════════════════════════════

class ResultAggregator(ABC):
    """
    结果聚合器抽象。等待多个 ExecutionHandle，合并结果。

    DefaultResultAggregator: 委托 CrossSkillFusion 做加权融合
    """

    @abstractmethod
    async def aggregate(
        self,
        handles: List[ExecutionHandle],
    ) -> "AggregatedResult":
        ...

    @abstractmethod
    def merge(self, tasks: List[Task]) -> "AggregatedResult":
        ...


# ═══════════════════════════════════════════════════════════════
#  AggregatedResult
# ═══════════════════════════════════════════════════════════════

class AggregatedResult:
    """
    聚合后的统一结果，供 LangGraph Synthesizer 消费。
    """

    def __init__(
        self,
        results: Dict[str, Any],
        tasks: List[Task],
        success_count: int = 0,
        fail_count: int = 0,
        timeout_count: int = 0,
        total_latency_ms: float = 0.0,
    ):
        self.results = results          # {skill_name: result_data}
        self.tasks = tasks              # 完整 Task 列表
        self.success_count = success_count
        self.fail_count = fail_count
        self.timeout_count = timeout_count
        self.total_latency_ms = total_latency_ms

    @property
    def all_success(self) -> bool:
        return self.fail_count == 0 and self.timeout_count == 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "results": self.results,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "timeout_count": self.timeout_count,
            "total_latency_ms": self.total_latency_ms,
            "all_success": self.all_success,
        }
