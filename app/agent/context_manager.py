"""
ContextManager — 上下文窗口管理 v1.0

职责：
- Token 统计（tiktoken 为主，字符估算为 fallback）
- 动态裁剪上下文，确保不超过 target_tokens
- 优先级保留顺序：Summary > User Query > Recent History > RAG Context

设计原则：
1. 不丢核心信息：Summary 和 User Query 永远优先保留
2. 渐进裁剪：依次缩短 RAG、历史、偏好，而非一次性截断
3. 可配置：target_tokens 可通过环境变量 CONTEXT_MAX_TOKENS 调整
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("agent.context_manager")

# 默认目标 token 数（8000 = system(~640) + history(~2000) + RAG(~3200) + query(~1200) + summary(~640) + prefs(~320)）
DEFAULT_MAX_TOKENS = 8000

# 尝试加载 tiktoken，失败则用字符估算
try:
    import tiktoken

    _ENCODER = tiktoken.get_encoding("cl100k_base")  # DeepSeek 与之兼容

    def count_tokens(text: str) -> int:
        """精确 token 计数（tiktoken）"""
        if not text:
            return 0
        try:
            return len(_ENCODER.encode(text))
        except Exception:
            return _char_estimate(text)

    _HAS_TIKTOKEN = True
except ImportError:
    _ENCODER = None
    _HAS_TIKTOKEN = False

    def count_tokens(text: str) -> int:
        """字符估算 token 数（中文字符 ≈ 1.5 token，英文 ≈ 0.25 token/char）"""
        return _char_estimate(text)


def _char_estimate(text: str) -> int:
    """基于字符的 token 估算（fallback）"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if "一" <= c <= "鿿")
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5 + other_chars * 0.25)


class ContextManager:
    """
    上下文窗口管理器。

    裁剪优先级（从低到高，优先裁剪低优先级内容）:
      4 (最低) → RAG Context
      3       → Recent History（从老到新）
      2       → User Preferences
      1 (最高) → User Query
      0 (最高) → Summary
    """

    # 各区域 token 预算比例（在总预算中的占比）
    BUDGET_RATIOS = {
        "summary": 0.08,         # 8%
        "user_preferences": 0.04, # 4%
        "user_query": 0.15,       # 15%
        "recent_history": 0.25,   # 25%
        "rag_context": 0.40,      # 40%
        "system_prompt": 0.08,    # 8%
    }

    def __init__(self, max_tokens: int = DEFAULT_MAX_TOKENS):
        self.max_tokens = max_tokens
        self._tokenizer_name = "tiktoken(cl100k_base)" if _HAS_TIKTOKEN else "char_estimate"

    # ==================== 公共 API ====================

    def fit_messages(
        self,
        messages: List[Dict[str, str]],
        rag_context: str = "",
        quant_context: str = "",
    ) -> List[Dict[str, str]]:
        """
        确保 messages 的 token 总数不超过 max_tokens。

        策略：
        1. 先计算当前总 token 数
        2. 如果已超标，按优先级从低到高裁剪
        3. 返回裁剪后的 messages

        Args:
            messages: OpenAI 格式的消息列表
            rag_context: RAG 检索上下文（已嵌入 user message 中）
            quant_context: 量化信号上下文（已嵌入 user message 中）

        Returns:
            裁剪后的 messages
        """
        total = self._count_messages(messages)
        if total <= self.max_tokens:
            logger.debug(f"ContextManager: {total}/{self.max_tokens} tokens — 无需裁剪")
            return messages

        logger.info(f"ContextManager: {total}/{self.max_tokens} tokens — 开始裁剪")

        # 裁剪后的 messages（在原列表上操作副本）
        trimmed = [dict(m) for m in messages]

        # 策略：从 user message 中逐步缩短 RAG 上下文
        trimmed = self._trim_rag_from_user_message(trimmed, rag_context, total)

        # 如果还不够，裁剪 assistant 历史回答长度
        total_after = self._count_messages(trimmed)
        if total_after > self.max_tokens:
            trimmed = self._trim_history_answers(trimmed)

        # 如果还不够，移除最早的历史轮次
        total_after = self._count_messages(trimmed)
        if total_after > self.max_tokens:
            trimmed = self._trim_history_turns(trimmed)

        # 最后手段：裁剪 system prompt 中的偏好部分
        total_after = self._count_messages(trimmed)
        if total_after > self.max_tokens:
            trimmed = self._trim_system_prompt(trimmed)

        final_total = self._count_messages(trimmed)
        logger.info(
            f"ContextManager: 裁剪完成 {total} → {final_total}/{self.max_tokens} tokens "
            f"(节省 {total - final_total} tokens)"
        )
        return trimmed

    def estimate_tokens(self, text: str) -> int:
        """估算单个文本的 token 数"""
        return count_tokens(text)

    def get_budget_allocations(self) -> Dict[str, int]:
        """返回各区域 token 预算"""
        return {
            region: int(self.max_tokens * ratio)
            for region, ratio in self.BUDGET_RATIOS.items()
        }

    def get_usage_report(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """生成上下文使用报告"""
        total = self._count_messages(messages)
        per_message = [
            {"role": m["role"], "tokens": count_tokens(m.get("content", ""))}
            for m in messages
        ]
        return {
            "total_tokens": total,
            "max_tokens": self.max_tokens,
            "utilization": round(total / self.max_tokens, 4) if self.max_tokens > 0 else 0,
            "per_message": per_message,
            "tokenizer": self._tokenizer_name,
        }

    # ==================== 裁剪策略 ====================

    def _trim_rag_from_user_message(
        self,
        messages: List[Dict[str, str]],
        rag_context: str,
        current_total: int,
    ) -> List[Dict[str, str]]:
        """裁剪 user message 中的 RAG 上下文"""
        excess = current_total - self.max_tokens
        if excess <= 0:
            return messages

        for i, msg in enumerate(messages):
            if msg["role"] != "user":
                continue

            content = msg["content"]

            # 定位 RAG 上下文区域
            rag_marker = "【研报上下文】"
            idx = content.find(rag_marker)
            if idx == -1:
                continue

            # 找到 RAG 区域的结束位置（下一个【】标记）
            rest = content[idx + len(rag_marker):]
            next_marker_idx = rest.find("\n【")
            if next_marker_idx == -1:
                next_marker_idx = len(rest)

            rag_part = rest[:next_marker_idx]
            after_rag = rest[next_marker_idx:]

            # 计算需要缩减的 token 数
            rag_tokens = count_tokens(rag_part)
            target_rag_tokens = max(500, rag_tokens - excess)  # 至少保留 500 tokens

            trimmed_rag = self._trim_text_to_tokens(rag_part, target_rag_tokens)
            new_content = content[:idx + len(rag_marker)] + trimmed_rag + after_rag
            messages[i] = {**msg, "content": new_content}

            # 检查是否已足够
            if self._count_messages(messages) <= self.max_tokens:
                break

        return messages

    def _trim_history_answers(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """缩短 assistant 回答的长度"""
        excess = self._count_messages(messages) - self.max_tokens
        if excess <= 0:
            return messages

        # 找所有 assistant 消息，按从新到老排序（保留最新的更完整）
        assistant_indices = [
            i for i, m in enumerate(messages) if m["role"] == "assistant"
        ]
        # 从最老的开始缩短
        for i in assistant_indices:
            content = messages[i]["content"]
            current_tokens = count_tokens(content)
            target_tokens = max(100, current_tokens - (excess // len(assistant_indices)) - 1)
            trimmed = self._trim_text_to_tokens(content, target_tokens)
            messages[i] = {**messages[i], "content": trimmed}

            if self._count_messages(messages) <= self.max_tokens:
                break

        return messages

    def _trim_history_turns(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """移除最早的历史对话轮次（一次移除一对 user+assistant）"""
        # 找到 system 消息之后的第一对 user/assistant（即最早的历史轮次）
        # 系统消息、历史消息、当前 user 消息的排列：
        # [system, user_old, assistant_old, ..., user_current]
        # 移除最早的非当前 user 和紧随的 assistant

        while self._count_messages(messages) > self.max_tokens:
            # 找最后一对历史对话（system 之后、当前 user 之前的 user+assistant）
            removed = False
            for i in range(1, len(messages) - 1):  # 跳过 system(0) 和最后一个 user
                if messages[i]["role"] == "user" and i + 1 < len(messages) - 1:
                    # 这是一对历史消息，移除它们
                    messages.pop(i + 1)  # 先移除 assistant
                    messages.pop(i)       # 再移除 user
                    removed = True
                    break

            if not removed:
                break  # 没有可移除的历史轮次了

        return messages

    def _trim_system_prompt(self, messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """裁剪 system prompt 中的非核心内容"""
        excess = self._count_messages(messages) - self.max_tokens
        if excess <= 0 or not messages:
            return messages

        content = messages[0].get("content", "")
        # 尝试移除偏好部分
        pref_marker = "【用户偏好】"
        idx = content.find(pref_marker)
        if idx != -1:
            # 找到偏好部分的结尾
            end_idx = content.find("\n\n", idx + len(pref_marker))
            if end_idx == -1:
                end_idx = len(content)
            new_content = content[:idx] + content[end_idx:]
            messages[0] = {**messages[0], "content": new_content.strip()}

        return messages

    # ==================== 工具方法 ====================

    def _count_messages(self, messages: List[Dict[str, str]]) -> int:
        """计算 messages 的总 token 数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            total += count_tokens(content)
            # 每条消息有 overhead（role token + formatting）
            total += 4
        return total

    def _trim_text_to_tokens(self, text: str, max_tokens: int) -> str:
        """
        将文本裁剪到指定 token 数以内。
        从末尾开始裁剪，保留开头（最重要的信息通常在前面）。
        """
        if not text or max_tokens <= 0:
            return ""

        current = count_tokens(text)
        if current <= max_tokens:
            return text

        # 二分查找最佳截断点
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if count_tokens(text[:mid]) <= max_tokens:
                lo = mid
            else:
                hi = mid - 1

        return text[:lo] + "\n...(内容已压缩)"


# 全局单例
_context_manager: Optional[ContextManager] = None


def get_context_manager(max_tokens: int = DEFAULT_MAX_TOKENS) -> ContextManager:
    """获取 ContextManager 单例"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager(max_tokens=max_tokens)
    return _context_manager


def reset_context_manager(max_tokens: int = DEFAULT_MAX_TOKENS) -> ContextManager:
    """重置 ContextManager 单例（用于测试）"""
    global _context_manager
    _context_manager = ContextManager(max_tokens=max_tokens)
    return _context_manager
