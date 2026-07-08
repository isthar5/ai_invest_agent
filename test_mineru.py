import os
from magic_pdf.pipe.ocrmd_pipe import OCRMDPipe
from magic_pdf.data.data_reader_writer import FileBasedDataReader, FileBasedDataWriter

# 路径设置
pdf_dir = r"E:\ai_invest_agent\data\pdfs"
output_dir = r"E:\ai_invest_agent\data\markdowns"
# 确保输出目录存在
os.makedirs(output_dir, exist_ok=True)

# 获取第一个 PDF
pdf_name = [f for f in os.listdir(pdf_dir) if f.endswith('.pdf')][0]
pdf_path = os.path.join(pdf_dir, pdf_name)

print(f"开始炼金: {pdf_name} (使用 3060 加速中...)")

try:
    # 1. 读写准备
    image_writer = FileBasedDataWriter(os.path.join(output_dir, "images"))
    md_writer = FileBasedDataWriter(output_dir)
    reader = FileBasedDataReader("")
    pdf_bytes = reader.read(pdf_path)

    # 2. 初始化最新版 Pipe
    # model_list 传空，它会自动读取 C:\Users\admin\magic-pdf.json 里的模型路径
    pipe = OCRMDPipe(pdf_bytes, model_list=[], image_writer=image_writer)

    # 3. 执行完整流程
    pipe.pipe_classify()
    pipe.pipe_analyze()
    pipe.pipe_parse()

    # 4. 生成结果
    pipe.pipe_mk_markdown(pdf_name.replace(".pdf", ""), output_dir)
    print("✨ 恭喜！解析成功。")

except Exception as e:
    import traceback
    traceback.print_exc()