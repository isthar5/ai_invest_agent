"""
GoScheduler — 通过 gRPC 连接 Go Runtime，实现 Scheduler 接口。

完全不修改 ExecutionRuntime。DI 注入即可切换 PythonScheduler ↔ GoScheduler。

用法：
    from app.runtime.go_scheduler import GoScheduler

    runtime = ExecutionRuntime(scheduler=GoScheduler(endpoint="localhost:9090"))
"""

from __future__ import annotations

import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import grpc

from .interfaces import ExecutionHandle, Scheduler
from .task import Task as PyTask, TaskStatus as PyTaskStatus
from .go_handle import GoExecutionHandle, _proto_status_to_py
from .proto.runtime.v1 import (
    Task as PBTask,
    TaskResult as PBTaskResult,
    SchedulerServiceStub,
)

logger = logging.getLogger("runtime.go_scheduler")


class GoScheduler(Scheduler):
    """
    gRPC-based Scheduler。

    Phase 1: 同步 gRPC unary RPC (SubmitTask)。
    Phase 2+: 异步 streaming RPC (SubmitTaskStream)。
    """

    def __init__(self, endpoint: str = "localhost:9090"):
        self._endpoint = endpoint
        self._channel: Optional[grpc.aio.Channel] = None
        self._stub: Optional[SchedulerServiceStub] = None
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._shutdown = False

    async def _ensure_channel(self):
        if self._channel is None:
            self._channel = grpc.aio.insecure_channel(self._endpoint)
            self._stub = SchedulerServiceStub(self._channel)

    async def submit(self, task: PyTask) -> ExecutionHandle:
        """提交 Task → gRPC → Go Runtime → TaskResult"""
        if self._shutdown:
            raise RuntimeError("GoScheduler is shut down")

        await self._ensure_channel()
        assert self._stub is not None

        # 1. Python Task → Protobuf Task
        pb_task = _py_task_to_proto(task)

        # 2. gRPC call
        try:
            pb_result: PBTaskResult = await self._stub.SubmitTask(
                pb_task, timeout=task.timeout + 5.0
            )
        except grpc.RpcError as e:
            logger.error(f"gRPC SubmitTask failed: {e.code()} {e.details()}")
            task.error = f"gRPC error: {e.details()}"
            task.status = PyTaskStatus.FAILED  # direct set for error path
            return GoExecutionHandle(task, None)

        # 3. Protobuf TaskResult → Python Task
        _apply_result_to_task(task, pb_result)

        return GoExecutionHandle(task, pb_result)

    async def cancel(self, task_id: str) -> bool:
        """取消 Task。调用 Go Runtime 的 CancelTask RPC。"""
        if self._shutdown:
            return False

        await self._ensure_channel()
        assert self._stub is not None

        try:
            from .proto.runtime.v1 import CancelTaskRequest

            req = CancelTaskRequest(task_id=task_id)
            resp = await self._stub.CancelTask(req, timeout=5.0)
            if resp.success:
                logger.info(f"Task {task_id} cancelled successfully")
            else:
                logger.warning(f"CancelTask failed for {task_id}: {resp.error}")
            return resp.success
        except grpc.RpcError as e:
            logger.error(f"gRPC CancelTask failed: {e.code()} {e.details()}")
            return False

    async def wait(
        self,
        handles: List[ExecutionHandle],
        timeout: Optional[float] = None,
    ) -> List[ExecutionHandle]:
        # Phase 1: all handles are already done (synchronous RPC)
        return [h for h in handles if h.done()]

    async def shutdown(self) -> None:
        self._shutdown = True
        if self._channel:
            await self._channel.close()
            self._channel = None
            self._stub = None
        self._executor.shutdown(wait=False)
        logger.info("GoScheduler shut down")


# ── 序列化辅助函数 ────────────────────────────────────

def _py_task_to_proto(task: PyTask) -> PBTask:
    """Python Task → Protobuf Task"""
    payload_bytes = json.dumps(task.payload, ensure_ascii=False).encode("utf-8")

    metadata = {}
    if task.request_id:
        metadata["request_id"] = task.request_id
    if task.trace_id:
        metadata["trace_id"] = task.trace_id
    metadata["stage"] = task.stage
    metadata["group"] = task.group

    max_retries = 0
    if task.retry_policy:
        max_retries = task.retry_policy.max_retries

    return PBTask(
        task_id=task.task_id,
        request_id=task.request_id or "",
        trace_id=task.trace_id or "",
        skill=task.skill,
        payload=payload_bytes,
        priority=task.priority,
        timeout_ms=task.timeout * 1000.0,
        metadata=metadata,
        max_retries=max_retries,
    )


def _apply_result_to_task(task: PyTask, pb_result: PBTaskResult) -> None:
    """将 Protobuf TaskResult 应用到 Python Task"""
    status = _proto_status_to_py(pb_result.status)

    # 按生命周期推进状态
    if not task.is_terminal:
        try:
            if task.status in (PyTaskStatus.CREATED,):
                task.transition_to(PyTaskStatus.QUEUED)
            if task.status == PyTaskStatus.QUEUED:
                task.transition_to(PyTaskStatus.RUNNING)
        except ValueError:
            pass  # 状态转换可能已由其他地方完成

    # 设置为最终状态
    task.status = status

    if pb_result.result:
        try:
            task.result = json.loads(pb_result.result.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            task.result = {"raw": pb_result.result}

    if pb_result.error:
        task.error = pb_result.error

    task.retry_count = pb_result.retry_count
