# AI Invest Agent 项目总结

> 视角：Go 后端开发工程师  
> 日期：2026-05-12  
> 项目路径：`E:\ai_invest_agent\app`

---

## 1. 一句话概述

这是一个 **化工行业智能投研助手**，核心能力是将 277 份 PDF 研报向量化存入 Qdrant，结合 LightGBM 量化选股模型，通过 FastAPI + RAG + Multi-Agent 架构对外提供自然语言投研问答服务。Go 部分仅占 ~5%，是一个被 Python 主进程通过 HTTP 调用的工具计算 Sidecar。

---

## 2. 项目规模与语言分布

| 语言 | 文件数（估算） | 占比 | 职责 |
|------|:---------:|:----:|------|
| Python 3.13 | ~60 | 92% | FastAPI 主服务、RAG、量化引擎、Multi-Agent、数据摄入 |
| Go 1.20 | ~4 | 5% | Gin 工具服务器（math/text2sql 工具代理） |
| YAML/配置 | ~5 | 3% | Prometheus、Grafana、Gateway 路由配置 |

### 2.1 目录树

```
app/
├── main.py                    # FastAPI 入口（8000端口）
├── api/
│   ├── chat.py                # /api/chat 接口（RAG/Agent/流式）
│   ├── upload_signal.py       # /api/upload_signal 信号文件上传
│   └── websocket.py           # /ws WebSocket（Multi-Agent 实时流）
├── agent/
│   ├── base.py                # BaseSkill 抽象基类（ABC）
│   ├── registry.py            # SkillRegistry 注册中心（类单例）
│   ├── fusion.py              # CrossSkillFusion 跨技能融合决策引擎
│   ├── go_tool_client.py      # Go 工具 HTTP 客户端
│   └── runtime.py             # Agent 运行时（LangGraph）
├── multi_agent/
│   ├── base.py                # AgentMessage / BaseAgent / StateManager
│   ├── agents.py              # QuantAgent / Text2SQLAgent / RAGAgent
│   ├── router.py              # RouterAgent（意图路由分发）
│   ├── tools.py               # Tool 注册表（5个工具）
│   └── fusion.py              # Fusion.aggregate（多Agent结果聚合）
├── rag/
│   └── pipeline.py            # RAG 主流程（检索→重排→LLM生成）
├── retrieval/
│   ├── embedder.py             # Dense(BGE-small-zh) + Sparse(BM25) 双路向量化
│   ├── hybrid.py               # Hybrid Search（RRF/Weighted 融合）
│   ├── reranker.py             # CrossEncoder 重排序（BGE-reranker-base）
│   ├── mmr.py                  # MMR 多样性算法
│   └── dedup.py               # 余弦去重
├── quant/
│   ├── data_engine.py          # Qlib + AKShare 数据源
│   ├── factor_engine.py        # FactorEngineV2（技术/动量/截面因子）
│   ├── model.py                # LightGBM + SHAP 模型
│   ├── pipeline.py             # 量化分析主流程（训练→预测→报告）
│   ├── quant_tool.py           # 量化工具入口（三级降级策略）
│   └── explainer.py            # SHAP 解释生成
├── ingestion/
│   ├── batch_parse.py          # magic-pdf 批量 PDF → Markdown
│   ├── loader.py               # MarkdownLoader（分块+元数据提取）
│   ├── cleaner.py              # FinancialCleaner（LangChain递归切分+表格保护）
│   └── ingest_to_qdrant.py     # Qdrant 入库器（批量upsert）
├── services/text2sql/
│   └── main.py                 # Text2SQL 独立服务（FastAPI + Schema Linking）
├── config/
│   ├── settings.py             # Settings 配置中心（env + dataclass）
│   └── stock_pool.py           # 化工股票池（33只）
├── gateway/                    # API 网关（未来扩展）
│   ├── app/main.py             # 网关入口
│   ├── app/gateway/router.py   # 路由匹配
│   ├── app/gateway/proxy.py    # HTTP 反向代理（带熔断+缓存）
│   ├── app/middleware/
│   │   ├── circuit_breaker.py  # 熔断器（CLOSED→OPEN→HALF_OPEN）
│   │   ├── rate_limiter.py     # Redis Token Bucket 限流（Lua脚本）
│   │   └── metrics.py          # Prometheus 指标采集
│   └── services/
│       ├── rag_service/        # RAG 微服务包装
│       ├── quant_service/      # Quant 微服务包装
│       └── auth_service/       # Auth 微服务包装
├── go-agent/
│   ├── go.mod                  # module go-agent, Go 1.20, 仅依赖 gin
│   ├── go.sum
│   ├── server/http.go          # Gin HTTP 服务器（/health /tools /call）
│   ├── router/router.go        # 工具路由器（注册/调用/列表）
│   ├── schema/schema.go        # ToolSchema 结构体
│   └── tools/math.go           # MathTool（加法计算器）
├── scripts/
│   ├── evaluate_retrieval.py
│   └── generate_eval_data.py
├── tests/
│   └── test.py                 # 集成测试（Agent vs RAG 对比）
└── utils/
    ├── tracer.py               # 微型耗时追踪器
    └── citation.py             # 引用标注工具
```

---

## 3. 架构分层（Go 开发者视角）

从 Go 后端习惯的分层架构来看，这个项目的层级对应关系：

```
┌──────────────────────────────────────────────────┐
│  Transport Layer (像 Gin Handler)                  │
│  - api/chat.py, api/websocket.py, main.py         │
│  - 路由注册、中间件、SSE/WS 流式输出               │
├──────────────────────────────────────────────────┤
│  Agent / Orchestration Layer (像 Service 层)       │
│  - multi_agent/router.py → 意图路由分发            │
│  - multi_agent/runtime.py → Multi-Agent 编排       │
│  - agent/fusion.py → 跨技能融合决策               │
├──────────────────────────────────────────────────┤
│  Domain Logic Layer (像 biz/ 或 usecase/)         │
│  - rag/pipeline.py → RAG 核心流程                 │
│  - quant/pipeline.py → 量化选股流程                │
│  - retrieval/* → 检索子系统                       │
├──────────────────────────────────────────────────┤
│  Infrastructure Layer (像 repo/ 或 infra/)         │
│  - Qdrant (向量数据库)                            │
│  - Redis (会话状态 + 限流)                         │
│  - PostgreSQL (结构化财务数据)                     │
│  - AKShare / Qlib (行情数据源)                     │
│  - DeepSeek API (LLM)                             │
└──────────────────────────────────────────────────┘
```

---

## 4. Go 组件深度分析

### 4.1 模块定位

`go-agent/` 是一个 **工具计算 Sidecar**，Python 主进程通过 HTTP (`GoToolClient`) 调用它。它扮演的角色类比：**一个独立的 gRPC/tRPC 微服务，只不 protocol 是 REST JSON**。

### 4.2 模块依赖

```
go-agent (module)
├── gin-gonic/gin v1.9.1    ← HTTP 框架
├── go 1.20                 ← 版本偏旧（2026年5月，1.20 是 2023 Q1 发布）
└── (间接依赖) sonic, go-playground/validator 等
```

### 4.3 代码结构分析

**`schema/schema.go`** — 定义 ToolSchema，相当于 gRPC 的 proto message：

```go
type ToolSchema struct {
    Name        string            `json:"name"`
    Description string            `json:"description"`
    Params      map[string]string `json:"params"`
}
```

**`router/router.go`** — 核心是 `Tool` 接口 + `Router` 注册表，经典 Go 模式：

```go
type Tool interface {
    Name() string
    Schema() schema.ToolSchema
    Run(input map[string]interface{}) (interface{}, error)
}
```

设计评价：
- ✅ `Tool` 接口设计干净，符合 Go 惯例（单方法接口）
- ✅ `Router.Register(t Tool)` 采用依赖注入，可测试
- ⚠️ `Run` 使用 `map[string]interface{}` 入参和 `interface{}` 出参，丢失类型安全。更好的做法是定义具体结构体或用泛型
- ⚠️ 参数校验仅检查 key 存在，不检查 value 类型

**`server/http.go`** — Gin Handler：

```go
engine.GET("/health", ...)
engine.GET("/tools", ...)      // 列出所有工具
engine.POST("/call", ...)      // 远程调用工具
```

设计评价：
- ✅ 经典的 RESTful 工具调用设计
- ❌ 没有超时控制（`r.Call` 可能永久阻塞）
- ❌ 没有中间件恢复（panic recovery），虽然有 Gin 默认 recovery
- ❌ 没有优雅关闭（graceful shutdown）

**`tools/math.go`** — MathTool 演示工具：

这是一个 Demo 级别的工具（两数相加）。实际项目中 Python 侧通过 `GoToolClient` 调用了 `text2sql` 工具，但 Go 代码中并未实现 Text2SQL——实际的 Text2SQL 是 Python 的独立 FastAPI 服务（`services/text2sql/main.py`）。

### 4.4 Python ↔ Go 通信

`agent/go_tool_client.py` 是一个薄 HTTP 客户端：

```python
class GoToolClient:
    def call(self, tool: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = requests.post(f"{self.base_url}/call", ...)
```

在 `multi_agent/tools.py` 中，`generate_sql()` 调用了这个客户端：
```python
client = GoToolClient()
return client.call("text2sql", {"query": content, "user": "multi_agent"})
```

**问题**：Go 侧没有注册 `text2sql` 工具，这个调用会返回 `"tool not found: text2sql"` 错误。这是一种未完成的集成。

---

## 5. 核心业务流程

### 5.1 请求入口

```
用户请求 POST /api/chat {"query":"万华化学怎么样？", "multi_agent":true}
         │
         ▼
┌─────────────────────┐
│  api/chat.py        │   multi_agent=true → run_multi_agent()
│                     │   use_agent=true  → run_agent()
│                     │   否则           → rag_quant_pipeline()
└─────────┬───────────┘
          │
          ▼
┌─────────────────────────────────────────────────┐
│           multi_agent/runtime.py                │
│  1. RouterAgent 关键词分类意图                    │
│  2. 根据意图分发到 QuantAgent/Text2SQL/RAGAgent  │
│  3. Fusion.aggregate 合并结果                    │
│  4. generate_answer → DeepSeek LLM 生成最终回答   │
└─────────────────────────────────────────────────┘
```

### 5.2 RAG 检索链路

```
query → classify_intent() → smart_retrieval()
         │                      │
         │        ┌─────────────┴─────────────┐
         │        │  multi_query_expansion()   │
         │        │  生成多个查询变体           │
         │        └─────────────┬─────────────┘
         │                      │
         │        ┌─────────────┴─────────────┐
         │        │  hybrid_search()          │
         │        │  双路并行: Dense + BM25    │
         │        │  RRF/Weighted 融合        │
         │        └─────────────┬─────────────┘
         │                      │
         │        ┌─────────────┴─────────────┐
         │        │  Reranker.rerank()        │
         │        │  CrossEncoder 精排         │
         │        └─────────────┬─────────────┘
         │                      │
         │        ┌─────────────┴─────────────┐
         │        │  apply_mmr()              │
         │        │  MMR 多样性去冗余           │
         │        └─────────────┬─────────────┘
         │                      │
         └──────────────────────┘
                │
    ┌───────────┴───────────┐
    │  LLM 生成              │
    │  DeepSeek-chat         │
    │  (流式 SSE / 非流式 JSON) │
    └───────────────────────┘
```

### 5.3 量化分析链路

```
run_quant_analysis()
    │
    ├─ build_features()  ← FactorEngineV2
    │   ├─ download_data()   ← AKShare（含 Parquet 本地缓存）
    │   ├─ add_industry()    ← 行业分类
    │   ├─ add_technical()   ← MA5/10/20/60, volatility, volume_z
    │   ├─ add_momentum()    ← 5/10/20/60日动量
    │   ├─ add_cross_section() ← 全市场排名 + 行业内排名
    │   └─ add_labels()      ← 未来5日收益
    │
    ├─ QuantModel (LightGBM + SHAP)
    │   ├─ train()
    │   └─ predict() → 预测收益 + SHAP 特征重要性
    │
    └─ 输出 Top5 股票 + 万华化学专项 + SHAP 解释
```

### 5.4 数据摄入链路

```
277 份 PDF 年报
    │
    ├─ magic-pdf (GPU) → Markdown
    │
    ├─ MarkdownLoader._split_markdown() → 按 ## 标题分块
    │
    ├─ FinancialCleaner.process()
    │   ├─ 识别保护表格行
    │   ├─ RecursiveCharacterTextSplitter (800字/150重叠)
    │   └─ Prefix 注入（公司|年份|Section）
    │
    └─ QdrantIngestor.ingest_directory()
        ├─ embed() → Dense(BGE-small-zh) + Sparse(BM25)
        └─ Qdrant upsert (batch=50)
```

---

## 6. 关键技术点

### 6.1 Multi-Agent 架构

项目实现了一个轻量级 Multi-Agent 系统（非 LangChain Agent）：

```
RouterAgent (意图分发)
    ├── "financial_analysis" → QuantAgent
    │       └── Tool: AnalyzeFinancials / CompareIndustries
    ├── "text2sql" → Text2SQLAgent  
    │       └── Tool: GenerateSQL → GoToolClient HTTP 调用
    └── "rag_query" → RAGAgent  
            ├── Tool: RAGRetrieve → hybrid_search()
            └── Tool: RAGGenerate → DeepSeek LLM
```

- 意图路由基于关键词匹配（可插拔 LLM 分类器）
- Agent 间通过 `AgentMessage` 传递状态
- `StateManager` 使用 Redis 持久化会话历史（fallback 到内存字典）
- 使用 `asyncio.wait_for(timeout=5)` 防止 Agent 永久阻塞
- `Fusion.aggregate` 合并多 Agent 结果

### 6.2 检索增强（RAG）亮点

1. **Hybrid Search**：Dense（BGE-small-zh-v1.5）+ Sparse（BM25）双路检索，支持 RRF 和 Weighted Sum 两种融合策略
2. **Query-Aware 动态权重**：短 Query 偏 BM25（0.3/0.7），长 Query 偏 Dense（0.7/0.3）
3. **Multi-Query Expansion**：将原始 query 扩展为多个变体，通过 RRF 融合结果
4. **Backoff 机制**：RRF 结果不足时回退到 Weighted 融合
5. **MMR**：Cosine 相似度计算 Relevance/Diversity 平衡
6. **文档过滤**：自动从 query 中提取年份、公司名、报告类型，构造 Qdrant 过滤条件

### 6.3 量化引擎亮点

1. **FactorEngineV2**：完整的因子工程流水线（技术+动量+截面+行业），带 Parquet 本地缓存
2. **行业因子**：行业分类 + 行业内排名 + 行业强度，这是投研的特色因子
3. **LightGBM + SHAP**：可解释的预测模型
4. **三级降级策略**（quant_tool.py）：实时计算 → 预生成 JSON 报告 → UNKNOWN 兜底
5. **万华化学专项优化**：作为行业龙头单独处理，即使不在 Top5 也返回信号
6. **functools.lru_cache**：Pipeline 单例缓存 + 每日结果缓存

### 6.4 网关基础设施

`gateway/` 目录实现了一个生产级 API 网关的基础设施（但尚未接入主流程）：

- **熔断器**：CLOSED → OPEN → HALF_OPEN 三态，基于时间窗口的错误率，线程安全（`threading.Lock`）
- **限流器**：Redis Token Bucket（Lua 脚本原子操作），双层（Service 级 + API 级）
- **反向代理**：httpx AsyncClient + 熔断缓存降级
- **Prometheus 指标**：请求量、延迟、错误率

### 6.5 Text2SQL 服务

`services/text2sql/` 是一个半成品的企业级 NL2SQL 服务：

- Schema Linking：动态召回相关表结构
- SQL 安全校验：仅允许 SELECT，检查用户表权限
- 执行保护：自动加 LIMIT + statement_timeout
- 多轮上下文：Redis 存储对话历史
- LLM 调用部分为 TODO 占位（返回固定模板 SQL）

---

## 7. 代码质量评估（Go 开发者视角）

### 7.1 做得好的地方

| 方面 | 说明 |
|------|------|
| **接口抽象** | Go 侧 `Tool` 接口 + Python 侧 `BaseSkill`/`BaseAgent`，遵循依赖倒置 |
| **单例模式** | `functools.lru_cache` 实现模型缓存，避免重复加载 |
| **降级策略** | 量化引擎三级降级、Reranker 自动降级、Fusion 容错 |
| **异步并发** | `asyncio.gather` 并行 Agent 调用，`asyncio.to_thread` 避免阻塞事件循环 |
| **配置管理** | `dataclass(frozen=True)` + 环境变量，类型安全 |
| **熔断/限流** | Gateway 层的生产级中间件实现 |
| **批量处理** | Qdrant 批量 upsert（50条/批），避免单条写入 |

### 7.2 需要改进的地方

| 问题 | 严重程度 | 说明 |
|------|:------:|------|
| **Go 侧工具未实现** | 🔴 高 | `text2sql` 工具在 Python 侧调用但 Go 侧未注册，会导致运行时错误 |
| **Go 版本过旧** | 🟡 中 | Go 1.20（2023 Q1），当前已是 1.24+。缺少 structured logging、新的 routing patterns |
| **Go 无超时控制** | 🟡 中 | `r.Call()` 无 context，长时间运行的工具有 goroutine 泄漏风险 |
| **Python 错误处理粗糙** | 🟡 中 | 大量裸 `except Exception` + `pass`，问题排查困难 |
| **无结构化日志** | 🟡 中 | 全项目使用 `print`/`logger.info`，无统一 trace ID 传递（虽然有 request_id 中间件） |
| **Go 侧无测试** | 🟡 中 | `go-agent/` 没有任何 `_test.go` 文件 |
| **Type Hints 不完整** | 🟢 低 | 大量 `Dict[str, Any]`，几乎等于无类型 |
| **Gateway 未接入主流程** | 🟡 中 | `gateway/` 是一个独立启动的服务，主流程 `main.py` 直接暴露端口 8000 |
| **Text2SQL 硬编码** | 🟡 中 | LLM 调用为 TODO 占位，返回固定 SQL |
| **Go 侧 math tool 无意义** | 🟢 低 | MathTool 是 Demo，未在 Python 侧使用 |

---

## 8. 设计模式总结

| 模式 | 出现位置 | Go 类比 |
|------|---------|---------|
| **Strategy** | `RouterAgent` 按意图选择不同 Agent | `switch-case` + 接口 |
| **Registry** | `SkillRegistry` / `Tool` 接口 | `map[string]Handler` |
| **Chain of Responsibility** | RAG pipeline（检索→重排→MMR→生成） | 中间件链 / Pipeline |
| **Circuit Breaker** | `gateway/middleware/circuit_breaker.py` | `go-kit/circuitbreaker` |
| **Token Bucket** | `gateway/middleware/rate_limiter.py` | `golang.org/x/time/rate` |
| **Observer** | Prometheus metrics + Tracer | OpenTelemetry |
| **Singleton** | `functools.lru_cache` / 全局 `Settings` | `sync.Once` |
| **Facade** | `quant_tool.run_quant_tool()` 对外统一入口 | Service 层 |
| **Fallback/Circuit Breaker** | 量化三级降级、Reranker 降级、Fusion 容错 | Resilience patterns |

---

## 9. 部署拓扑（推断）

```
                    ┌──────────────┐
                    │   Nginx/ LB  │
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
     ┌────────────┐ ┌──────────┐ ┌──────────┐
     │ main.py    │ │ gateway  │ │ text2sql │
     │ :8000      │ │ :8081    │ │ :8082    │
     │ FastAPI    │ │ FastAPI  │ │ FastAPI  │
     └──┬──┬──┬──┘ └──────────┘ └──────────┘
        │  │  │
        ▼  ▼  ▼
  ┌──────────┐ ┌─────────┐ ┌──────────┐
  │ Qdrant   │ │ Redis   │ │PostgreSQL│
  │ :6333    │ │ :6379   │ │ :5432    │
  └──────────┘ └─────────┘ └──────────┘
        ▲
   ┌────┴────┐
   │ Go-Agent│  ← HTTP Sidecar（Gin :8080）
   │ :8080   │     仅 math tool 可用
   └─────────┘
        ▲
   ┌────┴────┐
   │DeepSeek │  ← 外部 LLM API
   │   API   │
   └─────────┘
```

---

## 10. 综合评价

### 业务价值 ⭐⭐⭐⭐
化工行业投研是一个垂直细分场景，项目将 PDF 研报 RAG、量化因子选股、Multi-Agent 编排结合在一起，形成了从数据到决策的完整闭环。

### 工程成熟度 ⭐⭐⭐
Python 主流程（RAG + Quant）代码质量尚可，有降级策略和缓存优化。但 Go 组件基本是占位，Gateway 和 Text2SQL 是两个"半成品"服务，未与主流程打通。整体像是多个实验性模块拼在一起，尚未经历生产环境的打磨。

### Go 部分的意义
当前 Go 组件几乎无实际作用（唯一可用的 MathTool 未被调用）。设计意图是将 Go 作为**高性能工具 Sidecar**——这个思路是合理的，但需要补充实际可用的工具实现（Text2SQL、复杂计算等），并加上超时、重试、连接池等生产级特性。

### 如果要重构
作为 Go 开发者，如果接手这个项目，我会优先做：
1. 将 Go-Agent 升级到 Go 1.24，补充 `text2sql` 和量化计算工具的实际实现
2. 用 gRPC 替代 REST JSON 做 Python ↔ Go 通信（性能更好、类型安全）
3. 合并 Gateway 和 main.py 的路由层（消除双入口）
4. 统一 OpenTelemetry 全链路追踪（替换手写的 request_id + Tracer）
5. 补充 Go 侧的单元测试和集成测试
