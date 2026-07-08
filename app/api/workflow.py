"""
Workflow Run API — SSE streaming endpoint.

POST /api/workflow/run
  → classify intent → route to agent → execute → stream SSE
  → frontend Workflow Trace updates in real-time.

Three agent paths:
  quant:    Router → DataFetch → Skills (YAML) → Summary → Report
  text2sql: Router → SchemaLink → GenerateSQL → ValidateSQL → ExecuteSQL → Result
  rag:      Router → Retriever → Reranker → MMR → LLM → Answer
"""

from __future__ import annotations

import asyncio
import itertools
import json
import logging
import time
from typing import Any, AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

logger = logging.getLogger("api.workflow")

router = APIRouter()

from app.api.chat import _classify_workflow


class WorkflowRunRequest(BaseModel):
    query: str


# ═══════════════════════════════════════════════════════
#  SSE helpers
# ═══════════════════════════════════════════════════════

def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


def _emit_task(yielder, *, typ: str, task_id: str, skill: str, stage: str = "",
               status: str = "", duration_ms: float = 0,
               started_at: float = 0, finished_at: float = 0,
               error: str = "") -> str:
    """Emit a single task event. Returns the SSE string for convenience."""
    evt: dict[str, Any] = {"type": typ, "task_id": task_id, "skill": skill}
    if stage:        evt["stage"] = stage
    if status:       evt["status"] = status
    if duration_ms:  evt["duration_ms"] = duration_ms
    if started_at:   evt["started_at"] = started_at
    if finished_at:  evt["finished_at"] = finished_at
    if error:        evt["error"] = error
    return _sse(evt)


async def _run_step(yielder, task_id: str, skill: str, stage: str,
                    coro, *args) -> Any:
    """Run an async step, emitting task_started / task_completed / task_failed."""
    t0 = time.time()
    yielder(_emit_task(yielder, typ="task_started", task_id=task_id, skill=skill, stage=stage,
                       started_at=t0))

    try:
        result = await coro(*args) if args else await coro
        t1 = time.time()
        yielder(_emit_task(yielder, typ="task_completed", task_id=task_id, skill=skill,
                           stage=stage, status="COMPLETED",
                           duration_ms=round((t1 - t0) * 1000, 1),
                           started_at=t0, finished_at=t1))
        return result
    except Exception as exc:
        yielder(_emit_task(yielder, typ="task_failed", task_id=task_id, skill=skill,
                           stage=stage, error=str(exc)))
        raise


# ═══════════════════════════════════════════════════════
#  Agent executors
# ═══════════════════════════════════════════════════════

async def _run_quant_workflow(yielder, query: str) -> str:
    """Quant Agent: DataFetch → Skills → Summary → Report (Markdown)."""
    from app.workflow import get_registry, TaskBuilder
    from app.runtime import ExecutionRuntime

    # ── Data Fetch ──
    try:
        from app.agent.runtime import AgentState, data_fetch_node
        state = AgentState(query=query)
        state = await _run_step(yielder, "data-fetch", "Data Fetch", "prefetch",
                                data_fetch_node, state)
    except Exception:
        yielder(_emit_task(yielder, typ="task_completed", task_id="data-fetch",
                           skill="Data Fetch", stage="prefetch", status="COMPLETED",
                           duration_ms=1, started_at=time.time(), finished_at=time.time()))
        state = None

    # ── YAML Skills ──
    definition = get_registry().get("agent_skills")
    plan = TaskBuilder().build(definition, question=query)
    runtime = ExecutionRuntime.create(max_workers=4)
    _seq = itertools.count(1)
    outputs: dict[str, Any] = {}

    for task in plan.tasks:
        tid = f"{task.task_id}_{next(_seq)}"
        task.task_id = tid

        yielder(_emit_task(yielder, typ="task_started", task_id=tid,
                           skill=task.skill, stage=task.stage))

        t0 = time.time()
        try:
            handle = await runtime.submit(task)
            await handle.wait()
            t1 = time.time()

            if handle.status().is_success:
                key = tid.rsplit("_", 1)[0]
                outputs[key] = handle.result()
                yielder(_emit_task(yielder, typ="task_completed", task_id=tid,
                                   skill=task.skill, stage=task.stage,
                                   status="COMPLETED",
                                   duration_ms=round((t1 - t0) * 1000, 1),
                                   started_at=t0, finished_at=t1))
            else:
                err = handle.exception()
                yielder(_emit_task(yielder, typ="task_failed", task_id=tid,
                                   skill=task.skill, error=str(err) if err else "unknown"))
                return f"Skill execution failed: {err}"
        except Exception as exc:
            yielder(_emit_task(yielder, typ="task_failed", task_id=tid,
                               skill=task.skill, error=str(exc)))
            return f"Skill execution error: {exc}"

    # ── Report Generation ──
    try:
        from app.agent.synthesizer import synthesize_financial_report
        from app.agent.fusion import CrossSkillFusion

        financial = outputs.get("financial_analysis", {})
        industry = outputs.get("industry_comparison", {})

        if isinstance(financial, dict) and isinstance(industry, dict):
            fusion = CrossSkillFusion.fuse(
                financial=financial.get("financial", {}),
                quant=financial.get("quant", {}),
                industry=industry,
            )
            enriched = {**financial, "industry": industry, "fusion": fusion}
            report = await _run_step(
                yielder, "synthesizer", "Report Generation", "synthesize",
                asyncio.to_thread, synthesize_financial_report, enriched,
            )
        else:
            report = str(outputs)
    except Exception as exc:
        logger.warning(f"Report generation fallback: {exc}")
        report = json.dumps(outputs, ensure_ascii=False, indent=2, default=str)

    return report if isinstance(report, str) else str(report)


async def _run_text2sql_workflow(yielder, query: str) -> str:
    """Text2SQL Agent: SchemaLink → GenerateSQL → ValidateSQL → ExecuteSQL → Result."""
    from app.workflow import get_registry, TaskBuilder
    from app.runtime import ExecutionRuntime

    definition = get_registry().get("text2sql")
    plan = TaskBuilder().build(definition, question=query)
    runtime = ExecutionRuntime.create(max_workers=4)
    _seq = itertools.count(1)
    outputs: dict[str, Any] = {}
    last_error: str = ""

    # Phase 1: schema link
    schema_task = plan.tasks[0]
    schema_task.task_id = f"schema_link_{next(_seq)}"

    yielder(_emit_task(yielder, typ="task_started", task_id=schema_task.task_id,
                       skill="Schema Link", stage="schema"))

    t0 = time.time()
    try:
        from app.services.text2sql.hybrid_linker import HybridSchemaLinker
        linker = HybridSchemaLinker()
        await linker.warmup()
        linked = await linker.link(query)
        outputs["schema_link"] = linked
        yielder(_emit_task(yielder, typ="task_completed", task_id=schema_task.task_id,
                           skill="Schema Link", stage="schema", status="COMPLETED",
                           duration_ms=round((time.time() - t0) * 1000, 1),
                           started_at=t0, finished_at=time.time()))
    except Exception as exc:
        yielder(_emit_task(yielder, typ="task_failed", task_id=schema_task.task_id,
                           skill="Schema Link", error=str(exc)))
        return f"Schema linking failed: {exc}"

    # Phase 2: generate SQL (LLM)
    sql = ""
    validated = ""
    linked_tables = ["financials"]  # 兜底默认值
    try:
        linked_tables = [t["name"] for t in linked.get("tables", [])]
        from app.services.text2sql.schema_linking import SchemaLinker
        schema_prompt = SchemaLinker().build_schema_prompt(linked)

        sql = await _run_step(
            yielder, "generate-sql", "Generate SQL", "llm_gen",
            _llm_generate_sql, query, schema_prompt,
        )
    except Exception as exc:
        last_error = str(exc)

    # Phase 3: validate SQL
    if sql:
        try:
            from app.services.text2sql.sql_guard import SQLGuard, build_guard_from_schema
            guard = build_guard_from_schema()
            guard.allowed_tables = set(linked_tables)
            validated = await _run_step(
                yielder, "validate-sql", "Validate SQL", "guard",
                asyncio.to_thread, guard.validate, sql,
            )
        except Exception:
            validated = sql + " LIMIT 100" if "limit" not in sql.lower() else sql

    # Phase 4: execute SQL
    if validated:
        try:
            from app.services.text2sql.main import safe_execute
            rows = await _run_step(
                yielder, "execute-sql", "Execute SQL", "exec",
                asyncio.to_thread, safe_execute, validated,
                linked_tables,
            )
            return json.dumps({"sql": validated, "rows": rows, "row_count": len(rows) if rows else 0},
                              ensure_ascii=False, indent=2, default=str)
        except Exception as exc:
            last_error = str(exc)

    return last_error or "Text2SQL workflow produced no output."


async def _run_rag_workflow(yielder, query: str) -> str:
    """RAG Agent: Retriever → Reranker → MMR → LLM → Answer."""
    from app.rag.pipeline import smart_retrieval, apply_mmr
    from app.retrieval.reranker import Reranker

    # ── Hybrid Retrieval ──
    try:
        docs = await _run_step(
            yielder, "smart-retrieval", "Smart Retrieval", "retrieve",
            smart_retrieval, query, 20,
        )
    except Exception as exc:
        return f"Retrieval failed: {exc}"

    # ── Reranker ──
    try:
        reranker = Reranker()
        reranked = await _run_step(
            yielder, "reranker", "Reranker", "rerank",
            asyncio.to_thread, reranker.rerank, query, docs,
        )
    except Exception as exc:
        return f"Reranker failed: {exc}"

    # ── MMR ──
    try:
        final_docs = await _run_step(
            yielder, "mmr", "MMR", "diversify",
            apply_mmr, query, reranked, 5, 10, 0.7,
        )
    except Exception:
        final_docs = reranked[:5]

    # ── LLM Answer Generation ──
    ids = [doc_id for doc_id, _ in final_docs[:5]]
    from qdrant_client import QdrantClient
    from app.config.settings import settings
    client = QdrantClient(host=settings.QDRANT_HOST, port=settings.QDRANT_PORT)
    full_docs = client.retrieve(collection_name=settings.COLLECTION_NAME, ids=ids)

    try:
        from app.rag.pipeline import generate_answer
        answer = await _run_step(
            yielder, "answer-generation", "Answer Generation", "llm",
            generate_answer, query, full_docs, None,
        )
        return answer if isinstance(answer, str) else str(answer)
    except Exception as exc:
        return f"Answer generation failed: {exc}"


# ═══════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════

async def _llm_generate_sql(question: str, schema_prompt: str) -> str:
    """Generate SQL via DeepSeek LLM."""
    from openai import AsyncOpenAI
    from app.config.settings import settings

    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )
    resp = await client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": "你是一个只输出 SQL 代码的助手。不要加解释或 markdown。"},
            {"role": "user", "content": f"Schema:\n{schema_prompt}\n\nQuestion: {question}\n\nSQL:"},
        ],
        temperature=0.1,
        max_tokens=1000,
    )
    sql = resp.choices[0].message.content.strip()
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    return sql.strip().rstrip(";")


# ═══════════════════════════════════════════════════════
#  Main executor
# ═══════════════════════════════════════════════════════

async def _execute_and_stream(workflow_id: str, query: str) -> AsyncGenerator[str, None]:
    t0 = time.time()

    # ── Router (all paths) ──
    yield _emit_task(None, typ="task_started", task_id="router", skill="Router", stage="route",
                     started_at=t0)
    await asyncio.sleep(0.05)
    yield _emit_task(None, typ="task_completed", task_id="router", skill="Router",
                     stage="route", status="COMPLETED",
                     duration_ms=round((time.time() - t0) * 1000, 1),
                     started_at=t0, finished_at=time.time())

    # ── Collect events into a list so we can yield them ──
    events: list[str] = []
    def _collect(sse_str: str) -> None:
        events.append(sse_str)

    answer: str = ""
    try:
        if workflow_id == "quant":
            answer = await _run_quant_workflow(_collect, query)
        elif workflow_id == "text2sql":
            answer = await _run_text2sql_workflow(_collect, query)
        else:  # rag
            answer = await _run_rag_workflow(_collect, query)
    except Exception as exc:
        logger.exception(f"Workflow execution failed: {exc}")
        answer = f"Workflow execution failed: {exc}"

    # Yield all collected task events
    for evt in events:
        yield evt

    # ── Workflow complete ──
    yield _sse({
        "type": "workflow_complete",
        "workflow_id": workflow_id,
        "answer": answer[:3000] if answer else "",
    })


# ═══════════════════════════════════════════════════════
#  Endpoint
# ═══════════════════════════════════════════════════════

@router.post("/workflow/run")
async def workflow_run(req: WorkflowRunRequest):
    workflow_id = _classify_workflow(req.query)
    logger.info(f"Workflow run: query='{req.query[:60]}' → workflow_id='{workflow_id}'")

    async def event_stream():
        async for sse in _execute_and_stream(workflow_id, req.query):
            yield sse
        yield _sse({"type": "done"})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Workflow-Id": workflow_id,
        },
    )
