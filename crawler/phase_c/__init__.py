"""Phase C: 정제·재청크·메타 강화·인덱스 빌드.

플로우:
    sprint{1,2,3}/*.jsonl  (read-only 원본)
        -> 01_clean/      텍스트 정규화 + URL 정규화 + dedup
        -> 02_rechunked/  거대 청크 분할 + 초소형 병합
        -> 03_enriched/   메타 강화
        -> 04_index/      FAISS + BM25

정책: docs/phase_c_plan.md §3 참조.
"""
