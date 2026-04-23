# app/agent/skills/financial_analysis.py
import json
import asyncio
from app.agent.base import BaseSkill, SkillResult
from app.agent.registry import SkillRegistry
from app.agent.schemas import FinancialAnalysisOutput, FinancialMetrics, QuantSignal, MetricValue, BestStockInfo, StockBasicInfo
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

        if not stock_code:
            stock_code = self._extract_stock_from_query(query)

        # 1. 优先尝试使用 Go-agent 预取的 RAG 结果
        go_rag_raw = state.get("go_rag_raw")
        if go_rag_raw and isinstance(go_rag_raw, dict):
            # 假设 Go-agent 的 rag_search 返回格式中包含 docs 或 results
            # 如果不确定格式，这里可以做简单的解析尝试
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
            financial_raw = await self._extract_financials(docs_text)
            financial = self._build_financial_metrics(financial_raw)

            # 2. 优先尝试使用 Go-agent 预取的量化结果
            raw_quant = state.get("go_quant_raw") or state.get("quant_raw")
            if raw_quant is None:
                raw_quant = await asyncio.to_thread(run_quant_tool, stock_code or query)
            
            quant = self._build_quant_signal(raw_quant, stock_code=stock_code)
            peers = self._extract_peer_comparison(raw_quant)
            insight = await self._cross_reasoning(financial.dict(), quant.dict(), peers)

            output = FinancialAnalysisOutput(
                financial=financial,
                quant=quant,
                insight=insight,
                data_warning="财报数据可能非最新披露，请以官方公告为准",
                source_count=10 if not go_rag_raw else len(go_rag_raw.get("results", []) or go_rag_raw.get("docs", [])),
            )
            return SkillResult(success=True, data=output.dict())
        except AuthenticationError:
            return SkillResult(
                success=False, 
                data={}, 
                error="LLM 认证失败：请检查 .env 文件中的 DEEPSEEK_API_KEY 是否正确且有效"
            )
        except Exception as e:
            return SkillResult(success=False, data={}, error=f"数据格式校验失败: {e}")

    # -------------------- 辅助方法 --------------------
    def _merge_go_docs(self, docs: list) -> str:
        """合并 Go-agent 返回的文档列表"""
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

    async def _extract_financials(self, docs_text: str) -> dict:
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL
        )
        prompt = f"""
        从以下财报内容中提取关键财务指标，严格按指定 JSON 格式输出。

        内容：
        {docs_text[:3500]}

        要求：
        1. 数值统一为 float 类型，增长率以小数表示（如 12% → 0.12）
        2. 无法提取的字段填 null

        输出格式：
        {{
          "revenue": {{"value": 1820.0, "unit": "亿元", "yoy": 0.123}},
          "net_profit": {{"value": 210.0, "unit": "亿元", "yoy": 0.087}},
          "gross_margin": {{"value": 0.195, "yoy_change": 0.013}},
          "net_margin": {{"value": 0.115, "yoy_change": -0.004}},
          "roe": {{"value": 0.152, "yoy_change": 0.007}},
          "cash_flow": {{"value": 280.0, "unit": "亿元", "yoy": 0.15}},
          "growth_summary": "营收稳健增长，利润率小幅改善",
          "risk_flags": ["原材料价格波动", "汇率风险"]
        }}
        """
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
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

    async def _cross_reasoning(self, financial: dict, quant: dict, peers: dict) -> str:
        client = AsyncOpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL
        )
        prompt = f"""
        财报数据：{json.dumps(financial, ensure_ascii=False, indent=2)}
        量化信号：{json.dumps(quant, ensure_ascii=False, indent=2)}
        行业对标：{json.dumps(peers, ensure_ascii=False, indent=2)}

        请以专业投研分析师视角回答：

        1. 量化预测的上涨/下跌是否有基本面支撑？
        2. 是否存在“情绪驱动”迹象？（结合 volume_z 与 rank）
        3. 判断该信号的持续性：短期炒作 / 中期趋势 / 长期价值？
        4. 与行业竞争对手相比，该股票处于什么位置？
        5. 指出 1-2 个最关键的风险点。

        输出一段 150-200 字的专业分析。
        """
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=400
        )
        return resp.choices[0].message.content.strip()
