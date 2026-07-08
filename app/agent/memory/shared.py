"""
SharedAgentMemory — 跨 Agent 共享记忆 v1.0

职责：
- 提供 Agent 间的轻量级数据交换通道
- QuantAgent 写入量化结论 → RAGAgent/SQLAgent 读取以增强上下文
- 存储格式：Redis Hash at key `shared:{session_id}`

设计原则：
1. 写入即覆盖：每个 Agent 的最新数据覆盖旧数据（per-agent field）
2. 自动过期：TTL 24 小时，避免死数据堆积
3. 读写分离：写操作由各 Agent 自己触发，读操作统一由 PromptBuilder 归集
4. 异常安全：读写失败不影响 Agent 主流程

数据结构:
  shared:{session_id} → Hash
    quant:latest      → JSON {stock, score, signal, trend, conclusion, risk, timestamp}
    rag:latest        → JSON {sources, key_findings, timestamp}
    sql:latest        → JSON {sql, result_summary, timestamp}
    cross:latest      → JSON {consensus, conflicts, merged_conclusion, timestamp}
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import redis.asyncio as redis_asyncio
except ImportError:
    redis_asyncio = None

from .metrics import memory_latency, memory_hit

logger = logging.getLogger("agent.memory.shared")

# Shared Memory TTL（24 小时）
SHARED_MEMORY_TTL = 86400


class SharedAgentMemory:
    """
    跨 Agent 共享记忆。

    每个 Agent 有独立的 field，写入时覆盖自己的 field，
    读取时获取全部 fields 供 PromptBuilder 组装上下文。
    """

    REDIS_KEY_PREFIX = "shared"
    AGENT_QUANT = "quant"
    AGENT_RAG = "rag"
    AGENT_SQL = "sql"
    AGENT_CROSS = "cross"

    def __init__(
        self,
        ttl: int = SHARED_MEMORY_TTL,
        redis_url: str = "redis://localhost:6379",
    ):
        self.ttl = ttl
        self.redis = None
        if redis_asyncio is not None:
            try:
                self.redis = redis_asyncio.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.warning(f"SharedAgentMemory Redis 连接失败: {e}")

    def _key(self, session_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}:{session_id}"

    # ==================== 通用读写 ====================

    async def get_all(self, session_id: str) -> Dict[str, Any]:
        """
        获取所有 Agent 的共享数据。

        Returns:
            {
                "quant": {...},
                "rag": {...},
                "sql": {...},
                "cross": {...}
            }
        """
        with memory_latency.labels(operation="get_all", module="shared").time():
            try:
                if self.redis is None:
                    return {}

                data = await self.redis.hgetall(self._key(session_id))
                if not data:
                    return {}

                memory_hit.labels(module="shared").inc()

                result = {}
                for field, raw_json in data.items():
                    try:
                        result[field] = json.loads(raw_json)
                    except (json.JSONDecodeError, TypeError):
                        result[field] = raw_json

                return result
            except Exception as e:
                logger.error(f"SharedAgentMemory get_all 异常: {e}")
                return {}

    async def get_agent_data(
        self, session_id: str, agent_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取指定 Agent 的共享数据。

        Args:
            agent_name: "quant" | "rag" | "sql" | "cross"
        """
        with memory_latency.labels(operation="get_agent", module="shared").time():
            try:
                if self.redis is None:
                    return None

                raw = await self.redis.hget(self._key(session_id), agent_name)
                if raw:
                    memory_hit.labels(module="shared").inc()
                    return json.loads(raw)
                return None
            except Exception as e:
                logger.error(f"SharedAgentMemory get_agent({agent_name}) 异常: {e}")
                return None

    async def set_agent_data(
        self,
        session_id: str,
        agent_name: str,
        data: Dict[str, Any],
    ) -> bool:
        """
        写入指定 Agent 的共享数据，自动添加时间戳。

        Args:
            agent_name: "quant" | "rag" | "sql" | "cross"
            data: 任意可 JSON 序列化的字典
        """
        with memory_latency.labels(operation="set_agent", module="shared").time():
            try:
                if self.redis is None:
                    return False

                payload = {
                    **data,
                    "source_agent": agent_name,
                    "timestamp": datetime.now().isoformat(),
                }

                key = self._key(session_id)
                await self.redis.hset(
                    key, agent_name, json.dumps(payload, ensure_ascii=False)
                )
                await self.redis.expire(key, self.ttl)

                logger.debug(f"SharedAgentMemory: {agent_name} 写入共享数据")
                return True
            except Exception as e:
                logger.error(f"SharedAgentMemory set_agent({agent_name}) 异常: {e}")
                return False

    # ==================== 便捷方法 ====================

    async def write_quant_conclusion(
        self,
        session_id: str,
        stock: str,
        score: Optional[float] = None,
        signal: Optional[str] = None,
        trend: Optional[str] = None,
        conclusion: str = "",
        risk: Optional[str] = None,
    ) -> bool:
        """
        QuantAgent 写入量化分析结论。

        Args:
            stock: 股票代码
            score: 预测得分
            signal: 信号强度
            trend: 趋势方向
            conclusion: 分析结论文本
            risk: 风险提示
        """
        return await self.set_agent_data(
            session_id,
            self.AGENT_QUANT,
            {
                "stock": stock,
                "score": score,
                "signal": signal,
                "trend": trend,
                "conclusion": conclusion,
                "risk": risk,
            },
        )

    async def write_rag_findings(
        self,
        session_id: str,
        sources: List[str],
        key_findings: List[str],
    ) -> bool:
        """
        RAGAgent 写入检索发现。

        Args:
            sources: 来源文档列表
            key_findings: 关键发现列表
        """
        return await self.set_agent_data(
            session_id,
            self.AGENT_RAG,
            {
                "sources": sources,
                "key_findings": key_findings,
            },
        )

    async def write_sql_result(
        self,
        session_id: str,
        sql: str,
        result_summary: str,
    ) -> bool:
        """
        SQLAgent 写入查询结果摘要。

        Args:
            sql: 执行的 SQL
            result_summary: 结果摘要
        """
        return await self.set_agent_data(
            session_id,
            self.AGENT_SQL,
            {
                "sql": sql,
                "result_summary": result_summary,
            },
        )

    async def write_cross_conclusion(
        self,
        session_id: str,
        consensus: str = "",
        conflicts: List[str] = None,
        merged_conclusion: str = "",
    ) -> bool:
        """
        写入跨 Agent 融合结论。
        """
        return await self.set_agent_data(
            session_id,
            self.AGENT_CROSS,
            {
                "consensus": consensus,
                "conflicts": conflicts or [],
                "merged_conclusion": merged_conclusion,
            },
        )

    # ==================== 便捷读取 ====================

    async def get_quant_conclusion(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.get_agent_data(session_id, self.AGENT_QUANT)

    async def get_rag_findings(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.get_agent_data(session_id, self.AGENT_RAG)

    async def get_sql_result(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.get_agent_data(session_id, self.AGENT_SQL)

    async def get_cross_conclusion(self, session_id: str) -> Optional[Dict[str, Any]]:
        return await self.get_agent_data(session_id, self.AGENT_CROSS)

    # ==================== 格式化（供 PromptBuilder 使用）====================

    @classmethod
    def format_for_prompt(cls, shared_data: Dict[str, Any]) -> str:
        """
        将共享记忆格式化为 Prompt 可注入的文本。

        Args:
            shared_data: get_all() 的返回值

        Returns:
            格式化的字符串，可直接注入 system/user prompt
        """
        if not shared_data:
            return ""

        sections = ["【跨 Agent 共享上下文】"]

        # Quant 结论
        quant = shared_data.get("quant", {})
        if quant:
            parts = []
            stock = quant.get("stock", "")
            if stock:
                parts.append(f"关注股票: {stock}")
            signal = quant.get("signal", "")
            if signal:
                parts.append(f"量化信号: {signal}")
            trend = quant.get("trend", "")
            if trend:
                parts.append(f"趋势: {trend}")
            conclusion = quant.get("conclusion", "")
            if conclusion:
                parts.append(f"量化结论: {conclusion}")
            risk = quant.get("risk", "")
            if risk:
                parts.append(f"风险: {risk}")
            if parts:
                sections.append("  [QuantAgent] " + " | ".join(parts))

        # RAG 发现
        rag = shared_data.get("rag", {})
        if rag:
            findings = rag.get("key_findings", [])
            if findings:
                sections.append(f"  [RAGAgent] 关键发现: {'; '.join(findings[:3])}")

        # SQL 结果
        sql = shared_data.get("sql", {})
        if sql:
            summary = sql.get("result_summary", "")
            if summary:
                sections.append(f"  [SQLAgent] 查询摘要: {summary}")

        # 跨 Agent 融合
        cross = shared_data.get("cross", {})
        if cross:
            merged = cross.get("merged_conclusion", "")
            if merged:
                sections.append(f"  [CrossFusion] 融合结论: {merged}")

        if len(sections) == 1:
            return ""  # 只有标题，没有实质内容

        return "\n".join(sections) + "\n"

    # ==================== 生命周期 ====================

    async def clear(self, session_id: str) -> bool:
        """清除会话的共享记忆"""
        with memory_latency.labels(operation="clear", module="shared").time():
            try:
                if self.redis is None:
                    return False
                await self.redis.delete(self._key(session_id))
                return True
            except Exception as e:
                logger.error(f"SharedAgentMemory clear 异常: {e}")
                return False
