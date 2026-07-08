# ChemInvest AI Copilot

**An Enterprise AI Copilot for Chemical Industry Research & Decision Intelligence**

---

ChemInvest AI Copilot 是一个面向企业投研场景的 AI Agent 系统，围绕 **企业财务分析**、**行业知识检索**、**结构化数据查询** 三类核心能力，构建了 Multi-Agent + Workflow + RAG + Text-to-SQL 的智能分析平台。

系统支持自然语言分析企业经营情况，自动规划 Agent Workflow，调用结构化数据库与行业知识库，最终生成可解释的企业分析报告。

---

## Dashboard

> 截图占位 — 替换为实际 Dashboard 截图

```
┌──────────────────────────────────────────────────────────┐
│  [Dashboard]                                              │
│  ┌─────────┐  ┌──────────────────┐  ┌──────────────────┐ │
│  │ Chat    │  │ Workflow Trace   │  │ Enterprise       │ │
│  │         │  │                  │  │ Profile          │ │
│  │ 推荐问题 │  │ Router           │  │ ┌────┬────┬────┐ │ │
│  │ □ 营收分析│  │   ↓             │  │ │营收│利润│ROE │ │ │
│  │ □ 风险分析│  │ Schema Link     │  │ ├────┼────┼────┤ │ │
│  │ □ 行业对比│  │   ↓             │  │ │    │    │    │ │ │
│  │         │  │ Generate SQL     │  │ └────┴────┴────┘ │ │
│  │ [输入框] │  │   ↓             │  │                  │ │
│  │         │  │ Execute SQL      │  │ 风险分析          │ │
│  └─────────┘  │   ↓             │  │ ████░░░░ 40%     │ │
│               │ LLM Interpret    │  └──────────────────┘ │
│               └──────────────────┘                       │
│  [分析报告 — Markdown 渲染]                               │
└──────────────────────────────────────────────────────────┘
```

| Dashboard | Workflow Trace | Enterprise Profile | Chat | Report |
|:---------:|:-------------:|:------------------:|:----:|:------:|
| 一站式面板 | 实时步骤追踪 | 企业财务画像 | 引导式提问 | Markdown 报告 |

---

## ✨ Features

```
✓ Enterprise AI Copilot Dashboard    一站式投研分析面板
✓ Multi-Agent Workflow               多 Agent 协作编排
✓ Workflow Trace Visualization       工作流实时步骤追踪
✓ Enterprise Profile Dashboard       企业财务画像卡片
✓ Guided Questions                   智能引导式提问
✓ Hybrid RAG Retrieval               混合检索增强生成
✓ Text-to-SQL Query                  自然语言转结构化查询
✓ Financial Analysis Report          自动生成企业经营分析报告
✓ Workflow Engine                    YAML 驱动的工作流引擎
✓ Prompt Registry                    Prompt 版本管理与模板注入
```

---

## Demo

### Demo 1 — 企业经营分析

> 分析万华化学近五年各季度营业收入

```
Router → Text2SQL
  │
  ├─ Schema Link   → financials 表
  ├─ Generate SQL  → SELECT revenue ... WHERE company_name LIKE '%万华化学%'
  ├─ Validate SQL  → Guard 安全校验通过
  ├─ Execute SQL   → 20 行季度数据
  └─ LLM Interpret → "万华化学 2021-2025 营收从 313 亿增长至 2032 亿..."
```

### Demo 2 — 企业知识问答

> 万华化学有哪些经营风险？

```
Router → RAG
  │
  ├─ Hybrid Search  → Dense(BGE) + Sparse(BM25) 双路检索
  ├─ Reranker       → CrossEncoder 精排 Top-5
  ├─ MMR            → 多样性去冗余
  └─ LLM Generate   → "主要风险：原材料价格波动、海外贸易摩擦..."
```

### Demo 3 — 行业对比分析

> 化工行业哪些企业成长性最好？

```
Router → Quant
  │
  ├─ Factor Engine  → 技术因子 + 动量因子 + 截面排名
  ├─ LightGBM       → 预测收益排名
  ├─ SHAP           → 特征重要性解释
  └─ LLM Report     → "成长性 Top3：卫星化学、万华化学、华鲁恒升..."
```

---

## Architecture

```
                         Enterprise AI Copilot
                                │
                 ┌──────────────┴──────────────┐
                 │                             │
           Enterprise Chat            Enterprise Profile
                 │
           Router Agent
                 │
         ┌───────┼───────┐
         │       │       │
     Text2SQL   RAG    Quant
         │       │       │
         └───────┼───────┘
                 │
         Workflow Runtime
                 │
    ┌────────────────────────────┐
    │  ExecutionPlan             │
    │      ↓                     │
    │  Executor                  │
    │  ┌────┬────┬────┬──────┐   │
    │  │LLM │SQL │Skill│Result│   │
    │  └────┴────┴────┴──────┘   │
    └────────────────────────────┘
                 │
    Workflow Trace Visualization (SSE)
```

---

## ⭐ Project Highlights

```
✓ 自研 Workflow Framework     YAML 定义 → ExecutionPlan → 多 Executor 并行
✓ Prompt Registry             Prompt 模板版本化 + 变量注入 + 上下文裁剪
✓ Workflow Trace              SSE 实时推送每步状态，前端可视化渲染
✓ Multi-Agent Runtime         Planner → Executor → Synthesizer 编排
✓ Enterprise Dashboard        企业财务画像 + 知识图谱 + 报告展示
✓ Text-to-SQL Pipeline        SchemaLink → Guard → Execute → Interpret
✓ Hybrid RAG                  Dense + Sparse 双路 → Rerank → MMR
✓ Quant Engine                LightGBM + SHAP 可解释多因子选股
```

---

## Technical Highlights

### Workflow Framework

```
YAML Workflow → ExecutionPlan → Executor → Runtime
    支持: Task · Dependency · Retry · Timeout · Stage
```

### Multi-Agent Runtime

```
Planner → Executor → Synthesizer → Workflow
    支持: 意图路由 · 并行执行 · 结果融合 · 降级兜底
```

### Prompt Registry

```
Prompt Template → Context Injection → Window Management → Template Versioning
    支持: 版本管理 · 变量替换 · Token 裁剪 · 多 Prompt 链
```

### Workflow Trace

```
Task Started → Running → Completed  ── SSE 实时流
    前端: WorkflowNode · StatusBadge · WorkflowTimeline
```

### Enterprise Dashboard

```
Enterprise Profile · Knowledge Graph · Workflow Panel · Markdown Report
```

---

## Tech Stack

| Layer | Technology |
|:------|:-----------|
| **Frontend** | React 18 · TypeScript · Vite · TailwindCSS 3 · ReactFlow |
| **Backend** | FastAPI · Uvicorn · SSE · WebSocket · Pydantic |
| **LLM** | DeepSeek API (deepseek-chat) · OpenAI SDK |
| **Vector DB** | Qdrant · gRPC · Dense(BGE) + Sparse(BM25) |
| **Quant** | LightGBM · SHAP · AKShare · Pandas · Parquet |
| **Storage** | SQLite · Redis · PostgreSQL (optional) |
| **DevOps** | Docker Compose · Prometheus · GitHub Actions |
| **Go Sidecar** | Gin · gRPC · Protobuf |

---

## Project Structure

```
ai_invest_agent/
├── app/
│   ├── main.py                 # FastAPI 入口 (CORS/Metrics/RateLimiter)
│   ├── api/                    # API 路由层
│   │   ├── chat.py             # POST /api/chat
│   │   ├── workflow.py         # POST /api/workflow/run (SSE)
│   │   └── websocket.py        # WS /ws (Multi-Agent)
│   ├── agent/                  # Agent 引擎
│   │   ├── runtime.py          # LangGraph 运行时
│   │   ├── fusion.py           # 跨技能融合
│   │   └── memory/             # 短期/长期/摘要/共享记忆
│   ├── multi_agent/            # Multi-Agent 编排
│   ├── workflow/               # 工作流引擎 (YAML → ExecutionPlan)
│   ├── runtime/                # 任务执行运行时 (Executor/Retry/Timeout)
│   ├── services/
│   │   ├── text2sql/           # Text-to-SQL Pipeline
│   │   └── prompt/             # Prompt Registry
│   ├── rag/                    # RAG 检索增强
│   ├── retrieval/              # 检索子系统 (Hybrid/Reranker/MMR)
│   ├── quant/                  # 量化引擎 (Factor/LightGBM/SHAP)
│   ├── observability/          # 日志/指标/追踪
│   ├── middleware/              # 限流/熔断
│   └── config/                 # 配置 + 股票池
├── frontend/                   # React + Vite + TailwindCSS
│   └── src/
│       ├── pages/              # Dashboard
│       ├── components/         # Chat · Workflow · Enterprise · UI
│       ├── hooks/              # useWorkflowStream · useQuestionClick
│       └── api/                # API Client
├── configs/                    # YAML 配置
│   ├── prompts/                # Prompt 模板
│   └── workflows/              # Workflow 定义
├── scripts/                    # 数据下载 & 导入
├── go-runtime/                 # Go Sidecar (gRPC 调度)
├── docker-compose.yaml
└── Dockerfile
```

---

## 🚀 Roadmap

```
✓ Workflow DAG              有向无环图任务编排
✓ Enterprise Profile         企业财务画像 Dashboard
✓ Workflow Trace             实时步骤可视化

□ Plugin Framework           插件化 Skill 扩展
□ Evaluation Platform        检索 & 生成质量评估
□ MCP Support                Model Context Protocol
□ Memory Framework           多层级记忆管理
□ Agent Marketplace          Agent & Skill 市场
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker & Docker Compose
- [DeepSeek API Key](https://platform.deepseek.com/)

### Setup

```bash
# 1. 克隆
git clone <repo-url> && cd ai_invest_agent

# 2. 环境变量
cp .env.example .env
# 编辑 .env → 填入 DEEPSEEK_API_KEY

# 3. 安装
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 4. 导入数据 (化工股季度财报)
python scripts/download_finance.py

# 5. 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload  # 后端
cd frontend && npm run dev                                           # 前端
```

浏览器打开 `http://localhost:5173`。

### Docker

```bash
docker compose up -d
# Qdrant :6333 | ChemInvest :8000 | Redis :6379
```

---

## License

MIT
