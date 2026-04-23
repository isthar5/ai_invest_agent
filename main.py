from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
from app.api.upload_signal import router as upload_router
from dotenv import load_dotenv
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import time
import uuid
from fastapi import WebSocket
from app.api.websocket import websocket_endpoint

# 加载环境变量
load_dotenv()

app = FastAPI(title="ChemInvest Agent with Gateway")

# ==================== CORS 配置 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 网关中间件 ====================

@app.middleware("http")
async def gateway_middleware(request: Request, call_next):
    """
    统一网关中间件：
    - 生成 request_id 用于全链路追踪
    - 记录请求耗时
    - 注入追踪头到响应
    """
    # 生成请求 ID
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    
    # 记录开始时间
    start_time = time.time()
    
    # 执行后续处理
    response = await call_next(request)
    
    # 计算耗时
    process_time = time.time() - start_time
    
    # 注入追踪头
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.3f}s"
    
    # 可选：记录到日志
    # logger.info(f"[{request_id}] {request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s")
    
    return response


# ==================== 健康检查端点 ====================
@app.get("/health")
async def health_check():
    """网关健康检查"""
    return {
        "status": "healthy",
        "service": "chem-invest-agent",
        "timestamp": time.time()
    }


@app.get("/ready")
async def readiness_check():
    """就绪检查（可扩展检查下游服务）"""
    return {"status": "ready"}


# ==================== 注册业务路由 ====================
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(upload_router, prefix="/api", tags=["DataSync"])

@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_endpoint(websocket)


# ==================== 监控端点 ====================
@app.get("/metrics")
async def metrics():
    """Prometheus 指标暴露"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ==================== 启动入口 ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
