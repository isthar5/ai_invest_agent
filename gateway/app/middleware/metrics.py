from prometheus_client import Counter, Histogram
import time

REQUEST_COUNT = Counter("request_count", "Total Requests", ["path"])
LATENCY = Histogram("latency", "Request latency")

async def metrics_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    
    LATENCY.observe(time.time() - start)
    REQUEST_COUNT.labels(request.url.path).inc()
    
    return response