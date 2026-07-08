from app.quant.factor_engine import build_features
from app.quant.explainer import generate_text, summarize_shap
from app.quant.model import QuantModel
import json
from datetime import datetime
import pandas as pd
import sys
import os

def save_quant_report(result_dict: dict, date_str: str = None):
    """保存量化报告到 JSON 文件"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    
    # 创建 reports 目录
    report_path = "E:/ai_invest_agent/reports"
    os.makedirs(report_path, exist_ok=True)
    
    # 保存每日报告
    daily_file = os.path.join(report_path, f"{date_str}.json")
    with open(daily_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=4)
    
    # 保存最新报告（覆盖）
    latest_file = os.path.join(report_path, "latest.json")
    with open(latest_file, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, ensure_ascii=False, indent=4)
    
    print(f"✅ 量化报告已保存: {daily_file}")
    return latest_file

root_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root_path not in sys.path:
    sys.path.append(root_path)

try:
    from app.config.stock_pool import STOCK_LIST as CHEMICAL_STOCKS
except:
    CHEMICAL_STOCKS = ["600309", "600426", "002493"]


def run_quant_analysis(stock_list=CHEMICAL_STOCKS):
    # 1. 因子构建
    df = build_features(stock_list)
    
    # 2. 🔥 强制转换所有数值列为 float
    print("转换数据类型...")
    for col in df.columns:
        if col not in ['date', 'tic']:
            try:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            except:
                pass
    
    # 3. 删除 NaN
    before = len(df)
    df = df.dropna()
    print(f"删除空值: {before} -> {len(df)}")
    
    df = df.sort_values(["tic", "date"]).reset_index(drop=True)
    print(f"数据量: {len(df)}")

    # 4. 目标变量（未来5日收益）
    df["target"] = df.groupby("tic")["close"].shift(-5) / df["close"] - 1
    df = df.dropna().reset_index(drop=True)

    # 5. 特征列表
    exclude = ["date", "tic", "target"]
    features = [c for c in df.columns if c not in exclude]
    print(f"特征数量: {len(features)}")

    # 6. 时间切分
    split_idx = int(len(df) * 0.8)
    X_train = df.iloc[:split_idx][features]
    y_train = df.iloc[:split_idx]["target"]
    X_test = df.iloc[split_idx:][features]
    print(f"训练集: {len(X_train)} 测试集: {len(X_test)}")

    # 7. 训练模型
    model = QuantModel()
    model.train(X_train, y_train)

    # 8. 全量预测
    preds, _ = model.predict(df[features])
    df["pred"] = preds

    # 9. 最新截面
    latest_date = df["date"].max()
    latest_df = df[df["date"] == latest_date].copy()
    latest_df = latest_df.sort_values("pred", ascending=False)

    # 10. 提取结果
    best_row = latest_df.iloc[0] if len(latest_df) > 0 else None
    wanhua = latest_df[latest_df["tic"] == "600309"]
    wanhua_row = wanhua.iloc[0] if len(wanhua) > 0 else None

    # 11. SHAP 解释
    explanation = "无法生成解释"
    if best_row is not None and len(features) > 0:
        try:
            best_features = best_row[features].values.reshape(1, -1).astype(float)
            _, shap_values = model.predict(pd.DataFrame(best_features, columns=features))
            if shap_values is not None and len(shap_values) > 0:
                top_features = summarize_shap(features, shap_values[0])
                explanation = generate_text(top_features)
        except Exception as e:
            explanation = f"SHAP计算失败: {e}"
    result = {
        "date": latest_date.strftime("%Y-%m-%d"),
        "data_date": "2026-03-20",  # 实际数据截止日期
        "best_stock": {
            "stock": str(best_row["tic"]) if best_row is not None else "N/A",
            "prediction_5d_return": float(best_row["pred"]) if best_row is not None else 0.0,
            "industry_rank": float(best_row.get("industry_rank", 0)) if best_row is not None else 0,
        },
        "wanhua_chemical": {
            "stock": "600309",
            "name": "万华化学",
            "prediction_5d_return": float(wanhua_row["pred"]) if wanhua_row is not None else 0.0,
            "industry_rank": float(wanhua_row.get("industry_rank", 0)) if wanhua_row is not None else 0,
        },
        "top_5": [
            {"stock": str(row["tic"]), "pred": float(row["pred"])} 
            for _, row in latest_df.head(5).iterrows()
        ],
        "explanation": explanation,
        "feature_importance": top_features if 'top_features' in dir() else []
    }
    
    # 保存报告
    save_quant_report(result, latest_date.strftime("%Y-%m-%d"))
    

    # 12. 返回结果
    return {
        "date": latest_date.strftime("%Y-%m-%d"),
        "best_stock": {
            "stock": str(best_row["tic"]) if best_row is not None else "N/A",
            "prediction_5d_return": float(best_row["pred"]) if best_row is not None else 0.0,
        },
        "wanhua_chemical": {
            "stock": "600309",
            "prediction_5d_return": float(wanhua_row["pred"]) if wanhua_row is not None else 0.0,
        },
        "top_5": latest_df.head(5)[["tic", "pred"]].to_dict(orient="records"),
        "explanation": explanation
    }


if __name__ == "__main__":
    result = run_quant_analysis()
    print("\n" + "="*50)
    print("量化分析结果:")
    print("="*50)
    print(f"日期: {result['date']}")
    print(f"最佳股票: {result['best_stock']['stock']} (预测收益: {result['best_stock']['prediction_5d_return']:.4f})")
    print(f"万华化学: {result['wanhua_chemical']['prediction_5d_return']:.4f}")
    print(f"\nTop 5 股票:")
    for s in result['top_5']:
        print(f"  {s['tic']}: {s['pred']:.4f}")
    print(f"\n{result['explanation']}")