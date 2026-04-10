from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.rag.pipeline import rag_quant_pipeline
import json

router = APIRouter()


@router.post("/chat")
async def chat(query: str, stream: bool = False):
    if not stream:
        # 非流式：返回完整结果
        result = await rag_quant_pipeline(query, streaming=False)
        return result  # 直接返回字典，FastAPI 会自动转 JSON
    
    # 流式输出 (SSE)
    async def event_generator():
        try:
            stream_response = await rag_quant_pipeline(query, streaming=True)
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