"""
Agent Runtime — LangGraph Agent 执行引擎 v2.0

v2.0 变更：
- 集成 PromptBuilder：统一 prompt 构造
- 集成 ContextManager：token 级别的上下文窗口管理
- 集成 SummaryMemory：每 10 轮自动 LLM 摘要
- 集成 SharedAgentMemory：跨 Agent 数据共享
- memory_context 被所有 Node 实际消费
"""

import logging
from typing import Dict, Any, List, Optional
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path

from langgraph.graph import StateGraph, END
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.agent.registry import SkillRegistry
from app.agent.fusion import CrossSkillFusion
from app.agent.synthesizer import synthesize_financial_report
from app.agent.prompt_builder import PromptBuilder, build_report_prompt
from app.agent.context_manager import get_context_manager, ContextManager
from app.rag.pipeline import extract_company_from_query
from app.config.settings import settings
from app.quant.quant_tool import run_quant_tool
from app.agent.skills.financial_analysis import FinancialAnalysisSkill
from app.agent.skills.industry_comparison import IndustryComparisonSkill
from app.agent.skills.structured_query import StructuredQuerySkill
from app.agent.go_tool_client import GoToolClient
from app.agent.memory import (
    ShortTermMemory,
    LongTermMemory,
    SummaryMemory,
    SharedAgentMemory,
)
from app.runtime import ExecutionRuntime, Task
from app.workflow import get_registry as get_wf_registry                            # Workflow 驱动

logger = logging.getLogger(__name__)

# ── 模块级 Runtime 单例（DI 友好：可在测试中替换） ──
_runtime: Optional[ExecutionRuntime] = None


def get_runtime() -> ExecutionRuntime:
    """获取模块级 ExecutionRuntime 单例（懒初始化）"""
    global _runtime
    if _runtime is None:
        _runtime = ExecutionRuntime.create(max_workers=4)
    return _runtime


def set_runtime(runtime: ExecutionRuntime) -> None:
    """注入自定义 ExecutionRuntime（用于测试或 GoScheduler）"""
    global _runtime
    _runtime = runtime


# ==================== AgentState ====================

class AgentState(BaseModel):
    """Agent 状态（v2 增加摘要和共享记忆）"""
    query: str
    session_id: str = ""
    user_id: str = ""
    stock: str = ""
    intent: str = ""
    selected_skills: List[str] = []
    workflow_id: str = ""          # v4: Planner 返回 workflow_id，selected_skills 由 workflow 派生
    skill_results: Dict[str, Any] = {}
    quant_raw: Any = None
    go_quant_raw: Any = None
    go_rag_raw: Any = None
    go_sql_raw: Any = None
    data_timestamp: Optional[datetime] = None
    memory_context: Dict[str, Any] = {}     # 完整记忆上下文（含 summary/shared）
    final_answer: str = ""
    error: str = ""


# ==================== SkillManager ====================

class SkillManager:
    _instances = {}

    @classmethod
    def get_instance(cls, name: str):
        if name not in cls._instances:
            skill_cls = SkillRegistry.get_skill(name)
            if skill_cls:
                cls._instances[name] = skill_cls()
        return cls._instances.get(name)


# ==================== 追踪 ====================

def _trace_path() -> Path:
    default_path = Path(settings.PROJECT_ROOT) / "agent_traces.jsonl"
    raw = os.getenv("AGENT_TRACE_PATH")
    if not raw:
        return default_path
    p = Path(raw)
    if not p.is_absolute():
        p = Path(settings.PROJECT_ROOT) / p
    return p.resolve()


def log_state(node_name: str, state: AgentState) -> None:
    try:
        skill_results = state.skill_results or {}
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "node": node_name,
            "query": (state.query or "")[:500],
            "stock": state.stock,
            "intent": state.intent,
            "selected_skills": list(state.selected_skills or []),
            "skill_results_keys": list(skill_results.keys()),
            "error": state.error,
            "has_summary": bool(state.memory_context.get("summary")),
            "has_short_term": bool(state.memory_context.get("recent_history")),
            "has_shared": bool(state.memory_context.get("shared_memory")),
        }
        path = _trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        return


# ==================== 图节点 ====================

async def planner_node(state: AgentState) -> AgentState:
    """
    规划节点 v4：Workflow 驱动。

    v4 变更：
      - 不再直接选择 Skill 名称
      - 改为返回 workflow_id → Executor 从 YAML 加载 Skill 列表
      - 关键词匹配保留（选 workflow），Skill 清单由 YAML 定义
    """
    log_state("planner:before", state)
    query = state.query

    # 读取记忆上下文
    memory_ctx = state.memory_context or {}
    summary = memory_ctx.get("summary", {})
    shared = memory_ctx.get("shared_memory", {})

    known_stocks = []
    if isinstance(summary, dict):
        known_stocks = summary.get("watched_stocks", [])
    if isinstance(shared, dict):
        quant_data = shared.get("quant", {}) or shared.get("quant:latest", {})
        if isinstance(quant_data, dict) and quant_data.get("stock"):
            known_stocks.append(quant_data["stock"])

    # 意图检测 → 选 workflow
    has_financial = any(k in query for k in ["财报", "年报", "营收", "利润", "毛利率", "净利率", "ROE", "现金流"])
    has_compare = any(k in query for k in ["对比", "竞争对手", "行业", "排名", "地位", "同行"])
    has_structured = any(k in query for k in ["查询", "历年", "财务数据", "top"])
    has_stock = any(s in query for s in known_stocks)

    if has_financial or has_compare or has_structured or has_stock:
        state.workflow_id = "agent_skills"
    elif query.strip():
        state.workflow_id = "agent_skills"  # 默认
    else:
        state.workflow_id = ""

    # 提取股票代码
    company_name, ticker = extract_company_from_query(query)
    state.stock = ticker.split(".")[0] if ticker else ""

    logger.info(
        f"Planner v4: workflow_id={state.workflow_id}, stock={state.stock}"
    )
    log_state("planner:after", state)
    return state


def _parse_data_timestamp(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except Exception:
            pass
        if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
            try:
                return datetime.strptime(raw, "%Y-%m-%d")
            except Exception:
                return None
        if len(raw) == 8 and raw.isdigit():
            try:
                return datetime.strptime(raw, "%Y%m%d")
            except Exception:
                return None
    return None


async def data_fetch_node(state: AgentState) -> AgentState:
    """数据预取节点（与 v1 保持一致）"""
    log_state("data_fetch:before", state)
    try:
        key = state.stock or state.query

        client = GoToolClient()
        if client.health():
            try:
                async def _go_rag():
                    return await asyncio.to_thread(client.call, "rag_search", {"query": state.query})

                async def _go_quant():
                    return await asyncio.to_thread(client.call, "quant_analysis", {"stock": state.stock or state.query})

                async def _go_sql():
                    if "structured_query" in state.selected_skills:
                        return await asyncio.to_thread(client.call, "text2sql", {"query": state.query, "user": "agent"})
                    return None

                go_results = await asyncio.gather(
                    _go_rag(), _go_quant(), _go_sql(), return_exceptions=True
                )

                if not isinstance(go_results[0], Exception):
                    state.go_rag_raw = go_results[0]

                if not isinstance(go_results[1], Exception):
                    state.go_quant_raw = go_results[1]
                    if isinstance(state.go_quant_raw, dict):
                        ts = _parse_data_timestamp(state.go_quant_raw.get("data_date")) or \
                             _parse_data_timestamp(state.go_quant_raw.get("date"))
                        if ts:
                            state.data_timestamp = ts

                if not isinstance(go_results[2], Exception):
                    state.go_sql_raw = go_results[2]
            except Exception as ge:
                logger.warning(f"GoToolClient 调用异常: {ge}")

        if state.go_quant_raw is None:
            quant_raw = await asyncio.to_thread(run_quant_tool, key)
            state.quant_raw = quant_raw
            if isinstance(quant_raw, dict):
                ts = (
                    _parse_data_timestamp(quant_raw.get("data_date"))
                    or _parse_data_timestamp(quant_raw.get("date"))
                    or _parse_data_timestamp(quant_raw.get("timestamp"))
                )
                state.data_timestamp = ts
    except Exception as e:
        if not state.error:
            state.error = f"数据预取失败: {e}"
    log_state("data_fetch:after", state)
    return state


async def executor_node(state: AgentState) -> AgentState:
    """
    技能执行节点 v3：通过 ExecutionRuntime 统一执行 Skill。

    v3 变更：
      - 不再直接调用 skill.execute()，改为创建 Task → Runtime.execute_parallel()
      - ExecutionRuntime 统一管理生命周期、重试、超时、Hook、Event
      - 保持 skill_results 格式向后兼容（synthesizer_node 不变）
    """
    log_state("executor:before", state)

    memory_ctx = state.memory_context or {}
    shared_memory = memory_ctx.get("shared_memory", {})
    shared_context_text = SharedAgentMemory.format_for_prompt(shared_memory)

    skill_payload = {
        "query": state.query,
        "stock": state.stock,
        "quant_raw": state.quant_raw,
        "go_quant_raw": state.go_quant_raw,
        "go_rag_raw": state.go_rag_raw,
        "go_sql_raw": state.go_sql_raw,
        "data_timestamp": state.data_timestamp,
        "shared_memory": shared_memory,
        "shared_context_text": shared_context_text,
    }

    selected_skills = state.selected_skills or []
    if not selected_skills and state.workflow_id:
        # v4: Planner 只返回 workflow_id → 从 Workflow YAML 派生 selected_skills
        try:
            wf_def = get_wf_registry().get(state.workflow_id)
            selected_skills = list(wf_def.task_ids)
        except Exception:
            pass

    results: dict[str, Any] = {}
    errors: list[str] = []

    runtime = get_runtime()

    if selected_skills:
        try:
            # ── Workflow 驱动：从 YAML 读取 Skill 编排（depends_on）──
            rt_tasks = _build_skill_tasks(selected_skills, skill_payload)
            aggregated = await runtime.execute_dag(rt_tasks)

            # ── 映射回 state.skill_results（向后兼容）──
            for task in aggregated.tasks:
                skill_name = task.payload.get("skill", task.skill)
                if task.is_success:
                    results[skill_name] = task.result
                else:
                    err_msg = (
                        f"技能 [{skill_name}] 执行失败: {task.error or 'unknown'}"
                    )
                    logger.error(err_msg)
                    errors.append(err_msg)
                    if skill_name == "financial_analysis" and not state.error:
                        state.error = err_msg
        except Exception as runtime_err:
            logger.exception(f"ExecutionRuntime 异常，回退到直接执行: {runtime_err}")
            results, errors = await _executor_fallback(
                selected_skills, skill_payload, state
            )

    # ── Summary Task: 汇总 Skill 结果 ──────────────────
    if results and not errors:
        try:
            summary_task = _build_summary_task(results, skill_payload)
            if summary_task:
                handle = await runtime.submit(summary_task)
                await handle.wait()
                if handle.status().is_success:
                    results["summary"] = handle.result()
                    logger.info("Summary task completed")
                else:
                    logger.warning(f"Summary task failed: {handle.exception()}")
        except Exception as e:
            logger.warning(f"Summary task skipped: {e}")

    state.skill_results = results
    if errors and not state.error:
        state.error = "; ".join(errors[:2])
    log_state("executor:after", state)
    return state


def _build_skill_tasks(
    selected_skills: list[str],
    skill_payload: dict,
) -> list[Task]:
    """从 Workflow YAML 读取 depends_on，构造带依赖的 Task 列表。

    structured_query 自动依赖 financial_analysis（由 YAML 声明），
    financial_analysis 和 industry_comparison 无依赖 → 并行执行。
    """
    depends_map: dict[str, list[str]] = {}
    try:
        wf_registry = get_wf_registry()
        definition = wf_registry.get("agent_skills")
        for task_def in definition.tasks:
            if task_def.id in selected_skills:
                depends_map[task_def.id] = list(task_def.depends_on)
    except Exception:
        logger.warning("Workflow registry unavailable, using flat parallel execution")

    rt_tasks = []
    for name in selected_skills:
        rt_tasks.append(Task(
            skill="workflow_executor",
            payload={"__executor__": "skill", "skill": name, **skill_payload},
            depends_on=depends_map.get(name, []),
            stage="execute",
            group="agent",
        ))
    return rt_tasks


def _build_summary_task(
    skill_results: dict[str, Any],
    skill_payload: dict,
) -> Optional[Task]:
    """构造 Summary Task：用 LLM 汇总 Skill 分析结果。

    从 Workflow YAML 读取 summary task 的 config（prompt_id / model 等）。
    仅当至少有一个 Skill 产出非空结果时才构造。
    """
    import json as _json

    # 提取各 Skill 的输出文本
    financial_text = _json.dumps(
        skill_results.get("financial_analysis", {}), ensure_ascii=False, indent=2
    )
    industry_text = _json.dumps(
        skill_results.get("industry_comparison", {}), ensure_ascii=False, indent=2
    )
    structured_text = _json.dumps(
        skill_results.get("structured_query", {}), ensure_ascii=False, indent=2
    )

    # 至少有一个非空
    has_content = any(
        t.strip() not in ("", "{}", "null")
        for t in [financial_text, industry_text, structured_text]
    )
    if not has_content:
        return None

    # 从 Workflow YAML 读取 summary task 的 config
    summary_config = {"prompt_id": "skills.summary", "model": "deepseek-chat",
                      "temperature": 0.3, "max_tokens": 600,
                      "system_prompt": "你是化工行业资深投研分析师。"}
    try:
        wf_registry = get_wf_registry()
        definition = wf_registry.get("agent_skills")
        for task_def in definition.tasks:
            if task_def.id == "summary":
                summary_config = {**summary_config, **dict(task_def.config)}
                break
    except Exception:
        pass

    return Task(
        skill="workflow_executor",
        payload={
            "__executor__": "llm",
            **summary_config,
            "prompt_variables": {
                "financial_text": financial_text,
                "industry_text": industry_text,
                "structured_text": structured_text,
                "shared_context": skill_payload.get("shared_context_text", ""),
            },
        },
        stage="summary",
        group="agent",
    )


async def _executor_fallback(
    selected_skills: list[str],
    skill_payload: dict,
    state: AgentState,
) -> tuple[dict[str, Any], list[str]]:
    """
    降级路径：直接调用 Skill（不经过 ExecutionRuntime）。

    当 ExecutionRuntime 不可用时自动回退，保证系统可用性。
    """
    results: dict[str, Any] = {}
    errors: list[str] = []

    async def _run_one(skill_name: str):
        skill = SkillManager.get_instance(skill_name)
        if not skill:
            return skill_name, None, f"{skill_name} 未注册"
        try:
            skill_result = await skill.execute(skill_payload)
        except Exception as e:
            return skill_name, None, f"技能异常: {e}"
        if getattr(skill_result, "success", False):
            return skill_name, getattr(skill_result, "data", None), None
        return skill_name, None, getattr(skill_result, "error", "unknown error")

    coros = [_run_one(name) for name in selected_skills]
    out = await asyncio.gather(*coros)
    for skill_name, data, err in out:
        if err:
            err_msg = f"技能 [{skill_name}] 执行失败: {err}"
            logger.error(err_msg)
            errors.append(err_msg)
            if skill_name == "financial_analysis" and not state.error:
                state.error = err_msg
        else:
            results[skill_name] = data
    return results, errors


async def synthesizer_node(state: AgentState) -> AgentState:
    """
    综合节点 v2：

    改进：
    1. 使用 PromptBuilder 构造 LLM messages
    2. 使用 ContextManager 管理 token 窗口
    3. 触发 SummaryMemory 摘要
    4. 写入 SharedAgentMemory 跨 Agent 数据
    5. 写入 ShortTermMemory 对话历史
    """
    log_state("synthesizer:before", state)

    if state.error:
        state.final_answer = f"分析过程出错：{state.error}"
        log_state("synthesizer:error", state)
        return state

    skill_results = state.skill_results
    if not skill_results:
        state.final_answer = "未获取到有效的分析数据，请稍后重试。"
        log_state("synthesizer:empty", state)
        return state

    # 安全获取各数据块
    financial_data = skill_results.get("financial_analysis", {})
    industry_data = skill_results.get("industry_comparison", {})

    if not industry_data or "target" not in industry_data:
        industry_data = {
            "target": {"stock": state.stock or "unknown"},
            "comparison": {},
            "peers": [],
        }

    financial_detail = financial_data.get("financial", {})
    quant_detail = financial_data.get("quant", {})

    # 跨技能融合
    fusion_result = CrossSkillFusion.fuse(
        financial=financial_detail,
        quant=quant_detail,
        industry=industry_data,
        data_timestamp=state.data_timestamp,
    )

    enriched_data = {
        **financial_data,
        "industry": industry_data,
        "fusion": fusion_result,
    }

    # ===== v2 新增：写入 SharedAgentMemory =====
    if state.session_id:
        shared_mem = SharedAgentMemory(
            ttl=settings.MEMORY_SHARED_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
        )

        # 从 fusion_result 提取信息写入共享记忆
        stock_code = state.stock or financial_detail.get("stock", "")
        await shared_mem.write_quant_conclusion(
            session_id=state.session_id,
            stock=stock_code,
            score=fusion_result.get("score"),
            signal=fusion_result.get("signal_type"),
            conclusion=fusion_result.get("reasoning", ""),
            risk="; ".join(fusion_result.get("risk_factors", [])[:3]),
        )

        # 写入跨 Agent 融合结论
        await shared_mem.write_cross_conclusion(
            session_id=state.session_id,
            consensus=fusion_result.get("reasoning", ""),
            conflicts=[],
            merged_conclusion=fusion_result.get("reasoning", ""),
        )

    # ===== v2 新增：使用 PromptBuilder + ContextManager =====
    memory_ctx = state.memory_context or {}
    context_manager = get_context_manager(max_tokens=settings.CONTEXT_MAX_TOKENS)

    try:
        # 使用 PromptBuilder 构造 report prompt
        report_user_prompt = build_report_prompt(enriched_data)

        # 构造 messages（带历史+摘要+偏好+共享记忆）
        messages = PromptBuilder.build_messages(
            query=state.query,
            memory_context=memory_ctx,
            rag_context="",     # Agent 路径不直接使用 RAG 上下文
            quant_context="",   # 量化数据在 report_user_prompt 中
            recent_turns=5,
            include_summary=True,
            include_preferences=True,
            include_history=True,
        )

        # 将报告 prompt 替换最后一条 user message 的内容（保留历史上下文）
        # 找到最后一条 user message 并追加报告内容
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                original_content = messages[i]["content"]
                messages[i] = {
                    "role": "user",
                    "content": f"{original_content}\n\n[系统自动注入的分析数据]\n{report_user_prompt}",
                }
                break

        # ContextManager 裁剪
        messages = context_manager.fit_messages(messages)

        # 获取使用报告（用于 trace）
        usage = context_manager.get_usage_report(messages)
        logger.info(
            f"ContextManager 使用报告: {usage['total_tokens']}/{usage['max_tokens']} "
            f"({usage['utilization']:.1%})"
        )

        # ── WorkflowService 驱动 LLM 调用 ──
        from app.workflow import WorkflowService
        wf_service = WorkflowService(get_runtime())
        result = await wf_service.run("report_generation", messages=messages)
        state.final_answer = result.outputs.get("generate", "")

    except Exception as e:
        logger.error(f"WorkflowService LLM 调用失败: {e}")
        try:
            state.final_answer = synthesize_financial_report(enriched_data)
        except Exception as fallback_e:
            state.error = f"报告生成失败: {fallback_e}"
            state.final_answer = f"报告生成失败：{fallback_e}"

    # ===== 保存 ShortTermMemory =====
    if state.session_id:
        st_memory = ShortTermMemory(
            ttl=settings.MEMORY_SHORT_TERM_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
            max_len=settings.MEMORY_SHORT_TERM_MAX_LEN,
        )
        await st_memory.add(state.session_id, {
            "query": state.query,
            "answer": state.final_answer,
            "timestamp": datetime.now().isoformat(),
        })

    # ===== v2 新增：触发 SummaryMemory =====
    if state.session_id:
        summary_mem = SummaryMemory(
            ttl=settings.MEMORY_SUMMARY_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
            trigger_interval=settings.MEMORY_SUMMARY_TRIGGER_INTERVAL,
        )

        # 获取最近历史用于摘要
        recent_history = memory_ctx.get("recent_history", [])

        # 提取当前轮涉及的股票
        stocks = [state.stock] if state.stock else []

        summarized = await summary_mem.update_from_turn(
            session_id=state.session_id,
            query=state.query,
            answer=state.final_answer,
            stocks=stocks,
            llm_client=AsyncOpenAI(
                api_key=settings.DEEPSEEK_API_KEY,
                base_url=settings.DEEPSEEK_BASE_URL,
            ),
            recent_history=recent_history + [{
                "query": state.query,
                "answer": state.final_answer,
                "timestamp": datetime.now().isoformat(),
            }],
        )
        if summarized:
            logger.info(f"SummaryMemory: 触发了会话摘要 session={state.session_id}")

    log_state("synthesizer:after", state)
    return state


# ==================== Graph ====================

def create_agent_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("planner", planner_node)
    workflow.add_node("data_fetch", data_fetch_node)
    workflow.add_node("executor", executor_node)
    workflow.add_node("synthesizer", synthesizer_node)

    workflow.set_entry_point("planner")
    workflow.add_edge("planner", "data_fetch")
    workflow.add_edge("data_fetch", "executor")
    workflow.add_edge("executor", "synthesizer")
    workflow.add_edge("synthesizer", END)

    return workflow.compile()


# ==================== 对外入口 ====================

async def run_agent(
    query: str,
    session_id: str = "",
    user_id: str = "",
) -> Dict[str, Any]:
    """
    Agent v2 对外入口。

    改进：
    - 并发加载 ShortTermMemory, LongTermMemory, SummaryMemory, SharedAgentMemory
    - 组装完整的 memory_context（含 summary 和 shared_memory）
    - 传递给 LangGraph 各节点消费
    """
    # 1. 并发加载所有记忆
    memory_context: Dict[str, Any] = {
        "recent_history": [],
        "user_preferences": {},
        "summary": None,
        "shared_memory": {},
    }

    if session_id or user_id:
        st_memory = ShortTermMemory(
            ttl=settings.MEMORY_SHORT_TERM_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
            max_len=settings.MEMORY_SHORT_TERM_MAX_LEN,
        )
        lt_memory = LongTermMemory(
            ttl=settings.MEMORY_LONG_TERM_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
        )
        summary_mem = SummaryMemory(
            ttl=settings.MEMORY_SUMMARY_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
            trigger_interval=settings.MEMORY_SUMMARY_TRIGGER_INTERVAL,
        )
        shared_mem = SharedAgentMemory(
            ttl=settings.MEMORY_SHARED_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
        )

        async def _get_st():
            return await st_memory.get(session_id) if session_id else []

        async def _get_lt():
            return await lt_memory.get(user_id) if user_id else {}

        async def _get_summary():
            return await summary_mem.get(session_id) if session_id else None

        async def _get_shared():
            return await shared_mem.get_all(session_id) if session_id else {}

        short_term, long_term, summary, shared_data = await asyncio.gather(
            _get_st(), _get_lt(), _get_summary(), _get_shared(),
        )

        memory_context = {
            "recent_history": short_term or [],
            "user_preferences": long_term or {},
            "summary": summary,
            "shared_memory": shared_data or {},
        }

    # 2. 创建并运行图
    graph = create_agent_graph()
    initial_state = AgentState(
        query=query,
        session_id=session_id,
        user_id=user_id,
        memory_context=memory_context,
    )
    final_state = await graph.ainvoke(initial_state)

    # 3. 返回结果
    return {
        "answer": final_state.get("final_answer", ""),
        "intent": "agent",
        "selected_skills": final_state.get("selected_skills", []),
        "skill_results": final_state.get("skill_results", {}),
        "error": final_state.get("error", ""),
        # v2 新增：返回记忆元数据供前端展示
        "memory_meta": {
            "has_summary": bool(memory_context.get("summary")),
            "history_turns": len(memory_context.get("recent_history", [])),
            "has_shared_context": bool(memory_context.get("shared_memory")),
        },
    }
