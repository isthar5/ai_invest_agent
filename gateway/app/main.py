from fastapi import FastAPI, Request
from app.gateway.router import match_route
from app.gateway.proxy import proxy_request
from prometheus_client import generate_latest
from fastapi.responses import Response
from app.middleware.request_id import request_id_middleware
from app.middleware.metrics import metrics_middleware
from app.middleware.rate_limiter import rate_limit_middleware

app = FastAPI()

# 中间件顺序很重要
app.middleware("http")(request_id_middleware)
app.middleware("http")(metrics_middleware)
app.middleware("http")(rate_limit_middleware)
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def gateway(request: Request, path: str):
    target_url = match_route("/" + path)

    if not target_url:
        return {"error": "no route"}

    return await proxy_request(request, target_url)