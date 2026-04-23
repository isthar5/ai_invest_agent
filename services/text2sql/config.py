import os
import redis.asyncio as aioredis
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 数据库配置
DATABASE_URL = os.getenv("TEXT2SQL_DB_URL", "postgresql://user:password@localhost:5432/mydb")
ASYNC_DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

# Redis 配置
REDIS_URL = os.getenv("TEXT2SQL_REDIS_URL", "redis://localhost:6379")
REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))

# 缓存配置
SCHEMA_CACHE_TTL = int(os.getenv("SCHEMA_CACHE_TTL", "86400"))  # 24小时
SAMPLE_ROWS_LIMIT = int(os.getenv("SAMPLE_ROWS_LIMIT", "3"))

# 向量配置
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")
VECTOR_SIMILARITY_THRESHOLD = float(os.getenv("VECTOR_SIMILARITY_THRESHOLD", "0.3"))

# 全局连接池
_redis_pool: aioredis.Redis = None
_engine = None
_async_engine = None

async def get_redis() -> aioredis.Redis:
    """获取 Redis 连接池（单例）"""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            REDIS_URL,
            max_connections=REDIS_MAX_CONNECTIONS,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30
        )
    return _redis_pool

def get_engine():
    """获取同步数据库引擎（单例）"""
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )
    return _engine

def get_async_engine():
    """获取异步数据库引擎（单例）"""
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            ASYNC_DATABASE_URL,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,
            echo=False
        )
    return _async_engine