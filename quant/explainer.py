import numpy as np

def summarize_shap(feature_names, shap_values, topk=5):
    """计算特征重要性"""
    # 确保 shap_values 是 1D 数组
    if hasattr(shap_values, 'shape') and len(shap_values.shape) > 1:
        importance = np.abs(shap_values).mean(axis=0)
    else:
        importance = np.abs(shap_values)
    
    # 确保长度匹配
    if len(feature_names) != len(importance):
        # 如果长度不匹配，取较小的长度
        min_len = min(len(feature_names), len(importance))
        feature_names = feature_names[:min_len]
        importance = importance[:min_len]
    
    pairs = list(zip(feature_names, importance))
    pairs.sort(key=lambda x: x[1], reverse=True)
    return pairs[:topk]

def generate_text(top_features):
    text = "模型核心驱动因子：\n"
    for name, val in top_features:
        text += f"- {name}: {val:.4f}\n"
    return text