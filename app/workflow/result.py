"""
M1 — WorkflowResult 极简结果对象。

Node 只通过 result.outputs["task_id"] 取值，不关心 Task 细节。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(slots=True)
class WorkflowResult:
    """Workflow 执行结果。

    Attributes:
        workflow_id: 执行的 Workflow 标识。
        outputs: {task_id: result_data} — Node 唯一切入点。
        metadata: 扩展预留（后需可加 latency / status / artifacts）。
    """

    workflow_id: str
    outputs: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
