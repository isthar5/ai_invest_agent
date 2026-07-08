"""
Enterprise Text-to-SQL Agent — Workflow-driven (M1)。

M1 变更:
  - Pipeline 结构由 configs/workflows/text2sql.yaml 驱动
  - Task 执行通过 ExecutionRuntime + ExecutorRegistry
  - 数据传递在 Python 中手动完成（M2 VariableResolver 接管）
  - 对外 API 接口不变
"""

import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import create_engine

logger = logging.getLogger("text2sql")
logging.basicConfig(level=logging.INFO)

# ── 配置 ──────────────────────────────────────────
import os
DATABASE_URL = os.getenv("TEXT2SQL_DB_URL", "sqlite:///./data/chemical_stocks.db")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-xxx")
LLM_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
LLM_MODEL = os.getenv("TEXT2SQL_MODEL", "deepseek-chat")
MAX_RETRIES = 2

engine = create_engine(DATABASE_URL, pool_size=5, max_overflow=10)

# ── Workflow Framework (M1) ───────────────────────
from app.workflow import get_registry, TaskBuilder, ExecutionPlan      # noqa: E402
from app.runtime import ExecutionRuntime, Task                          # noqa: E402

# 尝试导入 sqlglot-based guard（可选依赖）
try:
    from .sql_guard import SQLGuard, build_guard_from_schema
    _HAS_SQLGLOT = True
except ImportError:
    _HAS_SQLGLOT = False

# ── 初始化模块 ─────────────────────────────────────
from .hybrid_linker import HybridSchemaLinker                            # noqa: E402
linker = HybridSchemaLinker()

if _HAS_SQLGLOT:
    sql_guard = build_guard_from_schema()
else:
    sql_guard = None
    logger.warning("sqlglot 未安装，SQL Guard 降级为字符串检查模式")

# Runtime 单例
_runtime: Optional[ExecutionRuntime] = None


def _get_runtime() -> ExecutionRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ExecutionRuntime.create(max_workers=4)
    return _runtime


# ── 数据模型 ──────────────────────────────────────

class User(BaseModel):
    username: str
    allowed_tables: List[str]


class SQLRequest(BaseModel):
    query_text: str
    conversation_id: Optional[str] = None
    user: User


class SQLResponse(BaseModel):
    sql: str
    result: Optional[List[Dict]] = None
    explanation: Optional[str] = None
    request_id: str


# ── FastAPI ───────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """启动时预热 HybridSchemaLinker 的 Embedding 索引。"""
    await linker.warmup()
    yield


app = FastAPI(
    title="Enterprise Text-to-SQL Agent (M1 Workflow)",
    lifespan=lifespan,
)


# ═══════════════════════════════════════════════════
#  核心流水线（Workflow 驱动 + Python 数据传递）
# ═══════════════════════════════════════════════════

async def text2sql_pipeline(
    question: str,
    allowed_tables: List[str],
) -> Dict[str, Any]:
    """Workflow 驱动的 Text2SQL 流水线 (M1)。

    Task 结构和顺序由 YAML 定义。数据传递在 Python 中手动完成。
    """
    registry = get_registry()
    definition = registry.get("text2sql")
    plan = TaskBuilder().build(definition, question=question, allowed_tables=allowed_tables)
    runtime = _get_runtime()

    # ── Task 1: Schema Linking ───────────────────────
    t1 = await _run_task(plan, runtime, "schema_link")
    linked = t1
    linked_tables = [t["name"] for t in linked.get("tables", [])]

    if not linked_tables:
        return {"sql": "", "result": None, "error": "未找到匹配的数据表", "retries": 0}

    # ── schema_prompt 推导（view 逻辑，M2 移入 YAML）──
    from .schema_linking import SchemaLinker
    schema_prompt = SchemaLinker().build_schema_prompt(linked)

    # ── Task 2: LLM 生成 SQL ─────────────────────────
    t2 = await _run_task(plan, runtime, "generate_sql",
        prompt_variables={
            "schema_prompt": schema_prompt,
            "question": question,
            "current_year": 2026,
        })
    sql = str(t2).strip() if t2 else ""

    # 清理 markdown 代码块
    if sql.startswith("```"):
        lines = sql.split("\n")
        sql = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    sql = sql.strip().rstrip(";")

    if not sql:
        return {"sql": "", "result": None, "error": "LLM 返回空 SQL", "retries": 0}

    # ── Task 3: SQL 安全校验 ─────────────────────────
    t3 = await _run_task(plan, runtime, "validate_sql",
        sql=sql, allowed_tables=linked_tables)
    validated = t3
    if not validated.get("is_safe"):
        return {"sql": sql, "result": None,
                "error": f"SQL Guard 拒绝: {validated.get('error')}", "retries": 0}
    final_sql = validated["sql"]

    # ── Task 4: SQL 执行 ─────────────────────────────
    rows = await _run_task(plan, runtime, "execute_sql",
        sql=final_sql, allowed_tables=allowed_tables)

    return {"sql": final_sql, "result": rows, "error": None, "retries": 0}


# ═══════════════════════════════════════════════════
#  Task 执行辅助
# ═══════════════════════════════════════════════════

import itertools as _itertools
_seq = _itertools.count(1)


async def _run_task(
    plan: ExecutionPlan,
    runtime: ExecutionRuntime,
    task_id: str,
    **config: Any,
) -> Any:
    """从 plan 中找到 task，注入 config 覆盖，提交到 Runtime 并等待完成。"""
    task = _find_task(plan, task_id)
    payload = {"__executor__": task.payload.get("__executor__", "skill"),
               **task.payload, **config}
    task.payload = payload
    task.task_id = f"{task_id}_{next(_seq)}"

    handle = await runtime.submit(task)
    await handle.wait()
    if not handle.status().is_success:
        raise RuntimeError(f"Task '{task_id}' failed: {handle.exception() or handle.result()}")
    return handle.result()


def _find_task(plan: ExecutionPlan, task_id: str) -> Task:
    for t in plan.tasks:
        if t.task_id == task_id:
            return t
    raise ValueError(f"Task '{task_id}' not found in plan")


# ═══════════════════════════════════════════════════
#  公用函数（Executor 通过 lazy import 引用）
# ═══════════════════════════════════════════════════

from .sql_guard import SecurityError  # noqa: E402


def _validate_sql(sql: str, linked_tables: List[str]) -> str:
    """SQL 安全校验。GuardExecutor 通过 lazy import 调用。"""
    if _HAS_SQLGLOT and sql_guard:
        sql_guard.allowed_tables = set(linked_tables)
        return sql_guard.validate(sql)
    else:
        return _legacy_validate(sql, linked_tables)


def _legacy_validate(sql: str, allowed_tables: List[str]) -> str:
    """降级校验（不依赖 sqlglot）。"""
    sql_upper = sql.upper().strip()
    forbidden = {"DROP", "DELETE", "INSERT", "UPDATE", "TRUNCATE", "ALTER", "CREATE"}
    for kw in forbidden:
        if kw in sql_upper:
            raise SecurityError(f"禁止的操作: {kw}")
    if not sql_upper.startswith("SELECT"):
        raise SecurityError("只允许 SELECT 查询")
    if "LIMIT" not in sql_upper:
        sql += " LIMIT 100"
    return sql


def safe_execute(
    sql: str,
    allowed_tables: List[str],
    max_rows: int = 1000,
    timeout_ms: int = 5000,
) -> List[Dict]:
    """安全执行 SQL。SQLExecutor 通过 lazy import 调用。"""
    import re
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError

    sql_lower = sql.lower()
    from_tables = re.findall(r"from\s+(\w+)", sql_lower)
    join_tables = re.findall(r"join\s+(\w+)", sql_lower)
    for t in set(from_tables + join_tables):
        if t not in allowed_tables:
            raise HTTPException(status_code=403, detail=f"无权访问表: {t}")

    if "limit" not in sql_lower:
        sql += f" LIMIT {max_rows}"

    try:
        with engine.connect() as conn:
            # SQLite 不支持 statement_timeout，使用超时上下文代替
            if DATABASE_URL.startswith("postgresql"):
                try:
                    conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                except Exception:
                    pass
            result = conn.execute(text(sql))
            return [dict(row) for row in result.fetchall()]
    except SQLAlchemyError as e:
        raise HTTPException(status_code=400, detail=f"SQL 执行错误: {str(e)}")


# ═══════════════════════════════════════════════════
#  API 端点
# ═══════════════════════════════════════════════════

@app.post("/text2sql", response_model=SQLResponse)
async def text2sql_endpoint(req: SQLRequest, http_request: Request):
    import uuid
    request_id = str(uuid.uuid4())
    start_time = time.time()

    logger.info(f"[{request_id}] 收到查询: {req.query_text[:100]}")

    result = await text2sql_pipeline(
        question=req.query_text,
        allowed_tables=req.user.allowed_tables,
    )

    elapsed = time.time() - start_time

    if result["error"] and not result["result"]:
        raise HTTPException(
            status_code=400,
            detail={"error": result["error"], "sql": result["sql"], "request_id": request_id},
        )

    row_count = len(result["result"]) if result["result"] else 0
    logger.info(f"[{request_id}] 完成: {elapsed:.2f}s, {row_count} 行")

    return SQLResponse(
        sql=result["sql"],
        result=result["result"],
        explanation=f"查询 '{req.query_text[:50]}...' 返回 {row_count} 行",
        request_id=request_id,
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "sqlglot_available": _HAS_SQLGLOT,
        "schema_tables": len(linker.schema),
    }
