"""
SummaryMemory — 会话摘要记忆 v1.0

职责：
- 每 N 轮（默认 10 轮）自动触发 LLM 摘要
- 保存长期主题、关键分析结论、用户关注股票、待解决问题
- 摘要控制在 300 字以内
- 存储格式：Redis Hash（key=summary:{session_id}）

设计原则：
1. 异步非阻塞：摘要生成失败不影响主流程
2. 渐进积累：新摘要与旧摘要合并，保留长期重要信息
3. 自动过期：TTL 30 天，与 LongTermMemory 保持一致
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

logger = logging.getLogger("agent.memory.summarizer")

# 摘要触发间隔（轮次）
SUMMARY_TRIGGER_INTERVAL = 10

# 摘要最大字数
SUMMARY_MAX_CHARS = 300


class SummaryMemory:
    """
    工业级会话摘要记忆。

    Redis 结构: Hash at key `summary:{session_id}`
      Fields:
        - summary_text: str          (最近摘要文本)
        - long_term_themes: JSON     (长期关注主题列表)
        - key_conclusions: JSON      (关键分析结论列表)
        - watched_stocks: JSON       (用户关注股票列表)
        - pending_questions: JSON    (待解决问题列表)
        - turn_count: int            (累计轮次)
        - last_summarized_at: str    (上次摘要时间 ISO)
        - created_at: str            (创建时间 ISO)
    """

    REDIS_KEY_PREFIX = "summary"

    def __init__(
        self,
        ttl: int = 2592000,  # 30 天
        redis_url: str = "redis://localhost:6379",
        trigger_interval: int = SUMMARY_TRIGGER_INTERVAL,
        max_chars: int = SUMMARY_MAX_CHARS,
    ):
        self.ttl = ttl
        self.trigger_interval = trigger_interval
        self.max_chars = max_chars
        self.redis = None
        if redis_asyncio is not None:
            try:
                self.redis = redis_asyncio.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.warning(f"SummaryMemory Redis 连接失败: {e}")

    def _key(self, session_id: str) -> str:
        return f"{self.REDIS_KEY_PREFIX}:{session_id}"

    # ==================== 公共 API ====================

    async def get(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        获取会话摘要。
        返回 None 表示尚无摘要。
        """
        with memory_latency.labels(operation="get", module="summarizer").time():
            try:
                if self.redis is None:
                    return None
                data = await self.redis.hgetall(self._key(session_id))
                if not data:
                    return None

                memory_hit.labels(module="summarizer").inc()

                return {
                    "summary_text": data.get("summary_text", ""),
                    "long_term_themes": self._parse_json_list(data.get("long_term_themes", "[]")),
                    "key_conclusions": self._parse_json_list(data.get("key_conclusions", "[]")),
                    "watched_stocks": self._parse_json_list(data.get("watched_stocks", "[]")),
                    "pending_questions": self._parse_json_list(data.get("pending_questions", "[]")),
                    "turn_count": int(data.get("turn_count", "0")),
                    "last_summarized_at": data.get("last_summarized_at", ""),
                    "created_at": data.get("created_at", ""),
                }
            except Exception as e:
                logger.error(f"SummaryMemory get 异常: {e}")
                return None

    async def increment_turn(self, session_id: str) -> int:
        """
        增加轮次计数，返回当前轮次。
        如果达到触发间隔，返回负值表示需要触发摘要。
        """
        with memory_latency.labels(operation="increment", module="summarizer").time():
            try:
                if self.redis is None:
                    return 0

                key = self._key(session_id)
                current = await self.redis.hget(key, "turn_count")
                current = int(current) if current else 0
                new_count = current + 1

                await self.redis.hset(key, "turn_count", str(new_count))
                await self.redis.expire(key, self.ttl)

                return new_count
            except Exception as e:
                logger.error(f"SummaryMemory increment_turn 异常: {e}")
                return 0

    async def should_summarize(self, session_id: str) -> bool:
        """检查是否应该触发摘要"""
        count = await self.increment_turn(session_id)
        return count > 0 and count % self.trigger_interval == 0

    async def save_summary(
        self,
        session_id: str,
        summary_data: Dict[str, Any],
        llm_client=None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        保存摘要数据到 Redis。

        Args:
            session_id: 会话 ID
            summary_data: 新摘要数据（可能来自 LLM 生成或手动构造）
            llm_client: 可选，用于 LLM 生成摘要
            recent_history: 可选，最近对话历史（用于 LLM 生成）
        """
        with memory_latency.labels(operation="save", module="summarizer").time():
            try:
                if self.redis is None:
                    return False

                # 如果有 LLM 客户端和历史，调用 LLM 生成摘要
                if llm_client and recent_history:
                    generated = await self._generate_summary_with_llm(
                        llm_client, recent_history
                    )
                    if generated:
                        summary_data = generated

                key = self._key(session_id)

                # 获取现有数据以做合并
                existing = await self.get(session_id) or {}

                # 合并长期数据（去重）
                mapping = {
                    "summary_text": summary_data.get("summary_text", ""),
                    "long_term_themes": self._merge_list(
                        existing.get("long_term_themes", []),
                        summary_data.get("long_term_themes", []),
                    ),
                    "key_conclusions": self._merge_list(
                        existing.get("key_conclusions", []),
                        summary_data.get("key_conclusions", []),
                        max_items=10,
                    ),
                    "watched_stocks": self._merge_list(
                        existing.get("watched_stocks", []),
                        summary_data.get("watched_stocks", []),
                    ),
                    "pending_questions": self._merge_list(
                        existing.get("pending_questions", []),
                        summary_data.get("pending_questions", []),
                        max_items=5,
                    ),
                    "last_summarized_at": datetime.now().isoformat(),
                }

                # 只在首次创建时设置 created_at
                if not existing.get("created_at"):
                    mapping["created_at"] = datetime.now().isoformat()

                # 批量写入
                pipe = self.redis.pipeline()
                for field, value in mapping.items():
                    if isinstance(value, list):
                        value = json.dumps(value, ensure_ascii=False)
                    pipe.hset(key, field, str(value) if value is not None else "")
                await pipe.execute()
                await self.redis.expire(key, self.ttl)

                logger.info(
                    f"SummaryMemory: 已保存摘要 session={session_id}, "
                    f"themes={len(mapping.get('long_term_themes', []))}, "
                    f"conclusions={len(mapping.get('key_conclusions', []))}, "
                    f"stocks={mapping.get('watched_stocks', [])}"
                )
                return True
            except Exception as e:
                logger.error(f"SummaryMemory save_summary 异常: {e}")
                return False

    async def update_from_turn(
        self,
        session_id: str,
        query: str,
        answer: str,
        stocks: Optional[List[str]] = None,
        llm_client=None,
        recent_history: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """
        每轮对话后更新摘要。自动判断是否需要触发 LLM 摘要。

        Returns:
            True 如果触发了摘要生成
        """
        should = await self.should_summarize(session_id)
        if not should:
            # 仍然更新 watched_stocks（增量）
            await self._add_stocks(session_id, stocks or [])
            return False

        # 触发摘要
        summary_data = await self._extract_summary_from_turn(query, answer, stocks)
        if llm_client and recent_history:
            await self.save_summary(
                session_id,
                summary_data,
                llm_client=llm_client,
                recent_history=recent_history,
            )
        else:
            await self.save_summary(session_id, summary_data)

        return True

    async def clear(self, session_id: str) -> bool:
        """清除会话摘要"""
        with memory_latency.labels(operation="clear", module="summarizer").time():
            try:
                if self.redis is None:
                    return False
                await self.redis.delete(self._key(session_id))
                return True
            except Exception as e:
                logger.error(f"SummaryMemory clear 异常: {e}")
                return False

    # ==================== 内部方法 ====================

    async def _add_stocks(self, session_id: str, stocks: List[str]):
        """增量添加关注股票"""
        if not stocks or self.redis is None:
            return
        try:
            key = self._key(session_id)
            existing_raw = await self.redis.hget(key, "watched_stocks") or "[]"
            existing = self._parse_json_list(existing_raw)
            merged = self._merge_list(existing, stocks)
            await self.redis.hset(key, "watched_stocks", json.dumps(merged, ensure_ascii=False))
        except Exception:
            pass

    async def _generate_summary_with_llm(
        self,
        llm_client,
        recent_history: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """调用 LLM 生成结构化摘要"""
        try:
            history_text = "\n".join([
                f"Q: {h.get('query', '')}\nA: {h.get('answer', '')[:200]}"
                for h in recent_history[-self.trigger_interval:]
            ])

            prompt = f"""基于以下对话历史，生成结构化摘要（JSON格式）。

要求：
1. summary_text: 不超过 {self.max_chars} 字
2. long_term_themes: 识别长期关注主题（数组）
3. key_conclusions: 提取关键分析结论（数组，最多3条）
4. watched_stocks: 提取讨论到的股票代码（数组）
5. pending_questions: 识别尚未解决的问题（数组，最多2条）

对话历史：
{history_text}

输出 JSON：
{{"summary_text": "...", "long_term_themes": [...], "key_conclusions": [...], "watched_stocks": [...], "pending_questions": [...]}}"""

            response = await llm_client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
                max_tokens=500,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            return result
        except Exception as e:
            logger.warning(f"SummaryMemory LLM 摘要生成失败: {e}")
            return None

    async def _extract_summary_from_turn(
        self,
        query: str,
        answer: str,
        stocks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """从当前轮次提取摘要数据（无 LLM 模式）"""
        # 基础规则提取
        themes = []
        conclusions = []

        # 从 query 推断主题
        theme_keywords = {
            "财务分析": ["财报", "年报", "营收", "利润", "ROE", "毛利率"],
            "量化信号": ["走势", "信号", "预测", "趋势", "量化"],
            "行业对标": ["行业", "对比", "竞争对手", "排名"],
            "结构化查询": ["SQL", "查询", "历年", "历史数据"],
        }
        for theme, keywords in theme_keywords.items():
            if any(k in query for k in keywords):
                themes.append(theme)

        # 从 answer 提取关键结论（简化版：取前 100 字）
        if answer:
            conclusions.append(answer[:100].replace("\n", " ").strip())

        return {
            "summary_text": f"讨论主题：{'、'.join(themes) if themes else '综合咨询'}。"
                           f"涉及股票：{'、'.join(stocks) if stocks else '未明确'}。",
            "long_term_themes": themes,
            "key_conclusions": conclusions,
            "watched_stocks": stocks or [],
            "pending_questions": [],
        }

    @staticmethod
    def _parse_json_list(raw: str) -> List[str]:
        """安全解析 JSON 列表"""
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return [str(x) for x in parsed]
            return []
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _merge_list(
        existing: List[str],
        new: List[str],
        max_items: int = 20,
    ) -> List[str]:
        """合并列表，去重，保留最近添加的在前面"""
        seen = set()
        merged = []
        for item in new + existing:
            if item and item not in seen:
                seen.add(item)
                merged.append(item)
        return merged[:max_items]
