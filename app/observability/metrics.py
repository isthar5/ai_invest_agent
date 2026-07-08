"""
Observability — 统一 Prometheus 指标定义与采集中间件。

指标清单：
  http_requests_total          — HTTP 请求计数
  http_request_duration_seconds — HTTP 请求延迟
  llm_requests_total           — LLM 调用计数
  llm_latency_seconds          — LLM 调用延迟
  tool_requests_total          — Tool 调用计数
  tool_latency_seconds         — Tool 调用延迟
  rag_retrieval_seconds        — RAG 检索耗时
  embedding_seconds            — 向量化耗时
  sql_execution_seconds        — SQL 执行耗时
  token_usage_total            — Token 用量
  agent_errors_total           — Agent 错误计数
  cb_status_gauge              — 熔断器状态
  memory_latency_seconds       — Memory 操作延迟（从 agent.memory.metrics 重新导出）
  memory_hit_total             — Memory 命中计数（从 agent.memory.metrics 重新导出）
"""

from prometheus_client import Counter, Gauge, Histogram

# ── HTTP 指标 ─────────────────────────────────────────

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# ── LLM 指标 ──────────────────────────────────────────

llm_requests_total = Counter(
    "llm_requests_total",
    "Total LLM requests",
    ["provider", "model", "agent"],
)

llm_latency_seconds = Histogram(
    "llm_latency_seconds",
    "LLM call latency in seconds",
    ["provider", "model"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0],
)

# ── Tool 指标 ─────────────────────────────────────────

tool_requests_total = Counter(
    "tool_requests_total",
    "Total tool invocations",
    ["tool_name", "status"],
)

tool_latency_seconds = Histogram(
    "tool_latency_seconds",
    "Tool execution latency in seconds",
    ["tool_name"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
)

# ── RAG / Embedding / SQL 指标 ────────────────────────

rag_retrieval_seconds = Histogram(
    "rag_retrieval_seconds",
    "RAG retrieval latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

embedding_seconds = Histogram(
    "embedding_seconds",
    "Embedding computation latency in seconds",
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5],
)

sql_execution_seconds = Histogram(
    "sql_execution_seconds",
    "SQL execution latency in seconds",
    buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0],
)

# ── Token / Error 指标 ────────────────────────────────

token_usage_total = Counter(
    "token_usage_total",
    "Total token usage",
    ["provider", "model", "type"],  # type = prompt | completion
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Total agent errors",
    ["agent", "error_type"],
)

# ── 熔断器状态 ────────────────────────────────────────

cb_status_gauge = Gauge(
    "cb_status",
    "Circuit breaker status (0=Closed, 1=Open, 0.5=Half-Open)",
    ["service"],
)


# ── Memory 指标（从 agent.memory.metrics 重新导出） ──

_memory_metrics_loaded = False
_memory_latency = None
_memory_hit = None


def _load_memory_metrics():
    """延迟导入 Memory 指标，避免循环依赖"""
    global _memory_metrics_loaded, _memory_latency, _memory_hit
    if _memory_metrics_loaded:
        return
    try:
        from app.agent.memory.metrics import memory_latency, memory_hit
        _memory_latency = memory_latency
        _memory_hit = memory_hit
    except ImportError:
        pass
    _memory_metrics_loaded = True


def get_memory_latency_seconds():
    """返回 Memory 操作延迟 Histogram（延迟加载）"""
    _load_memory_metrics()
    return _memory_latency


def get_memory_hit_total():
    """返回 Memory 命中 Counter（延迟加载）"""
    _load_memory_metrics()
    return _memory_hit


# ── 采集中间件 ────────────────────────────────────────

import time as _time


async def metrics_middleware(request, call_next):
    """记录 HTTP 请求指标 + 延迟 + X-Process-Time 响应头"""
    start = _time.time()
    method = request.method
    path = request.url.path

    response = await call_next(request)

    duration = _time.time() - start
    http_requests_total.labels(
        method=method, path=path, status_code=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(method=method, path=path).observe(duration)

    # 统一的 process_time（避免多个中间件重复计时）
    response.headers["X-Process-Time"] = f"{duration:.3f}s"

    return response
