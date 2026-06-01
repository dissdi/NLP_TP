"""Phase E hybrid + reranker smoke test.

Compares against smoke_test.py (RRF only) on the same 7 queries.

Usage:
  python -m crawler.phase_e.smoke_test_rerank
"""
from __future__ import annotations

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


def main() -> None:
    print("[rerank-smoke] loading indices ...", flush=True)
    r = build_default()
    print("[rerank-smoke] ready", flush=True)

    for q in QUERIES:
        print(f"\n[Q] {q}")
        # 1) hybrid retrieve a wide pool
        pool = r.retrieve(q, top_k=30, bm25_pool=100, dense_pool=50)
        # 2) cross-encoder rerank to top 3
        hits = rerank(q, pool, top_k=3)
        for rk, h in enumerate(hits, 1):
            m = h.meta or {}
            title = (m.get("source_title") or "")[:60]
            body = (m.get("text") or "")[:80].replace("\n", " ")
            rscore = m.get("_rerank_score", 0.0)
            bm_rk = f"BM25 #{h.bm25_rank}" if h.bm25_rank else "BM25 -"
            de_rk = f"dense #{h.dense_rank}" if h.dense_rank else "dense -"
            print(f"  {rk}. rerank={rscore:+.3f} | {bm_rk} | {de_rk} | dom={m.get('domains')}")
            print(f"     title={title!r}")
            print(f"     {body}...")


if __name__ == "__main__":
    main()
