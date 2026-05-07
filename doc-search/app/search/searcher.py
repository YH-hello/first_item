"""
하이브리드 검색 엔진
 - Semantic: Qdrant 벡터 검색 (cosine similarity)
 - Keyword:  BM25 역인덱스 검색 (rank-bm25)
 - Hybrid:   RRF(Reciprocal Rank Fusion) 결합
"""
import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np

import config

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """검색 결과 단위"""

    file_path: str
    file_name: str
    file_type: str
    page_num: int
    page_label: str
    page_link_cmd: str
    text_preview: str
    score: float
    source: str  # "semantic" | "keyword" | "hybrid"
    extra_meta: dict

    def to_dict(self) -> dict:
        return {
            "file_path": self.file_path,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "page_num": self.page_num,
            "page_label": self.page_label,
            "page_link_cmd": self.page_link_cmd,
            "text_preview": self.text_preview,
            "score": self.score,
            "source": self.source,
            "extra_meta": self.extra_meta,
        }

    @classmethod
    def from_payload(cls, payload: dict, score: float, source: str) -> "SearchResult":
        extra = {
            k: v
            for k, v in payload.items()
            if k not in {
                "file_path", "file_name", "file_type", "page_num",
                "page_label", "page_link_cmd", "text",
            }
        }
        return cls(
            file_path=payload.get("file_path", ""),
            file_name=payload.get("file_name", ""),
            file_type=payload.get("file_type", ""),
            page_num=int(payload.get("page_num", 1)),
            page_label=payload.get("page_label", ""),
            page_link_cmd=payload.get("page_link_cmd", ""),
            text_preview=str(payload.get("text", ""))[:400],
            score=score,
            source=source,
            extra_meta=extra,
        )


class HybridSearcher:
    """Semantic + Keyword Hybrid Search (RRF 결합)"""

    RRF_K = 60  # RRF 상수 (높을수록 순위 차이 완화)

    def __init__(self, index_manager) -> None:
        self._qdrant = index_manager.qdrant
        self._embed = index_manager.embed_model
        self._index_manager = index_manager

    # ── 단독 검색 ────────────────────────────────────────────────────────────

    def semantic_search(self, query: str, top_k: Optional[int] = None) -> List[SearchResult]:
        """Qdrant 벡터 유사도 검색"""
        k = top_k or config.SEARCH_TOP_K
        vec = self._embed.encode(query, normalize_embeddings=True).tolist()

        hits = self._qdrant.search(
            collection_name=config.QDRANT_COLLECTION,
            query_vector=vec,
            limit=k,
            with_payload=True,
        )
        return [SearchResult.from_payload(h.payload, h.score, "semantic") for h in hits]

    def keyword_search(self, query: str, top_k: Optional[int] = None) -> List[SearchResult]:
        """BM25 키워드 검색"""
        k = top_k or config.SEARCH_TOP_K
        bm25 = self._index_manager.bm25
        docs = self._index_manager.bm25_docs

        if not bm25 or not docs:
            return []

        scores: np.ndarray = bm25.get_scores(query.split())
        top_idx = np.argsort(scores)[::-1][:k]

        results: List[SearchResult] = []
        for idx in top_idx:
            if scores[idx] <= 0:
                break
            d = docs[idx]
            results.append(
                SearchResult(
                    file_path=d.get("file_path", ""),
                    file_name=d.get("file_name", ""),
                    file_type=d.get("file_type", ""),
                    page_num=int(d.get("page_num", 1)),
                    page_label=d.get("page_label", ""),
                    page_link_cmd=d.get("page_link_cmd", ""),
                    text_preview=d.get("text", "")[:400],
                    score=float(scores[idx]),
                    source="keyword",
                    extra_meta={},
                )
            )
        return results

    # ── 하이브리드 (RRF) ─────────────────────────────────────────────────────

    def hybrid_search(self, query: str, top_k: Optional[int] = None) -> List[SearchResult]:
        """RRF(Reciprocal Rank Fusion) 기반 하이브리드 검색"""
        k = top_k or config.SEARCH_TOP_K
        fetch_k = k * 2  # 각 검색기에서 더 많이 가져온 후 융합

        semantic = self.semantic_search(query, fetch_k)
        keyword = self.keyword_search(query, fetch_k)

        # (file_path, page_num) 키로 RRF 점수 누적
        rrf_map: dict = {}

        for rank, r in enumerate(semantic):
            key = (r.file_path, r.page_num)
            entry = rrf_map.setdefault(key, {"score": 0.0, "result": r})
            entry["score"] += config.SEMANTIC_WEIGHT / (self.RRF_K + rank + 1)

        for rank, r in enumerate(keyword):
            key = (r.file_path, r.page_num)
            entry = rrf_map.setdefault(key, {"score": 0.0, "result": r})
            entry["score"] += config.KEYWORD_WEIGHT / (self.RRF_K + rank + 1)

        sorted_entries = sorted(rrf_map.values(), key=lambda x: x["score"], reverse=True)

        results: List[SearchResult] = []
        for entry in sorted_entries[:k]:
            r = entry["result"]
            r.score = round(entry["score"], 6)
            r.source = "hybrid"
            results.append(r)

        return results

    # ── 통합 진입점 ──────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        mode: str = "hybrid",
        top_k: Optional[int] = None,
    ) -> List[SearchResult]:
        if not query.strip():
            return []

        if mode == "semantic":
            return self.semantic_search(query, top_k)
        elif mode == "keyword":
            return self.keyword_search(query, top_k)
        else:
            return self.hybrid_search(query, top_k)
