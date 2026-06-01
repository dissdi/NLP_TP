# T1 5-cat regression (coverage + BM25 sparse)

## Coverage (expected_source_url in in-scope corpus)
- In-scope D-1 questions: **104**
  - covered: **94** = 90.4%
- OUT D-1 questions: **66**
  - leaked (in-scope corpus still has the URL): 21 = 31.8%

## Per-label in-scope coverage
| label | covered/total | pct |
|---:|---:|---:|
| 0 졸업요건 | 0/1 | 0.0% |
| 1 공지 | 56/62 | 90.3% |
| 2 학사일정 | 29/32 | 90.6% |
| 3 식단 | 6/6 | 100.0% |
| 4 셔틀 | 3/3 | 100.0% |

## BM25 sparse recall@K (in-scope only)
| K | hits | total | recall |
|---:|---:|---:|---:|
| 5 | 90 | 104 | 86.5% |
| 10 | 92 | 104 | 88.5% |
| 20 | 93 | 104 | 89.4% |

## Per-label BM25 R@10
| label | hits/total | recall |
|---:|---:|---:|
| 0 졸업요건 | 0/1 | 0.0% |
| 1 공지 | 56/62 | 90.3% |
| 2 학사일정 | 27/32 | 84.4% |
| 3 식단 | 6/6 | 100.0% |
| 4 셔틀 | 3/3 | 100.0% |

## Notes
- BM25-only (no dense FAISS, no reranker) - baseline floor.
- Phase F achieved 89.4% D-1 with dense + reranker; this measures only sparse coverage on the reduced corpus.
- For full hybrid measurement, FAISS bge-m3 must be re-encoded against the 1,151 in-scope chunks (Colab).
