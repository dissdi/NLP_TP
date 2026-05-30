"""D-1 full RAG evaluation: generate answer for each of 170 QA, save, score.

Heavy step: 170 * LLM answer ≈ 30 min ~ 1h on RTX A6000 (14B 4-bit).
Resumable: skips qa_id already in the output file.

Outputs:
  eval/results/full_eval_answers.jsonl    # one row per qa_id with answer + sources
  eval/results/full_eval_auto.json        # auto metrics aggregate
  eval/results/full_eval_auto_report.md   # readable report

Auto metrics (LLM-free):
  - fallback match accuracy (used_fallback == is_fallback_expected)
  - fallback precision / recall (vs is_fallback_expected)
  - source URL precision/recall@k (vs expected_source_urls)
  - per-domain breakdown
  - average answer length / by domain

LLM-as-judge is a separate module (eval_full_judge.py).
"""
from __future__ import annotations

import json
import os
import time
from collections import defaultdict

from .pipeline import RAGPipeline

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_PATH = os.environ.get("EVAL_PATH", os.path.join(ROOT, "eval", "eval-generated.jsonl"))
OUT_DIR = os.path.join(ROOT, "eval", "results")
_TAG = os.environ.get("EVAL_TAG", "")
_SUFFIX = f"_{_TAG}" if _TAG else ""
ANS_PATH = os.path.join(OUT_DIR, f"full_eval_answers{_SUFFIX}.jsonl")


def load_eval() -> list[dict]:
    rows: list[dict] = []
    with open(EVAL_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_done() -> set[str]:
    done: set[str] = set()
    if not os.path.exists(ANS_PATH):
        return done
    with open(ANS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                done.add(json.loads(line)["qa_id"])
            except Exception:
                pass
    return done


def chunk_urls_from_source(s: dict) -> set[str]:
    return {(s.get("source_url") or "").strip()} - {""}


def run_generate(rerank_top_k: int = 8, max_new_tokens: int = 512) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    pipeline = RAGPipeline()
    qa_rows = load_eval()
    done = load_done()
    print(f"[full-eval] total {len(qa_rows)}  already done {len(done)}", flush=True)

    t_global = time.time()
    n_new = 0
    with open(ANS_PATH, "a", encoding="utf-8") as out:
        for i, qa in enumerate(qa_rows, 1):
            qid = qa["qa_id"]
            if qid in done:
                continue
            t0 = time.time()
            res = pipeline.answer(qa["question"], rerank_top_k=rerank_top_k, max_new_tokens=max_new_tokens)
            row = {
                "qa_id": qid,
                "question": qa["question"],
                "answer_gold": qa.get("answer_gold", ""),
                "domain": qa.get("domain", 0),
                "question_type": qa.get("question_type", ""),
                "is_fallback_expected": bool(qa.get("is_fallback_expected", False)),
                "expected_source_urls": qa.get("expected_source_urls") or [],
                "generated_answer": res.answer,
                "used_fallback": res.used_fallback,
                "top_rerank_score": res.top_rerank_score,
                "sources": res.sources,
                "elapsed_s": round(time.time() - t0, 2),
            }
            out.write(json.dumps(row, ensure_ascii=False) + "\n")
            out.flush()
            n_new += 1
            if n_new % 5 == 0 or n_new == 1:
                eta = (time.time() - t_global) / n_new * (len(qa_rows) - len(done) - n_new)
                print(f"[full-eval] {i}/{len(qa_rows)} (+{n_new})  last={row['elapsed_s']}s  ETA={eta/60:.1f}m", flush=True)
    print(f"[full-eval] done. new answers: {n_new}", flush=True)


def auto_metrics() -> dict:
    rows: list[dict] = []
    with open(ANS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))

    standard = [r for r in rows if not r["is_fallback_expected"]]
    fb_expected = [r for r in rows if r["is_fallback_expected"]]

    # fallback metrics
    fb_tp = sum(1 for r in fb_expected if r["used_fallback"])
    fb_fn = sum(1 for r in fb_expected if not r["used_fallback"])
    fb_fp = sum(1 for r in standard if r["used_fallback"])
    fb_tn = sum(1 for r in standard if not r["used_fallback"])
    fb_precision = fb_tp / max(1, fb_tp + fb_fp)
    fb_recall = fb_tp / max(1, fb_tp + fb_fn)

    # source URL match at top-1 / top-3 (only for non-fallback standard with expected urls)
    def _urls_at_k(srcs: list[dict], k: int) -> set[str]:
        urls: set[str] = set()
        for s in srcs[:k]:
            urls |= chunk_urls_from_source(s)
        return urls

    src_eval = [r for r in standard if r["expected_source_urls"]]
    p_at_1 = sum(1 for r in src_eval if _urls_at_k(r["sources"], 1) & set(r["expected_source_urls"])) / max(1, len(src_eval))
    p_at_3 = sum(1 for r in src_eval if _urls_at_k(r["sources"], 3) & set(r["expected_source_urls"])) / max(1, len(src_eval))

    # per-domain answer length and fallback rate
    by_domain: dict[int, dict] = {}
    for d in sorted({r["domain"] for r in rows}):
        sub = [r for r in rows if r["domain"] == d]
        std = [r for r in sub if not r["is_fallback_expected"]]
        lens = [len(r["generated_answer"]) for r in sub]
        by_domain[d] = {
            "n": len(sub),
            "n_standard": len(std),
            "answer_len_avg": int(sum(lens) / max(1, len(lens))),
            "answer_len_max": max(lens) if lens else 0,
            "fallback_triggered_rate": (sum(1 for r in sub if r["used_fallback"]) / max(1, len(sub))),
        }

    return {
        "n_total": len(rows),
        "n_standard": len(standard),
        "n_fallback_expected": len(fb_expected),
        "fallback": {
            "tp": fb_tp, "fn": fb_fn, "fp": fb_fp, "tn": fb_tn,
            "precision": fb_precision, "recall": fb_recall,
        },
        "source_url_match": {"p@1": p_at_1, "p@3": p_at_3, "n_eligible": len(src_eval)},
        "by_domain": by_domain,
    }


def write_report(agg: dict) -> None:
    path = os.path.join(OUT_DIR, "full_eval_auto_report.md")
    L = ["# D-1 Full RAG Evaluation (auto metrics)", ""]
    L.append(f"- total answered: {agg['n_total']}  (standard {agg['n_standard']} + fallback-expected {agg['n_fallback_expected']})")
    L.append("")
    L.append("## Fallback")
    fb = agg["fallback"]
    L.append(f"- precision = {fb['precision']:.1%}  recall = {fb['recall']:.1%}")
    L.append(f"- TP={fb['tp']} FN={fb['fn']} FP={fb['fp']} TN={fb['tn']}")
    L.append("")
    L.append("## Source URL match (standard only, expected_urls present)")
    su = agg["source_url_match"]
    L.append(f"- precision@1 = {su['p@1']:.1%}  precision@3 = {su['p@3']:.1%}  (n={su['n_eligible']})")
    L.append("")
    L.append("## Per-domain")
    L.append("| domain | n | answer len avg | fallback rate |")
    L.append("|---:|---:|---:|---:|")
    for d, st in sorted(agg["by_domain"].items()):
        L.append(f"| {d} | {st['n']} | {st['answer_len_avg']} | {st['fallback_triggered_rate']:.1%} |")
    L.append("")
    L.append("## Note")
    L.append("- Auto metrics are LLM-free. Answer factual accuracy requires LLM-as-judge (eval_full_judge.py).")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"[full-eval] report: {path}", flush=True)


def main() -> None:
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("gen", "all"):
        run_generate()
    if cmd in ("metrics", "all"):
        agg = auto_metrics()
        agg_path = os.path.join(OUT_DIR, "full_eval_auto.json")
        with open(agg_path, "w", encoding="utf-8") as fh:
            json.dump(agg, fh, ensure_ascii=False, indent=2)
        write_report(agg)
        print(f"[full-eval] aggregate: {agg_path}", flush=True)
        print(json.dumps(agg["fallback"], ensure_ascii=False))
        print(json.dumps(agg["source_url_match"], ensure_ascii=False))


if __name__ == "__main__":
    main()
