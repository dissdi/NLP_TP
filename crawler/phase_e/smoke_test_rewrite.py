"""Phase E: compare 4 retrieval variants (rerank baseline vs rewrite vs HyDE vs both).

Variant naming:
  R    = retrieve(original query) + rerank
  RW   = retrieve(LLM-rewritten query) + rerank
  HY   = retrieve(LLM-HyDE-passage as query) + rerank
  RWHY = retrieve(rewritten + HyDE concatenated) + rerank

Usage:
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.smoke_test_rewrite
"""
from __future__ import annotations

from .query_rewrite import hyde_query, rewrite_query
from .reranker import rerank
from .retriever import build_default

QUERIES = [
    "졸업요건 학점은 몇 학점인가요",
    "휴학 신청 절차가 어떻게 되나요",
    "장학금 신청 방법",
    "기숙사 입소 시기",
    "수강신청 변경 기간",
    "컴퓨터공학과 졸업하려면",
    "도서관 운영시간",
]


def _top1_str(hits) -> str:
    if not hits:
        return "(no hits)"
    h = hits[0]
    m = h.meta or {}
    title = (m.get("source_title") or "")[:55]
    body = (m.get("text") or "")[:60].replace("\n", " ")
    rs = m.get("_rerank_score", 0.0)
    return f"rerank={rs:+.3f} | title={title!r}\n     {body}..."


def run_variant(r, q_for_retrieve: str, original_q: str, label: str) -> None:
    pool = r.retrieve(q_for_retrieve, top_k=30, bm25_pool=100, dense_pool=50)
    hits = rerank(original_q, pool, top_k=3)
    print(f"  [{label}] {_top1_str(hits)}")


def main() -> None:
    print("[rewrite-smoke] loading indices ...", flush=True)
    r = build_default()
    print("[rewrite-smoke] ready", flush=True)

    for q in QUERIES:
        print(f"\n[Q] {q}")
        # 1) baseline rerank (original query)
        run_variant(r, q, q, "R   ")

        # 2) rewrite
        q_rw = rewrite_query(q)
        print(f"  rewritten: {q_rw}")
        run_variant(r, q_rw, q, "RW  ")

        # 3) HyDE
        q_hy = hyde_query(q)
        print(f"  hyde     : {q_hy[:100]}...")
        run_variant(r, q_hy, q, "HY  ")

        # 4) both
        run_variant(r, q_rw + "\n" + q_hy, q, "RWHY")


if __name__ == "__main__":
    main()
