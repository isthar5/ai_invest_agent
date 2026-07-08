"""
Tracing — 轻量级分布式追踪。

自动生成并传播 trace_id / span_id。
基于 RequestContext，整个调用链共享同一个 trace_id。

用法：
  from app.observability.tracing import trace_span

  # 作为上下文管理器：
  with trace_span("rag_retrieval") as span:
      docs = await hybrid_search(query)
      span.set_tag("doc_count", len(docs))

  # trace_id 自动从 RequestContext 获取
  from app.observability.tracing import get_trace_id
  tid = get_trace_id()
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

from .context import request_context


@dataclass
class Span:
    name: str
    trace_id: str = ""
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_span_id: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    tags: dict = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time) * 1000 if self.end_time > 0 else 0

    def set_tag(self, key: str, value):
        self.tags[key] = value

    def set_error(self, error: str):
        self.error = error


def get_trace_id() -> str:
    return request_context().trace_id


def get_request_id() -> str:
    return request_context().request_id


@contextmanager
def trace_span(name: str, **tags):
    """
    创建一个追踪 Span。

    自动从 RequestContext 继承 trace_id。
    退出时记录耗时和异常。
    """
    ctx = request_context()
    span = Span(
        name=name,
        trace_id=ctx.trace_id,
    )
    span.start_time = time.time()
    for k, v in tags.items():
        span.set_tag(k, v)

    try:
        yield span
    except Exception as e:
        span.set_error(str(e))
        raise
    finally:
        span.end_time = time.time()
