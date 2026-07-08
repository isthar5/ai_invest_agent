from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from typing import Optional, List, Dict
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
import uuid
import redis
import sqlparse
import logging
import time
from .schema_linking import SchemaLinker

# --------------------------
# 初始化
# --------------------------
linker = SchemaLinker()

# --------------------------
# 配置
# --------------------------
DATABASE_URL = "postgresql://user:password@localhost:5432/mydb"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)

REDIS_HOST = "localhost"
REDIS_PORT = 6379
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=0)

app = FastAPI(title="Enterprise Text-to-SQL Agent")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("text2sql_agent")

# --------------------------
# 数据模型
# --------------------------
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

# --------------------------
# 工具函数
# --------------------------
def generate_request_id():
    return str(uuid.uuid4())

def extract_tables(sql: str) -> List[str]:
    """从 SQL AST 中提取表名"""
    tables = set()
    parsed = sqlparse.parse(sql)
    for stmt in parsed:
        for token in stmt.tokens:
            if isinstance(token, sqlparse.sql.Identifier):
                tables.add(token.get_real_name())
            elif isinstance(token, sqlparse.sql.IdentifierList):
                for idf in token.get_identifiers():
                    tables.add(idf.get_real_name())
    return list(filter(None, tables))

def check_permission(sql: str, user: User):
    tables_in_sql = extract_tables(sql)
    for t in tables_in_sql:
        if t not in user.allowed_tables:
            raise HTTPException(status_code=403, detail=f"Unauthorized table: {t}")

def enforce_read_only(sql: str):
    first_token = sql.strip().split()[0].lower()
    if first_token != "select":
        raise HTTPException(status_code=403, detail="Only SELECT statements allowed")

def safe_execute(sql: str, max_rows=1000, timeout_ms=5000):
    """执行 SQL，增加 LIMIT 和超时保护"""
    enforce_read_only(sql)
    if "limit" not in sql.lower():
        sql += f" LIMIT {max_rows}"
    # 设置 statement timeout（PostgreSQL 例子）
    with engine.connect() as conn:
        conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        try:
            result = conn.execute(text(sql))
            rows = [dict(r) for r in result.fetchall()]
        except SQLAlchemyError as e:
            logger.error(f"SQL execution failed: {e}")
            raise HTTPException(status_code=400, detail="SQL execution error")
    return rows

def get_conversation_context(conversation_id: str) -> List[Dict]:
    if not conversation_id:
        return []
    data = r.get(conversation_id)
    if data:
        return eval(data)  # 简单示例，生产用 JSON 序列化
    return []

def update_conversation_context(conversation_id: str, query_text: str, sql: str):
    if not conversation_id:
        return
    history = get_conversation_context(conversation_id)
    history.append({"query": query_text, "sql": sql})
    r.set(conversation_id, str(history), ex=3600*24)  # 1天过期

# --------------------------
# NL -> SQL (LLM 调用)
# --------------------------
async def nl_to_sql(query_text: str, allowed_tables: List[str], conversation_context: List[Dict]):
    """
    真正的企业级 NL->SQL:
    - schema_linking: 动态召回相关表结构
    - conversation_context: 历史查询
    """
    # 1. 执行 Schema Linking
    linked = await linker.link(query_text, allowed_tables)
    schema_prompt = linker.build_schema_prompt(linked)

    prompt = f"""
    You are an AI assistant to convert natural language to SQL.
    Schema Info:
    {schema_prompt}
    
    Conversation history: {conversation_context}
    
    Convert the query to SQL: {query_text}
    Ensure the SQL is safe and only SELECT statements.
    Output only the SQL code, no explanation.
    """
    # TODO: 调用 LLM 接口 (例如 call_deepseek_api(prompt))
    # 下面示例模拟生成
    if "top 5 revenue" in query_text.lower():
        sql = "SELECT company, revenue FROM financials ORDER BY revenue DESC LIMIT 5;"
    else:
        sql = "SELECT 1;"
    return sql

# --------------------------
# FastAPI Endpoint
# --------------------------
@app.post("/text2sql", response_model=SQLResponse)
async def text2sql(req: SQLRequest, http_request: Request):
    request_id = generate_request_id()
    logger.info(f"[{request_id}] Received query: {req.query_text}")

    # 获取多轮上下文
    conversation_context = get_conversation_context(req.conversation_id)

    # 生成 SQL
    sql = await nl_to_sql(req.query_text, req.user.allowed_tables, conversation_context)
    logger.info(f"[{request_id}] Generated SQL: {sql}")

    # 权限校验
    check_permission(sql, req.user)

    # 执行 SQL
    start_time = time.time()
    result = safe_execute(sql)
    elapsed = time.time() - start_time
    logger.info(f"[{request_id}] SQL executed in {elapsed:.3f}s, rows: {len(result)}")

    # 更新上下文
    update_conversation_context(req.conversation_id, req.query_text, sql)

    # 返回
    explanation = f"Generated SQL for query '{req.query_text}', rows returned: {len(result)}"
    return SQLResponse(sql=sql, result=result, explanation=explanation, request_id=request_id)