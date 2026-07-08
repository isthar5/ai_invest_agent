"""
Unified JSON Logger — 结构化日志，所有服务统一使用。

特性：
  - JSON 格式输出（生产环境友好，可被 ELK/Loki 直接索引）
  - 自动从 RequestContext 注入 request_id / session_id / trace_id
  - 标准字段：latency_ms / status_code / tokens / tool_calls / retry_count / exception
  - 兼容标准 logging 接口，无需修改现有 logger 调用

用法：
  from app.observability.logger import get_logger

  logger = get_logger(__name__)
  logger.info("RAG retrieval done", extra={"doc_count": 5, "latency_ms": 42})

配置：
  环境变量 LOG_FORMAT=json|text（默认 json）
  环境变量 LOG_LEVEL=DEBUG|INFO|WARNING|ERROR（默认 INFO）
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional

from .context import request_context

# ── 配置 ──────────────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "json").lower()


# ── JSON Formatter ────────────────────────────────────

class JSONFormatter(logging.Formatter):
    """输出 JSON 格式日志，自动注入 RequestContext 字段"""

    def format(self, record: logging.LogRecord) -> str:
        ctx = request_context()

        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            # 从 RequestContext 自动注入
            "request_id": ctx.request_id,
            "session_id": ctx.session_id or None,
            "user_id": ctx.user_id or None,
            "trace_id": ctx.trace_id,
            "agent": ctx.agent or None,
            "skill": ctx.skill or None,
        }

        # 合并 extra 字段（业务日志注入的）
        extra_fields = {
            "latency_ms": None,
            "status_code": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "estimated_cost": None,
            "tool_calls": None,
            "retry_count": None,
            "exception": None,
        }
        for key in extra_fields:
            if hasattr(record, key):
                val = getattr(record, key)
                if val is not None:
                    log_entry[key] = val

        # 任意 extra 字段也合并
        _skip_fields = {
            "name", "msg", "args", "created", "filename", "funcName",
            "levelname", "levelno", "lineno", "module", "msecs",
            "pathname", "process", "processName", "relativeCreated",
            "stack_info", "thread", "threadName", "exc_info", "exc_text",
            "taskName",  # Python 3.12+ asyncio
        }
        for key, val in record.__dict__.items():
            if key not in log_entry and key not in _skip_fields:
                log_entry[key] = val

        # 异常信息
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
            log_entry["exception_type"] = type(record.exc_info[1]).__name__

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """开发环境友好的文本格式"""

    def format(self, record: logging.LogRecord) -> str:
        ctx = request_context()
        extra_parts = []
        if ctx.request_id:
            extra_parts.append(f"rid={ctx.request_id[:8]}")
        if ctx.agent:
            extra_parts.append(f"agent={ctx.agent}")
        if ctx.skill:
            extra_parts.append(f"skill={ctx.skill}")
        extra = " | ".join(extra_parts)

        base = f"[{record.levelname}] {record.name} | {record.getMessage()}"
        if extra:
            base = f"{base} | {extra}"
        return base


# ── 全局初始化 ────────────────────────────────────────

_initialized = False


def setup_logging():
    """配置根 Logger（幂等，应用启动时调用一次）"""
    global _initialized
    if _initialized:
        return

    root = logging.getLogger()
    root.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

    # 清除已有的 handler（避免重复）
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if LOG_FORMAT == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(TextFormatter())

    root.addHandler(handler)
    _initialized = True


def get_logger(name: str) -> logging.Logger:
    """
    获取 logger（替代 logging.getLogger）。

    首次调用时自动初始化根 Logger。
    Logger 实例会从 RequestContext 自动提取上下文字段。
    """
    setup_logging()
    return logging.getLogger(name)


# ── 便捷适配器 ────────────────────────────────────────

class ObservabilityLogger(logging.LoggerAdapter):
    """
    自动注入 extra 字段的 LoggerAdapter。

    业务代码可用此类来简化结构化字段的日志记录：
      logger = ObservabilityLogger(get_logger(__name__))
      logger.info("LLM call", extra={"latency_ms": 320, "total_tokens": 1500})
    """

    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        ctx = request_context()
        extra.setdefault("request_id", ctx.request_id)
        extra.setdefault("trace_id", ctx.trace_id)
        kwargs["extra"] = extra
        return msg, kwargs
