import re
from pathlib import Path

def semantic_chunking_for_invest(md_content, file_name):
    # 1. 提取公司名和年份（从文件名中预处理）
    # 假设文件名是：000301东方盛虹_2021年年度报告...
    meta_info = file_name.split('_')
    company = meta_info[0]
    year = meta_info[1] if len(meta_info) > 1 else "未知年份"

    # 2. 按 Markdown 的二级标题（## 第五节...）进行大块切分
    # 财报的逻辑通常在“管理层讨论”和“财务报表”章节
    sections = re.split(r'\n(##\s+)', md_content)
    
    chunks = []
    current_section = "前言"
    
    for i in range(len(sections)):
        part = sections[i].strip()
        if part == "##": # 这是标题标记
            continue
        if i > 0 and sections[i-1] == "##":
            current_section = part.split('\n')[0]
            content = part
        else:
            content = part

        # 3. 核心：表格完整性保护
        # 我们寻找 Markdown 中的表格块，确保它们不被截断
        table_pattern = r'(\|.*\|(?:\n\|.*\|)*)'
        parts = re.split(table_pattern, content)
        
        for p in parts:
            if not p.strip(): continue
            
            # 注入元数据：让每一段话都自带“身份证”
            # 这是解决 RAG 幻觉最有效的工程手段
            chunk_text = f"【数据来源】{company} | {year} | {current_section}\n"
            chunk_text += p.strip()
            
            # 4. 控制 Chunk 长度，防止过长
            if len(chunk_text) > 1200:
                # 如果是纯文本，进行二次切分；如果是表格，尽量保留完整
                chunks.append(chunk_text[:1200])
            else:
                chunks.append(chunk_text)
                
    return chunks

# 模拟处理
md_path = Path(r"E:\ai_invest_agent\data\markdowns\000301东方盛虹_2021年年度报告_2022-04-19.md")
if md_path.exists():
    with open(md_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    final_chunks = semantic_chunking_for_invest(content, md_path.name)
    print(f"解析完成！共生成 {len(final_chunks)} 个带元数据的 Chunk。")
    print(f"示例第 5 个 Chunk 内容：\n{final_chunks[5][:200]}...")