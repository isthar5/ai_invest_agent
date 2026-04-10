import numpy as np


def cosine_sim(a, b) -> float:
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-6
    return float(np.dot(a, b) / denom)


def deduplicate_indices(embeddings, threshold: float = 0.92) -> list[int]:
    kept = []
    kept_embs = []
    for i, emb in enumerate(embeddings):
        emb_arr = np.asarray(emb, dtype=np.float32)
        is_dup = False
        for kemb in kept_embs:
            if cosine_sim(emb_arr, kemb) > threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(i)
            kept_embs.append(emb_arr)
    return kept


def deduplicate_chunks(chunks, embeddings, threshold: float = 0.92):
    idx = deduplicate_indices(embeddings, threshold=threshold)
    kept_chunks = [chunks[i] for i in idx]
    kept_embeddings = [embeddings[i] for i in idx]
    return kept_chunks, kept_embeddings

