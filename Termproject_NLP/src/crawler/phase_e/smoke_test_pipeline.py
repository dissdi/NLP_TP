"""End-to-end RAG pipeline smoke test on 7 fixed queries.

Outputs:
  - generated answer
  - whether fallback was triggered
  - top-3 sources with rerank scores

Usage:
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.smoke_test_pipeline
"""
from __future__ import annotations

from .pipeline import RAGPipeline

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
    print("[pipeline-smoke] loading ...", flush=True)
    p = RAGPipeline()
    print("[pipeline-smoke] ready", flush=True)

    for q in QUERIES:
        print(f"\n{'='*70}\n[Q] {q}")
        r = p.answer(q)
        fb = "  (FALLBACK)" if r.used_fallback else ""
        print(f"[top rerank score] {r.top_rerank_score:+.3f}{fb}")
        print(f"[answer]\n{r.answer}")
        print(f"[sources top-3]")
        for s in r.sources[:3]:
            print(f"  - {s['rerank_score']:+.3f}  {s['title'][:60]}")
            if s['source_url']:
                print(f"           {s['source_url'][:90]}")


if __name__ == "__main__":
    main()
