"""
Workflow Executor — M1 最小集。

ExecutorRegistry 管理 4 种内置 Executor:
  skill  — 委托 SkillRegistry 执行已注册 Skill
  llm    — PromptRegistry.render() + LLM 调用
  guard  — SQL 安全校验
  sql    — SQL 执行

桥接: WorkflowExecutorSkill (@SkillRegistry.register)
  DefaultTaskExecutor 通过 SkillRegistry 查找 "workflow_executor"，
  WorkflowExecutorSkill 读取 payload["__executor__"] → ExecutorRegistry → 执行。
  Runtime 零改动。
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from app.agent.base import BaseSkill, SkillResult
from app.agent.registry import SkillRegistry

logger = logging.getLogger("workflow.executors")


# ═══════════════════════════════════════════════════════════════
#  ExecutorRegistry — 单例注册表
# ═══════════════════════════════════════════════════════════════

class ExecutorRegistry:
    """Executor 注册表。模块加载时自动注册 4 个内置 Executor。"""

    _executors: Dict[str, Any] = {}

    @classmethod
    def register(cls, name: str, executor: Any) -> None:
        cls._executors[name] = executor

    @classmethod
    def resolve(cls, name: str) -> Any:
        if name not in cls._executors:
            raise KeyError(
                f"Executor '{name}' not found. "
                f"Available: {list(cls._executors.keys())}"
            )
        return cls._executors[name]


# ═══════════════════════════════════════════════════════════════
#  Skill Executor — 委托 SkillRegistry
# ═══════════════════════════════════════════════════════════════

class SkillExecutor:
    """委托已注册 Skill 执行。

    payload:
        skill: str  — SkillRegistry 中的名称
        state: dict — 传给 skill.execute(state) 的参数
    """

    async def execute(self, payload: Dict[str, Any]) -> Any:
        skill_name = payload["skill"]
        state = payload.get("state", {})

        skill_cls = SkillRegistry.get_skill(skill_name)
        if skill_cls is None:
            raise ValueError(f"Skill '{skill_name}' not registered")

        from app.agent.runtime import SkillManager
        instance = SkillManager.get_instance(skill_name)
        if instance is None:
            instance = skill_cls()

        result = await instance.execute(state)
        if isinstance(result, SkillResult):
            if result.success:
                return result.data
            raise RuntimeError(result.error or f"Skill '{skill_name}' failed")
        return result


# ═══════════════════════════════════════════════════════════════
#  LLM Executor — PromptRegistry.render() + LLM
# ═══════════════════════════════════════════════════════════════

class LLMExecutor:
    """LLM 调用 Executor。

    两种模式（优先级从高到低）:
      1. messages 直传 — payload["messages"] 已是完整的 OpenAI messages 列表
         → 直接调用 LLM，不经过 PromptRegistry（Synthesizer 路径）
      2. prompt_id 渲染 — payload["prompt_id"] + prompt_variables
         → PromptRegistry.render() 后调用 LLM（Text2SQL / Summary 路径）

    payload:
        messages: list | None         — 完整 messages 列表（优先级最高）
        prompt_id: str | None         — PromptRegistry 模板 id
        prompt_variables: dict        — 模板变量
        model: str = "deepseek-chat"
        temperature: float = 0.1
        max_tokens: int = 1000
        system_prompt: str = ""
    """

    async def execute(self, payload: Dict[str, Any]) -> str:
        import os
        from openai import AsyncOpenAI

        # 模式 1: messages 直传（Synthesizer 已构建完整 messages）
        messages = payload.get("messages")
        if messages is not None:
            pass  # 直接使用
        else:
            # 模式 2: prompt_id 渲染（向后兼容）
            from app.services.prompt.registry import get_registry
            prompt_id = payload.get("prompt_id", "")
            variables = payload.get("prompt_variables", {})
            user_content = get_registry().render(prompt_id, **variables) if prompt_id else ""

            system_content = payload.get("system_prompt", "")
            messages = []
            if system_content:
                messages.append({"role": "system", "content": str(system_content)})
            messages.append({"role": "user", "content": user_content})

        client = AsyncOpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY", "sk-xxx"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        )
        response = await client.chat.completions.create(
            model=payload.get("model", "deepseek-chat"),
            messages=messages,
            temperature=payload.get("temperature", 0.1),
            max_tokens=payload.get("max_tokens", 1000),
        )
        return response.choices[0].message.content.strip()


# ═══════════════════════════════════════════════════════════════
#  Guard Executor — SQL 安全校验
# ═══════════════════════════════════════════════════════════════

class GuardExecutor:
    """SQL 安全校验。

    payload:
        sql: str             — 待校验 SQL
        allowed_tables: list — 允许的表名

    Returns:
        {"is_safe": bool, "sql": str, "error": str | None}
    """

    async def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        from app.services.text2sql.main import _validate_sql

        sql = payload["sql"]
        allowed_tables = payload.get("allowed_tables", [])

        try:
            validated = _validate_sql(sql, allowed_tables)
            return {"is_safe": True, "sql": validated, "error": None}
        except Exception as e:
            return {"is_safe": False, "sql": sql, "error": str(e)}


# ═══════════════════════════════════════════════════════════════
#  SQL Executor — SQL 执行
# ═══════════════════════════════════════════════════════════════

class SQLExecutor:
    """安全执行 SQL 并返回结果。

    payload:
        sql: str              — 要执行的 SQL
        allowed_tables: list  — 表白名单
        max_rows: int = 1000
    """

    async def execute(self, payload: Dict[str, Any]) -> list:
        from app.services.text2sql.main import safe_execute

        sql = payload["sql"]
        allowed_tables = payload.get("allowed_tables", [])
        max_rows = payload.get("max_rows", 1000)

        return safe_execute(sql, allowed_tables, max_rows)


# ═══════════════════════════════════════════════════════════════
#  注册
# ═══════════════════════════════════════════════════════════════

ExecutorRegistry.register("skill", SkillExecutor())
ExecutorRegistry.register("llm", LLMExecutor())
ExecutorRegistry.register("guard", GuardExecutor())
ExecutorRegistry.register("sql", SQLExecutor())


# ═══════════════════════════════════════════════════════════════
#  桥接 Skill — DefaultTaskExecutor → ExecutorRegistry
# ═══════════════════════════════════════════════════════════════

@SkillRegistry.register("workflow_executor")
class WorkflowExecutorSkill(BaseSkill):
    """桥接: SkillRegistry → ExecutorRegistry。

    TaskBuilder 创建的所有 Task 统一用 skill="workflow_executor"。
    DefaultTaskExecutor 通过 SkillRegistry 找到本 Skill，
    本 Skill 读取 payload["__executor__"] → ExecutorRegistry → 执行。
    """

    name = "workflow_executor"
    description = "Workflow Executor 桥接"

    async def execute(self, state: Dict[str, Any]) -> SkillResult:
        executor_name = state.get("__executor__")
        if not executor_name:
            return SkillResult(
                success=False, data=None,
                error="Missing '__executor__' in payload",
            )
        try:
            executor = ExecutorRegistry.resolve(executor_name)
            result = await executor.execute(state)
            return SkillResult(success=True, data=result)
        except Exception as e:
            logger.error(f"Executor '{executor_name}' failed: {e}")
            return SkillResult(success=False, data=None, error=str(e))
