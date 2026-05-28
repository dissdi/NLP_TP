"""Phase E hybrid retrieval smoke test.

Runs the same 7 queries we used for BM25 and dense alone, this time via RRF.
Compare the rank-1 of hybrid vs. BM25-only and dense-only.

Usage:
  python -m crawler.phase_e.smoke_test
"""
from __future__ import annotations

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
    print("[phase_e] loading indices ...", flush=True)
    r = build_default()
    print(f"[phase_e] bm25 tracks: {[t.name for t in r.idx.bm25_tracks]}", flush=True)
    print(f"[phase_e] dense tracks: {[t.name for t in r.idx.faiss_tracks]}", flush=True)
    print(f"[phase_e] meta rows: {len(r.idx.meta)}", flush=True)

    for q in QUERIES:
        print(f"\n[Q] {q}")
        hits = r.retrieve(q, top_k=3)
        for rk, h in enumerate(hits, 1):
            m = h.meta or {}
            title = (m.get("source_title") or "")[:60]
            body = (m.get("text") or "")[:80].replace("\n", " ")
            bm_rk = f"BM25 #{h.bm25_rank}" if h.bm25_rank else "BM25 -"
            de_rk = f"dense #{h.dense_rank}" if h.dense_rank else "dense -"
            print(f"  {rk}. RRF={h.rrf_score:.4f} | {bm_rk} | {de_rk} | dom={m.get('domains')}")
            print(f"     title={title!r}")
            print(f"     {body}...")


if __name__ == "__main__":
    main()
