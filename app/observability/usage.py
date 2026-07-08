"""
Usage Tracker — 统一 LLM Token 用量追踪。

所有 LLM 调用通过 UsageTracker 记录，不在各 Agent 内重复统计。

UsageRecord 字段：
  request_id, session_id, user_id, agent, skill,
  provider, model, prompt_tokens, completion_tokens,
  cached_tokens, reasoning_tokens, total_tokens,
  latency_ms, tool_calls, estimated_cost, timestamp

用法：
  from app.observability.usage import UsageTracker, UsageRecord

  tracker = UsageTracker.get_instance()

  # 记录 LLM 调用
  tracker.record(UsageRecord(
      agent="QuantAgent",
      model="deepseek-chat",
      prompt_tokens=500,
      completion_tokens=200,
      latency_ms=320,
  ))

  # 查询统计
  total = tracker.total_tokens()
  records = tracker.recent(limit=10)
"""

from __future__ import annotations

import time
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from .context import request_context

# ── 定价表（$/1M tokens） ─────────────────────────────

PRICING = {
    "deepseek-chat":       {"prompt": 0.14, "completion": 0.28},
    "deepseek-reasoner":   {"prompt": 0.55, "completion": 2.19},
    "gpt-4o":              {"prompt": 2.50, "completion": 10.00},
    "gpt-4o-mini":         {"prompt": 0.15, "completion": 0.60},
    "claude-sonnet-5":     {"prompt": 3.00, "completion": 15.00},
    "claude-haiku-4-5":    {"prompt": 0.80, "completion": 4.00},
}


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """根据模型和 token 数估算费用（USD）"""
    pricing = PRICING.get(model)
    if not pricing:
        return 0.0
    return (
        prompt_tokens / 1_000_000 * pricing["prompt"]
        + completion_tokens / 1_000_000 * pricing["completion"]
    )


@dataclass
class UsageRecord:
    agent: str = ""
    skill: str = ""
    provider: str = ""
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    tool_calls: int = 0
    request_id: str = ""
    session_id: str = ""
    user_id: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def estimated_cost(self) -> float:
        return estimate_cost(self.model, self.prompt_tokens, self.completion_tokens)


class UsageTracker:
    """线程安全的 LLM 用量追踪器（单例）"""

    _instance: Optional["UsageTracker"] = None
    _lock = threading.Lock()

    def __init__(self, max_records: int = 10_000):
        self._records: deque[UsageRecord] = deque(maxlen=max_records)
        self._total_prompt_tokens = 0
        self._total_completion_tokens = 0
        self._total_cost = 0.0

    @classmethod
    def get_instance(cls) -> "UsageTracker":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def record(self, record: UsageRecord):
        """记录一次 LLM 调用"""
        # 自动从 RequestContext 补充字段
        ctx = request_context()
        if not record.request_id:
            record.request_id = ctx.request_id
        if not record.session_id:
            record.session_id = ctx.session_id
        if not record.user_id:
            record.user_id = ctx.user_id
        if not record.agent:
            record.agent = ctx.agent
        if not record.skill:
            record.skill = ctx.skill

        # 自动计算 total_tokens
        if record.total_tokens == 0:
            record.total_tokens = (
                record.prompt_tokens + record.completion_tokens
                + record.cached_tokens + record.reasoning_tokens
            )

        with self._lock:
            self._records.append(record)
            self._total_prompt_tokens += record.prompt_tokens
            self._total_completion_tokens += record.completion_tokens
            self._total_cost += record.estimated_cost

    def recent(self, limit: int = 10) -> List[UsageRecord]:
        """获取最近 N 条记录"""
        with self._lock:
            return list(self._records)[-limit:]

    def total_prompt_tokens(self) -> int:
        return self._total_prompt_tokens

    def total_completion_tokens(self) -> int:
        return self._total_completion_tokens

    def total_cost(self) -> float:
        return self._total_cost

    def record_count(self) -> int:
        with self._lock:
            return len(self._records)

    def summary(self) -> dict:
        """获取用量摘要"""
        with self._lock:
            records = list(self._records)
        by_model = {}
        for r in records:
            if r.model not in by_model:
                by_model[r.model] = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost": 0.0}
            by_model[r.model]["calls"] += 1
            by_model[r.model]["prompt_tokens"] += r.prompt_tokens
            by_model[r.model]["completion_tokens"] += r.completion_tokens
            by_model[r.model]["cost"] += r.estimated_cost

        return {
            "total_requests": len(records),
            "total_prompt_tokens": self._total_prompt_tokens,
            "total_completion_tokens": self._total_completion_tokens,
            "total_cost_usd": round(self._total_cost, 6),
            "by_model": by_model,
        }
