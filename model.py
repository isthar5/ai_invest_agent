from modelscope import snapshot_download
import os

# 定义你想要存放模型的路径
model_dir = "E:/ai_invest_agent/models/PDF-Extract-Kit"

if not os.path.exists(model_dir):
    os.makedirs(model_dir)

print("正在从 ModelScope 下载 MinerU 模型包，请保持网络畅通...")

# 下载整个模型仓库
snapshot_download('OpenDataLab/PDF-Extract-Kit', local_dir=model_dir)

print(f"✨ 下载完成！模型已存放在: {model_dir}")