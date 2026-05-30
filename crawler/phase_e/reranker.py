"""Cross-encoder reranker.

Re-scores (query, passage) pairs from the hybrid retriever to fix RRF's
"strong dense top-1 gets diluted by BM25 noise" issue we observed in smoke_test.

Defaults to BAAI/bge-reranker-v2-m3 (multilingual). For Korean-tuned use
dragonkue/bge-reranker-v2-m3-ko by passing model_id at construction time.
"""
from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Optional

from .retriever import RetrievedChunk


DEFAULT_RERANKER = "BAAI/bge-reranker-v2-m3"


@lru_cache(maxsize=2)
def _load_reranker(model_id: str):
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model_id, max_length=512, device="cpu")


def rerank(
    query: str,
    candidates: list[RetrievedChunk],
    top_k: int = 5,
    model_id: str = DEFAULT_RERANKER,
    passage_field: str = "_passage",
) -> list[RetrievedChunk]:
    """Score (query, passage) pairs and return top_k re-ordered candidates.

    passage_field: meta key to use as passage text. Falls back to 'text' if absent.
    """
    if not candidates:
        return []
    model = _load_reranker(model_id)
    pairs: list[tuple[str, str]] = []
    for c in candidates:
        m = c.meta or {}
        passage = m.get(passage_field) or m.get("text") or ""
        pairs.append((query, passage))
    scores = model.predict(pairs, show_progress_bar=False)
    out: list[RetrievedChunk] = []
    for c, s in zip(candidates, scores):
        nc = replace(c, rrf_score=float(s))  # overwrite rrf_score with rerank score
        # keep original ranks/scores via meta side-channel
        nc.meta = dict(nc.meta) if nc.meta else {}
        nc.meta["_rerank_score"] = float(s)
        out.append(nc)
    out.sort(key=lambda c: -c.meta["_rerank_score"])
    return out[:top_k]
