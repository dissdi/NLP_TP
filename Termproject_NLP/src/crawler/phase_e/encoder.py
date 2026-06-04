"""Query encoder for dense retrieval.

Wraps sentence-transformers with model-specific prefix handling
(must mirror crawler/phase_c/index_faiss.py at encode-time).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

import numpy as np

# Query-side prefix per model. Passage prefix is applied at index build time.
# - bge-m3:    no prefix
# - e5-large:  "query: " for queries (passage uses "passage: ")
MODEL_QUERY_PREFIX = {
    "BAAI/bge-m3": "",
    "intfloat/multilingual-e5-large": "query: ",
    "jhgan/ko-sroberta-multitask": "",
}


@lru_cache(maxsize=2)
def _load_model(model_id: str):
    import os
    from sentence_transformers import SentenceTransformer
    # 평가 환경 Colab Free T4(15GB): Qwen3-14B 4-bit(~9GB) + bge-m3 동시 적재 시
    # KV 캐시 자리가 부족해 OOM. 인코더는 query 1건만 처리하므로 CPU로 내려도
    # 1-2초/쿼리 수준이라 무방. 강제 변경하려면 env로 override 가능.
    device = os.environ.get("RAG_ENCODER_DEVICE", "cpu")
    return SentenceTransformer(model_id, device=device)


def encode_query(query: str, model_id: str = "BAAI/bge-m3") -> np.ndarray:
    """Return shape (1, dim) float32, L2-normalized."""
    model = _load_model(model_id)
    prefix = MODEL_QUERY_PREFIX.get(model_id, "")
    text = prefix + query if prefix else query
    emb = model.encode(
        [text],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return emb.astype("float32")


def encode_queries(queries: list[str], model_id: str = "BAAI/bge-m3", batch_size: int = 8) -> np.ndarray:
    """Return shape (N, dim) float32, L2-normalized."""
    model = _load_model(model_id)
    prefix = MODEL_QUERY_PREFIX.get(model_id, "")
    texts = [prefix + q if prefix else q for q in queries]
    emb = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    return emb.astype("float32")
