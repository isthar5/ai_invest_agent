"""
ChemInvest Agent — 统一 FastAPI 入口。

中间件注册顺序（先注册 = 最外层包裹）：
  CORS → Metrics → RateLimiter → RequestID + Context → Handler
"""

from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
from app.api.upload_signal import router as upload_router
from app.api.workflow import router as workflow_router
from dotenv import load_dotenv
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import uuid
from fastapi import WebSocket
from app.api.websocket import websocket_endpoint
from app.observability.logger import setup_logging, get_logger
from app.observability.context import init_request_context
from app.observability.metrics import metrics_middleware
from app.middleware.rate_limiter import rate_limit_middleware

# 加载环境变量
load_dotenv()

# 初始化统一 JSON Logger（幂等，全局生效）
setup_logging()
logger = get_logger(__name__)

app = FastAPI(title="ChemInvest Agent")

# ==================== CORS 配置 ====================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== 基础设施中间件 ====================
# 注册顺序决定包裹层级（先注册 = 外层）

# 1. 最外层：Metrics（记录 HTTP 延迟 + 计数 + X-Process-Time）
app.middleware("http")(metrics_middleware)

# 2. 限流（提前拒绝超量请求）
app.middleware("http")(rate_limit_middleware)

# 3. 最内层：Request ID + RequestContext 初始化
@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """
    初始化请求级上下文：
    - 生成/继承 request_id（全链路追踪）
    - 初始化 RequestContext（协程安全的请求上下文）
    - 注入 X-Request-ID 响应头
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    session_id = request.headers.get("X-Session-ID", "")
    user_id = request.headers.get("X-User-ID", "")

    # 初始化 RequestContext（后续所有 logger/metrics 自动继承）
    init_request_context(
        request_id=request_id,
        session_id=session_id,
        user_id=user_id,
    )

    # 存到 request.state（兼容旧代码）
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# ==================== 健康检查端点 ====================
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "chem-invest-agent",
    }


@app.get("/ready")
async def readiness_check():
    return {"status": "ready"}


# ==================== 注册业务路由 ====================
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(upload_router, prefix="/api", tags=["DataSync"])
app.include_router(workflow_router, prefix="/api", tags=["Workflow"])


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket_endpoint(websocket)


# ==================== 监控端点 ====================
@app.get("/metrics")
async def metrics():
    """Prometheus 指标暴露"""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ==================== 用量统计端点 ====================
@app.get("/usage")
async def usage_summary():
    """LLM Token 用量摘要"""
    from app.observability.usage import UsageTracker
    return UsageTracker.get_instance().summary()


# ==================== 启动入口 ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
