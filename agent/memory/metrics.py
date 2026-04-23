from prometheus_client import Histogram, Counter

# 集中定义 Memory 相关的 Prometheus 指标，避免多个模块重复注册导致冲突
# 通过 "module" 标签区分 short_term 和 long_term

memory_latency = Histogram(
    "agent_memory_latency_seconds",
    "Memory operation latency",
    ["operation", "module"]
)

memory_hit = Counter(
    "agent_memory_hit_total",
    "Memory hit count",
    ["module"]
)
