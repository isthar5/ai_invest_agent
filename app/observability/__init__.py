"""
Observability — 统一可观测性基础设施。

模块：
  context   — RequestContext（请求级上下文，contextvars 协程安全）
  tracing   — TraceContext（trace_id / span_id 传播）
  logger    — JSON 结构化日志
  metrics   — Prometheus 指标（HTTP / LLM / Tool / RAG / SQL / Token / Error）
  usage     — UsageTracker（LLM Token 用量追踪 + 费用估算）
"""

from .context import (
    RequestContext,
    request_context,
    set_request_context,
    init_request_context,
)
from .tracing import (
    Span,
    trace_span,
    get_trace_id,
    get_request_id,
)
from .logger import (
    setup_logging,
    get_logger,
    ObservabilityLogger,
)
from .metrics import (
    http_requests_total,
    http_request_duration_seconds,
    llm_requests_total,
    llm_latency_seconds,
    tool_requests_total,
    tool_latency_seconds,
    rag_retrieval_seconds,
    embedding_seconds,
    sql_execution_seconds,
    token_usage_total,
    agent_errors_total,
    cb_status_gauge,
    metrics_middleware,
)
from .usage import (
    UsageTracker,
    UsageRecord,
    estimate_cost,
    PRICING,
)

__all__ = [
    # context
    "RequestContext",
    "request_context",
    "set_request_context",
    "init_request_context",
    # tracing
    "Span",
    "trace_span",
    "get_trace_id",
    "get_request_id",
    # logger
    "setup_logging",
    "get_logger",
    "ObservabilityLogger",
    # metrics
    "http_requests_total",
    "http_request_duration_seconds",
    "llm_requests_total",
    "llm_latency_seconds",
    "tool_requests_total",
    "tool_latency_seconds",
    "rag_retrieval_seconds",
    "embedding_seconds",
    "sql_execution_seconds",
    "token_usage_total",
    "agent_errors_total",
    "cb_status_gauge",
    "metrics_middleware",
    # usage
    "UsageTracker",
    "UsageRecord",
    "estimate_cost",
    "PRICING",
]
