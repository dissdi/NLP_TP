"""Hybrid retriever: BM25 + FAISS dense, combined via Reciprocal Rank Fusion.

Tracks (built in Phase C):
  BM25:  general (1,279) + almi_cell (2,235)
  FAISS: general (1,279) + almi_dept (101)  [bge-m3, 1024-dim]

Strategy (unified search, see project-nlp-tp-phase-e-strategy):
  - BM25 score across all BM25 tracks (general + almi_cell pooled by chunk_id)
  - Dense score across all dense tracks (general + almi_dept pooled by chunk_id)
  - RRF fusion: score = sum(1 / (k + rank))  over the two lists
  - Tie-breaker: max original score
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .encoder import encode_query
from .loader import RetrievalIndex, load_all
from .tokenizer import tokenize

DEFAULT_RRF_K = 60


@dataclass
class RetrievedChunk:
    chunk_id: str
    rrf_score: float
    bm25_rank: Optional[int] = None
    bm25_score: Optional[float] = None
    dense_rank: Optional[int] = None
    dense_score: Optional[float] = None
    sources: list[str] = field(default_factory=list)  # which tracks contributed
    meta: dict = field(default_factory=dict)


class HybridRetriever:
    def __init__(self, index: RetrievalIndex, model_id: str = "BAAI/bge-m3"):
        self.idx = index
        self.model_id = model_id

    # ---- single-track scorers -----------------------------------------------

    def _bm25_scores(self, query_tokens: list[str]) -> dict[str, tuple[float, str]]:
        """Return chunk_id -> (max_score, source_track)."""
        out: dict[str, tuple[float, str]] = {}
        for track in self.idx.bm25_tracks:
            scores = track.bm25.get_scores(query_tokens)
            for cid, sc in zip(track.chunk_ids, scores):
                if sc <= 0:
                    continue
                prev = out.get(cid)
                if prev is None or sc > prev[0]:
                    out[cid] = (float(sc), f"bm25:{track.name}")
        return out

    def _dense_scores(self, q_emb: np.ndarray, top_per_track: int = 50) -> dict[str, tuple[float, str]]:
        """Return chunk_id -> (max_score, source_track). q_emb shape (1, dim)."""
        out: dict[str, tuple[float, str]] = {}
        for track in self.idx.faiss_tracks:
            k = min(top_per_track, track.index.ntotal)
            D, I = track.index.search(q_emb, k)
            for rank, (sc, i) in enumerate(zip(D[0], I[0])):
                if i < 0:
                    continue
                cid = track.chunk_ids[int(i)]
                prev = out.get(cid)
                if prev is None or float(sc) > prev[0]:
                    out[cid] = (float(sc), f"dense:{track.name}")
        return out

    # ---- RRF fusion ----------------------------------------------------------

    @staticmethod
    def _to_ranked(score_map: dict[str, tuple[float, str]]) -> list[tuple[str, int, float, str]]:
        """Sort by score desc, return list of (cid, rank_1based, score, src)."""
        items = sorted(score_map.items(), key=lambda kv: -kv[1][0])
        return [(cid, rank + 1, sc, src) for rank, (cid, (sc, src)) in enumerate(items)]

    def retrieve(
        self,
        query: str,
        top_k: int = 10,
        bm25_pool: int = 100,
        dense_pool: int = 50,
        rrf_k: int = DEFAULT_RRF_K,
    ) -> list[RetrievedChunk]:
        # 1) BM25 across all bm25 tracks
        q_tokens = tokenize(query)
        bm25_map = self._bm25_scores(q_tokens)
        bm25_ranked = self._to_ranked(bm25_map)[:bm25_pool]

        # 2) Dense across all faiss tracks (skip encoding if no faiss tracks)
        if self.idx.faiss_tracks:
            q_emb = encode_query(query, model_id=self.model_id)
            dense_map = self._dense_scores(q_emb, top_per_track=dense_pool)
            dense_ranked = self._to_ranked(dense_map)[:dense_pool]
        else:
            dense_ranked = []

        # 3) RRF fusion
        rrf: dict[str, float] = defaultdict(float)
        bm_info: dict[str, tuple[int, float, str]] = {}
        de_info: dict[str, tuple[int, float, str]] = {}
        for cid, rk, sc, src in bm25_ranked:
            rrf[cid] += 1.0 / (rrf_k + rk)
            bm_info[cid] = (rk, sc, src)
        for cid, rk, sc, src in dense_ranked:
            rrf[cid] += 1.0 / (rrf_k + rk)
            de_info[cid] = (rk, sc, src)

        fused = sorted(rrf.items(), key=lambda kv: -kv[1])[:top_k]
        results: list[RetrievedChunk] = []
        for cid, score in fused:
            bm = bm_info.get(cid)
            de = de_info.get(cid)
            srcs: list[str] = []
            if bm:
                srcs.append(bm[2])
            if de:
                srcs.append(de[2])
            results.append(RetrievedChunk(
                chunk_id=cid,
                rrf_score=float(score),
                bm25_rank=bm[0] if bm else None,
                bm25_score=bm[1] if bm else None,
                dense_rank=de[0] if de else None,
                dense_score=de[1] if de else None,
                sources=srcs,
                meta=self.idx.meta.get(cid, {}),
            ))
        return results


def build_default(model_tag: str = "bge-m3", model_id: str = "BAAI/bge-m3") -> HybridRetriever:
    return HybridRetriever(load_all(model_tag=model_tag), model_id=model_id)
