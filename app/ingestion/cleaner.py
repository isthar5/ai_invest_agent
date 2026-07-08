import re
from langchain_text_splitters import RecursiveCharacterTextSplitter

class FinancialCleaner:
    def __init__(self):
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=800, # 表格保护需要略微增加窗口
            chunk_overlap=150,
            separators=["\n\n", "\n", "。", "；", ""]
        )

    def _is_table_row(self, line):
        """判断是否为表格行：包含分隔符且数字较多"""
        return "|" in line and len(re.findall(r'\d', line)) > 2

    def process(self, raw_text, meta):
        # 1. 预处理：识别并保护表格结构
        lines = raw_text.split('\n')
        processed_lines = []
        for line in lines:
            if self._is_table_row(line):
                processed_lines.append(f"[TABLE_DATA] {line}") # 标记表格
            else:
                processed_lines.append(line)
        
        text = "\n".join(processed_lines)
        
        # 2. 递归切分
        raw_chunks = self.splitter.split_text(text)
        
        enhanced_chunks = []
        for c in raw_chunks:
            # 3. 动态提取 Section (增强点)
            section = "正文内容"
            if "管理层讨论" in c[:100]: section = "管理层讨论与分析"
            elif "财务报表" in c[:100]: section = "财务报表"
            elif "风险" in c[:100]: section = "风险提示"

            # 4. Prefix 注入 (Prefix + Section)
            prefix = f"【{meta['company']} | {meta['year']} | {section}】\n"
            
            enhanced_chunks.append({
                "content": prefix + c,
                "metadata": {
                    **meta,
                    "section": section,
                    "has_table": "[TABLE_DATA]" in c
                }
            })
        return enhanced_chunks