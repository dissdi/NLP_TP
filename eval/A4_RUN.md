# Ablation A4 — rerank-expanded (run guide)

**What A4 changes (vs main/master 89.4% baseline):**
- `pipeline.py`: `enable_expand` default **True**, and the **expanded** query is fed to the
  cross-encoder reranker too (baseline reranked with the original query).
- `aliases.json`: includes colloquial endings (어캄/뭐임/됨/알려줘 …) + dept abbrevs.
- New eval set `eval/eval-colloquial.jsonl` (29 rows; gold/URLs copied from D-1 source rows,
  every row exercises expansion, 0 tool-routing, 3 fallback-expected).
- `eval_full.py` / `eval_full_judge.py`: honor `EVAL_PATH` (input) + `EVAL_TAG` (output suffix).

> A4 bundles **expand-on + rerank-expanded**, so A4-vs-master is the net effect of the bundle.
> To isolate "rerank-expanded" alone, optionally run a control with line 62 reverted to
> `rerank(query, pool, ...)` (expand still on).

---

## 0. One-time cleanup on Windows (stale git locks left by the sandbox)

The sandbox couldn't delete these. In PowerShell at the repo root:

```powershell
Remove-Item .git\index.lock, .git\packed-refs.lock, .git\objects\maintenance.lock, .git\refs\heads\__a4_write_test.lock -ErrorAction SilentlyContinue
git branch -D __a4_write_test   # delete the stray test branch
```

## 1. Branch + commit (Windows, repo root)

```powershell
git reset                       # unstage pre-existing sprint2/3 deletions so they don't ride along
git checkout -b ablation/A4-rerank-expanded
git add crawler/phase_e/pipeline.py crawler/phase_e/eval_full.py crawler/phase_e/eval_full_judge.py crawler/phase_e/aliases.json eval/eval-colloquial.jsonl eval/A4_RUN.md
git commit -m "ablation(A4): rerank with expanded query + expand-on default + colloquial eval set (29)"
git push -u NLP_TP ablation/A4-rerank-expanded
```

> Note: do **not** `git add .` — loader.py/retriever.py/etc. show only CRLF whitespace churn,
> and reranker.py/encoder.py have an unrelated uncommitted `device="cpu"` change. Stage only the 5 files above.

## 2. Server: check out + run both eval sets

```bash
cd /data2/donginson/projects/NLP_TP
git fetch && git checkout ablation/A4-rerank-expanded

# --- D-1 (170, regression check vs 89.4%) ---
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all

# --- Colloquial (29, where A4 should shine) ---
export EVAL_TAG=colloquial
export EVAL_PATH=$(pwd)/eval/eval-colloquial.jsonl
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full all
CUDA_VISIBLE_DEVICES=8 python -m crawler.phase_e.eval_full_judge all
unset EVAL_TAG EVAL_PATH
```

Outputs:
- D-1 → `eval/results/full_eval_judged_agg.json` (+ answers/report)
- Colloquial → `eval/results/full_eval_judged_agg_colloquial.json` (+ `*_colloquial.*`)

## 3. Back up results for comparison

```bash
cp eval/results/full_eval_judged_agg.json            eval/results/ablation_A4_d1_agg.json
cp eval/results/full_eval_judged_agg_colloquial.json eval/results/ablation_A4_colloquial_agg.json
```

## Promotion gate
Merge to main only if D-1 ≥ ~91% (no regression vs 89.4% lock) **and** colloquial set improves
over a colloquial-on-master baseline. Otherwise keep A4 as a branch-only result for the report.
