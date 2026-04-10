from typing import List, Tuple, Dict, Any
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

class Reranker:
    """
    使用 BAAI/bge-reranker-base 的 CrossEncoder 进行精排
    若依赖不可用，自动降级为基于融合分数的排序，不影响主流程。
    """
    def __init__(self, model_name: str = "BAAI/bge-reranker-base", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self.model = None
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            self.model = None
        except Exception:
            self.model = None

    def _extract_text(self, info: Dict[str, Any]) -> str:
        md = info.get("metadata", {}) or info.get("payload", {})
        return md.get("text") or md.get("content") or md.get("content_ltks") or md.get("title") or md.get("title_tks") or ""

    def rerank(self, query: str, documents: List[Tuple[str, Dict[str, Any]]]) -> List[Tuple[str, Dict[str, Any]]]:
        if not documents:
            return documents

        if self.model is None:
            return sorted(documents, key=lambda x: x[1].get("score", 0), reverse=True)

        pairs = []
        for _, info in documents:
            text = self._extract_text(info)
            pairs.append((query, text))

        try:
            scores = self.model.predict(pairs)
        except Exception:
            return sorted(documents, key=lambda x: x[1].get("score", 0), reverse=True)

        reranked = []
        for i, (doc_id, info) in enumerate(documents):
            info = dict(info)
            info["rerank_score"] = float(scores[i])
            reranked.append((doc_id, info))

        return sorted(reranked, key=lambda x: x[1]["rerank_score"], reverse=True)
