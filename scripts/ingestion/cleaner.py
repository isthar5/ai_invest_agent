import re


def clean_text(text: str) -> str:
    text = re.sub(r"\r\n", "\n", text)
    text = re.sub(r"\n+", "\n", text)
    text = re.sub(r"第\s*\d+\s*页", "", text)
    text = re.sub(r"[^\w\u4e00-\u9fa5，。！？；：\n]", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()

