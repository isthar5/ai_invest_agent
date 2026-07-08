import math
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from app.agent.schemas import FusionInput, FusionOutput


class CrossSkillFusion:
    """
    跨 Skill 融合决策引擎 v2.0
    
    设计原则：
    1. 连续打分代替硬阈值
    2. 不确定性通过缺失数据惩罚与信号背离计算
    3. 支持信号时效性衰减
    4. 输出结构化，便于回测与 Agent 消费
    """

    # 权重配置（可调参）
    WEIGHT_FINANCIAL = 0.35
    WEIGHT_QUANT = 0.40
    WEIGHT_INDUSTRY = 0.25

    # 衰减半衰期（天）
    DECAY_HALF_LIFE_DAYS = 7.0

    @classmethod
    def fuse(cls, financial: Dict[str, Any], quant: Dict[str, Any], industry: Dict[str, Any], data_timestamp: Optional[datetime] = None) -> Dict[str, Any]:
        """
        主融合接口，返回字典格式（兼容旧版调用）
        """
        # 1. 输入校验与标准化
        inp = FusionInput(financial=financial, quant=quant, industry=industry, data_timestamp=data_timestamp)
        
        # 2. 计算各维度得分
        f_score, f_conf, f_missing = cls._evaluate_financial(inp.financial.dict())
        q_score, q_conf, q_missing = cls._evaluate_quant(inp.quant.dict())
        i_score, i_conf, i_missing = cls._evaluate_industry(inp.industry.dict())

        # 3. 应用时效性衰减（基于 timestamp）
        if inp.data_timestamp:
            decay_factor = cls._compute_decay(inp.data_timestamp)
            q_score *= decay_factor
            i_score *= decay_factor

        # 4. 加权综合得分
        raw_score = (
            cls.WEIGHT_FINANCIAL * f_score +
            cls.WEIGHT_QUANT * q_score +
            cls.WEIGHT_INDUSTRY * i_score
        )

        # 5. 置信度计算（基于数据完整性和信号一致性）
        data_completeness = (f_conf + q_conf + i_conf) / 3.0
        signal_consistency = cls._compute_consistency(f_score, q_score, i_score)
        confidence = data_completeness * signal_consistency

        # 6. 风险评分（缺失数据 + 信号背离 + 高波动）
        risk_score = cls._compute_risk_score(f_missing, q_missing, i_missing, signal_consistency, q_score)

        # 7. 生成结构化输出
        output = cls._build_output(
            raw_score=raw_score,
            confidence=confidence,
            risk_score=risk_score,
            f_score=f_score, q_score=q_score, i_score=i_score,
            missing_flags=f_missing + q_missing + i_missing,
            financial_data=inp.financial,
            quant_data=inp.quant,
            industry_data=inp.industry
        )

        return output.dict()

    # -------------------- 维度评估函数 --------------------
    @classmethod
    def _evaluate_financial(cls, data: Dict[str, Any]) -> Tuple[float, float, list]:
        """
        财务维度评分：返回 (score ∈ [-1,1], confidence, missing_flags)
        """
        missing = []
        score = 0.0
        conf = 1.0

        # 营收增长
        revenue = data.get("revenue", {})
        if revenue and isinstance(revenue, dict):
            yoy = revenue.get("yoy")
            if yoy is not None:
                # 增长率映射到 [-1,1]：-0.3 → -1, 0 → 0, 0.3 → 1
                score += min(max(yoy / 0.3, -1.0), 1.0) * 0.3
            else:
                missing.append("revenue_yoy")
                conf *= 0.9
        else:
            missing.append("revenue")
            conf *= 0.8

        # 净利润增长
        profit = data.get("net_profit", {})
        if profit and isinstance(profit, dict):
            yoy = profit.get("yoy")
            if yoy is not None:
                score += min(max(yoy / 0.3, -1.0), 1.0) * 0.35
            else:
                missing.append("profit_yoy")
                conf *= 0.9
        else:
            missing.append("net_profit")
            conf *= 0.8

        # ROE 水平与变化
        roe = data.get("roe", {})
        if roe and isinstance(roe, dict):
            value = roe.get("value")
            change = roe.get("yoy_change")
            if value is not None:
                # ROE > 15% 视为优秀，<5% 视为较差
                roe_score = min(max((value - 0.05) / 0.15, -1.0), 1.0)
                score += roe_score * 0.2
            if change is not None:
                change_score = min(max(change / 0.05, -1.0), 1.0)
                score += change_score * 0.15
        else:
            missing.append("roe")
            conf *= 0.85

        # 现金流
        cashflow = data.get("cash_flow", {})
        if cashflow and cashflow.get("value") is not None:
            # 正现金流为正向加分
            if cashflow["value"] > 0:
                score += 0.1
        else:
            missing.append("cash_flow")

        # 风险标记惩罚
        risk_flags = data.get("risk_flags", [])
        if risk_flags:
            score -= 0.1 * len(risk_flags)
            conf *= 0.95

        # 截断到 [-1,1]
        score = max(-1.0, min(1.0, score))
        return score, conf, missing

    @classmethod
    def _evaluate_quant(cls, data: Dict[str, Any]) -> Tuple[float, float, list]:
        """
        量化维度评分：基于 industry_rank 或 return_rank 映射到 [-1,1]
        rank 越高（接近1）代表越靠前，得分越高
        """
        missing = []
        score = 0.0
        conf = 1.0

        rank = data.get("industry_rank") or data.get("return_rank")
        if rank is not None:
            # rank ∈ [0,1]，映射到 [-1,1]：rank=0.5 → 0，rank=1 → 1，rank=0 → -1
            score = 2.0 * (rank - 0.5)
        else:
            missing.append("quant_rank")
            conf *= 0.5
            # 尝试从 pred_return 推断
            pred = data.get("pred_return")
            if pred is not None:
                score = min(max(pred / 0.05, -1.0), 1.0)
                conf *= 0.7

        # 成交量 Z 值（情绪代理）
        volume_z = data.get("volume_z")
        if volume_z is not None:
            if volume_z > 2.0:
                # 极端放量可能预示反转风险
                score *= 0.8
            elif volume_z > 1.0:
                score += 0.1 * min(volume_z, 2.0)
        else:
            missing.append("volume_z")

        # 信号强度
        signal = data.get("signal", "")
        if signal == "STRONG":
            score += 0.2
        elif signal == "WEAK":
            score -= 0.2

        score = max(-1.0, min(1.0, score))
        return score, conf, missing

    @classmethod
    def _evaluate_industry(cls, data: Dict[str, Any]) -> Tuple[float, float, list]:
        """
        行业维度评分：基于相对强度和行业趋势
        """
        missing = []
        score = 0.0
        conf = 1.0

        comp = data.get("comparison", {})
        if comp:
            rel_str = comp.get("relative_strength", "0%")
            try:
                rel_val = float(rel_str.replace("%", "")) / 100.0
                # 映射超额收益到 [-1,1]：+5% → 1，-5% → -1
                score = min(max(rel_val / 0.05, -1.0), 1.0)
            except (ValueError, AttributeError):
                missing.append("relative_strength_parse_error")
                conf *= 0.8
        else:
            missing.append("industry_comparison")
            conf *= 0.6

        # 行业趋势
        trend = comp.get("industry_trend", "")
        if trend == "回暖":
            score += 0.15
        elif trend == "走弱":
            score -= 0.15

        # 目标公司排名位置
        target = data.get("target", {})
        ind_rank = target.get("industry_rank")
        if ind_rank is not None:
            rank_score = 2.0 * (ind_rank - 0.5)
            score = 0.7 * score + 0.3 * rank_score
        else:
            missing.append("industry_rank")

        score = max(-1.0, min(1.0, score))
        return score, conf, missing

    # -------------------- 辅助函数 --------------------
    @classmethod
    def _compute_decay(cls, timestamp: Optional[datetime]) -> float:
        """计算时效性衰减因子"""
        if timestamp is None:
            return 1.0
        age_days = (datetime.now() - timestamp).total_seconds() / 86400.0
        decay = math.exp(-math.log(2) * age_days / cls.DECAY_HALF_LIFE_DAYS)
        return max(0.3, decay)  # 不低于 0.3

    @classmethod
    def _compute_consistency(cls, f: float, q: float, i: float) -> float:
        """计算信号一致性：同向得高分，背离得低分"""
        signs = [1 if x > 0 else (-1 if x < 0 else 0) for x in (f, q, i)]
        if signs.count(1) == 3 or signs.count(-1) == 3:
            return 1.0
        elif signs.count(1) == 2 or signs.count(-1) == 2:
            return 0.8
        elif signs.count(0) >= 2:
            return 0.5
        else:
            return 0.3  # 明显背离

    @classmethod
    def _compute_risk_score(cls, f_miss: list, q_miss: list, i_miss: list, consistency: float, q_score: float) -> float:
        """计算风险评分"""
        risk = 0.0
        # 缺失数据惩罚
        total_missing = len(f_miss) + len(q_miss) + len(i_miss)
        risk += min(total_missing * 0.1, 0.5)
        # 低一致性惩罚
        risk += (1.0 - consistency) * 0.3
        # 量化极端值风险（高分可能伴随高波动）
        if abs(q_score) > 0.8:
            risk += 0.15
        return min(risk, 1.0)

    @classmethod
    def _build_output(cls, raw_score: float, confidence: float, risk_score: float,
                      f_score: float, q_score: float, i_score: float,
                      missing_flags: list, financial_data: dict, quant_data: dict, industry_data: dict) -> FusionOutput:
        """构建最终输出"""
        # 确定信号类型
        if confidence < 0.4:
            signal_type = "uncertain"
        elif abs(raw_score) < 0.15:
            signal_type = "neutral"
        elif raw_score > 0:
            if q_score > 0.5 and f_score > 0.2:
                signal_type = "trend_follow"
            elif f_score > 0.3 and q_score < 0.2:
                signal_type = "value_reversal"
            elif q_score > 0.4 and f_score < 0.1:
                signal_type = "sentiment_driven"
            else:
                signal_type = "positive"
        else:
            signal_type = "negative"

        # 生成推理文本
        reasoning = cls._generate_reasoning(signal_type, raw_score, f_score, q_score, i_score)
        risk_factors = cls._extract_risk_factors(financial_data, quant_data, industry_data, missing_flags)

        return FusionOutput(
            signal_type=signal_type,
            score=round(raw_score, 4),
            confidence=round(confidence, 4),
            risk_score=round(risk_score, 4),
            reasoning=reasoning,
            risk_factors=risk_factors,
            missing_data_flags=missing_flags
        )

    @classmethod
    def _generate_reasoning(cls, signal_type: str, total: float, f: float, q: float, i: float) -> str:
        components = []
        if f > 0.2:
            components.append("基本面偏积极")
        elif f < -0.2:
            components.append("基本面承压")
        if q > 0.3:
            components.append("量化信号强势")
        elif q < -0.3:
            components.append("量化信号弱势")
        if i > 0.1:
            components.append("行业相对占优")
        elif i < -0.1:
            components.append("行业相对落后")
        if not components:
            components.append("信号交织")
        prefix = "综合来看，"
        return prefix + "，".join(components) + f"（得分 {total:.2f}）"

    @classmethod
    def _extract_risk_factors(cls, financial, quant, industry, missing: list) -> list:
        risks = []
        # Pydantic 模型属性访问
        risk_flags = getattr(financial, "risk_flags", [])
        if risk_flags:
            risks.extend(list(risk_flags)[:2])
        
        volume_z = getattr(quant, "volume_z", None)
        if volume_z is not None:
            if volume_z > 2.5:
                risks.append("成交量异常放大，警惕情绪过热")
            elif volume_z < -1.5:
                risks.append("成交量极度萎缩，流动性风险")
        
        comp = None
        if industry is not None:
            comp = getattr(industry, "comparison", None)
        if comp is not None:
            conclusion = getattr(comp, "conclusion", "")
            if conclusion and isinstance(conclusion, str) and "弱于同行" in conclusion:
                risks.append("相对行业处于劣势")
        if missing:
            risks.append(f"部分数据缺失: {', '.join(missing[:3])}")
        return risks[:5]
