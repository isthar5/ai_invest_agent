"""
RetryPolicy — 可配置的重试策略。

支持：指数退避、最大重试、可重试/不可重试异常分类。

SOLID：单一职责（仅负责重试决策），依赖注入（策略对象可替换）。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Optional, Tuple, Type

logger = logging.getLogger("runtime.retry")


@dataclass
class RetryPolicy:
    """
    重试策略配置。

    Args:
        max_retries: 最大重试次数
        backoff_base: 退避基数（秒）
        backoff_multiplier: 每次退避倍增值
        max_backoff: 最大退避时间（秒）
        retryable_exceptions: 可重试的异常类型元组
        non_retryable_exceptions: 不可重试的异常类型元组（优先级高于 retryable）
    """

    max_retries: int = 3
    backoff_base: float = 0.5
    backoff_multiplier: float = 2.0
    max_backoff: float = 10.0
    retryable_exceptions: Tuple[Type[BaseException], ...] = (Exception,)
    non_retryable_exceptions: Tuple[Type[BaseException], ...] = ()

    def should_retry(self, attempt: int, exception: BaseException) -> bool:
        """判断是否应该重试"""
        if attempt >= self.max_retries:
            return False
        # 不可重试异常优先
        if isinstance(exception, self.non_retryable_exceptions):
            return False
        return isinstance(exception, self.retryable_exceptions)

    def backoff_delay(self, attempt: int) -> float:
        """计算第 N 次重试的退避延迟（指数退避）"""
        delay = self.backoff_base * (self.backoff_multiplier ** attempt)
        return min(delay, self.max_backoff)

    async def execute(
        self,
        fn: Callable,
        *args,
        on_retry: Optional[Callable[[int, BaseException], None]] = None,
        **kwargs,
    ):
        """
        执行带重试的函数调用。

        Args:
            fn: 要执行的异步函数
            on_retry: 每次重试时的回调（attempt, exception）
        """
        last_exception: Optional[BaseException] = None

        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as exc:
                last_exception = exc
                if not self.should_retry(attempt, exc):
                    raise

                delay = self.backoff_delay(attempt)
                logger.warning(
                    f"Retry {attempt + 1}/{self.max_retries} "
                    f"after {delay:.1f}s: {exc}"
                )
                if on_retry:
                    on_retry(attempt, exc)
                await asyncio.sleep(delay)

        raise last_exception  # type: ignore[misc]
