"""
Rate Limiter — Token Bucket 限流中间件。

从 app/gateway 迁移至 app/middleware/。
基于 Redis Lua 脚本实现原子 Token Bucket 算法。

配置通过环境变量覆盖：
  RL_SERVICE_RATE: 令牌填充速率（默认 50）
  RL_SERVICE_CAPACITY: 桶容量（默认 50）

用法（在 main.py 中注册）：
    from app.middleware.rate_limiter import rate_limit_middleware
    app.middleware("http")(rate_limit_middleware)
"""

import os
import time
import logging

from fastapi.responses import JSONResponse

logger = logging.getLogger("middleware.rate_limiter")

# ── 配置 ──────────────────────────────────────────────

RATE_LIMIT = {
    "service": {
        "rate": int(os.getenv("RL_SERVICE_RATE", "50")),
        "capacity": int(os.getenv("RL_SERVICE_CAPACITY", "50")),
    },
}

# ── Redis 连接（延迟初始化，复用主应用 Redis URL） ──

_redis_client = None

TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local rate = tonumber(ARGV[1])
local capacity = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", key, "tokens", "timestamp")
local tokens = tonumber(data[1])
local last_time = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_time = now
end

local delta = math.max(0, now - last_time)
local new_tokens = math.min(capacity, tokens + delta * rate)

if new_tokens < 1 then
    redis.call("HMSET", key, "tokens", new_tokens, "timestamp", now)
    return 0
else
    redis.call("HMSET", key, "tokens", new_tokens - 1, "timestamp", now)
    return 1
end
"""


async def _get_redis():
    """延迟初始化 Redis 连接，使用主应用统一的 MEMORY_REDIS_URL"""
    global _redis_client
    if _redis_client is None:
        try:
            import redis.asyncio as aioredis
            redis_url = os.getenv("MEMORY_REDIS_URL", "redis://localhost:6379")
            _redis_client = aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            logger.info(f"Rate limiter Redis connected: {redis_url}")
        except Exception as e:
            logger.warning(f"Rate limiter Redis unavailable, disabling: {e}")
            return None
    return _redis_client


# ── 中间件 ────────────────────────────────────────────

async def rate_limit_middleware(request, call_next):
    """服务级 Token Bucket 限流中间件"""
    now = int(time.time())
    svc = RATE_LIMIT["service"]

    redis = await _get_redis()
    if redis is None:
        # Redis 不可用时放行
        return await call_next(request)

    try:
        allowed = await redis.eval(
            TOKEN_BUCKET_LUA, 1, "rl:svc",
            svc["rate"], svc["capacity"], now,
        )
    except Exception as e:
        logger.warning(f"Rate limit check failed, allowing: {e}")
        return await call_next(request)

    if allowed == 0:
        return JSONResponse(
            {"error": "rate limit exceeded", "retry_after": int(1.0 / svc["rate"])},
            status_code=429,
        )

    return await call_next(request)
