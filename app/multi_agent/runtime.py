"""
Multi-Agent Runtime v2

v2 变更：
- 集成 SharedAgentMemory：Agent 间数据共享
- 集成 ShortTermMemory：对话历史持久化
"""

import asyncio
import json
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.multi_agent.agents import QuantAgent, RAGAgent, Text2SQLAgent
from app.multi_agent.base import AgentMessage, StateManager
from app.multi_agent.router import RouterAgent
from app.agent.memory import ShortTermMemory, SharedAgentMemory

_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager(redis_url=settings.MEMORY_REDIS_URL)
    return _state_manager


async def run_multi_agent(
    query: str,
    session_id: str = "default",
    stream_callback=None,
) -> Dict[str, Any]:
    state_manager = get_state_manager()

    # v2 新增：初始化 SharedAgentMemory
    shared_mem = SharedAgentMemory(
        ttl=settings.MEMORY_SHARED_TTL,
        redis_url=settings.MEMORY_REDIS_URL,
    )

    # v2 新增：读取共享记忆供 Agent 使用
    shared_context = await shared_mem.get_all(session_id)

    if stream_callback:
        await stream_callback("status", "planning")
        await stream_callback("reasoning", f"分析用户意图: {query[:50]}...")

    agents = {
        "QuantAgent": QuantAgent(state_manager),
        "Text2SQLAgent": Text2SQLAgent(state_manager),
        "RAGAgent": RAGAgent(state_manager),
    }
    router = RouterAgent(agents)
    msg = AgentMessage(content=query, metadata={
        "session_id": session_id,
        "shared_memory": shared_context,  # v2 新增
    })

    if stream_callback:
        await stream_callback("status", "executing")
        await stream_callback("tool", {"name": "RouterAgent", "action": "dispatching"})

    response = await router.run(msg)

    # v2 新增：将 Agent 执行结果写入共享记忆
    current_skill_results, current_errors = extract_current_run_results(response)
    await _write_shared_memory(shared_mem, session_id, current_skill_results)

    state = await state_manager.get_state(session_id)

    if stream_callback:
        for agent_name, result in current_skill_results.items():
            await stream_callback("tool", {"name": agent_name, "result": result})
        await stream_callback("status", "generating")
        answer = await generate_streaming_answer(current_skill_results, stream_callback)
    else:
        answer = await generate_answer(current_skill_results)

    # v2 新增：保存 ShortTermMemory
    st_memory = ShortTermMemory(
        ttl=settings.MEMORY_SHORT_TERM_TTL,
        redis_url=settings.MEMORY_REDIS_URL,
        max_len=settings.MEMORY_SHORT_TERM_MAX_LEN,
    )
    from datetime import datetime
    await st_memory.add(session_id, {
        "query": query,
        "answer": answer,
        "timestamp": datetime.now().isoformat(),
    })

    errors = current_errors
    return {
        "success": len(errors) == 0,
        "answer": answer,
        "skill_results": current_skill_results,
        "state": state,
        "error": "; ".join(errors),
        "memory_meta": {  # v2 新增
            "has_shared_context": bool(shared_context),
        },
    }


async def _write_shared_memory(
    shared_mem: SharedAgentMemory,
    session_id: str,
    agent_results: Dict[str, Any],
):
    """将 Agent 执行结果写入共享记忆"""
    # QuantAgent 结果
    quant_result = agent_results.get("QuantAgent")
    if isinstance(quant_result, dict):
        await shared_mem.write_quant_conclusion(
            session_id=session_id,
            stock=quant_result.get("stock", ""),
            score=quant_result.get("score"),
            signal=quant_result.get("signal"),
            conclusion=quant_result.get("insight") or quant_result.get("summary", ""),
            risk=quant_result.get("risk"),
        )

    # RAGAgent 结果
    rag_result = agent_results.get("RAGAgent")
    if isinstance(rag_result, dict):
        await shared_mem.write_rag_findings(
            session_id=session_id,
            sources=rag_result.get("sources", []),
            key_findings=rag_result.get("key_findings", [rag_result.get("answer", "")[:200]]),
        )

    # Text2SQLAgent 结果
    sql_result = agent_results.get("Text2SQLAgent")
    if sql_result is not None:
        sql_str = ""
        result_summary = ""
        if isinstance(sql_result, dict):
            sql_str = sql_result.get("sql", "")
            result_summary = json.dumps(sql_result.get("result", ""), ensure_ascii=False)[:500]
        await shared_mem.write_sql_result(
            session_id=session_id,
            sql=sql_str,
            result_summary=result_summary,
        )


async def generate_answer(agent_results: Dict[str, Any]) -> str:
    if not agent_results:
        return "未获取到可用的 Multi-Agent 结果。"

    quant_result = agent_results.get("QuantAgent")
    if isinstance(quant_result, dict):
        return (
            quant_result.get("insight")
            or quant_result.get("summary")
            or json.dumps(quant_result, ensure_ascii=False, indent=2)
        )

    sql_result = agent_results.get("Text2SQLAgent")
    if sql_result is not None:
        return json.dumps(sql_result, ensure_ascii=False, indent=2)

    rag_result = agent_results.get("RAGAgent")
    if isinstance(rag_result, dict):
        return rag_result.get("answer") or json.dumps(rag_result, ensure_ascii=False, indent=2)
    if rag_result is not None:
        return str(rag_result)

    return json.dumps(agent_results, ensure_ascii=False, indent=2)


async def generate_streaming_answer(agent_results: Dict[str, Any], callback) -> str:
    answer_text = await generate_answer(agent_results)
    parts = [answer_text[i:i + 32] for i in range(0, len(answer_text), 32)] or [answer_text]

    full_answer = ""
    for part in parts:
        full_answer += part
        await callback("token", part)
        await asyncio.sleep(0.05)
    return full_answer


def extract_current_run_results(msg: AgentMessage) -> tuple[Dict[str, Any], list[str]]:
    agent_results: Dict[str, Any] = {}
    errors: list[str] = []

    for item in msg.history:
        agent_name = item.get("agent")
        result = item.get("result")
        if not agent_name:
            continue
        agent_results[agent_name] = result
        if isinstance(result, dict) and result.get("error"):
            errors.append(result["error"])

    return agent_results, errors
