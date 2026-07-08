"""
FinancialAnalysisSkill v2.0

v2.0 变更：
- 使用 PromptBuilder 统一构造 LLM messages
- 读取 SharedAgentMemory 获取跨 Agent 上下文
- 写入 SharedAgentMemory 供其他 Agent 消费
"""

import json
import asyncio
from app.agent.base import BaseSkill, SkillResult
from app.agent.registry import SkillRegistry
from app.agent.prompt_builder import PromptBuilder
from app.agent.memory.shared import SharedAgentMemory
from app.services.prompt.registry import get_registry
from app.agent.schemas import (
    FinancialAnalysisOutput,
    FinancialMetrics,
    QuantSignal,
    MetricValue,
    BestStockInfo,
    StockBasicInfo,
)
from app.retrieval.hybrid import hybrid_search
from app.quant.quant_tool import run_quant_tool
from app.config.stock_pool import CHEMICAL_STOCK_POOL
from app.config.settings import settings
from openai import AsyncOpenAI, AuthenticationError


@SkillRegistry.register("financial_analysis")
class FinancialAnalysisSkill(BaseSkill):
    name = "financial_analysis"
    description = "深度财报分析 + 量化信号交叉验证 + 行业对标"

    async def execute(self, state: dict) -> SkillResult:
        query = state.get("query", "")
        stock_code = state.get("stock", "")

        # v2 新增：读取跨 Agent 共享记忆
        shared_context_text = state.get("shared_context_text", "")

        if not stock_code:
            stock_code = self._extract_stock_from_query(query)

        # 1. 文档检索
        go_rag_raw = state.get("go_rag_raw")
        if go_rag_raw and isinstance(go_rag_raw, dict):
            docs_list = go_rag_raw.get("results") or go_rag_raw.get("docs") or []
            if docs_list:
                docs_text = self._merge_go_docs(docs_list)
            else:
                results, _, _ = await hybrid_search(query, limit=10)
                docs_text = self._merge_docs(results)
        else:
            results, _, _ = await hybrid_search(query, limit=10)
            docs_text = self._merge_docs(results)

        try:
            # 2. 财务数据提取（使用 PromptBuilder）
            financial_raw = await self._extract_financials(docs_text, shared_context_text)
            financial = self._build_financial_metrics(financial_raw)

            # 3. 量化信号
            raw_quant = state.get("go_quant_raw") or state.get("quant_raw")
            if raw_quant is None:
                raw_quant = await asyncio.to_thread(run_quant_tool, stock_code or query)

            quant = self._build_quant_signal(raw_quant, stock_code=stock_code)
            peers = self._extract_peer_comparison(raw_quant)

            # 4. 交叉推理（使用 PromptBuilder）
            insight = await self._cross_reasoning(
                financial.dict(), quant.dict(), peers, shared_context_text
            )

            output = FinancialAnalysisOutput(
                financial=financial,
                quant=quant,
                insight=insight,
                data_warning="财报数据可能非最新披露，请以官方公告为准",
                source_count=10 if not go_rag_raw else len(
                    go_rag_raw.get("results", []) or go_rag_raw.get("docs", [])
                ),
            )
            return SkillResult(success=True, data=output.dict())

        except AuthenticationError:
            return SkillResult(
                success=False,
                data={},
                error="LLM 认证失败：请检查 .env 文件中的 DEEPSEEK_API_KEY 是否正确且有效",
            )
        except Exception as e:
            return SkillResult(success=False, data={}, error=f"数据格式校验失败: {e}")

    # ==================== 辅助方法 ====================

    def _merge_go_docs(self, docs: list) -> str:
        texts = []
        for doc in docs[:10]:
            if isinstance(doc, dict):
                text = doc.get("text") or doc.get("content") or doc.get("metadata", {}).get("text") or ""
                if text:
                    texts.append(text[:600])
            elif isinstance(doc, str):
                texts.append(doc[:600])
        return "\n---\n".join(texts)

    def _extract_stock_from_query(self, query: str) -> str:
        for code, info in CHEMICAL_STOCK_POOL.items():
            if info.get("name") in query or code in query:
                return code
        return ""

    def _merge_docs(self, results: list) -> str:
        texts = []
        for doc_id, info in results[:10]:
            md = info.get("metadata", {})
            text = md.get("text") or md.get("content") or ""
            if text:
                texts.append(text[:600])
        return "\n---\n".join(texts)

    async def _extract_financials(
        self, docs_text: str, shared_context: str = ""
    ) -> dict:
        """使用 PromptBuilder 提取财务指标"""
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

        shared_block = (
            f"【跨 Agent 共享上下文】\n{shared_context}" if shared_context else ""
        )
        extraction_prompt = get_registry().render(
            "skills.financial_extraction",
            shared_context=shared_block,
            docs_text=docs_text[:3500],
        )

        messages = PromptBuilder.build_messages(
            query=extraction_prompt,
            memory_context={},
            rag_context="",
            quant_context="",
            system_prompt=PromptBuilder.SYSTEM_PROMPT_EXTRACTION,
            include_history=False,
            include_summary=False,
            include_preferences=False,
        )

        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)

    def _build_financial_metrics(self, raw: dict) -> FinancialMetrics:
        revenue = raw.get("revenue") if isinstance(raw, dict) else None
        net_profit = raw.get("net_profit") if isinstance(raw, dict) else None
        gross_margin = raw.get("gross_margin") if isinstance(raw, dict) else None
        net_margin = raw.get("net_margin") if isinstance(raw, dict) else None
        roe = raw.get("roe") if isinstance(raw, dict) else None
        cash_flow = raw.get("cash_flow") if isinstance(raw, dict) else None
        growth_summary = raw.get("growth_summary") if isinstance(raw, dict) else None
        risk_flags = raw.get("risk_flags") if isinstance(raw, dict) else None

        return FinancialMetrics(
            revenue=MetricValue(**revenue) if isinstance(revenue, dict) else None,
            net_profit=MetricValue(**net_profit) if isinstance(net_profit, dict) else None,
            gross_margin=MetricValue(**gross_margin) if isinstance(gross_margin, dict) else None,
            net_margin=MetricValue(**net_margin) if isinstance(net_margin, dict) else None,
            roe=MetricValue(**roe) if isinstance(roe, dict) else None,
            cash_flow=MetricValue(**cash_flow) if isinstance(cash_flow, dict) else None,
            growth_summary=growth_summary if isinstance(growth_summary, str) else None,
            risk_flags=[str(x) for x in (risk_flags or [])] if isinstance(risk_flags, list) else [],
        )

    def _build_quant_signal(self, raw: dict, stock_code: str = "") -> QuantSignal:
        if isinstance(raw, dict) and raw.get("stock"):
            return QuantSignal(
                stock=str(raw.get("stock")),
                pred_return=raw.get("score"),
                signal=raw.get("signal"),
                trend=raw.get("trend"),
                industry_rank=raw.get("industry_rank"),
                return_rank=raw.get("return_rank"),
                volume_z=raw.get("volume_z"),
                industry_strength=raw.get("industry_strength"),
            )

        if isinstance(raw, dict) and raw.get("top_5"):
            best_raw = raw.get("best_stock") or {}
            best_stock = None
            if isinstance(best_raw, dict) and best_raw.get("stock") is not None:
                best_stock = BestStockInfo(
                    stock=str(best_raw.get("stock")),
                    pred_return=float(best_raw.get("prediction_5d_return", best_raw.get("pred", 0.0))),
                    signal=str(best_raw.get("signal", "NEUTRAL")),
                )

            top_3: list[StockBasicInfo] = []
            for s in (raw.get("top_5") or [])[:3]:
                if not isinstance(s, dict) or s.get("stock") is None:
                    continue
                top_3.append(
                    StockBasicInfo(
                        stock=str(s.get("stock")),
                        pred_return=s.get("pred"),
                    )
                )

            wanhua = raw.get("wanhua") or {}
            wanhua_return = None
            if isinstance(wanhua, dict):
                wanhua_return = wanhua.get("prediction_5d_return")

            return QuantSignal(
                industry=str(raw.get("industry", "化工")),
                best_stock=best_stock,
                top_3=top_3,
                wanhua_return=wanhua_return,
            )

        return QuantSignal(stock=stock_code or None)

    def _extract_peer_comparison(self, raw_quant: dict) -> dict:
        if isinstance(raw_quant, dict) and raw_quant.get("top_5"):
            return {
                "top_peers": raw_quant.get("top_5", [])[:3],
                "industry": raw_quant.get("industry", "化工"),
            }
        return {"top_peers": [], "industry": None}

    async def _cross_reasoning(
        self,
        financial: dict,
        quant: dict,
        peers: dict,
        shared_context: str = "",
    ) -> str:
        """使用 PromptBuilder 进行交叉推理"""
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
        )

        shared_block = (
            f"【跨 Agent 上下文】\n{shared_context}" if shared_context else ""
        )
        reasoning_prompt = get_registry().render(
            "skills.cross_reasoning",
            financial_json=json.dumps(financial, ensure_ascii=False, indent=2),
            quant_json=json.dumps(quant, ensure_ascii=False, indent=2),
            peers_json=json.dumps(peers, ensure_ascii=False, indent=2),
            shared_context=shared_block,
        )

        messages = PromptBuilder.build_simple_user_message(
            query="",
            context_data={"analysis_request": reasoning_prompt},
            instruction="请输出专业分析：",
        )

        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=0.3,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
