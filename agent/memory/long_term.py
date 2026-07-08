# app/agent/memory/long_term.py
import json
import logging
import redis.asyncio as redis_asyncio
from .metrics import memory_latency, memory_hit

logger = logging.getLogger("agent.memory.long_term")

class LongTermMemory:
    """
    工业级长期用户偏好记忆
    - Redis Hash 或 RedisJSON
    - 字段级更新，支持向量检索扩展
    - 异常降级，防止 Agent 中断
    """
    def __init__(self, ttl: int = 2592000, redis_url: str = "redis://localhost:6379"):
        self.ttl = ttl
        self.redis = redis_asyncio.from_url(redis_url, decode_responses=True)

    async def get(self, user_id: str) -> dict:
        with memory_latency.labels(operation="get", module="long_term").time():
            try:
                data = await self.redis.hgetall(user_id)
                memory_hit.labels(module="long_term").inc()
                return {k: json.loads(v) for k, v in data.items()} if data else {}
            except Exception as e:
                logger.error(f"Redis error in long_term get: {e}")
                return {}

    async def update(self, user_id: str, data: dict):
        with memory_latency.labels(operation="update", module="long_term").time():
            try:
                pipe = self.redis.pipeline()
                for k, v in data.items():
                    # 使用 default=str 确保 datetime 等对象能被序列化
                    pipe.hset(user_id, k, json.dumps(v, default=str))
                await pipe.execute()
                await self.redis.expire(user_id, self.ttl)
            except Exception as e:
                logger.error(f"Redis error in long_term update: {e}")

    async def clear(self, user_id: str):
        with memory_latency.labels(operation="clear", module="long_term").time():
            try:
                await self.redis.delete(user_id)
            except Exception as e:
                logger.error(f"Redis error in long_term clear: {e}")
