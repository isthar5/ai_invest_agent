def add_citation(answer, docs):
    citations = []

    for i, doc in enumerate(docs):
        text = doc.payload.get("text", "")
        if text[:15] in answer:
            citations.append(f"[来源:{i}]")

    return answer + " " + " ".join(citations)