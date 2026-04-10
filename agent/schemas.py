from pydantic import BaseModel, Field, validator
from typing import Optional, List, Literal
from datetime import datetime


# ======================
# 基础类型定义
# ======================
class MetricValue(BaseModel):
    """数值指标（带单位与同比）"""
    value: Optional[float] = Field(None, description="数值")
    unit: Optional[str] = Field(None, description="单位（如亿元）")
    yoy: Optional[float] = Field(None, ge=-1.0, le=10.0, description="同比增长率，小数形式")
    yoy_change: Optional[float] = Field(None, description="同比变化量（用于利润率等）")

    class Config:
        extra = "forbid"


class StockBasicInfo(BaseModel):
    """股票基本信息（用于行业对标中的同行条目）"""
    stock: str = Field(..., description="股票代码")
    pred_return: Optional[float] = Field(None, description="预测收益率")


# ======================
# 财务指标模型
# ======================
class FinancialMetrics(BaseModel):
    """财务分析核心指标"""
    version: Literal["v1"] = "v1"
    revenue: Optional[MetricValue] = Field(None, description="营业收入")
    net_profit: Optional[MetricValue] = Field(None, description="归母净利润")
    gross_margin: Optional[MetricValue] = Field(None, description="毛利率")
    net_margin: Optional[MetricValue] = Field(None, description="净利率")
    roe: Optional[MetricValue] = Field(None, description="净资产收益率")
    cash_flow: Optional[MetricValue] = Field(None, description="经营活动现金流净额")
    growth_summary: Optional[str] = Field(None, description="增长趋势总结")
    risk_flags: List[str] = Field(default_factory=list, description="风险标记")

    class Config:
        extra = "forbid"


# ======================
# 量化信号模型（拆解为具体子模型）
# ======================
class BestStockInfo(BaseModel):
    """最佳股票信息"""
    stock: str = Field(..., description="股票代码")
    pred_return: float = Field(..., description="预测收益率")
    signal: str = Field("NEUTRAL", description="信号强度")


class QuantSignal(BaseModel):
    """量化信号标准化模型"""
    version: Literal["v1"] = "v1"
    stock: Optional[str] = Field(None, description="股票代码")
    pred_return: Optional[float] = Field(None, description="预测收益率")
    signal: Optional[str] = Field(None, description="信号强度（STRONG/POSITIVE/NEUTRAL/WEAK）")
    trend: Optional[str] = Field(None, description="趋势方向")
    industry_rank: Optional[float] = Field(None, ge=0.0, le=1.0, description="行业排名百分位（0-1，越大越强）")
    return_rank: Optional[float] = Field(None, ge=0.0, le=1.0, description="全市场排名百分位")
    volume_z: Optional[float] = Field(None, description="成交量Z-score")
    industry_strength: Optional[float] = Field(None, description="行业强度")
    
    # 行业扫描模式专用字段（拆解为具体类型）
    industry: Optional[str] = Field(None, description="行业名称")
    best_stock: Optional[BestStockInfo] = Field(None, description="最佳股票")
    top_3: Optional[List[StockBasicInfo]] = Field(None, description="Top3股票")
    wanhua_return: Optional[float] = Field(None, description="万华化学预测收益")

    class Config:
        extra = "forbid"


# ======================
# 行业对标模型（彻底去除 Dict）
# ======================
class TargetMetrics(BaseModel):
    """目标公司关键指标"""
    stock: str = Field(..., description="股票代码")
    pred_return: Optional[float] = Field(None)
    signal: Optional[str] = Field(None)
    trend: Optional[str] = Field(None)
    industry_rank: Optional[float] = Field(None, ge=0.0, le=1.0)
    return_rank: Optional[float] = Field(None, ge=0.0, le=1.0)
    volume_z: Optional[float] = Field(None)
    industry_strength: Optional[float] = Field(None)

    class Config:
        extra = "forbid"


class DetailedMetrics(BaseModel):
    """详细对比数值"""
    target_pred_return: Optional[float] = Field(None)
    peer_avg_pred_return: Optional[float] = Field(None)
    return_rank: Optional[float] = Field(None)
    industry_rank: Optional[float] = Field(None)
    volume_z: Optional[float] = Field(None)

    class Config:
        extra = "forbid"


class ComparisonDetail(BaseModel):
    """对比分析详细结果"""
    target_position: Optional[str] = Field(None, description="目标位置描述")
    relative_strength: Optional[str] = Field(None, description="相对强弱百分比字符串")
    industry_trend: Optional[str] = Field(None, description="行业趋势")
    volume_sentiment: Optional[str] = Field(None, description="成交量情绪")
    peer_avg_return: Optional[str] = Field(None, description="同行平均预测收益")
    conclusion: Optional[str] = Field(None, description="对比结论")
    detailed_metrics: Optional[DetailedMetrics] = Field(None, description="详细数值")

    class Config:
        extra = "forbid"


class IndustryComparisonOutput(BaseModel):
    """行业对标 Skill 完整输出"""
    version: Literal["v1"] = "v1"
    industry: str = Field("化工", description="行业名称")
    target: TargetMetrics = Field(..., description="目标公司指标")
    peers: List[StockBasicInfo] = Field(default_factory=list, description="同行公司列表")
    comparison: ComparisonDetail = Field(default_factory=ComparisonDetail, description="对比分析结果")
    data_source: Optional[str] = Field(None, description="数据来源说明")

    class Config:
        extra = "forbid"


# ======================
# 财报分析 Skill 完整输出
# ======================
class FinancialAnalysisOutput(BaseModel):
    """FinancialAnalysisSkill 完整输出结构"""
    version: Literal["v1"] = "v1"
    financial: FinancialMetrics = Field(..., description="财报指标")
    quant: QuantSignal = Field(..., description="量化信号")
    insight: str = Field(..., description="交叉推理洞察")
    data_warning: Optional[str] = Field(None, description="数据时效性警告")
    source_count: int = Field(0, ge=0, description="RAG检索文档数")

    class Config:
        extra = "forbid"


# ======================
# 融合模块输入模型
# ======================
class FusionInput(BaseModel):
    """跨技能融合输入"""
    version: Literal["v1"] = "v1"
    financial: FinancialMetrics = Field(..., description="财务指标")
    quant: QuantSignal = Field(..., description="量化信号")
    industry: IndustryComparisonOutput = Field(..., description="行业对标数据")
    data_timestamp: Optional[datetime] = Field(None, description="数据产生时间（财报发布日期或量化计算日期）")

    class Config:
        extra = "forbid"


# ======================
# 融合输出模型
# ======================
class FusionOutput(BaseModel):
    """融合决策输出"""
    version: Literal["v1"] = "v1"
    signal_type: str = Field(..., description="信号类型: trend_follow, value_reversal, sentiment_driven, weak, uncertain")
    score: float = Field(..., ge=-1.0, le=1.0, description="综合得分")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")
    risk_score: float = Field(..., ge=0.0, le=1.0, description="风险评分")
    reasoning: str = Field(..., description="决策逻辑简述")
    risk_factors: List[str] = Field(default_factory=list, description="具体风险因素")
    missing_data_flags: List[str] = Field(default_factory=list, description="缺失数据标记")

    class Config:
        extra = "forbid"


# ======================
# 辅助校验函数（供 Skill 直接调用）
# ======================
def validate_financial_analysis(data: dict) -> FinancialAnalysisOutput:
    """校验并返回财务分析输出对象"""
    return FinancialAnalysisOutput(**data)


def validate_industry_comparison(data: dict) -> IndustryComparisonOutput:
    """校验并返回行业对标输出对象"""
    return IndustryComparisonOutput(**data)


def validate_fusion_input(data: dict) -> FusionInput:
    """校验融合输入"""
    return FusionInput(**data)