import json
import asyncio
from app.retrieval.hybrid import hybrid_search
from app.retrieval.reranker import Reranker

KS = [1, 3, 5, 10]


def compute_recall_at_k(results, relevant_docs, k):
    """
    Recall@K：TopK中是否包含正确答案
    """
    top_k_ids = [doc_id for doc_id, _ in results[:k]]

    for rel in relevant_docs:
        if rel in top_k_ids:
            return 1
    return 0


def compute_mrr(results, relevant_docs):
    """
    MRR：第一个正确答案的位置
    """
    for rank, (doc_id, _) in enumerate(results, start=1):
        if doc_id in relevant_docs:
            return 1.0 / rank
    return 0.0


async def evaluate():
    with open("eval_data.json", "r", encoding="utf-8") as f:
        dataset = json.load(f)

    total_recall = {k: 0 for k in KS}
    total_recall_rerank = {k: 0 for k in KS}
    total_mrr = 0.0
    total_mrr_rerank = 0.0
    total_queries = len(dataset)
    reranker = Reranker()

    for item in dataset:
        query = item["query"]
        relevant_docs = item["relevant_docs"]

        results, _, _ = await hybrid_search(query, limit=20)
        reranked = reranker.rerank(query, results[:20])

        for k in KS:
            total_recall[k] += compute_recall_at_k(results, relevant_docs, k)
            total_recall_rerank[k] += compute_recall_at_k(reranked, relevant_docs, k)

        mrr = compute_mrr(results, relevant_docs)
        mrr_rerank = compute_mrr(reranked, relevant_docs)
        total_mrr += mrr
        total_mrr_rerank += mrr_rerank

        print(f"\nQuery: {query}")
        for k in KS:
            recall = compute_recall_at_k(results, relevant_docs, k)
            recall_rerank = compute_recall_at_k(reranked, relevant_docs, k)
            print(f"Recall@{k}: {recall} | Recall@{k} (Rerank): {recall_rerank}")
        print(f"MRR: {mrr:.3f} | MRR (Rerank): {mrr_rerank:.3f}")

    avg_recall = {k: total_recall[k] / total_queries for k in KS}
    avg_recall_rerank = {k: total_recall_rerank[k] / total_queries for k in KS}
    avg_mrr = total_mrr / total_queries
    avg_mrr_rerank = total_mrr_rerank / total_queries

    print("\n====== FINAL METRICS ======")
    for k in KS:
        print(f"Recall@{k}: {avg_recall[k]:.3f} | Recall@{k} (Rerank): {avg_recall_rerank[k]:.3f}")
    print(f"MRR: {avg_mrr:.3f} | MRR (Rerank): {avg_mrr_rerank:.3f}")

    with open("eval_results.json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "recall": avg_recall,
                "recall_rerank": avg_recall_rerank,
                "mrr": avg_mrr,
                "mrr_rerank": avg_mrr_rerank,
                "ks": KS,
            },
            f,
            ensure_ascii=False,
            indent=4,
        )


if __name__ == "__main__":
    asyncio.run(evaluate())
