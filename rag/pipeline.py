from app.retrieval.hybrid import hybrid_search
from app.retrieval.reranker import Reranker
from app.retrieval.mmr import mmr
from app.retrieval.embedder import dense_model
from app.config.stock_pool import CHEMICAL_STOCK_POOL
from qdrant_client.http import models as qmodels
from app.utils.tracer import Tracer
from app.utils.citation import add_citation
from qdrant_client import QdrantClient
from openai import AsyncOpenAI
from app.config.settings import settings
import os
import asyncio
import json
import re
from typing import List, Optional

# 初始化客户端
client = QdrantClient(
    host=settings.QDRANT_HOST,
    port=settings.QDRANT_PORT,
)

llm_client = AsyncOpenAI(
    api_key=settings.DEEPSEEK_API_KEY,
    base_url=settings.DEEPSEEK_BASE_URL,
)

COLLECTION_NAME = settings.COLLECTION_NAME


from datetime import datetime

CURRENT_DATE = datetime.now().strftime("%Y-%m-%d")
CURRENT_YEAR = datetime.now().year

# ==================== 量化信号格式化 ====================
def format_quant_signal_for_llm(quant_result) -> str:
    """
    将量化信号格式化为 LLM 可读的文本
    """
    if not quant_result:
        return "暂无量化信号"
    
    if isinstance(quant_result, str):
        return quant_result
    
    if isinstance(quant_result, dict):
        # 个股信号
        if "stock" in quant_result and "score" in quant_result:
            signal_icon = "🔴" if quant_result.get("signal") == "SELL" else "🟢" if quant_result.get("signal") == "BUY" else "🟡"
            return f"""
{signal_icon} **量化信号 - {quant_result.get('name', quant_result.get('stock'))}**
- 预测收益率: {quant_result.get('score', 0):.2%}
- 信号强度: {quant_result.get('signal', 'NEUTRAL')}
- 趋势: {quant_result.get('trend', 'unknown')}
- 模型解释: {quant_result.get('explanation', '暂无')[:150]}
"""
        
        # 行业概览
        if "top_5" in quant_result:
            top_text = "\n".join([
                f"  {i+1}. {s['stock']}: {s['pred']:.2%}"
                for i, s in enumerate(quant_result.get('top_5', [])[:3])
            ])
            return f"""
 **量化引擎 - {quant_result.get('industry', '化工')}行业扫描**
- 数据日期: {quant_result.get('date', 'N/A')}
- 最佳股票: {quant_result.get('best_stock', {}).get('stock', 'N/A')} 
  (预测收益 {quant_result.get('best_stock', {}).get('prediction_5d_return', 0):.2%})
- Top 3 机会:
{top_text}
- 万华化学: {quant_result.get('wanhua', {}).get('prediction_5d_return', 0):.2%}
- 模型解释: {quant_result.get('explanation', '暂无')[:200]}
"""
        
        if "msg" in quant_result:
            return quant_result["msg"]
    
    if isinstance(quant_result, list):
        # Top stocks list
        text = "📊 **量化选股 Top 列表**\n"
        for i, stock in enumerate(quant_result[:5]):
            text += f"  {i+1}. {stock['stock']}: 得分 {stock.get('score', 0):.2%}, 信号 {stock.get('signal', 'N/A')}\n"
        return text
    
    return str(quant_result)[:500]


# ==================== 生成回答（流式）====================
async def generate_answer_stream(query, context_docs, quant_signal):
    # 格式化上下文（带编号，用于 citation）
    context_text = []
    for i, doc in enumerate(context_docs[:5], 1):
        source = doc.payload.get('source', '未知')
        year = doc.payload.get('year', '未知')
        text = (doc.payload.get('text') or doc.payload.get('content') or '')[:800]
        context_text.append(f"[{i}] 来源：{source} ({year})\n{text}\n")
    
    context_str = "\n---\n".join(context_text)
    quant_text = format_quant_signal_for_llm(quant_signal)
    
    # ✅ 修复：使用 f-string 格式化当前日期
    system_prompt = f"""你是化工行业分析师。
当前日期：{CURRENT_DATE}（今天是{CURRENT_YEAR}年）

**重要规则**：
1. 引用数据必须标注年份，如“根据2024年年报...”
2. 每个结论必须引用文档编号，格式如 [1]、[2]
3. 如果问题包含“最近”、“最新”，优先使用近2年的文档
4. 如果只能找到老数据，必须明确说“该数据为X年，可能已过时”
5. 不要编造文档中没有的内容

请结合【研报上下文】和【量化信号】回答问题。"""

    user_content = f"""【用户问题】：{query}

【研报上下文】：
{context_str}

【量化信号】：
{quant_text}

请给出专业分析："""

    try:
        response = await llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            max_tokens=2000,
            stream=True
        )
        return response
    except Exception as e:
        async def fallback_stream():
            yield f"LLM 调用失败: {e}\n\n量化信号: {quant_text[:200]}"
        return fallback_stream()


# ==================== 生成回答（非流式）====================
async def generate_answer(query, context_docs, quant_signal) -> str:
    # 同样带 citation 的格式化
    context_text = []
    for i, doc in enumerate(context_docs[:5], 1):
        source = doc.payload.get('source', '未知')
        year = doc.payload.get('year', '未知')
        text = (doc.payload.get('text') or doc.payload.get('content') or '')[:600]
        context_text.append(f"[{i}] 来源：{source} ({year})\n{text}\n")
    
    context_str = "\n---\n".join(context_text)
    quant_text = format_quant_signal_for_llm(quant_signal)
    
    system_prompt = f"""你是化工行业分析师。
当前日期：{CURRENT_DATE}
请基于文档回答问题，每个结论必须引用文档编号如[1]。"""
    
    user_content = f"""问题：{query}

研报：
{context_str}

量化信号：
{quant_text}

请分析："""
    
    try:
        response = await llm_client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.3,
            max_tokens=1500
        )
        answer = response.choices[0].message.content
        # 可选：后处理校验 citation
        return answer
    except Exception as e:
        return f"LLM 调用失败: {e}\n\n量化信号: {quant_text[:300]}"


# ==================== 意图识别 ====================
def classify_intent(query: str) -> str:
    """
    意图识别（基于关键词匹配，兼顾响应速度）。
    """
    quant_keywords = ["买", "卖", "走势", "股票", "行情", "预测", "建议", "信号", "收益"]
    rag_keywords = ["年报", "财报", "报告", "披露", "公告", "研报"]
    
    if any(k in query for k in quant_keywords):
        return "quant"
    if any(k in query for k in rag_keywords):
        return "rag"
    return "hybrid"


# ==================== 工具函数 ====================
def extract_year_from_query(query: str) -> Optional[int]:
    m = re.search(r"(20\d{2})", query)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def extract_company_from_query(query: str) -> tuple[Optional[str], Optional[str]]:
    for code, info in CHEMICAL_STOCK_POOL.items():
        name = info.get("name")
        if not name:
            continue
        if name in query or str(code) in query:
            ticker = f"{code}.SH" if str(code).startswith("6") else f"{code}.SZ"
            return name, ticker
    return None, None


def build_query_filter(query: str):
    must = []
    year = extract_year_from_query(query)
    if year is not None:
        must.append(qmodels.FieldCondition(key="year", match=qmodels.MatchValue(value=year)))

    company, ticker = extract_company_from_query(query)
    if company is not None:
        must.append(qmodels.FieldCondition(key="company", match=qmodels.MatchValue(value=company)))
    if ticker is not None:
        must.append(qmodels.FieldCondition(key="ticker", match=qmodels.MatchValue(value=ticker)))

    if "管理层讨论与分析" in query or "MD&A" in query or "md&a" in query:
        must.append(qmodels.FieldCondition(key="type", match=qmodels.MatchValue(value="mdna")))

    return qmodels.Filter(must=must) if must else None


async def multi_query_expansion(query: str) -> List[str]:
    """Multi-query: 生成多个查询变体以提高召回率。"""
    queries = [query]
    if "走势" in query:
        queries.append(query.replace("走势", "未来行情预测"))
    if "怎么看" in query:
        queries.append(query.replace("怎么看", "深度价值分析"))
    return list(set(queries))


def multi_query_fusion(results_list: List[List[tuple]], k=60):
    """RRF 融合来自不同查询的结果。"""
    fused_scores = {}
    for results in results_list:
        for rank, (doc_id, info) in enumerate(results):
            score = 1 / (k + rank + 1)
            if doc_id not in fused_scores:
                fused_scores[doc_id] = info.copy()
                fused_scores[doc_id]["score"] = 0
            fused_scores[doc_id]["score"] += score
    return sorted(fused_scores.items(), key=lambda x: x[1]["score"], reverse=True)


async def smart_retrieval(query, limit=5):
    """实现 Multi-query, Hybrid Search 权重分配和 Backoff 机制"""
    expanded_queries = await multi_query_expansion(query)
    query_filter = build_query_filter(query)
    
    tasks = [hybrid_search(q, limit=limit * 2, method="rrf", query_filter=query_filter) for q in expanded_queries]
    search_results = await asyncio.gather(*tasks)
    
    fused_results_list = [res[0] for res in search_results]
    sorted_results = multi_query_fusion(fused_results_list)

    if len(sorted_results) < limit:
        fused_weighted, _, _ = await hybrid_search(query, limit=limit * 2, method="weighted", weights=None, query_filter=query_filter)
        existing_ids = {doc_id for doc_id, _ in sorted_results}
        for doc_id, info in fused_weighted:
            if doc_id not in existing_ids:
                sorted_results.append((doc_id, info))
                existing_ids.add(doc_id)

    return sorted_results[:limit]


async def apply_mmr(query: str, docs, top_k: int = 5, candidate_k: int = 10, lambda_param: float = 0.7):
    candidates = docs[:candidate_k]
    if len(candidates) <= top_k:
        return candidates

    def _extract_text(info):
        md = info.get("metadata", {}) if isinstance(info, dict) else {}
        return md.get("text") or md.get("content") or md.get("content_ltks") or ""

    texts = [_extract_text(info) for _, info in candidates]
    if not any(t.strip() for t in texts):
        return candidates[:top_k]

    def _embed():
        q_emb = next(dense_model.query_embed(query)).tolist()
        d_embs = [e.tolist() for e in dense_model.embed(texts)]
        return q_emb, d_embs

    try:
        q_emb, d_embs = await asyncio.to_thread(_embed)
        selected = mmr(q_emb, d_embs, candidates, lambda_param=lambda_param, top_k=top_k)
        return selected
    except Exception:
        return candidates[:top_k]


# ==================== 主 Pipeline ====================
async def rag_quant_pipeline(query: str, streaming: bool = False):
    """
    RAG + Quant 融合主流程
    
    Args:
        query: 用户问题
        streaming: 是否流式输出
    
    Returns:
        包含答案、量化信号、来源的结果
    """
    tracer = Tracer()

    # 1️ 意图识别
    intent = classify_intent(query)

    # 2️ 检索 + 重排 + MMR
    tracer.start("retrieval")
    candidate_docs = await smart_retrieval(query, limit=20)
    
    reranker = Reranker()
    reranked_docs = reranker.rerank(query, candidate_docs)
    
    if settings.ENABLE_MMR:
        final_docs = await apply_mmr(query, reranked_docs, top_k=5, candidate_k=10, lambda_param=settings.MMR_LAMBDA)
    else:
        final_docs = reranked_docs[:5]
    
    tracer.end("retrieval")

    # 3️ 回表获取完整文档
    ids = [doc_id for doc_id, _ in final_docs]
    docs = client.retrieve(
        collection_name=COLLECTION_NAME,
        ids=ids
    )
    
    sources = []
    for d in docs:
        payload = getattr(d, "payload", {}) or {}
        md = payload.get("metadata") or {}
        sources.append({
            "id": str(getattr(d, "id", "")),
            "doc_id": payload.get("doc_id", ""),
            "title": payload.get("title", ""),
            "source": payload.get("source", ""),
            "year": payload.get("year"),
            "company": payload.get("company", ""),
        })

    # 4️ 量化工具调用（核心修改点）
    from app.quant.quant_tool import run_quant_tool
    
    quant_result = None
    if intent in ["quant", "hybrid"] or any(k in query for k in ["股票", "化工", "买", "卖", "预测"]):
        quant_result = run_quant_tool(query)
    
    # 5️ 大模型生成
    if streaming:
        response_stream = await generate_answer_stream(query, docs, quant_result)
        return response_stream
    else:
        answer = await generate_answer(query, docs, quant_result)
        # 添加引用
        answer = add_citation(answer, docs)
        
        return {
            "answer": answer,
            "intent": intent,
            "quant": quant_result,
            "sources": sources,
            "trace": tracer.report()
        }
