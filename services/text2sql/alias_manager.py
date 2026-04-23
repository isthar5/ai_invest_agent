import json
import logging
from typing import Dict, List

from .config import get_redis

logger = logging.getLogger("text2sql.alias_manager")

# 默认别名
DEFAULT_COLUMN_ALIASES = {
    "营收": ["revenue", "income", "sales"],
    "营业收入": ["revenue", "operating_revenue"],
    "净利润": ["net_profit", "profit"],
    "归母净利润": ["net_profit_attributable"],
    "毛利率": ["gross_margin"],
    "净利率": ["net_margin"],
    "ROE": ["roe", "return_on_equity"],
    "ROA": ["roa", "return_on_assets"],
    "现金流": ["cash_flow", "operating_cash_flow"],
    "年份": ["year", "fiscal_year", "report_year"],
    "季度": ["quarter", "q"],
    "公司": ["company", "company_name", "name"],
    "股票代码": ["code", "stock_code", "ticker", "symbol"],
}

DEFAULT_TABLE_ALIASES = {
    "财务": ["financials", "income_statement"],
    "利润表": ["financials", "income_statement"],
    "营收": ["financials"],
    "公司": ["companies", "company_info"],
    "资产负债表": ["balance_sheet"],
    "现金流量表": ["cash_flow_statement"],
    "订单": ["orders"],
    "行业": ["industries", "sectors"],
}


class AliasManager:
    """动态管理表名/列名别名"""

    async def _get_redis(self):
        return await get_redis()

    async def init_default_aliases(self):
        """初始化默认别名到 Redis"""
        redis = await self._get_redis()

        for chinese, aliases in DEFAULT_COLUMN_ALIASES.items():
            if not await redis.hexists("schema:column_aliases", chinese):
                await redis.hset("schema:column_aliases", chinese, ",".join(aliases))

        for chinese, aliases in DEFAULT_TABLE_ALIASES.items():
            if not await redis.hexists("schema:table_aliases", chinese):
                await redis.hset("schema:table_aliases", chinese, ",".join(aliases))

        logger.info("Initialized default aliases")

    async def get_column_aliases(self) -> Dict[str, List[str]]:
        redis = await self._get_redis()
        data = await redis.hgetall("schema:column_aliases")
        return {k: v.split(",") for k, v in data.items()} if data else DEFAULT_COLUMN_ALIASES

    async def get_table_aliases(self) -> Dict[str, List[str]]:
        redis = await self._get_redis()
        data = await redis.hgetall("schema:table_aliases")
        return {k: v.split(",") for k, v in data.items()} if data else DEFAULT_TABLE_ALIASES

    async def add_column_alias(self, chinese_name: str, aliases: List[str]):
        redis = await self._get_redis()
        await redis.hset("schema:column_aliases", chinese_name, ",".join(aliases))

    async def add_table_alias(self, chinese_name: str, aliases: List[str]):
        redis = await self._get_redis()
        await redis.hset("schema:table_aliases", chinese_name, ",".join(aliases))