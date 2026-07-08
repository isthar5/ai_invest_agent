"""
RequestContext — 请求级上下文，基于 contextvars 实现协程安全。

整个请求链路共享同一个 Context：
  API → Router → Planner → Skill → Retriever → LLM → Response

字段：
  request_id   — 请求唯一 ID
  user_id      — 用户标识
  session_id   — 会话标识
  trace_id     — 分布式追踪 ID
  agent        — 当前 Agent 名称
  skill        — 当前 Skill 名称
  provider     — LLM provider
  model        — 当前使用的模型名

用法：
  from app.observability.context import request_context

  ctx = request_context()
  ctx.request_id = "abc123"
  ctx.agent = "QuantAgent"

  # 在任意深层函数中：
  rid = request_context().request_id
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    session_id: str = ""
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    agent: str = ""
    skill: str = ""
    provider: str = ""
    model: str = ""

    def to_dict(self) -> dict:
        return {
            "request_id": self.request_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "trace_id": self.trace_id,
            "agent": self.agent,
            "skill": self.skill,
            "provider": self.provider,
            "model": self.model,
        }


_ctx: ContextVar[RequestContext] = ContextVar("request_context", default=RequestContext())


def request_context() -> RequestContext:
    """获取当前协程的 RequestContext"""
    return _ctx.get()


def set_request_context(ctx: RequestContext) -> None:
    """设置当前协程的 RequestContext"""
    _ctx.set(ctx)


def init_request_context(**kwargs) -> RequestContext:
    """
    初始化一个新的 RequestContext 并绑定到当前协程。

    自动生成 request_id / trace_id（若未提供）。
    """
    ctx = RequestContext(**{k: v for k, v in kwargs.items() if v})
    _ctx.set(ctx)
    return ctx
