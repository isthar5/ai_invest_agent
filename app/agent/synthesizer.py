"""
投研报告合成器 v2.0

v2.0 变更：
- 使用 PromptBuilder 统一构造 prompt（向后兼容旧接口）
- 支持接收 memory_context 参数
- 保留旧版 synthesize_financial_report() 作为 fallback
"""

import json
from openai import OpenAI, AuthenticationError
from app.config.settings import settings
from app.agent.prompt_builder import PromptBuilder, build_report_prompt


def synthesize_financial_report(
    skill_data: dict,
    memory_context: dict = None,
) -> str:
    """
    生成投研分析报告（v2 增强版）。

    Args:
        skill_data: 技能数据，包含 financial, quant, industry, fusion, insight
        memory_context: 记忆上下文（可选，用于 PromptBuilder）

    Returns:
        Markdown 格式的分析报告
    """
    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    # 使用 PromptBuilder 构造 report prompt
    report_prompt = build_report_prompt(skill_data)

    # 如果有 memory_context，使用 PromptBuilder 构建完整 messages
    if memory_context:
        messages = PromptBuilder.build_messages(
            query="请生成分析报告",
            memory_context=memory_context,
            rag_context="",
            quant_context="",
            recent_turns=3,
            include_summary=True,
            include_preferences=True,
        )
        # 将报告 prompt 追加到最后一条 user message
        for i in range(len(messages) - 1, -1, -1):
            if messages[i]["role"] == "user":
                messages[i] = {
                    "role": "user",
                    "content": f"{messages[i]['content']}\n\n{report_prompt}",
                }
                break
    else:
        # 无记忆上下文：使用简单的单条 user message（兼容旧版）
        messages = [
            {
                "role": "user",
                "content": report_prompt,
            }
        ]

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=2000,
        )
        return response.choices[0].message.content
    except AuthenticationError:
        return "报告生成失败：LLM 认证失败，请检查 API Key 配置。"
    except Exception as e:
        return f"报告生成失败: {e}"
