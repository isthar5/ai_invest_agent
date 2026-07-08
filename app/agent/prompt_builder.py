"""
PromptBuilder — 工业级 Prompt 构造器 v2.0

v2.0 变更：
- 所有 Prompt 模板从 PromptRegistry 读取（不再硬编码）
- class-level 常量改为 PromptProperty 描述符
- build_report_prompt() 静态部分从 Registry 加载
- 对外接口 100% 保持兼容

职责：
- 统一构造 OpenAI messages 格式
- 注入 system prompt / conversation summary / 最近 N 轮历史 / 用户偏好 / RAG 上下文
- 与 ContextManager 协作实现动态 token 管理
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.prompt.registry import PromptProperty, get_registry

logger = logging.getLogger("agent.prompt_builder")

CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
CURRENT_YEAR = datetime.now().year


class PromptBuilder:
    """工业级 Prompt 构造器（Registry 薄封装）"""

    # ── System Prompt（从 Registry 实时读取）──

    DEFAULT_SYSTEM_PROMPT = PromptProperty(
        "agent.system_prompt",
        current_date=CURRENT_DATE,
        current_year=CURRENT_YEAR,
    )

    SYSTEM_PROMPT_COMPACT = PromptProperty(
        "agent.system_prompt_compact",
        current_date=CURRENT_DATE,
        current_year=CURRENT_YEAR,
    )

    SYSTEM_PROMPT_EXTRACTION = PromptProperty("agent.extraction")

    SYSTEM_PROMPT_SQL = PromptProperty("agent.text2sql")

    @classmethod
    def build_messages(
        cls,
        query: str,
        memory_context: Optional[Dict[str, Any]] = None,
        rag_context: str = "",
        quant_context: str = "",
        system_prompt: Optional[str] = None,
        recent_turns: int = 5,
        include_summary: bool = True,
        include_preferences: bool = True,
        include_history: bool = True,
    ) -> List[Dict[str, str]]:
        """
        构造标准的 OpenAI chat messages。

        Args:
            query: 当前用户问题
            memory_context: 记忆上下文，包含 recent_history, user_preferences, summary
            rag_context: RAG 检索到的文档上下文（已格式化）
            quant_context: 量化信号上下文（已格式化）
            system_prompt: 自定义 system prompt（None 则使用默认）
            recent_turns: 注入最近 N 轮对话历史
            include_summary: 是否注入对话摘要
            include_preferences: 是否注入用户偏好
            include_history: 是否注入对话历史

        Returns:
            OpenAI messages 格式: [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]
        """
        memory_context = memory_context or {}
        messages: List[Dict[str, str]] = []

        # ===== 1. System Message =====
        sys_prompt = system_prompt or cls.DEFAULT_SYSTEM_PROMPT

        # 注入对话摘要
        summary_text = ""
        if include_summary:
            summary_text = cls._build_summary_section(memory_context)

        # 注入用户偏好
        preferences_text = ""
        if include_preferences:
            preferences_text = cls._build_preferences_section(memory_context)

        # 组装 system prompt
        if summary_text or preferences_text:
            sys_prompt = f"{sys_prompt}\n\n{summary_text}{preferences_text}".strip()

        messages.append({"role": "system", "content": sys_prompt})

        # ===== 2. 注入历史对话（作为 user/assistant 交替消息）=====
        if include_history:
            history_messages = cls._build_history_messages(memory_context, recent_turns)
            messages.extend(history_messages)

        # ===== 3. 当前 User Message =====
        user_content = cls._build_user_content(query, rag_context, quant_context)
        messages.append({"role": "user", "content": user_content})

        # ===== 4. 日志 =====
        total_chars = sum(len(m.get("content", "")) for m in messages)
        logger.info(
            f"PromptBuilder: {len(messages)} messages, "
            f"{total_chars} chars, "
            f"summary={bool(summary_text)}, prefs={bool(preferences_text)}, "
            f"history_turns={recent_turns if include_history else 0}"
        )

        return messages

    @classmethod
    def build_simple_user_message(
        cls,
        query: str,
        context_data: Dict[str, Any],
        instruction: str = "",
    ) -> List[Dict[str, str]]:
        """
        构造简洁的单轮 user message（用于 Skill 内部的 LLM 调用）。

        Args:
            query: 用户问题
            context_data: 结构化数据字典
            instruction: 额外指令
        """
        parts = []
        if query:
            parts.append(f"【用户问题】\n{query}")
        for key, value in context_data.items():
            if value:
                label = cls._label_for_key(key)
                formatted = (
                    json.dumps(value, ensure_ascii=False, indent=2)
                    if isinstance(value, (dict, list))
                    else str(value)
                )
                parts.append(f"【{label}】\n{formatted}")
        if instruction:
            parts.append(instruction)

        return [{"role": "user", "content": "\n\n".join(parts)}]

    # ==================== 内部构造方法 ====================

    @classmethod
    def _build_summary_section(cls, memory_context: Dict[str, Any]) -> str:
        """构造对话摘要注入文本"""
        summary = memory_context.get("summary", "")
        if not summary:
            return ""

        # summary 可能是 dict（SummaryMemory 结构）或 str
        if isinstance(summary, dict):
            parts = ["【会话摘要】"]
            themes = summary.get("long_term_themes", [])
            if themes:
                parts.append(f"长期关注主题：{'、'.join(themes)}")
            conclusions = summary.get("key_conclusions", [])
            if conclusions:
                parts.append(f"关键分析结论：{'；'.join(conclusions[:3])}")
            stocks = summary.get("watched_stocks", [])
            if stocks:
                parts.append(f"用户关注股票：{'、'.join(stocks)}")
            pending = summary.get("pending_questions", [])
            if pending:
                parts.append(f"待解决问题：{'；'.join(pending[-3:])}")
            summary_str = summary.get("summary_text", "")
            if summary_str:
                parts.append(f"摘要：{summary_str}")
            return "\n".join(parts) + "\n"
        else:
            return f"【会话摘要】\n{str(summary)}\n"

    @classmethod
    def _build_preferences_section(cls, memory_context: Dict[str, Any]) -> str:
        """构造用户偏好注入文本"""
        preferences = memory_context.get("user_preferences", {})
        if not preferences:
            return ""

        prefs_lines = ["【用户偏好】"]
        for k, v in preferences.items():
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    pass
            prefs_lines.append(f"- {k}: {v}")

        return "\n".join(prefs_lines) + "\n" if len(prefs_lines) > 1 else ""

    @classmethod
    def _build_history_messages(
        cls, memory_context: Dict[str, Any], max_turns: int = 5
    ) -> List[Dict[str, str]]:
        """
        将对话历史转换为 user/assistant 交替的 messages。

        历史格式: [{"query": "...", "answer": "...", "timestamp": "..."}, ...]
        转换为: [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
        """
        recent_history = memory_context.get("recent_history", [])
        if not recent_history:
            return []

        # 取最近 N 轮，反转顺序（最老的在前）
        turns = list(reversed(recent_history[-max_turns:]))
        messages = []
        for turn in turns:
            if isinstance(turn, dict):
                q = turn.get("query", "")
                a = turn.get("answer", "")
                if q:
                    messages.append({"role": "user", "content": q})
                if a:
                    # 截断过长的历史回答，避免挤占上下文
                    truncated = a[:500] + "..." if len(a) > 500 else a
                    messages.append({"role": "assistant", "content": truncated})

        return messages

    @classmethod
    def _build_user_content(
        cls, query: str, rag_context: str = "", quant_context: str = ""
    ) -> str:
        """构造最终的 user message 内容"""
        parts = [f"【用户问题】\n{query}"]

        if rag_context:
            parts.append(f"【研报上下文】\n{rag_context}")

        if quant_context:
            parts.append(f"【量化信号】\n{quant_context}")

        if rag_context or quant_context:
            parts.append("请结合以上信息给出专业分析：")
        else:
            parts.append("请给出专业分析：")

        return "\n\n".join(parts)

    @classmethod
    def _label_for_key(cls, key: str) -> str:
        """将 key 映射为中文标签"""
        mapping = {
            "financial": "财报数据",
            "quant": "量化信号",
            "industry": "行业对标",
            "docs_text": "研报内容",
            "peers": "同行数据",
            "fusion": "融合研判",
            "insight": "AI 初步洞察",
            "query": "用户问题",
            "stock": "股票代码",
            "docs": "相关文档",
        }
        return mapping.get(key, key)


def build_report_prompt(enriched_data: Dict[str, Any]) -> str:
    """
    构造投研报告生成的 prompt（兼容旧版 synthesizer 的直接字符串 prompt 模式）。

    静态部分（角色定义 + 报告结构）从 PromptRegistry 加载，
    动态数据（financial/quant/industry/fusion）仍然由函数拼接。

    Registry 内置所有 10 个 Prompt 的 fallback，不再需要消费者自行兜底。
    """
    registry = get_registry()
    financial = enriched_data.get("financial", {})
    quant = enriched_data.get("quant", {})
    industry = enriched_data.get("industry", {})
    fusion = enriched_data.get("fusion", {})
    insight = enriched_data.get("insight", "")

    system_role = registry.get("report.system_role").template
    report = registry.render(
        "report.structure",
        financial_json=json.dumps(financial, ensure_ascii=False, indent=2),
        quant_json=json.dumps(quant, ensure_ascii=False, indent=2),
        industry_json=json.dumps(industry, ensure_ascii=False, indent=2),
        insight_text=insight,
        signal_type=fusion.get("signal_type", "未知"),
        confidence=fusion.get("confidence", "未知"),
        reasoning=fusion.get("reasoning", "未知"),
        risk_factors=", ".join(fusion.get("risk_factors", ["未知"])),
    )

    return f"{system_role}\n\n{report}"
