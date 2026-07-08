"""
DefaultTaskExecutor — 通过 SkillRegistry 查找并执行 Skill。

职责：
  - Skill 查找（SkillRegistry）
  - Skill 调用
  - Retry 策略应用
  - Timeout 策略应用
  - Hook 调用（Before/After/Retry/Timeout/Error）
  - Event 发布

不负责：调度、生命周期（由 Worker 负责）

SOLID：
  - Single Responsibility: 仅负责 Skill 执行编排
  - Dependency Injection: SkillRegistry / RetryPolicy / TimeoutPolicy / Hooks / EventBus 全部注入
  - Open/Closed: 通过 Hook 扩展，无需修改本类
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, List, Optional

from .interfaces import TaskExecutor
from .task import Task, TaskStatus
from .retry import RetryPolicy
from .timeout import TimeoutPolicy
from .events import EventBus, EventType, RuntimeEvent

logger = logging.getLogger("runtime.executor")


class DefaultTaskExecutor(TaskExecutor):
    """
    默认 TaskExecutor 实现。

    通过 DI 注入所有依赖：
      - skill_registry: SkillRegistry（查找 Skill 实例）
      - retry_policy: 默认重试策略（Task 级别可覆盖）
      - timeout_policy: 默认超时策略（Task 级别可覆盖）
      - hooks: Hook 列表
      - event_bus: 事件总线
    """

    def __init__(
        self,
        skill_registry: Any = None,
        retry_policy: Optional[RetryPolicy] = None,
        timeout_policy: Optional[TimeoutPolicy] = None,
        hooks: Optional[List[Any]] = None,
        event_bus: Optional[EventBus] = None,
    ):
        self._registry = skill_registry
        self._default_retry = retry_policy or RetryPolicy()
        self._default_timeout = timeout_policy or TimeoutPolicy()
        self._hooks = hooks or []
        self._event_bus = event_bus or EventBus()

    # ── TaskExecutor 接口实现 ──────────────────────────────

    def resolve(self, skill_name: str) -> Any:
        """通过 SkillRegistry 查找 Skill 实例"""
        if self._registry is None:
            raise RuntimeError(
                f"Cannot resolve skill '{skill_name}': "
                f"no skill_registry injected"
            )

        # SkillRegistry + SkillManager 模式（复用现有代码）
        try:
            from app.agent.registry import SkillRegistry
            skill_cls = SkillRegistry.get_skill(skill_name)
            if skill_cls is None:
                raise ValueError(f"Skill '{skill_name}' not registered")

            # SkillManager 单例缓存（复用现有代码）
            from app.agent.runtime import SkillManager
            instance = SkillManager.get_instance(skill_name)
            if instance is None:
                instance = skill_cls()
            return instance
        except ImportError:
            raise RuntimeError(f"Skill resolution failed for '{skill_name}'")

    async def execute(self, task: Task) -> Task:
        """执行 Task：Hook → Retry → Timeout → Skill → Hook"""
        retry_policy = task.retry_policy or self._default_retry
        timeout_policy = task.timeout_policy or self._default_timeout
        hooks = task.hooks if task.hooks else self._hooks

        # ── Before Hooks ──────────────────────────────────
        for hook in hooks:
            if hasattr(hook, "on_before_execute"):
                task = await hook.on_before_execute(task)

        # ── 执行（Retry + Timeout 包裹） ──────────────────
        async def _do_execute() -> Task:
            skill = self.resolve(task.skill)
            result = await skill.execute(task.payload)

            # 将 SkillResult 写入 Task
            if hasattr(result, "success"):
                if result.success:
                    task.result = result.data
                    task.transition_to(TaskStatus.COMPLETED)
                else:
                    task.error = result.error or "Skill returned failure"
                    task.transition_to(TaskStatus.FAILED)
            else:
                task.result = result
                task.transition_to(TaskStatus.COMPLETED)
            return task

        async def _on_retry(attempt: int, exc: BaseException) -> None:
            task.retry_count = attempt + 1
            for hook in hooks:
                if hasattr(hook, "on_retry"):
                    await hook.on_retry(task, attempt, exc)

        async def _on_timeout() -> None:
            task.transition_to(TaskStatus.TIMEOUT)
            for hook in hooks:
                if hasattr(hook, "on_timeout"):
                    await hook.on_timeout(task)

        try:
            effective_timeout = timeout_policy.effective_timeout(task.timeout)
            await timeout_policy.execute(
                lambda: retry_policy.execute(_do_execute, on_retry=_on_retry),
                timeout=effective_timeout,
                on_timeout=_on_timeout,
            )
        except asyncio.TimeoutError:
            task.transition_to(TaskStatus.TIMEOUT)
            task.error = f"Timeout after {task.timeout}s"
        except Exception as exc:
            task.transition_to(TaskStatus.FAILED)
            task.error = str(exc)
            for hook in hooks:
                if hasattr(hook, "on_error"):
                    await hook.on_error(task, exc)

        # ── After Hooks ──────────────────────────────────
        for hook in hooks:
            if hasattr(hook, "on_after_execute"):
                await hook.on_after_execute(task)

        return task
