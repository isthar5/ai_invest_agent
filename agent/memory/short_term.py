# app/agent/memory/short_term.py
import json
import logging
import redis.asyncio as redis_asyncio
from .metrics import memory_latency, memory_hit

logger = logging.getLogger("agent.memory.short_term")

class ShortTermMemory:
    """
    工业级短期会话记忆
    - Redis List 原子操作，固定长度 FIFO
    - 异常降级，不阻断 Agent 主流程
    """
    def __init__(self, ttl: int = 3600, redis_url: str = "redis://localhost:6379", max_len: int = 20):
        self.ttl = ttl
        self.max_len = max_len
        self.redis = redis_asyncio.from_url(redis_url, decode_responses=True)

    async def get(self, session_id: str) -> list:
        # 使用 labels(module="short_term") 区分模块
        with memory_latency.labels(operation="get", module="short_term").time():
            try:
                data = await self.redis.lrange(session_id, 0, -1)
                memory_hit.labels(module="short_term").inc()
                return [json.loads(d) for d in reversed(data)]
            except Exception as e:
                logger.error(f"Redis error in short_term get: {e}")
                return []

    async def add(self, session_id: str, item: dict):
        with memory_latency.labels(operation="add", module="short_term").time():
            try:
                # 使用 default=str 确保 datetime 等对象能被序列化
                data = json.dumps(item, default=str)
                await self.redis.lpush(session_id, data)
                await self.redis.ltrim(session_id, 0, self.max_len - 1)
                await self.redis.expire(session_id, self.ttl)
            except Exception as e:
                logger.error(f"Redis error in short_term add: {e}")

    async def clear(self, session_id: str):
        with memory_latency.labels(operation="clear", module="short_term").time():
            try:
                await self.redis.delete(session_id)
            except Exception as e:
                logger.error(f"Redis error in short_term clear: {e}")
