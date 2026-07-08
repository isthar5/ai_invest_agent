import numpy as np


def _cosine(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-6
    return float(np.dot(a, b) / denom)


def mmr(query_emb, doc_embs, docs, lambda_param: float = 0.7, top_k: int = 5):
    if not docs or top_k <= 0:
        return []

    doc_embs = [np.asarray(e, dtype=np.float32) for e in doc_embs]
    query_emb = np.asarray(query_emb, dtype=np.float32)

    selected = []
    selected_idx = []

    n = min(len(docs), len(doc_embs))
    for _ in range(min(top_k, n)):
        best_score = None
        best_idx = None
        for i in range(n):
            if i in selected_idx:
                continue
            relevance = _cosine(query_emb, doc_embs[i])
            diversity = 0.0
            if selected_idx:
                diversity = max(_cosine(doc_embs[i], doc_embs[j]) for j in selected_idx)
            score = (lambda_param * relevance) - ((1.0 - lambda_param) * diversity)
            if best_score is None or score > best_score:
                best_score = score
                best_idx = i
        if best_idx is None:
            break
        selected.append(docs[best_idx])
        selected_idx.append(best_idx)

    return selected

