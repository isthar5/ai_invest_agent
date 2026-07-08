import type { WorkflowNode } from "@/types/dashboard";
import type { AgentType } from "@/types/chat";

export const workflowMock: WorkflowNode[] = [];

/**
 * Per-agent workflow traces — derived from backend architecture:
 *
 *   Quant:  configs/workflows/agent_skills.yaml
 *   Text2SQL: configs/workflows/text2sql.yaml
 *   RAG:   app/rag/pipeline.py
 *
 * Each trace begins with Router → Planner which mirror
 *   app/multi_agent/router.py  (RouterAgent)
 *   app/agent/runtime.py       (planner_node)
 *
 * Data Fetch mirrors app/agent/runtime.py → data_fetch_node
 * (pre-fetches quant / rag / sql from Go runtime).
 */
export const agentWorkflows: Record<AgentType, WorkflowNode[]> = {
  /* ── Quant: agent_skills.yaml ─────────────────────────────────
     financial_analysis  ──┐
     industry_comparison ──┤  (parallel — no depends_on)
     structured_query    ──┘  (depends_on: financial_analysis)
     summary                 (depends_on: all three)
  ─────────────────────────────────────────────────────────────── */
  quant: [
    {
      id: "router",
      name: "Router",
      status: "success",
      startTime: "14:30:00.112",
      endTime: "14:30:00.224",
      duration: "112ms",
      description: "Intent classified → financial_analysis + industry_comparison route.",
    },
    {
      id: "planner",
      name: "Planner",
      status: "success",
      startTime: "14:30:00.225",
      endTime: "14:30:00.473",
      duration: "248ms",
      description: "Selected workflow: agent_skills. Prepared 3-Skill investigation plan.",
    },
    {
      id: "data-fetch",
      name: "Data Fetch",
      status: "success",
      startTime: "14:30:00.474",
      endTime: "14:30:00.892",
      duration: "418ms",
      description: "Prefetched quant signals + RAG documents from Go runtime.",
    },
    {
      id: "financial-analysis",
      name: "Financial Analysis",
      status: "running",
      startTime: "14:30:00.893",
      endTime: undefined,
      duration: "1.8s",
      description: "DeepSeek-chat: extracting revenue, margins, ROE, cash-flow from annual reports.",
    },
    {
      id: "industry-comparison",
      name: "Industry Comparison",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "Cross-sectional quant ranking vs peer group (600426, 002493, 600346, 002064).",
    },
    {
      id: "structured-query",
      name: "Structured Query",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "depends_on: financial_analysis. Will execute Text2SQL for structured historical data.",
    },
    {
      id: "summary",
      name: "Summary",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "depends_on: all three Skills. LLM synthesizes cross-skill fusion report.",
    },
  ],

  /* ── Text2SQL: configs/workflows/text2sql.yaml ───────────────
     schema_link  →  generate_sql  →  validate_sql  →  execute_sql
  ─────────────────────────────────────────────────────────────── */
  text2sql: [
    {
      id: "router",
      name: "Router",
      status: "success",
      startTime: "14:30:00.112",
      endTime: "14:30:00.224",
      duration: "112ms",
      description: "Intent classified → Text2SQL structured query route.",
    },
    {
      id: "planner",
      name: "Planner",
      status: "success",
      startTime: "14:30:00.225",
      endTime: "14:30:00.473",
      duration: "248ms",
      description: "Selected workflow: text2sql. Prepared schema-linking + generation plan.",
    },
    {
      id: "schema-link",
      name: "Schema Link",
      status: "success",
      startTime: "14:30:00.474",
      endTime: "14:30:00.611",
      duration: "137ms",
      description: "HybridSchemaLinker: dense + sparse embedding matched tables to query intent.",
    },
    {
      id: "generate-sql",
      name: "Generate SQL",
      status: "running",
      startTime: "14:30:00.612",
      endTime: undefined,
      duration: "420ms",
      description: "depends_on: schema_link. DeepSeek-chat generating SQL with schema prompt (temp=0.1).",
    },
    {
      id: "validate-sql",
      name: "Validate SQL",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "depends_on: generate_sql. SQLGuard checking syntax + forbidden operations.",
    },
    {
      id: "execute-sql",
      name: "Execute SQL",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "depends_on: validate_sql. SQLAlchemy → chemical_stocks.db (max 1000 rows, 5s timeout).",
    },
  ],

  /* ── RAG: app/rag/pipeline.py ────────────────────────────────
     smart_retrieval  →  Reranker  →  MMR  →  Answer Generation
     (multi-query expansion + hybrid RRF fusion + backoff)
  ─────────────────────────────────────────────────────────────── */
  rag: [
    {
      id: "router",
      name: "Router",
      status: "success",
      startTime: "14:30:00.112",
      endTime: "14:30:00.224",
      duration: "112ms",
      description: "Intent classified → RAG knowledge retrieval route.",
    },
    {
      id: "planner",
      name: "Planner",
      status: "success",
      startTime: "14:30:00.225",
      endTime: "14:30:00.473",
      duration: "248ms",
      description: "Prepared knowledge retrieval + synthesis plan with PromptBuilder.",
    },
    {
      id: "smart-retrieval",
      name: "Smart Retrieval",
      status: "running",
      startTime: "14:30:00.474",
      endTime: undefined,
      duration: "320ms",
      description: "Multi-query expansion → Hybrid Search (dense + BM25) → RRF fusion. Qdrant collection.",
    },
    {
      id: "reranker",
      name: "Reranker",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "Cross-encoder re-ranking of candidate documents by relevance.",
    },
    {
      id: "mmr",
      name: "MMR",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "Maximal Marginal Relevance — diversity-aware dedup (λ=0.7, optional per ENABLE_MMR).",
    },
    {
      id: "answer-generation",
      name: "Answer Generation",
      status: "pending",
      startTime: "--",
      endTime: undefined,
      duration: "--",
      description: "DeepSeek-chat: PromptBuilder + ContextManager → citation-backed answer (temp=0.3, max 2000 tokens).",
    },
  ],
};

/** Default idle trace — shown when no question is selected */
export const defaultWorkflow: WorkflowNode[] = [
  {
    id: "router",
    name: "Router",
    status: "pending",
    startTime: "--",
    endTime: undefined,
    duration: "--",
    description: "RouterAgent waiting for question to classify intent (quant / text2sql / rag).",
  },
  {
    id: "planner",
    name: "Planner",
    status: "pending",
    startTime: "--",
    endTime: undefined,
    duration: "--",
    description: "planner_node will select workflow_id from YAML registry.",
  },
  {
    id: "data-fetch",
    name: "Data Fetch",
    status: "pending",
    startTime: "--",
    endTime: undefined,
    duration: "--",
    description: "data_fetch_node will prefetch quant / rag / sql from Go runtime.",
  },
  {
    id: "executor",
    name: "Executor",
    status: "pending",
    startTime: "--",
    endTime: undefined,
    duration: "--",
    description: "executor_node runs Skills via ExecutionRuntime based on workflow YAML depends_on DAG.",
  },
  {
    id: "synthesizer",
    name: "Synthesizer",
    status: "pending",
    startTime: "--",
    endTime: undefined,
    duration: "--",
    description: "synthesizer_node generates final report via PromptBuilder + ContextManager.",
  },
];
