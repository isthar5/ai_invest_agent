# tests/unit/test_schemas.py
import pytest
from pydantic import ValidationError
from app.agent.schemas import FinancialMetrics, MetricValue, QuantSignal

def test_metric_value_validation():
    """测试 MetricValue 校验"""
    # 有效数据
    metric = MetricValue(value=1820.0, unit="亿元", yoy=0.123)
    assert metric.value == 1820.0
    
    # 无效数据（yoy 超出范围）
    with pytest.raises(ValidationError):
        MetricValue(value=100, yoy=100.0)

def test_financial_metrics_validation():
    """测试 FinancialMetrics 校验"""
    revenue = MetricValue(value=1820.0, unit="亿元", yoy=0.12)
    metrics = FinancialMetrics(revenue=revenue)
    assert metrics.revenue.value == 1820.0
    assert metrics.version == "v1"

def test_quant_signal_validation():
    """测试 QuantSignal 校验"""
    # industry_rank 必须在 0-1 之间
    signal = QuantSignal(stock="600309", industry_rank=0.85)
    assert signal.industry_rank == 0.85
    
    with pytest.raises(ValidationError):
        QuantSignal(stock="600309", industry_rank=1.5)