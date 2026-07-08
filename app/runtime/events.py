"""
Runtime Events — 事件定义 + 轻量 EventBus。

所有 Runtime 状态变更都通过 Event 发布。
Observability / Metrics / Tracing / Audit 通过订阅 Event 接入，
不与 Runtime 内部耦合。

SOLID：单一职责（事件定义与分发），开放-封闭（新增 Event 类型无需改 EventBus）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List

from .task import Task

logger = logging.getLogger("runtime.events")


# ═══════════════════════════════════════════════════════════════
#  Event Types
# ═══════════════════════════════════════════════════════════════

class EventType(Enum):
    TASK_CREATED = auto()
    TASK_QUEUED = auto()
    TASK_STARTED = auto()
    TASK_COMPLETED = auto()
    TASK_FAILED = auto()
    TASK_TIMEOUT = auto()
    TASK_CANCELLED = auto()
    RETRY_SCHEDULED = auto()
    RESULT_AGGREGATED = auto()
    RUNTIME_SHUTDOWN = auto()


@dataclass
class RuntimeEvent:
    type: EventType
    task: Task
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.task.task_id

    @property
    def skill(self) -> str:
        return self.task.skill


# ═══════════════════════════════════════════════════════════════
#  EventBus
# ═══════════════════════════════════════════════════════════════

EventHandler = Callable[[RuntimeEvent], None]


class EventBus:
    """
    轻量级发布-订阅事件总线。

    不依赖任何外部 MQ/lib。线程安全。
    """

    def __init__(self):
        self._subscribers: Dict[EventType, List[EventHandler]] = {
            et: [] for et in EventType
        }

    def subscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """订阅某类事件"""
        self._subscribers[event_type].append(handler)

    def unsubscribe(self, event_type: EventType, handler: EventHandler) -> None:
        """取消订阅"""
        try:
            self._subscribers[event_type].remove(handler)
        except ValueError:
            pass

    def publish(self, event: RuntimeEvent) -> None:
        """发布事件（同步通知所有订阅者）"""
        handlers = self._subscribers.get(event.type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception:
                logger.exception(
                    f"EventBus: handler failed for {event.type.name}"
                )


# ═══════════════════════════════════════════════════════════════
#  Built-in subscribers（可选，应用启动时注册）
# ═══════════════════════════════════════════════════════════════

def _create_logging_subscriber():
    """创建日志订阅者（生产环境可替换为 OpenTelemetry 等）"""
    from app.observability.logger import get_logger
    evt_logger = get_logger("runtime.events")

    def on_event(event: RuntimeEvent) -> None:
        evt_logger.info(
            f"Task {event.task_id} {event.type.name}",
            extra={
                "task_id": event.task_id,
                "skill": event.skill,
                "event_type": event.type.name,
                "task_status": event.task.status.name,
            },
        )

    return on_event


def _create_metrics_subscriber():
    """创建 Prometheus 指标订阅者"""
    def on_event(event: RuntimeEvent) -> None:
        try:
            from app.observability.metrics import (
                tool_requests_total,
                agent_errors_total,
            )
            task = event.task
            if event.type == EventType.TASK_COMPLETED:
                tool_requests_total.labels(
                    tool_name=task.skill, status="success"
                ).inc()
            elif event.type == EventType.TASK_FAILED:
                tool_requests_total.labels(
                    tool_name=task.skill, status="error"
                ).inc()
                agent_errors_total.labels(
                    agent=task.skill, error_type="task_failed"
                ).inc()
            elif event.type == EventType.TASK_TIMEOUT:
                tool_requests_total.labels(
                    tool_name=task.skill, status="timeout"
                ).inc()
        except ImportError:
            pass

    return on_event
