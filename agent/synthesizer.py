import json
from openai import OpenAI
from app.config.settings import settings

def synthesize_financial_report(skill_data: dict) -> str:
    client = OpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL
    )

    # 提取各部分数据
    financial = skill_data.get("financial", {})
    quant = skill_data.get("quant", {})
    industry = skill_data.get("industry", {})
    fusion = skill_data.get("fusion", {})
    insight = skill_data.get("insight", "")

    prompt = f"""
你是一位资深化工行业投研分析师，请基于以下多源数据生成一份专业分析报告。

【财报数据】
{json.dumps(financial, ensure_ascii=False, indent=2)}

【量化信号】
{json.dumps(quant, ensure_ascii=False, indent=2)}

【行业对标】
{json.dumps(industry, ensure_ascii=False, indent=2)}

【AI 初步洞察】
{insight}

【⚠️ 综合研判（系统融合结论，必须采纳）】
信号类型：{fusion.get('signal_type', '未知')}
置信度：{fusion.get('confidence', '未知')}
核心逻辑：{fusion.get('reasoning', '未知')}
主要风险：{", ".join(fusion.get('risk_factors', ['未知']))}


---
请按以下结构生成 Markdown 报告：

## 一、综合研判结论
（直接引用上方【综合研判】的内容，并稍作展开，100字以内）

## 二、财务健康度分析
- 营收与利润趋势
- 利润率与 ROE 变化
- 现金流质量

## 三、量化信号解读
- 当前信号强度与方向
- 核心驱动因素
- 与基本面的交叉验证

## 四、行业地位与对标
- 行业内百分位排名
- 与竞争对手的量化对比
- 行业趋势判断

## 五、风险提示
- 财务风险
- 量化模型风险
- 行业风险

## 六、免责声明
本报告由 AI 基于公开数据生成，仅供参考，不构成投资建议。
"""
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"报告生成失败: {e}"