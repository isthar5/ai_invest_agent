import os
import subprocess
from tqdm import tqdm

# --- 配置路径 ---
PDF_DIR = r"E:\ai_invest_agent\data\pdfs"          # 你的 277 份 PDF 存放处
OUTPUT_DIR = r"E:\ai_invest_agent\data\markdowns" # 解析后的结果存放处

def run_mineru_batch():
    # 1. 创建输出目录
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    # 2. 获取所有 PDF 文件列表
    pdf_files = [f for f in os.listdir(PDF_DIR) if f.lower().endswith('.pdf')]
    print(f"🚀 找到 {len(pdf_files)} 份年报，准备开始‘降维打击’解析...")

    # 3. 循环调用 magic-pdf 指令
    for pdf_file in tqdm(pdf_files, desc="Parsing PDFs"):
        pdf_path = os.path.join(PDF_DIR, pdf_file)
        
        # 构建命令行指令
        # -device-gpu: 使用你的 3060 加速
        # -m office: 针对年报这种文档效果最好
        command = [
            "magic-pdf",
            "-i", pdf_path,
            "-o", OUTPUT_DIR,
            "-m", "auto",  # 自动识别布局
            "--device-gpu" # 开启显卡炼金模式
        ]

        try:
            # 执行解析
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            print(f"❌ 文件 {pdf_file} 解析失败: {e}")

    print(f"✨ 全部完成！结果已存入: {OUTPUT_DIR}")

if __name__ == "__main__":
    run_mineru_batch()