# Ablation A4 — rerank-expanded (run guide)

**What A4 changes (vs main/master 89.4% baseline):**
- `pipeline.py`: `enable_expand` default **True**, and the **expanded** query is fed to the
  cross-encoder reranker too (baseline reranked with the original query). Plus env toggles
  `RAG_ENABLE_EXPAND` and `RAG_RERANK_ON_EXPANDED` for control runs (see section 4).
- `aliases.json`: includes colloquial endings (어캄/뭐임/됨/알려줘 …) + dept abbrevs.
- New eval set `eval/eval-colloquial.jsonl` (29 rows; gold/URLs copied from D-1 source rows,
  every row exercises expansion, 0 tool-routing, 3 fallback-expected).
- `eval_full.py` / `eval_full_judge.py`: honor `EVAL_PATH` (input) + `EVAL_TAG` (output suffix).

---

## 0. One-time cleanup on Windows (stale git locks left by the sandbox)

In PowerShell at the repo root:

```powershell
Remove-Item .git\index.lock, .git\packed-refs.lock, .git\objects\maintenance.lock, .git\refs\heads\__a4_write_test.lock -ErrorAction SilentlyContinue
git branch -D __a4_write_test
```

## 1. Branch + commit (Windows, repo root)

```powershell
git reset
git checkout -b ablation/A4-rerank-expanded
git add crawler/phase_e/pipeline.py crawler/phase_e/eval_full.py crawler/phase_e/eval_full_judge.py crawler/phase_e/aliases.json eval/eval-colloquial.jsonl eval/A4_RUN.md
git commit -m "ablation(A4): rerank-expanded + expand-on default + env toggles + colloquial eval set (29)"
git push -u NLP_TP ablation/A4-rerank-expanded
```

> Do **not** `git add .` — loader.py/retriever.py/etc. are CRLF-only churn, and
> reranker.py/encoder.py have an unrelated uncommitted `device="cpu"` change. Stage only the 6 files above.
> If you already committed an earlier pipeline.py, just re-add + `git commit --amend` (or a new commit) so the env toggles are included.

## 2. Quick single run (sanity)

```bash
cd /data2/donginson/projects/NLP_TP
git fetch && git checkout ablation/A4-rerank-expanded
export EVAL_TAG=colloquial
export EVAL_PATH=$(pwd)/eval/eval-colloquial.jsonl
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all
unset EVAL_TAG EVAL_PATH
```
(First run already done: colloquial A4 = 96.6%. D-1 was stale-cached — see step 4d.)

## 4. FULL MATRIX (the real ablation)

> Env toggles (no code edits): `RAG_ENABLE_EXPAND` (0/1), `RAG_RERANK_ON_EXPANDED` (0/1).
> **Commit the updated pipeline.py (with toggles) to the branch and re-checkout on the server first.**

```bash
cd /data2/donginson/projects/NLP_TP
git fetch && git checkout ablation/A4-rerank-expanded
export EVAL_PATH=$(pwd)/eval/eval-colloquial.jsonl

# (a) BASELINE — shipped system (expand OFF, rerank original)
EVAL_TAG=collo_base RAG_ENABLE_EXPAND=0 \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
EVAL_TAG=collo_base \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all

# (b) EXPAND-ONLY — expand ON, rerank on ORIGINAL query
EVAL_TAG=collo_exp RAG_ENABLE_EXPAND=1 RAG_RERANK_ON_EXPANDED=0 \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
EVAL_TAG=collo_exp \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all

# (c) A4 — expand ON + rerank EXPANDED
EVAL_TAG=collo_a4 RAG_ENABLE_EXPAND=1 RAG_RERANK_ON_EXPANDED=1 \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
EVAL_TAG=collo_a4 \
  CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all
unset EVAL_PATH

# (d) D-1 FRESH A4 — clear stale cache, run branch defaults (expand ON + rerank expanded)
rm -f eval/results/full_eval_answers.jsonl eval/results/full_eval_judged.jsonl
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all
cp eval/results/full_eval_judged_agg.json eval/results/ablation_A4_d1_agg.json
```

Read `overall_correct_rate_score2` from each `full_eval_judged_agg_<tag>.json`:

| Condition | expand | rerank-on | tag |
|---|---|---|---|
| (a) baseline (shipped) | off | original | collo_base |
| (b) expand-only | on | original | collo_exp |
| (c) A4 | on | expanded | collo_a4 (≈96.6%) |

- (c) − (a) = total A4-bundle gain on colloquial queries.
- (c) − (b) = gain from **rerank-on-expanded specifically** (the A4 lever).
- (b) − (a) = gain from query expansion alone.

> Cached D-1 baseline (89.4%) = master behavior (expand off). Compare fresh D-1 A4 (step d) against it.

## Promotion gate
Merge to main only if fresh D-1 A4 ≥ ~89.4% (no regression vs lock) **and** colloquial (c) > (a).
Otherwise keep A4 as a branch-only result for the report.
