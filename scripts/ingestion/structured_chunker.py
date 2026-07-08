import re


def split_by_paragraph(text: str) -> list[str]:
    paragraphs = re.split(r"\n{2,}", text)
    return [p.strip() for p in paragraphs if len(p.strip()) > 20]


def is_title(line: str) -> bool:
    if len(line) >= 30:
        return False
    if "一、" in line or "二、" in line or "三、" in line or "四、" in line or "五、" in line:
        return True
    if "（一）" in line or "（二）" in line or "（三）" in line or "（四）" in line or "（五）" in line:
        return True
    if re.match(r"^\d+\.\s*", line):
        return True
    return False


def structured_chunk(text: str, max_len: int = 500) -> list[str]:
    paragraphs = split_by_paragraph(text)

    chunks = []
    current_chunk = ""
    current_title = ""

    for para in paragraphs:
        if is_title(para):
            current_title = para
            continue

        combined = f"{current_title}\n{para}" if current_title else para

        if not current_chunk:
            current_chunk = combined
            continue

        if len(current_chunk) + 1 + len(combined) < max_len:
            current_chunk += "\n" + combined
        else:
            chunks.append(current_chunk.strip())
            current_chunk = combined

    if current_chunk:
        chunks.append(current_chunk.strip())

    return chunks


def structured_chunk_pages(pages: list[dict], max_len: int = 500) -> list[dict]:
    chunks = []
    current_chunk = ""
    current_title = ""
    current_pages = set()

    for page in pages:
        page_num = page.get("page_num")
        text = page.get("text") or ""
        for para in split_by_paragraph(text):
            if is_title(para):
                current_title = para
                continue

            combined = f"{current_title}\n{para}" if current_title else para

            if not current_chunk:
                current_chunk = combined
                if page_num is not None:
                    current_pages.add(int(page_num))
                continue

            if len(current_chunk) + 1 + len(combined) < max_len:
                current_chunk += "\n" + combined
                if page_num is not None:
                    current_pages.add(int(page_num))
            else:
                page_range = None
                if current_pages:
                    page_range = [min(current_pages), max(current_pages)]
                chunk_obj = {"text": current_chunk.strip(), "page_range": page_range}
                if page_range and page_range[0] == page_range[1]:
                    chunk_obj["page_num"] = page_range[0]
                chunks.append(chunk_obj)
                current_chunk = combined
                current_pages = set()
                if page_num is not None:
                    current_pages.add(int(page_num))

    if current_chunk:
        page_range = None
        if current_pages:
            page_range = [min(current_pages), max(current_pages)]
        chunk_obj = {"text": current_chunk.strip(), "page_range": page_range}
        if page_range and page_range[0] == page_range[1]:
            chunk_obj["page_num"] = page_range[0]
        chunks.append(chunk_obj)

    return chunks
