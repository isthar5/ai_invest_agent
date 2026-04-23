from fastapi.responses import JSONResponse
from app.core.config import RATE_LIMIT
from app.services.redis_client import redis_client

# Lua 脚本（令牌桶）
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

-- 补充 token
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

async def rate_limit_middleware(request, call_next):
    import time

    client_ip = request.client.host
    key = f"tb:{client_ip}"

    allowed = await redis_client.eval(
        TOKEN_BUCKET_LUA,
        1,
        key,
        RATE_LIMIT["rate"],     # rate: 每秒生成 token
        RATE_LIMIT["capacity"],     # capacity: 桶容量
        int(time.time())
    )

    if allowed == 0:
        return JSONResponse({"error": "rate limit exceeded"}, status_code=429)

    return await call_next(request)