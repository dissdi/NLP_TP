# Ablation A4 (rerank-expanded) — Results

**Date:** 2026-05-29 · **Baseline (main lock):** D-1 89.4% (LLM-judge correct rate)
**A4 change:** query expansion ON by default, and the **expanded** query is fed to the
cross-encoder reranker (baseline reranked with the original query). Env toggles
`RAG_ENABLE_EXPAND` / `RAG_RERANK_ON_EXPANDED` enable the control conditions.

## Colloquial set (29 items, slang/구어체 variants of D-1 questions)

| # | Condition | expand | rerank input | correct rate | avg score | fallback P/R | src p@1 / p@3 |
|---|---|---|---|---|---|---|---|
| a | baseline (shipped) | off | original | 89.7% | 1.793 | 0.50 / 0.67 | 0.846 / 0.885 |
| b | expand-only | on | original | 89.7% | 1.793 | 0.50 / 0.67 | 0.846 / 0.885 |
| c | **A4** | on | **expanded** | **96.6%** | 1.931 | **1.00** / 0.67 | 0.808 / 0.923 |

**Decomposition**
- (c) − (a) = **+6.9 pp** — total A4-bundle gain on colloquial queries.
- (c) − (b) = **+6.9 pp** — the entire gain is attributable to **rerank-on-expanded** (the A4 lever).
- (b) − (a) = **0** — query expansion in retrieval alone does nothing here; reranking on the
  original query reselects the same top-8 regardless of the expanded retrieval pool.

**Mechanism note.** A4 also eliminated 2 false fallbacks (fp 2 → 0, precision 0.50 → 1.00).
Colloquial queries scored low on the cross-encoder against the right passages, dropping below the
fallback threshold; the expanded query raises that score above threshold, so the answer is produced
instead of falling back.

## D-1 set (170 clean questions)

| Condition | correct rate | avg score | fallback P/R | src p@1 / p@3 |
|---|---|---|---|---|
| baseline (master lock) | 89.4% | 1.824 | 0.79 / 0.73 | 0.910 / 0.961 |
| A4 | **86.5%** | 1.759 | 0.91 / 0.67 | 0.890 / 0.948 |

**A4 regresses clean D-1 by −2.9 pp.** Cause: expansion injects false-alias noise on clean
phrasing (e.g. "2학기" → "제2학생회관" because the 1학~4학 aliases match "학기"), and that noise
now propagates into the reranker.

## Verdict

A4 is a **trade-off**: +6.9 pp on colloquial queries, −2.9 pp on clean queries.

- **Do not merge A4 as a global default** (D-1 regression).
- Bind the A4 lever (rerank-on-expanded) to the **expand-on path only**. Since main keeps expansion
  opt-in, applying A4 there yields the +6.9 pp on slang queries at no cost to clean queries.
- The D-1 regression is rooted in alias false-matches → next step **A2 (aliases-clean)**: stop
  1학~4학 from matching "학기". Re-running A4 after A2 may turn it net-positive.

## Reproduce
See `eval/A4_RUN.md` §4. Aggregates: `full_eval_judged_agg_{collo_base,collo_exp,collo_a4}.json`
and `ablation_A4_d1_agg.json`.
