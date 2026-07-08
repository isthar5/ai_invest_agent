import logging
from app.agent.registry import SkillRegistry
from typing import Dict, Any, List, Optional
import asyncio
import os
import json
from datetime import datetime
from pathlib import Path
from app.agent.fusion import CrossSkillFusion
from langgraph.graph import StateGraph, END
from app.agent.synthesizer import synthesize_financial_report
from app.rag.pipeline import extract_company_from_query  
from app.config.settings import settings
from app.quant.quant_tool import run_quant_tool
from app.agent.skills.financial_analysis import FinancialAnalysisSkill
from app.agent.skills.industry_comparison import IndustryComparisonSkill
from app.agent.skills.structured_query import StructuredQuerySkill
from app.agent.go_tool_client import GoToolClient
from app.agent.memory import ShortTermMemory, LongTermMemory
from pydantic import BaseModel

logger = logging.getLogger(__name__)

class AgentState(BaseModel):
    query: str
    session_id: str = ""
    user_id: str = ""
    stock: str = ""
    intent: str = ""
    selected_skills: List[str] = []      # 规划阶段决定的技能列表
    skill_results: Dict[str, Any] = {}    # 各技能执行结果
    quant_raw: Any = None
    go_quant_raw: Any = None              # Go-agent 量化工具结果
    go_rag_raw: Any = None                # Go-agent RAG 工具结果
    go_sql_raw: Any = None                # Go-agent Text2SQL 结果
    data_timestamp: Optional[datetime] = None
    memory_context: Dict[str, Any] = {}   # 记忆上下文
    final_answer: str = ""
    error: str = ""


# 技能实例注册表
class SkillManager:
    _instances = {}

    @classmethod
    def get_instance(cls, name: str):
        if name not in cls._instances:
            skill_cls = SkillRegistry.get_skill(name)
            if skill_cls:
                cls._instances[name] = skill_cls()
        return cls._instances.get(name)



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
        }
        path = _trace_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception:
        return


async def planner_node(state: AgentState) -> AgentState:
    """
    规划节点：分析用户意图，决定需要调用哪些技能。
    当前版本用规则匹配，未来可升级为 LLM 规划。
    """
    log_state("planner:before", state)
    query = state.query
    skills = []

    # 规则1：财报/基本面相关 → 调用财务分析技能
    financial_keywords = ["财报", "年报", "营收", "利润", "毛利率", "净利率", "ROE", "现金流"]
    if any(k in query for k in financial_keywords):
        skills.append("financial_analysis")

    # 规则2：量化/预测相关（未来可扩展）
    # if any(k in query for k in ["预测", "信号", "走势"]):
    #     skills.append("quant_explainer")

    # 规则3：对比分析（未来可扩展）
    if any(k in query for k in ["对比", "竞争对手", "行业", "排名", "地位", "同行"]):
        skills.append("industry_comparison")

    # 规则4：结构化查询（Text2SQL）
    structured_keywords = ["营收", "利润", "收入", "查询", "历年", "财务数据", "top", "排名"]
    if any(k in query for k in structured_keywords):
        if "structured_query" not in skills:
            skills.append("structured_query")

    # 如果没有命中任何技能，默认使用财务分析（兜底）
    if not skills:
        skills.append("financial_analysis")

    # 提取股票代码（复用 RAG 模块的现有函数）
    company_name, ticker = extract_company_from_query(query)
    if ticker:
        # ticker 格式如 "600309.SH"，提取纯数字部分
        stock_code = ticker.split(".")[0]
        state.stock = stock_code
    else:
        # 如果提取失败，保持空字符串，Skill 内部会再次尝试
        state.stock = ""

    state.selected_skills = skills
    logger.info(f"Planner 选择技能: {skills}, 股票: {state.stock}")
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
    log_state("data_fetch:before", state)
    try:
        key = state.stock or state.query
        
        # 1. 优先尝试通过 Go-agent 获取 RAG、量化 和 SQL 结果 (并行触发)
        client = GoToolClient()
        if client.health():
            try:
                # 并行调用 Go 工具
                async def _go_rag():
                    return client.call("rag_search", {"query": state.query})
                
                async def _go_quant():
                    return client.call("quant_analysis", {"stock": state.stock or state.query})

                async def _go_sql():
                    if "structured_query" in state.selected_skills:
                        return client.call("text2sql", {"query": state.query, "user": "agent"})
                    return None

                go_results = await asyncio.gather(_go_rag(), _go_quant(), _go_sql(), return_exceptions=True)
                
                if not isinstance(go_results[0], Exception):
                    state.go_rag_raw = go_results[0]
                
                if not isinstance(go_results[1], Exception):
                    state.go_quant_raw = go_results[1]
                    # 尝试从 Go 结果中提取时间戳
                    if isinstance(state.go_quant_raw, dict):
                        ts = _parse_data_timestamp(state.go_quant_raw.get("data_date")) or \
                             _parse_data_timestamp(state.go_quant_raw.get("date"))
                        if ts:
                            state.data_timestamp = ts

                if not isinstance(go_results[2], Exception):
                    state.go_sql_raw = go_results[2]
            except Exception as ge:
                logger.warning(f"GoToolClient 调用异常: {ge}")

        # 2. 如果 Go-agent 没能提供量化数据，回退到本地量化工具
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
    log_state("executor:before", state)

    async def _run_one(skill_name: str):
        skill = SkillManager.get_instance(skill_name)
        if not skill:
            return skill_name, None, f"{skill_name} 未注册"
        try:
            skill_result = await skill.execute(
                {
                    "query": state.query,
                    "stock": state.stock,
                    "quant_raw": state.quant_raw,
                    "go_quant_raw": state.go_quant_raw,
                    "go_rag_raw": state.go_rag_raw,
                    "go_sql_raw": state.go_sql_raw,
                    "data_timestamp": state.data_timestamp,
                }
            )
        except Exception as e:
            return skill_name, None, f"技能异常: {e}"
        if getattr(skill_result, "success", False):
            return skill_name, getattr(skill_result, "data", None), None
        return skill_name, None, getattr(skill_result, "error", "unknown error")

    tasks = [_run_one(name) for name in (state.selected_skills or [])]
    results: dict[str, Any] = {}
    errors: list[str] = []

    if tasks:
        out = await asyncio.gather(*tasks)
        for skill_name, data, err in out:
            if err:
                err_msg = f"技能 [{skill_name}] 执行失败: {err}"
                logger.error(err_msg)
                errors.append(err_msg)
                if skill_name == "financial_analysis" and not state.error:
                    state.error = err_msg
            else:
                results[skill_name] = data

    state.skill_results = results
    if errors and not state.error:
        state.error = "; ".join(errors[:2])
    log_state("executor:after", state)
    return state


async def synthesizer_node(state: AgentState) -> AgentState:
    log_state("synthesizer:before", state)
    if state.error:
        state.final_answer = f"分析过程出错：{state.error}"
        log_state("synthesizer:error", state)
        return state

    data_timestamp = state.data_timestamp

    skill_results = state.skill_results
    if not skill_results:
        state.final_answer = "未获取到有效的分析数据，请稍后重试。"
        log_state("synthesizer:empty", state)
        return state

    # 安全获取各数据块
    financial_data = skill_results.get("financial_analysis", {})
    industry_data = skill_results.get("industry_comparison", {})

    # 兜底：确保 industry_data 符合 FusionInput 的最低要求
    if not industry_data or "target" not in industry_data:
        industry_data = {
            "target": {"stock": state.stock or "unknown"},
            "comparison": {},
            "peers": []
        }

    financial_detail = financial_data.get("financial", {})
    quant_detail = financial_data.get("quant", {})

    fusion_result = CrossSkillFusion.fuse(
        financial=financial_detail,
        quant=quant_detail,
        industry=industry_data,
        data_timestamp=state.data_timestamp
    )

    enriched_data = {
        **financial_data,
        "industry": industry_data,
        "fusion": fusion_result
    }

    try:
        final_report = synthesize_financial_report(enriched_data)
        state.final_answer = final_report

        # 保存本轮对话到短期记忆
        if state.session_id:
            st_memory = ShortTermMemory(
                ttl=settings.MEMORY_SHORT_TERM_TTL,
                redis_url=settings.MEMORY_REDIS_URL,
                max_len=settings.MEMORY_SHORT_TERM_MAX_LEN
            )
            await st_memory.add(state.session_id, {
                "query": state.query,
                "answer": state.final_answer,
                "timestamp": datetime.now().isoformat()
            })
    except Exception as e:
        state.error = f"报告生成失败: {str(e)}"
        state.final_answer = f"报告生成失败：{e}"

    log_state("synthesizer:after", state)
    return state

    # 安全获取各数据块
    financial_data = skill_results.get("financial_analysis", {})
    industry_data = skill_results.get("industry_comparison", {})

    # 如果某个技能完全失败，提供空字典，融合模块内部有降级处理
    financial_detail = financial_data.get("financial", {})
    quant_detail = financial_data.get("quant", {})

    # ========== 跨 Skill 融合 ==========
    # 从 financial_detail 中提取 data_timestamp
    data_timestamp = financial_detail.get("data_timestamp")
    
    fusion_result = CrossSkillFusion.fuse(
        financial=financial_detail,
        quant=quant_detail,
        industry=industry_data,
        data_timestamp=data_timestamp
    )

    # 将融合结果回写到数据中，供 synthesizer 使用
    enriched_data = {
        **financial_data,
        "industry": industry_data,
        "fusion": fusion_result
    }

    # 生成最终报告
    try:
        final_report = synthesize_financial_report(enriched_data)
        state.final_answer = final_report
    except Exception as e:
        state.error = f"报告生成失败: {str(e)}"
        state.final_answer = f"报告生成失败：{e}"

    log_state("synthesizer:after", state)
    return state


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


async def run_agent(query: str, session_id: str = "", user_id: str = "") -> Dict[str, Any]:
    """对外暴露的 Agent 入口"""
    # 1. 获取记忆上下文
    memory_context = {}
    if session_id or user_id:
        st_memory = ShortTermMemory(
            ttl=settings.MEMORY_SHORT_TERM_TTL,
            redis_url=settings.MEMORY_REDIS_URL,
            max_len=settings.MEMORY_SHORT_TERM_MAX_LEN
        )
        lt_memory = LongTermMemory(
            ttl=settings.MEMORY_LONG_TERM_TTL,
            redis_url=settings.MEMORY_REDIS_URL
        )
        
        # 并发获取短期和长期记忆
        async def _get_st():
            return await st_memory.get(session_id) if session_id else []
        async def _get_lt():
            return await lt_memory.get(user_id) if user_id else {}
        
        short_term, long_term = await asyncio.gather(_get_st(), _get_lt())
        
        memory_context = {
            "recent_history": short_term,
            "user_preferences": long_term
        }

    graph = create_agent_graph()
    initial_state = AgentState(
        query=query, 
        session_id=session_id, 
        user_id=user_id,
        memory_context=memory_context
    )
    final_state = await graph.ainvoke(initial_state)
    
    # final_state 是 dict，不是 AgentState 实例
    return {
        "answer": final_state.get("final_answer", ""),
        "intent": "agent",
        "selected_skills": final_state.get("selected_skills", []),
        "skill_results": final_state.get("skill_results", {}),
        "error": final_state.get("error", "")
    }