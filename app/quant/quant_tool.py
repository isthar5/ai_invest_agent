# app/quant/quant_tool.py
import copy
import json
import os
import functools
from datetime import datetime
from typing import Optional, Dict, Any, List
from app.config.stock_pool import CHEMICAL_STOCK_POOL
from app.config.settings import settings

# ==================== 配置 ====================
CACHE_DIR = str(settings.REPORT_PATH)
os.makedirs(CACHE_DIR, exist_ok=True)


# ==================== 模型缓存（单例模式）====================
@functools.lru_cache(maxsize=1)
def get_cached_pipeline():
    """
    缓存 pipeline 模块，避免每次调用都重新导入
    使用 lru_cache 实现单例模式
    """
    from app.quant.pipeline import run_quant_analysis
    return run_quant_analysis


def run_realtime_quant() -> Dict:
    """
    运行实时量化分析（带缓存优化）
    """
    try:
        # 使用缓存的函数，避免重复导入开销
        run_quant_analysis = get_cached_pipeline()
        return run_quant_analysis()
    except Exception as e:
        return {"error": str(e)}


# ==================== 核心入口 ====================
def _run_quant_tool_uncached(query: str) -> Dict:
    """
    核心入口：给 RAG 调用
    
    分级降级策略：
    1. 实时量化引擎（最新计算）
    2. 预生成 JSON 报告（持久化）
    3. 兜底返回 UNKNOWN
    """
    stock_code = extract_stock(query)

    # 1️⃣ 个股分析
    if stock_code:
        # 第一层：实时量化引擎
        realtime = run_realtime_quant()
        if isinstance(realtime, dict) and "best_stock" in realtime:
            stock_signal = find_stock_in_realtime(realtime, stock_code)
            if stock_signal:
                return stock_signal
        
        # 第二层：预生成报告
        report = load_report(stock_code)
        if "error" not in report:
            return report
        
        # 第三层：兜底信号
        return {
            "stock": stock_code,
            "signal": "UNKNOWN",
            "score": 0.0,
            "trend": "unknown",
            "explanation": "暂无量化数据，请稍后再试"
        }

    # 2️⃣ 行业分析
    if any(keyword in query for keyword in ["化工", "行业", "市场", "板块"]):
        return get_industry_overview()

    return {"msg": "未识别股票或行业，请尝试询问化工行业或具体股票（如万华化学）"}


# ==================== 股票识别 ====================
def extract_stock(query: str) -> Optional[str]:
    """
    从 query 中提取股票代码
    支持：股票名称、股票代码
    """
    # 第一层：匹配股票名称（模糊匹配）
    for code, info in CHEMICAL_STOCK_POOL.items():
        name = info.get("name", "")
        if name and name in query:
            return code
    
    # 第二层：匹配股票代码
    for code in CHEMICAL_STOCK_POOL.keys():
        if code in query:
            return code
    
    return None


@functools.lru_cache(maxsize=32)
def _cached_quant_tool(mode: str, key: str, date_key: str) -> Any:
    if mode == "industry":
        return get_industry_overview()
    return _run_quant_tool_uncached(key)


def run_quant_tool(query: str) -> Any:
    date_key = datetime.now().strftime("%Y%m%d")
    stock_code = extract_stock(query)
    if stock_code:
        mode = "stock"
        key = stock_code
    elif any(keyword in query for keyword in ["化工", "行业", "市场", "板块"]):
        mode = "industry"
        key = "chemical"
    else:
        mode = "query"
        key = query

    result = _cached_quant_tool(mode, key, date_key)
    return copy.deepcopy(result)


# ==================== 实时结果查找 ====================
def find_stock_in_realtime(quant_result: dict, stock_code: str) -> Optional[Dict]:
    """
    在实时量化结果中查找指定股票
    
    特殊逻辑：
    - 万华化学（600309）作为核心资产，即使不在 Top5 也会单独返回
    """
    # 特殊处理：万华化学（核心资产专项优化）
    if stock_code == "600309" and quant_result.get("wanhua_chemical"):
        w = quant_result["wanhua_chemical"]
        score = w.get("prediction_5d_return", 0)
        signal = "POSITIVE" if score > 0.03 else "NEUTRAL"
        trend = "up" if score > 0 else "down"
        return {
            "stock": "600309",
            "name": "万华化学",
            "score": score,
            "signal": signal,
            "trend": trend,
            "industry_rank": w.get("industry_rank"),
            "return_rank": w.get("return_rank"),
            "volume_z": w.get("volume_z"),
            "industry_strength": w.get("industry_strength"),
            "explanation": f"万华化学预测收益 {score:.2%}",
        }
    
    # 检查是否是最佳股票
    best = quant_result.get("best_stock", {})
    if best.get("stock") == stock_code:
        score = best.get("prediction_5d_return", 0)
        signal = "STRONG" if score > 0.05 else "NEUTRAL"
        trend = "up" if score > 0 else "down"
        return {
            "stock": stock_code,
            "score": score,
            "signal": signal,
            "trend": trend,
            "industry_rank": best.get("industry_rank"),
            "return_rank": best.get("return_rank"),
            "volume_z": best.get("volume_z"),
            "industry_strength": best.get("industry_strength"),
            "explanation": _truncate_text(quant_result.get("explanation", ""), 200),
        }
    
    # 检查是否在 Top 5 中
    for s in quant_result.get("top_5", []):
        if s.get("stock") == stock_code:
            score = s.get("pred", 0)
            signal = "POSITIVE" if score > 0.03 else "NEUTRAL"
            trend = "up" if score > 0 else "down"
            return {
                "stock": stock_code,
                "score": score,
                "signal": signal,
                "trend": trend,
                "industry_rank": s.get("industry_rank"),
                "return_rank": s.get("return_rank"),
                "volume_z": s.get("volume_z"),
                "industry_strength": s.get("industry_strength"),
                "explanation": f"该股票入选机会池，预测收益 {score:.2%}",
            }
    
    return None


# ==================== 行业概览 ====================
def get_industry_overview() -> Dict:
    """获取行业概览"""
    realtime = run_realtime_quant()
    
    if "error" in realtime:
        return {"error": realtime["error"]}
    
    return {
        "industry": "化工",
        "date": realtime.get("date", ""),
        "data_date": realtime.get("data_date", ""),
        "best_stock": realtime.get("best_stock", {}),
        "top_5": realtime.get("top_5", []),
        "wanhua": realtime.get("wanhua_chemical", {}),
        "explanation": _truncate_text(realtime.get("explanation", ""), 300)
    }


# ==================== 报告读取（降级方案）====================
def load_report(code: str) -> Dict:
    """读取预生成的 JSON 报告（降级方案）"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, f"{code}.json")
    
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "stock": data.get("stock") or data.get("symbol") or code,
                "score": data.get("latest_score", data.get("score", 0)),
                "signal": data.get("signal", ""),
                "trend": data.get("trend", ""),
                "ret": data.get("ret", 0),
            }
        except (json.JSONDecodeError, IOError) as e:
            return {"error": f"读取报告失败: {e}"}
    
    return {"error": f"{code} 无量化数据"}


# ==================== LLM 格式化输出 ====================
def format_quant_for_llm(stock_code: Optional[str] = None) -> str:
    """
    格式化量化信号为 LLM 可读的文本（Markdown 格式）
    
    这是专门为 LLM 设计的语义化接口：
    - 使用 Emoji 增强可读性
    - 控制输出长度，避免挤占 Context Window
    - 结构化排版，便于 LLM 理解
    """
    if stock_code:
        realtime = run_realtime_quant()
        if "best_stock" in realtime:
            signal = find_stock_in_realtime(realtime, stock_code)
            if signal:
                return f"""
**量化信号 - {signal.get('name', stock_code)}**
- 预测收益率: {signal.get('score', 0):.2%}
- 信号强度: {signal.get('signal', 'NEUTRAL')}
- 趋势判断: {signal.get('trend', 'unknown')}
- 模型解释: {_truncate_text(signal.get('explanation', '暂无'), 150)}
"""
    else:
        overview = get_industry_overview()
        if "error" not in overview:
            top_stocks = overview.get('top_5', [])[:3]
            top_text = "\n".join([
                f"  {i+1}. {s['stock']}: {s['pred']:.2%}"
                for i, s in enumerate(top_stocks)
            ]) if top_stocks else "  暂无数据"
            
            return f"""
**量化引擎 - 化工行业扫描**
- 数据日期: {overview.get('date', 'N/A')}
- 最佳股票: {overview.get('best_stock', {}).get('stock', 'N/A')} 
  (预测收益 {overview.get('best_stock', {}).get('prediction_5d_return', 0):.2%})
- Top 3 机会:
{top_text}
- 万华化学: {overview.get('wanhua', {}).get('prediction_5d_return', 0):.2%}
- 模型解释: {_truncate_text(overview.get('explanation', '暂无'), 150)}
"""
    
    return " 暂无量化数据"


# ==================== 工具函数 ====================
def _truncate_text(text: str, max_length: int) -> str:
    """安全截断文本，避免挤占 LLM Context Window"""
    if not text:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def get_latest_quant_report() -> Dict:
    """获取最新的完整量化报告"""
    return run_realtime_quant()


def get_cached_quant_summary() -> Dict:
    """
    获取缓存的量化摘要（适合高频调用）
    避免每次调用都重新运行量化引擎
    """
    import time
    cache_file = os.path.join(CACHE_DIR, ".summary_cache.json")
    
    # 如果缓存存在且未过期（5分钟内），直接返回
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cache_time = cache.get("_cache_time", 0)
            if time.time() - cache_time < 300:  # 5分钟有效期
                return cache.get("data", {})
        except:
            pass
    
    # 重新计算
    result = get_industry_overview()
    
    # 保存缓存
    try:
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump({
                "_cache_time": time.time(),
                "data": result
            }, f, ensure_ascii=False, indent=2)
    except:
        pass
    
    return result
