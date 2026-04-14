import asyncio
from typing import Dict, List, Any, Optional
from app.agent.base import BaseSkill, SkillResult
from app.agent.registry import SkillRegistry
from app.agent.schemas import IndustryComparisonOutput, TargetMetrics, StockBasicInfo, ComparisonDetail, DetailedMetrics
from app.quant.quant_tool import run_quant_tool
from app.quant.factor_engine import FactorEngineV2  # 如需直接调用底层因子
import logging

logger = logging.getLogger(__name__)

@SkillRegistry.register("industry_comparison")
class IndustryComparisonSkill(BaseSkill):
    name = "industry_comparison"
    description = "化工行业横向对标分析：对比目标公司与竞争对手的量化排名、基本面与行业强度"

    # 化工行业默认股票池（与 quant 模块保持一致）
    CHEMICAL_PEERS = ["600309", "600426", "002493", "600346", "002064"]  # 万华、华鲁、荣盛、恒力、华峰

    async def execute(self, state: dict) -> SkillResult:
        stock = state.get("stock", "").strip()
        if not stock:
            return SkillResult(success=False, error="缺少股票代码，无法进行行业对比")

        # 确保是化工行业股票（可选校验）
        if stock not in self.CHEMICAL_PEERS:
            logger.warning(f"股票 {stock} 不在预设化工股票池中，分析可能不准确")

        # 1. 优先尝试使用 Go-agent 预取的量化结果
        raw_quant = state.get("go_quant_raw") or state.get("quant_raw")
        if not (isinstance(raw_quant, dict) and (raw_quant.get("stock") == stock or raw_quant.get("top_5"))):
            try:
                raw_quant = await asyncio.to_thread(run_quant_tool, stock)
            except Exception as e:
                return SkillResult(success=False, error=f"量化数据获取失败: {str(e)}")

        # 2. 提取目标公司的关键指标
        target_metrics = self._extract_target_metrics(raw_quant, stock)

        # 3. 提取同行公司的指标（从 quant 的 top_5 或其他来源）
        peers_metrics = self._extract_peers_metrics(raw_quant, stock)

        # 4. 构建对比分析
        comparison = self._build_comparison(target_metrics, peers_metrics)

        try:
            output = IndustryComparisonOutput(
                industry="化工",
                target=target_metrics,
                peers=peers_metrics,
                comparison=comparison,
                data_source="量化横截面因子 + 行业强度模型",
            )
            return SkillResult(success=True, data=output.dict())
        except Exception as e:
            return SkillResult(success=False, error=f"数据格式校验失败: {e}")

    def _extract_target_metrics(self, quant: dict, stock: str) -> TargetMetrics:
        """从量化结果中提取目标股票的详细指标"""
        # 优先从 "stock" 字段获取个股信号
        if "stock" in quant and quant.get("stock") == stock:
            return TargetMetrics(
                stock=stock,
                pred_return=quant.get("score", 0.0),
                signal=quant.get("signal", "NEUTRAL"),
                trend=quant.get("trend", "unknown"),
                industry_rank=quant.get("industry_rank"),
                return_rank=quant.get("return_rank"),
                volume_z=quant.get("volume_z"),
                industry_strength=quant.get("industry_strength"),
            )

        # 降级：从行业扫描结果中查找
        if "top_5" in quant:
            for s in quant["top_5"]:
                if s.get("stock") == stock:
                    return TargetMetrics(
                        stock=stock,
                        pred_return=s.get("pred", 0.0),
                        industry_rank=quant.get("industry_rank"),
                        return_rank=None,
                        volume_z=None,
                        industry_strength=quant.get("industry_strength"),
                    )

        # 如果都没找到，返回基础信息
        return TargetMetrics(
            stock=stock,
            pred_return=0.0,
            industry_rank=None,
            return_rank=None,
            volume_z=None,
            industry_strength=None,
        )

    def _extract_peers_metrics(self, quant: dict, target_stock: str) -> List[StockBasicInfo]:
        """提取同行业其他股票的指标"""
        peers: list[StockBasicInfo] = []

        # 方法1：从 quant 的 top_5 中提取（排除目标股票）
        if "top_5" in quant:
            for s in quant["top_5"]:
                if s.get("stock") != target_stock:
                    if s.get("stock") is None:
                        continue
                    peers.append(
                        StockBasicInfo(
                            stock=str(s.get("stock")),
                            pred_return=s.get("pred", 0.0),
                        )
                    )
            if peers:
                return peers[:4]  # 最多返回4个同行

        # 方法2：如果 top_5 不足，可以调用 factor_engine 获取预设股票池的数据
        # 这里简化，直接返回预设股票池中除目标外的股票（需要实际数据填充）
        other_stocks = [c for c in self.CHEMICAL_PEERS if c != target_stock][:4]
        # 实际应用中，应该批量获取这些股票的最新量化信号
        # 这里仅返回占位符，真实实现需调用量化接口
        return [StockBasicInfo(stock=code, pred_return=0.0) for code in other_stocks]

    def _build_comparison(self, target: TargetMetrics, peers: List[StockBasicInfo]) -> ComparisonDetail:
        """构建详细的对比分析"""
        if not peers:
            return ComparisonDetail(conclusion="同行数据不足，无法进行对比")

        # 计算同行平均预测收益
        peer_returns = [p.pred_return for p in peers if p.pred_return is not None]
        avg_peer_return = sum(peer_returns) / len(peer_returns) if peer_returns else 0.0
        target_pred = target.pred_return or 0.0
        return_diff = target_pred - avg_peer_return

        # 排名解读
        industry_rank = target.industry_rank
        rank_text = f"行业前{int((1 - industry_rank) * 100)}%" if industry_rank is not None else "排名未知"

        # 行业强度趋势
        industry_strength = target.industry_strength
        strength_trend = "回暖" if industry_strength and industry_strength > 0.02 else "平稳" if industry_strength else "未知"

        # 相对强弱结论
        if return_diff > 0.01:
            relative_conclusion = f"显著强于同行（超额收益 +{return_diff:.2%}）"
        elif return_diff > 0:
            relative_conclusion = f"略强于同行（超额收益 +{return_diff:.2%}）"
        elif return_diff > -0.01:
            relative_conclusion = f"略弱于同行（超额收益 {return_diff:.2%}）"
        else:
            relative_conclusion = f"显著弱于同行（超额收益 {return_diff:.2%}）"

        # 成交量情绪
        volume_z = target.volume_z
        volume_sentiment = "资金关注度高" if volume_z and volume_z > 1.5 else "资金关注度正常" if volume_z else "未知"

        return ComparisonDetail(
            target_position=rank_text,
            relative_strength=f"{return_diff:+.2%}",
            industry_trend=strength_trend,
            volume_sentiment=volume_sentiment,
            peer_avg_return=f"{avg_peer_return:.2%}",
            conclusion=f"{relative_conclusion}，{volume_sentiment}，行业趋势{strength_trend}。",
            detailed_metrics=DetailedMetrics(
                target_pred_return=target.pred_return,
                peer_avg_pred_return=avg_peer_return,
                return_rank=target.return_rank,
                industry_rank=industry_rank,
                volume_z=volume_z,
            ),
        )
