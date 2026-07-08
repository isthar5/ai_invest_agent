import json
from datetime import datetime
from typing import Any, Dict, List

try:
    import redis.asyncio as redis_asyncio
except ImportError:
    redis_asyncio = None


class AgentMessage:
    def __init__(self, content: str, metadata: Dict = None, history: List[Dict] = None):
        self.content = content
        self.metadata = metadata or {}
        self.history = history or []
        self.timestamp = datetime.utcnow().isoformat()

    def record_history(self, agent_name: str, result: Any, duration: float, tokens: int = 0):
        self.history.append(
            {
                "agent": agent_name,
                "result": result,
                "duration": duration,
                "tokens": tokens,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )


class BaseAgent:
    def __init__(self, name: str, state_manager):
        self.name = name
        self.state_manager = state_manager

    async def run(self, msg: AgentMessage) -> AgentMessage:
        import time

        start = time.time()
        try:
            result = await self._process(msg)
            duration = time.time() - start
            tokens = len(msg.content.split())
            msg.record_history(self.name, result, duration, tokens)
            if self.state_manager:
                await self.state_manager.save_message(msg.metadata.get("session_id", "default"), msg)
            return msg
        except Exception as e:
            duration = time.time() - start
            msg.record_history(self.name, {"error": str(e)}, duration, 0)
            if self.state_manager:
                await self.state_manager.save_message(msg.metadata.get("session_id", "default"), msg)
            return msg

    async def _process(self, msg: AgentMessage) -> dict:
        raise NotImplementedError


class StateManager:
    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis_url = redis_url
        self.redis = None
        self._memory_store: Dict[str, List[str]] = {}

    async def init(self):
        if redis_asyncio is None:
            self.redis = None
            return
        self.redis = redis_asyncio.from_url(self.redis_url, decode_responses=True)

    async def save_message(self, session_id: str, msg: AgentMessage):
        if self.redis is None:
            await self.init()

        key = f"session:{session_id}"
        payload = json.dumps(
            {
                "content": msg.content,
                "metadata": msg.metadata,
                "history": msg.history,
                "timestamp": msg.timestamp,
            }
        )

        if self.redis is not None:
            await self.redis.rpush(key, payload)
        else:
            self._memory_store.setdefault(key, []).append(payload)

    async def load_messages(self, session_id: str) -> List[AgentMessage]:
        if self.redis is None:
            await self.init()

        key = f"session:{session_id}"
        if self.redis is not None:
            data = await self.redis.lrange(key, 0, -1)
        else:
            data = list(self._memory_store.get(key, []))

        messages = []
        for item in data:
            obj = json.loads(item)
            messages.append(AgentMessage(obj["content"], obj["metadata"], obj["history"]))
        return messages

    async def get_state(self, session_id: str) -> Dict[str, Any]:
        messages = await self.load_messages(session_id)
        state: Dict[str, Any] = {
            "session_id": session_id,
            "history": [],
            "agent_results": {},
            "errors": [],
        }

        for msg in messages:
            for item in msg.history:
                agent_name = item.get("agent", "unknown")
                result = item.get("result")
                state["history"].append(item)
                state["agent_results"][agent_name] = result
                if isinstance(result, dict) and result.get("error"):
                    state["errors"].append({"agent": agent_name, "error": result["error"]})

        return state
