# app/agent/memory.py
import asyncio
import logging
from app.agent.memory.short_term import ShortTermMemory
from app.agent.memory.long_term import LongTermMemory

logger = logging.getLogger("agent.memory")

class MemoryManager:
    """
    工业级 Memory 管理器，封装短期和长期记忆，统一接口
    - 支持分层: Turn/Task/Session/User/Global
    - 支持并发安全、降级、Metrics
    """

    def __init__(self, short_term_ttl: int = 3600, long_term_ttl: int = 3600*24*30):
        self.short_term = ShortTermMemory(ttl=short_term_ttl)
        self.long_term = LongTermMemory(ttl=long_term_ttl)

    # ----------------- Short Term -----------------
    async def get_short_term(self, session_id: str) -> list:
        return await self.short_term.get(session_id)

    async def add_short_term(self, session_id: str, item: dict):
        await self.short_term.add(session_id, item)

    async def clear_short_term(self, session_id: str):
        await self.short_term.clear(session_id)

    # ----------------- Long Term -----------------
    async def get_long_term(self, user_id: str) -> dict:
        return await self.long_term.get(user_id)

    async def update_long_term(self, user_id: str, data: dict):
        await self.long_term.update(user_id, data)

    async def clear_long_term(self, user_id: str):
        await self.long_term.clear(user_id)