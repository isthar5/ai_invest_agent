import asyncio
import json
from typing import Any, Dict, Optional

from app.config.settings import settings
from app.multi_agent.agents import QuantAgent, RAGAgent, Text2SQLAgent
from app.multi_agent.base import AgentMessage, StateManager
from app.multi_agent.router import RouterAgent

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

    if stream_callback:
        await stream_callback("status", "planning")
        await stream_callback("reasoning", f"分析用户意图: {query[:50]}...")

    agents = {
        "QuantAgent": QuantAgent(state_manager),
        "Text2SQLAgent": Text2SQLAgent(state_manager),
        "RAGAgent": RAGAgent(state_manager),
    }
    router = RouterAgent(agents)
    msg = AgentMessage(content=query, metadata={"session_id": session_id})

    if stream_callback:
        await stream_callback("status", "executing")
        await stream_callback("tool", {"name": "RouterAgent", "action": "dispatching"})

    response = await router.run(msg)
    state = await state_manager.get_state(session_id)
    current_skill_results, current_errors = extract_current_run_results(response)

    if stream_callback:
        for agent_name, result in current_skill_results.items():
            await stream_callback("tool", {"name": agent_name, "result": result})
        await stream_callback("status", "generating")
        answer = await generate_streaming_answer(current_skill_results, stream_callback)
    else:
        answer = await generate_answer(current_skill_results)

    errors = current_errors
    return {
        "success": len(errors) == 0,
        "answer": answer,
        "skill_results": current_skill_results,
        "state": state,
        "error": "; ".join(errors),
    }


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
