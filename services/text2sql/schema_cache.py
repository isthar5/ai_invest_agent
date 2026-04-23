import json
import logging
from typing import List, Dict, Optional
from sqlalchemy import text

from .config import get_redis, get_engine, SCHEMA_CACHE_TTL, SAMPLE_ROWS_LIMIT
from .utils import escape_sample_row, sanitize_table_name

logger = logging.getLogger("text2sql.schema_cache")

class SchemaCache:
    """缓存数据库 Schema，支持异步刷新和降级"""

    def __init__(self):
        self.engine = get_engine()
        self.cache_ttl = SCHEMA_CACHE_TTL

    async def _get_redis(self):
        return await get_redis()

    async def get_tables(self, refresh: bool = False) -> List[str]:
        """获取所有表名"""
        redis = await self._get_redis()
        key = "schema:tables"

        if not refresh:
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """))
            tables = [row[0] for row in result]

        await redis.setex(key, self.cache_ttl, json.dumps(tables))
        logger.info(f"Cached {len(tables)} tables")
        return tables

    async def get_table_schema(self, table_name: str, refresh: bool = False) -> Dict:
        """获取单表完整 Schema（带缓存锁防击穿）"""
        redis = await self._get_redis()
        table_name = sanitize_table_name(table_name)
        key = f"schema:table:{table_name}"
        lock_key = f"{key}:lock"

        if not refresh:
            cached = await redis.get(key)
            if cached:
                return json.loads(cached)

        # 缓存锁避免击穿
        try:
            async with redis.lock(lock_key, timeout=10, blocking_timeout=5):
                # 双重检查
                cached = await redis.get(key)
                if cached:
                    return json.loads(cached)

                schema = await self._query_table_schema_from_db(table_name)
                await redis.setex(key, self.cache_ttl, json.dumps(schema))
                logger.info(f"Cached schema for {table_name}")
                return schema
        except Exception as e:
            logger.warning(f"Failed to acquire lock for {table_name}: {e}")
            # 降级：直接查询数据库
            return await self._query_table_schema_from_db(table_name)

    async def _query_table_schema_from_db(self, table_name: str) -> Dict:
        """从数据库查询表结构"""
        with self.engine.connect() as conn:
            # 列信息
            columns_result = conn.execute(text("""
                SELECT
                    column_name, data_type, is_nullable,
                    column_default, character_maximum_length,
                    numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_name = :table_name
                ORDER BY ordinal_position
            """), {"table_name": table_name})

            columns = []
            for row in columns_result:
                columns.append({
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": str(row[3]) if row[3] else None,
                    "max_length": row[4],
                    "numeric_precision": row[5],
                    "numeric_scale": row[6]
                })

            # 主键
            pk_result = conn.execute(text("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = :table_name::regclass AND i.indisprimary
            """), {"table_name": table_name})
            primary_keys = [row[0] for row in pk_result]

            # 外键
            fk_result = conn.execute(text("""
                SELECT
                    kcu.column_name,
                    ccu.table_name AS foreign_table_name,
                    ccu.column_name AS foreign_column_name
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                    ON tc.constraint_name = kcu.constraint_name
                JOIN information_schema.constraint_column_usage AS ccu
                    ON ccu.constraint_name = tc.constraint_name
                WHERE tc.constraint_type = 'FOREIGN KEY'
                    AND tc.table_name = :table_name
            """), {"table_name": table_name})
            foreign_keys = [dict(row) for row in fk_result]

        return {
            "name": table_name,
            "columns": columns,
            "primary_keys": primary_keys,
            "foreign_keys": foreign_keys
        }

    async def get_sample_rows(self, table_name: str, limit: int = None) -> List[Dict]:
        """获取示例数据行"""
        redis = await self._get_redis()
        table_name = sanitize_table_name(table_name)
        limit = limit or SAMPLE_ROWS_LIMIT
        key = f"schema:sample:{table_name}"

        cached = await redis.get(key)
        if cached:
            return json.loads(cached)

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {limit}"))
                rows = [escape_sample_row(dict(row)) for row in result]
                await redis.setex(key, self.cache_ttl, json.dumps(rows, default=str))
                return rows
        except Exception as e:
            logger.warning(f"Failed to get sample rows for {table_name}: {e}")
            return []

    async def invalidate_table(self, table_name: str):
        """使指定表的缓存失效"""
        redis = await self._get_redis()
        table_name = sanitize_table_name(table_name)
        await redis.delete(f"schema:table:{table_name}")
        await redis.delete(f"schema:sample:{table_name}")
        logger.info(f"Invalidated cache for {table_name}")