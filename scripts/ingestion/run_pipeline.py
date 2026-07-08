import os
import json

from scripts.ingestion.pdf_to_text import batch_process
from scripts.ingestion.cleaner import clean_text
from scripts.ingestion.chunker import chunk_text
from scripts.ingestion.embed_and_store import get_client, get_collection_name, create_collection, store_chunks
from scripts.ingestion.mdna_extractor import extract_mdna, extract_mdna_robust
from scripts.ingestion.structured_chunker import structured_chunk, structured_chunk_pages


def run():
    input_dir = os.getenv("INGEST_PDF_DIR", "./data/pdf")
    text_dir = os.getenv("INGEST_TEXT_DIR", "./data/text")
    recreate = os.getenv("INGEST_RECREATE_COLLECTION", "0") == "1"
    chunk_size = int(os.getenv("INGEST_CHUNK_SIZE", "400"))
    overlap = int(os.getenv("INGEST_CHUNK_OVERLAP", "50"))
    doc_type = os.getenv("INGEST_DOC_TYPE", "report")
    mdna_only = os.getenv("INGEST_MDNA_ONLY", "0") == "1"
    mdna_robust = os.getenv("INGEST_MDNA_ROBUST", "1") == "1"
    structured = os.getenv("INGEST_STRUCTURED_CHUNK", "1") == "1"
    max_len = int(os.getenv("INGEST_MAX_LEN", "500"))

    client = get_client()
    collection_name = get_collection_name()

    if os.path.isdir(input_dir):
        batch_process(input_dir, text_dir)

    create_collection(client, collection_name, recreate=recreate)

    if not os.path.isdir(text_dir):
        return

    for file in os.listdir(text_dir):
        path = os.path.join(text_dir, file)
        if file.lower().endswith(".json"):
            with open(path, "r", encoding="utf-8") as f:
                pages = json.load(f)
            cleaned_pages = []
            for p in pages:
                cleaned_pages.append({"page_num": p.get("page_num"), "text": clean_text(p.get("text") or "")})
            cleaned = "\n\n".join([p.get("text") or "" for p in cleaned_pages])
            source = os.path.splitext(file)[0] + ".pdf"
        elif file.lower().endswith(".txt"):
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
            cleaned = clean_text(text)
            cleaned_pages = None
            source = file
        else:
            continue

        if mdna_only:
            mdna = extract_mdna_robust(cleaned) if mdna_robust else extract_mdna(cleaned)
            if mdna:
                cleaned = mdna
                doc_type = os.getenv("INGEST_DOC_TYPE", "mdna")
        if structured:
            if cleaned_pages is not None and not mdna_only:
                chunks = structured_chunk_pages(cleaned_pages, max_len=max_len)
            else:
                chunks = structured_chunk(cleaned, max_len=max_len)
        else:
            chunks = chunk_text(cleaned, chunk_size=chunk_size, overlap=overlap)
        store_chunks(
            client=client,
            collection_name=collection_name,
            chunks=chunks,
            source=source,
            title=os.path.splitext(file)[0],
            doc_id=os.path.splitext(file)[0],
            doc_type=doc_type,
        )


if __name__ == "__main__":
    run()
