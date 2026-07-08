import os
import re
from app.ingestion.cleaner import FinancialCleaner

class MarkdownLoader:
    def __init__(self):
        self.cleaner = FinancialCleaner()

    def load(self, md_path):
        with open(md_path, "r", encoding="utf-8") as f:
            text = f.read()

        meta = self._extract_meta(md_path)

        # 🔥 核心：markdown → chunks
        chunks = self._split_markdown(text)

        # 🔥 走你现有 cleaner pipeline
        docs = self.cleaner.process("\n".join(chunks), meta)

        return docs

    # =========================
    # Markdown分块（核心）
    # =========================
    def _split_markdown(self, text):
        lines = text.split("\n")

        chunks = []
        current_chunk = ""
        current_title = ""

        for line in lines:
            line = line.strip()

            # 标题识别
            if line.startswith("#"):
                if current_chunk:
                    chunks.append(current_chunk)

                current_title = line.replace("#", "").strip()
                current_chunk = f"【{current_title}】\n"

            else:
                current_chunk += line + "\n"

        if current_chunk:
            chunks.append(current_chunk)

        return chunks

    # =========================
    # 文件名解析
    # =========================
    def _extract_meta(self, path):
        fname = os.path.basename(path)

        company = "未知公司"
        year = "未知年份"

        m1 = re.findall(r'[\u4e00-\u9fa5]+', fname)
        m2 = re.findall(r'20\d{2}', fname)

        if m1:
            company = m1[0]
        if m2:
            year = m2[0]

        return {
            "company": company,
            "year": year,
            "source": fname
        }