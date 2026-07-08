"""
Chat API v2

v2 变更：
- 所有路径统一传递 session_id 和 memory 上下文
- RAG 路径注入 memory_context 以供 PromptBuilder 使用
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.rag.pipeline import rag_quant_pipeline
from app.agent.runtime import run_agent
from app.agent.memory import ShortTermMemory, LongTermMemory, SummaryMemory, SharedAgentMemory
from app.multi_agent.runtime import run_multi_agent
from app.config.settings import settings
from pydantic import BaseModel
from typing import Optional
import json
import uuid
import asyncio

router = APIRouter()


class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    stream: bool = False
    use_agent: bool = True
    multi_agent: bool = True


class RouterRequest(BaseModel):
    query: str


class RouterResponse(BaseModel):
    workflow: str  # "quant" | "text2sql" | "rag"


async def _load_memory_context(session_id: str, user_id: str) -> dict:
    """并发加载完整记忆上下文"""
    if not session_id and not user_id:
        return {}

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

    return {
        "recent_history": short_term or [],
        "user_preferences": long_term or {},
        "summary": summary,
        "shared_memory": shared_data or {},
    }


def _classify_workflow(query: str) -> str:
    """
    Intent classification → frontend AgentType mapping.

    Mirrors app/multi_agent/router.py → RouterAgent keyword logic.
    Maps internal intents to frontend workflow ids:
      financial_analysis | industry_comparison → quant
      text2sql                                → text2sql
      rag_query                               → rag
    """
    text = (query or "").lower()

    sql_keywords = ["sql", "数据库", "历年", "资产负债", "排名", "top", "营业收入", "利润排名"]
    financial_keywords = [
        "财务", "财报", "年报", "毛利率", "净利率",
        "roe", "现金流", "估值", "盈利能力", "偿债能力",
    ]
    # compound phrases only — standalone "行业"/"竞争" are too broad
    industry_keywords = [
        "行业竞争", "竞争格局", "行业对标", "行业对比",
        "同业对比", "同业估值", "市场份额", "行业排名",
    ]

    if any(k in text for k in sql_keywords):
        return "text2sql"
    if any(k in text for k in financial_keywords):
        return "quant"
    if any(k in text for k in industry_keywords):
        return "quant"
    # default: knowledge / RAG queries
    return "rag"


@router.post("/router", response_model=RouterResponse)
async def route_intent(req: RouterRequest):
    """
    Lightweight Router endpoint — Phase 1.

    Only classifies query intent and returns the target workflow id.
    Does NOT execute the full agent pipeline.
    """
    workflow = _classify_workflow(req.query)
    return RouterResponse(workflow=workflow)


@router.post("/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    user_id = req.user_id or "default"

    if req.multi_agent:
        result = await run_multi_agent(
            req.query,
            session_id=session_id,
        )
        return result

    if req.use_agent:
        result = await run_agent(
            req.query,
            session_id=session_id,
            user_id=user_id,
        )
        return result

    # RAG 路径：加载 memory_context
    memory_context = await _load_memory_context(session_id, user_id)

    if not req.stream:
        result = await rag_quant_pipeline(
            req.query,
            streaming=False,
            memory_context=memory_context,
        )
        return result

    # 流式输出 (SSE)
    async def event_generator():
        try:
            stream_response = await rag_quant_pipeline(
                req.query,
                streaming=True,
                memory_context=memory_context,
            )
            async for chunk in stream_response:
                content = None
                if hasattr(chunk, 'choices') and chunk.choices:
                    delta = chunk.choices[0].delta
                    content = getattr(delta, 'content', None)
                elif isinstance(chunk, str):
                    content = chunk
                elif isinstance(chunk, dict):
                    content = chunk.get('content')

                if content:
                    yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
