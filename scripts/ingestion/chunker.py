def chunk_text(text: str, chunk_size: int = 400, overlap: int = 50) -> list[str]:
    if chunk_size <= 0:
        return []
    overlap = max(0, min(overlap, chunk_size - 1))
    chunks = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end]
        if chunk.strip():
            chunks.append(chunk)
        start += chunk_size - overlap
    return chunks

