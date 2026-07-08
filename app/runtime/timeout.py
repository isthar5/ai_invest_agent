"""
TimeoutPolicy — 可配置的超时策略。

支持：per-Task 超时、全局超时、超时回调。

SOLID：单一职责（仅负责超时控制），依赖注入。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("runtime.timeout")


@dataclass
class TimeoutPolicy:
    """
    超时策略配置。

    Args:
        task_timeout: 单个 Task 的默认超时（秒），Task 级别的 timeout 优先
        global_timeout: 整个执行批次的全局超时（秒），None 表示不限制
    """

    task_timeout: float = 30.0
    global_timeout: Optional[float] = None

    def effective_timeout(self, task_timeout: Optional[float] = None) -> float:
        """计算有效超时（取 Task 级别和 Policy 级别的最小值）"""
        candidates = [self.task_timeout]
        if task_timeout is not None:
            candidates.append(task_timeout)
        if self.global_timeout is not None:
            candidates.append(self.global_timeout)
        return min(candidates)

    async def execute(
        self,
        fn: Callable,
        timeout: Optional[float] = None,
        on_timeout: Optional[Callable[[], None]] = None,
        *args,
        **kwargs,
    ):
        """
        在超时保护下执行异步函数。

        Args:
            fn: 要执行的异步函数
            timeout: 覆盖默认超时（秒）
            on_timeout: 超时时回调
        """
        effective = timeout or self.task_timeout

        try:
            return await asyncio.wait_for(
                fn(*args, **kwargs),
                timeout=effective,
            )
        except asyncio.TimeoutError:
            logger.error(f"Task timed out after {effective}s")
            if on_timeout:
                on_timeout()
            raise
