"""
M2 — VariableResolver / InputResolver / RetryBuilder / TimeoutBuilder。

VariableResolver: 解析 ${params.x} / ${tasks.a.output.b} / ${env.X} / ${const.x}
InputResolver:    解析整个 task config dict 中的变量引用
RetryBuilder:     YAML retry 配置 → RetryPolicy
TimeoutBuilder:   超时字符串 → float 秒数
VarContext:       变量上下文（params / tasks / env / const）

Usage:
    from app.workflow.resolver import (
        VariableResolver, InputResolver,
        RetryBuilder, TimeoutBuilder, VarContext,
    )

    resolver = VariableResolver()
    ctx = VarContext(params={"question": "..."}, tasks={"schema_link": {"output": {...}}})
    resolved = resolver.resolve("${params.question}", ctx)         # → "..."
    resolved = resolver.resolve("${tasks.schema_link.output.tables}", ctx)  # → [...]
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from app.runtime.retry import RetryPolicy

logger = logging.getLogger("workflow.resolver")

# ── 正则：匹配 ${...} 引用 ──────────────────────────────────
_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

# M1 兼容占位符
_RUNTIME_PLACEHOLDER = "__FROM_RUNTIME__"

# ── 时间单位映射 ───────────────────────────────────────────
_TIME_UNITS: Dict[str, float] = {
    "ms": 0.001,
    "s": 1.0,
    "sec": 1.0,
    "m": 60.0,
    "min": 60.0,
    "h": 3600.0,
    "hour": 3600.0,
}


# ═══════════════════════════════════════════════════════════════
#  VarContext — 变量查找上下文
# ═══════════════════════════════════════════════════════════════

class VarContext:
    """变量解析上下文。

    分层查找（优先级从高到低）:
      1. tasks  — 上游 task 的输出（运行时填充）
      2. params — workflow 调用参数
      3. const  — workflow 常量（YAML 中定义）
      4. env    — 环境变量（os.environ）

    Attributes:
        params: 运行时参数字典。
        tasks: 已完成的 task 输出 {task_id: {"output": result}}。
        const: workflow 级常量。
        env: 环境变量（默认读取 os.environ）。
    """

    def __init__(
        self,
        params: Optional[Dict[str, Any]] = None,
        tasks: Optional[Dict[str, Any]] = None,
        const: Optional[Dict[str, Any]] = None,
        env: Optional[Dict[str, str]] = None,
    ):
        self.params = params or {}
        self.tasks = tasks or {}
        self.const = const or {}
        self.env = env or dict(os.environ)

    def lookup(self, path: str) -> Any:
        """按路径查找值。

        Args:
            path: 点分隔路径，如 "params.question" / "tasks.a.output.sql" / "env.HOME"。

        Returns:
            查找到的值。

        Raises:
            KeyError: 路径无法解析。
        """
        parts = path.split(".", 1)
        root = parts[0]

        if root == "params":
            return self._navigate(self.params, parts[1] if len(parts) > 1 else "")
        elif root == "tasks":
            return self._navigate(self.tasks, parts[1] if len(parts) > 1 else "")
        elif root == "const":
            return self._navigate(self.const, parts[1] if len(parts) > 1 else "")
        elif root == "env":
            key = parts[1] if len(parts) > 1 else ""
            val = self.env.get(key)
            if val is None:
                raise KeyError(f"Environment variable '{key}' not set")
            return val
        else:
            raise KeyError(f"Unknown variable root: '{root}'. Expected: params | tasks | const | env")

    @staticmethod
    def _navigate(data: Dict[str, Any], path: str) -> Any:
        """按点分隔路径在嵌套字典中查找值。

        Args:
            data: 根字典。
            path: 点分隔路径，如 "schema_link.output.tables"。

        Returns:
            查找到的值。

        Raises:
            KeyError: 路径中的某个 key 不存在。
        """
        if not path:
            return data
        current: Any = data
        for key in path.split("."):
            if isinstance(current, dict):
                if key not in current:
                    raise KeyError(
                        f"Key '{key}' not found in path '{path}'. Available: {list(current.keys())}"
                    )
                current = current[key]
            else:
                raise KeyError(
                    f"Cannot navigate into {type(current).__name__} at key '{key}' (path: {path})"
                )
        return current


# ═══════════════════════════════════════════════════════════════
#  VariableResolver
# ═══════════════════════════════════════════════════════════════

class VariableResolver:
    """解析字符串中的 ${...} 变量引用。

    支持递归解析 dict / list 容器中的嵌套引用。
    M1 兼容：__FROM_RUNTIME__ 保持不变（由 TaskBuilder 处理）。

    Usage:
        resolver = VariableResolver()
        ctx = VarContext(params={"q": "hello"})
        result = resolver.resolve("${params.q} world", ctx)  # → "hello world"
    """

    def resolve(self, value: Any, context: VarContext) -> Any:
        """递归解析 value 中的所有 ${...} 引用。

        Args:
            value: 待解析的值（可以是 str / dict / list / 其他）。
            context: 变量上下文。

        Returns:
            解析后的值。
        """
        if isinstance(value, str):
            return self._resolve_string(value, context)
        elif isinstance(value, dict):
            return {k: self.resolve(v, context) for k, v in value.items()}
        elif isinstance(value, list):
            return [self.resolve(item, context) for item in value]
        else:
            return value

    def _resolve_string(self, text: str, context: VarContext) -> Any:
        """解析单个字符串中的 ${...} 引用。

        规则:
          - "${params.x}" 作为独立值 → 返回原始类型（不强制转 str）
          - "... ${params.x} ..." 作为子串 → 替换为 str(context.lookup(...))
          - 无 ${} → 原样返回
          - __FROM_RUNTIME__ → 原样返回（M1 兼容）
        """
        if text == _RUNTIME_PLACEHOLDER:
            return text

        matches = _VAR_PATTERN.findall(text)

        if not matches:
            return text

        # 整个字符串就是一个 ${...} 引用 → 返回原始类型
        if len(matches) == 1 and text.strip() == f"${{{matches[0]}}}":
            return context.lookup(matches[0])

        # 混合文本 + 引用 → 全部转字符串拼接
        result = text
        for path in matches:
            try:
                val = context.lookup(path)
                result = result.replace(f"${{{path}}}", str(val))
            except KeyError as e:
                logger.warning(f"VariableResolver: {e} — using empty string")
                result = result.replace(f"${{{path}}}", "")

        return result


# ═══════════════════════════════════════════════════════════════
#  InputResolver
# ═══════════════════════════════════════════════════════════════

class InputResolver:
    """解析 task 的整个 input/config 字典。

    先做 M1 兼容（__FROM_RUNTIME__ → params.<key>），
    再做 M2 变量解析（${...} → VarContext）。

    Usage:
        resolver = InputResolver()
        ctx = VarContext(params={"question": "hello"})
        inputs = {"q": "${params.question}", "limit": 10}
        resolved = resolver.resolve(inputs, ctx)  # → {"q": "hello", "limit": 10}
    """

    def __init__(self, var_resolver: Optional[VariableResolver] = None):
        self._var_resolver = var_resolver or VariableResolver()

    def resolve(
        self,
        inputs: Dict[str, Any],
        context: VarContext,
    ) -> Dict[str, Any]:
        """解析整个 input 字典。

        Args:
            inputs: 原始 input 字典（来自 YAML task config）。
            context: 变量上下文。

        Returns:
            解析后的字典，所有 ${} 引用被替换为实际值。
        """
        resolved: Dict[str, Any] = {}
        for key, value in inputs.items():
            # M1 兼容：__FROM_RUNTIME__ → 从 params 中按 key 名查找
            if value == _RUNTIME_PLACEHOLDER:
                resolved[key] = context.lookup(f"params.{key}")
            else:
                resolved[key] = self._var_resolver.resolve(value, context)
        return resolved


# ═══════════════════════════════════════════════════════════════
#  RetryBuilder
# ═══════════════════════════════════════════════════════════════

class RetryBuilder:
    """YAML retry 配置 → RetryPolicy。

    YAML 格式:
        retry:
          max: 2
          backoff: 1s
          multiplier: 2.0
          max_backoff: 10s

    Usage:
        policy = RetryBuilder.build(task_def.config.get("retry"))
    """

    @staticmethod
    def build(retry_config: Optional[Dict[str, Any]]) -> Optional[RetryPolicy]:
        """从 YAML retry 配置构建 RetryPolicy。

        Args:
            retry_config: YAML 中 task 的 retry 字段。None 表示不配置。

        Returns:
            RetryPolicy 实例，或 None。
        """
        if retry_config is None:
            return None

        return RetryPolicy(
            max_retries=int(retry_config.get("max", 3)),
            backoff_base=RetryBuilder._parse_duration(
                retry_config.get("backoff", "0.5s")
            ),
            backoff_multiplier=float(retry_config.get("multiplier", 2.0)),
            max_backoff=RetryBuilder._parse_duration(
                retry_config.get("max_backoff", "10s")
            ),
        )

    @staticmethod
    def _parse_duration(value: Any) -> float:
        """解析时间字符串为秒数。

        Args:
            value: "30s" / "5m" / "500ms" / 数字。

        Returns:
            float 秒数。
        """
        if isinstance(value, (int, float)):
            return float(value)

        value_str = str(value).strip().lower()

        for unit, factor in sorted(_TIME_UNITS.items(), key=lambda x: -len(x[0])):
            if value_str.endswith(unit):
                num_part = value_str[: -len(unit)].strip()
                return float(num_part) * factor

        # 无单位 → 视为秒
        try:
            return float(value_str)
        except ValueError:
            logger.warning(f"RetryBuilder: cannot parse duration '{value}', using 1.0s")
            return 1.0


# ═══════════════════════════════════════════════════════════════
#  TimeoutBuilder
# ═══════════════════════════════════════════════════════════════

class TimeoutBuilder:
    """超时配置 → float 秒数。

    支持:
      - 数字: 30 → 30.0
      - 字符串: "30s" → 30.0, "5m" → 300.0, "500ms" → 0.5
      - 带单位的 YAML 原生类型（如 5s 在某些 YAML 解析器中可能被解析为不同格式）

    Usage:
        timeout = TimeoutBuilder.build("30s")  # → 30.0
    """

    @staticmethod
    def build(value: Any, default: float = 30.0) -> float:
        """解析超时配置为秒数。

        Args:
            value: 超时配置（数字 / 字符串 / None）。
            default: 默认值。

        Returns:
            float 秒数。
        """
        if value is None:
            return default

        if isinstance(value, (int, float)):
            return float(value)

        value_str = str(value).strip().lower()

        for unit, factor in sorted(_TIME_UNITS.items(), key=lambda x: -len(x[0])):
            if value_str.endswith(unit):
                num_part = value_str[: -len(unit)].strip()
                try:
                    return float(num_part) * factor
                except ValueError:
                    return default

        # 无单位 → 视为秒
        try:
            return float(value_str)
        except ValueError:
            logger.warning(f"TimeoutBuilder: cannot parse '{value}', using default {default}s")
            return default
