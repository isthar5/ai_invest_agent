import httpx
from fastapi.responses import JSONResponse, Response
from app.services.cache import get_cache, set_cache
from app.middleware.circuit_breaker import get_cb

def extract_service_key(target_url: str):
    return target_url.split("/")[2].split(":")[0]

timeout = httpx.Timeout(connect=1.0, read=5.0, write=1.0, pool=1.0)

async def proxy_request(request, target_url):
    query = request.url.query
    cache_key = f"{target_url}?{query}"
    cached = await get_cache(cache_key)
    if cached:
        return Response(content=cached, media_type="application/json")

    service_key = extract_service_key(target_url)
    cb = get_cb(service_key)

    # 熔断判断
    if not cb.allow_request():
        cached = await get_cache(cache_key)
        if cached:
            return Response(content=cached, media_type="application/json")
        return JSONResponse({"msg": f"{service_key} degraded"}, status_code=503)

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                content=await request.body()
            )

        # 成功
        cb.on_success()

        # 缓存 GET
        if request.method == "GET":
            await set_cache(cache_key, resp.text)

        return Response(content=resp.content, status_code=resp.status_code)

    except Exception:
        cb.on_failure()

        cached = await get_cache(cache_key)
        if cached:
            return Response(content=cached, media_type="application/json")

        return JSONResponse({"error": f"{service_key} failure"}, status_code=500)