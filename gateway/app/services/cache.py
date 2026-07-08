import json
from app.services.redis_client import redis_client
from app.core.config import CACHE_CONFIG

EMPTY_VALUE = "__EMPTY__"

async def get_cache(key):
    data = await redis_client.get(key)
    if data == EMPTY_VALUE:
        return None
    return data

async def set_cache(key, value):
    if value is None or value == "" or value == "null":
        await redis_client.setex(key, 60, EMPTY_VALUE)
    else:
        await redis_client.setex(key, CACHE_CONFIG["ttl"], value)