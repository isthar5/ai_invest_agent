from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.rag.pipeline import rag_quant_pipeline
from app.agent.runtime import run_agent
from app.multi_agent.runtime import run_multi_agent
from pydantic import BaseModel
from typing import Optional
import json
import uuid

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    stream: bool = False
    use_agent: bool = True
    multi_agent: bool = True  # 新增 multi_agent 开关，默认为 True

@router.post("/chat")
async def chat(req: ChatRequest):
    if req.multi_agent:
        # 使用新的 Multi-Agent 架构
        result = await run_multi_agent(
            req.query,
            session_id=req.session_id or str(uuid.uuid4())
        )
        return result

    if req.use_agent:
        # 使用 LangGraph Agent
        result = await run_agent(
            req.query,
            session_id=req.session_id or str(uuid.uuid4()),
            user_id=req.user_id or "default"
        )
        return result

    if not req.stream:
        # 非流式：返回完整结果
        result = await rag_quant_pipeline(req.query, streaming=False)
        return result  # 直接返回字典，FastAPI 会自动转 JSON
    
    # 流式输出 (SSE)
    async def event_generator():
        try:
            stream_response = await rag_quant_pipeline(req.query, streaming=True)
            async for chunk in stream_response:
                # 适配不同格式
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
