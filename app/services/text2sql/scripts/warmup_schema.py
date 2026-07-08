import asyncio
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

from app.services.text2sql import SchemaLinker, AliasManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("warmup")


async def warmup(allowed_tables: list = None):
    """预热 Schema 缓存和别名"""
    logger.info("Starting schema warmup...")

    # 初始化默认别名
    alias_mgr = AliasManager()
    await alias_mgr.init_default_aliases()
    logger.info("Aliases initialized")

    # 预热 Schema
    linker = SchemaLinker()
    tables = await linker.cache.get_tables(refresh=True)

    if allowed_tables:
        tables = [t for t in tables if t in allowed_tables]

    for table_name in tables:
        logger.info(f"Warming up {table_name}...")
        schema = await linker.cache.get_table_schema(table_name, refresh=True)
        await linker.cache.get_sample_rows(table_name)

        # 索引向量
        await linker.embedder.index_tables({table_name: schema})

    logger.info(f"Warmup completed for {len(tables)} tables")


if __name__ == "__main__":
    asyncio.run(warmup())