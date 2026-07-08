import os
import fitz
import json


def pdf_to_text(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    parts = []
    for page in doc:
        parts.append(page.get_text())
    return "".join(parts)


def extract_with_page(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages_content = []
    for page_num, page in enumerate(doc):
        pages_content.append(
            {
                "page_num": page_num + 1,
                "text": page.get_text(),
            }
        )
    return pages_content


def batch_process(input_dir: str, output_dir: str) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    outputs = []
    for file in os.listdir(input_dir):
        if not file.lower().endswith(".pdf"):
            continue
        path = os.path.join(input_dir, file)
        pages = extract_with_page(path)
        out_path = os.path.join(output_dir, os.path.splitext(file)[0] + ".json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(pages, f, ensure_ascii=False, indent=2)
        outputs.append(out_path)
    return outputs
