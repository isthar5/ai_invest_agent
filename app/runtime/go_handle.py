"""
GoExecutionHandle — 包装 gRPC TaskResult，实现 ExecutionHandle 接口。

完全不暴露 gRPC 细节给上层。Runtime 只依赖接口。
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from .interfaces import ExecutionHandle
from .task import Task as PyTask, TaskStatus as PyTaskStatus


class GoExecutionHandle(ExecutionHandle):
    """
    基于 gRPC 同步响应的 ExecutionHandle。

    Phase 1: TaskResult 已包含完整结果 → 构造时即完成。
    Phase 2+: 包装 gRPC stream → wait() 时解析。
    """

    def __init__(self, py_task: PyTask, grpc_result):
        self._task = py_task
        self._grpc_result = grpc_result

    @property
    def task_id(self) -> str:
        return self._task.task_id

    def status(self) -> PyTaskStatus:
        return self._task.status

    def result(self) -> Any:
        if self._task.error:
            raise RuntimeError(self._task.error)
        return self._task.result

    def exception(self) -> Optional[Exception]:
        if self._task.error:
            return RuntimeError(self._task.error)
        return None

    def done(self) -> bool:
        return True  # Phase 1: synchronous RPC, result available immediately

    async def wait(self, timeout: Optional[float] = None) -> PyTask:
        return self._task

    def cancel(self) -> bool:
        # Phase 1: synchronous RPC, cancellation not supported mid-flight
        return False


def _proto_status_to_py(grpc_status: int) -> PyTaskStatus:
    """Map protobuf TaskStatus → Python TaskStatus"""
    from .proto.runtime.v1 import TaskStatus as PBStatus

    mapping = {
        PBStatus.TASK_STATUS_UNSPECIFIED: PyTaskStatus.CREATED,
        PBStatus.TASK_STATUS_CREATED: PyTaskStatus.CREATED,
        PBStatus.TASK_STATUS_QUEUED: PyTaskStatus.QUEUED,
        PBStatus.TASK_STATUS_RUNNING: PyTaskStatus.RUNNING,
        PBStatus.TASK_STATUS_COMPLETED: PyTaskStatus.COMPLETED,
        PBStatus.TASK_STATUS_FAILED: PyTaskStatus.FAILED,
        PBStatus.TASK_STATUS_TIMEOUT: PyTaskStatus.TIMEOUT,
        PBStatus.TASK_STATUS_CANCELLED: PyTaskStatus.CANCELLED,
    }
    return mapping.get(grpc_status, PyTaskStatus.FAILED)
