"""D-1 retrieval-only evaluation.

For each of the 170 QA items in eval/eval-generated.jsonl, run HybridRetriever
+ rerank and check whether expected_source_urls appear in the retrieved top-k.

Metrics:
  - recall@k for k in {1, 5, 10, 20}
  - top-1 hit rate
  - per-domain breakdown
  - fallback precision/recall (is_fallback_expected vs whether top-1 rerank score
    falls below threshold)

This is RETRIEVAL-only (no LLM answer generation), so it runs fast (~5 minutes
on GPU for 170 queries).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

from .reranker import rerank
from .retriever import build_default

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
EVAL_PATH = os.path.join(ROOT, "eval", "eval-generated.jsonl")
OUT_DIR = os.path.join(ROOT, "eval", "results")

# Same threshold used by the live pipeline (generate.py).
FALLBACK_THRESHOLD = 0.3

K_VALUES = [1, 5, 10, 20]


def load_eval() -> list[dict]:
    rows: list[dict] = []
    with open(EVAL_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            rows.append(json.loads(line))
    return rows


def chunk_urls(meta: dict) -> set[str]:
    """Collect all URLs that identify a retrieved chunk."""
    urls: set[str] = set()
    for k in ("_canonical_url", "source_url"):
        v = (meta or {}).get(k)
        if v:
            urls.add(v.strip())
    for v in (meta or {}).get("_alias_urls") or []:
        if v:
            urls.add(v.strip())
    return urls


def _hits_at_k(retrieved_urls_per_rank: list[set[str]], expected: set[str], k: int) -> bool:
    """Return True if any expected URL is in retrieved top-k union."""
    if not expected or k == 0:
        return False
    union: set[str] = set()
    for s in retrieved_urls_per_rank[:k]:
        union |= s
    return bool(union & expected)


def _top1_url_match(retrieved_urls_per_rank: list[set[str]], expected: set[str]) -> bool:
    if not expected or not retrieved_urls_per_rank:
        return False
    return bool(retrieved_urls_per_rank[0] & expected)


@dataclass
class EvalRow:
    qa_id: str
    question: str
    domain: int
    question_type: str
    is_fallback_expected: bool
    expected_urls: list[str]
    retrieved_top: list[dict]  # list of {chunk_id, title, rerank_score, urls}
    recall_at: dict[int, bool]
    top1_url_match: bool
    top_rerank_score: float
    triggered_fallback: bool


def evaluate_one(retriever, qa: dict, retrieve_top_k: int = 30, rerank_top_k: int = 20) -> EvalRow:
    q = qa["question"]
    expected = set((qa.get("expected_source_urls") or []))

    pool = retriever.retrieve(q, top_k=retrieve_top_k, bm25_pool=100, dense_pool=50)
    hits = rerank(q, pool, top_k=rerank_top_k)

    retrieved_urls_per_rank: list[set[str]] = []
    retrieved_top: list[dict] = []
    for h in hits:
        urls = chunk_urls(h.meta or {})
        retrieved_urls_per_rank.append(urls)
        retrieved_top.append({
            "chunk_id": h.chunk_id,
            "title": ((h.meta or {}).get("source_title") or "")[:80],
            "rerank_score": float((h.meta or {}).get("_rerank_score", 0.0)),
            "urls": sorted(urls),
        })

    top_score = retrieved_top[0]["rerank_score"] if retrieved_top else 0.0
    triggered_fallback = top_score < FALLBACK_THRESHOLD

    return EvalRow(
        qa_id=qa["qa_id"],
        question=q,
        domain=qa.get("domain", 0),
        question_type=qa.get("question_type", ""),
        is_fallback_expected=bool(qa.get("is_fallback_expected", False)),
        expected_urls=sorted(expected),
        retrieved_top=retrieved_top,
        recall_at={k: _hits_at_k(retrieved_urls_per_rank, expected, k) for k in K_VALUES},
        top1_url_match=_top1_url_match(retrieved_urls_per_rank, expected),
        top_rerank_score=top_score,
        triggered_fallback=triggered_fallback,
    )


def aggregate(rows: list[EvalRow]) -> dict:
    # Split rows
    standard = [r for r in rows if not r.is_fallback_expected]
    fallback = [r for r in rows if r.is_fallback_expected]

    def _mean_recall(items: list[EvalRow], k: int) -> float:
        if not items:
            return 0.0
        return sum(1 for r in items if r.recall_at[k]) / len(items)

    overall = {f"recall@{k}": _mean_recall(standard, k) for k in K_VALUES}
    overall["top1_url_match"] = sum(1 for r in standard if r.top1_url_match) / max(1, len(standard))

    # per-domain
    by_domain: dict[int, dict] = {}
    domains = sorted({r.domain for r in standard})
    for d in domains:
        sub = [r for r in standard if r.domain == d]
        by_domain[d] = {
            "n": len(sub),
            **{f"recall@{k}": _mean_recall(sub, k) for k in K_VALUES},
        }

    # fallback precision/recall
    # TP = fallback_expected True AND triggered_fallback True
    tp = sum(1 for r in fallback if r.triggered_fallback)
    fn = sum(1 for r in fallback if not r.triggered_fallback)
    fp = sum(1 for r in standard if r.triggered_fallback)
    tn = sum(1 for r in standard if not r.triggered_fallback)
    fb_precision = tp / max(1, tp + fp)
    fb_recall = tp / max(1, tp + fn)
    return {
        "overall": overall,
        "by_domain": by_domain,
        "fallback": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": fb_precision,
            "recall": fb_recall,
            "n_fallback_expected": len(fallback),
            "n_standard": len(standard),
        },
    }


def save_results(rows: list[EvalRow], agg: dict) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    # per-query JSONL
    per_query_path = os.path.join(OUT_DIR, "retrieval_eval_per_query.jsonl")
    with open(per_query_path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps({
                "qa_id": r.qa_id,
                "question": r.question,
                "domain": r.domain,
                "question_type": r.question_type,
                "is_fallback_expected": r.is_fallback_expected,
                "expected_urls": r.expected_urls,
                "retrieved_top": r.retrieved_top[:5],
                "recall_at_1": r.recall_at[1],
                "recall_at_5": r.recall_at[5],
                "recall_at_10": r.recall_at[10],
                "recall_at_20": r.recall_at[20],
                "top1_url_match": r.top1_url_match,
                "top_rerank_score": r.top_rerank_score,
                "triggered_fallback": r.triggered_fallback,
            }, ensure_ascii=False) + "\n")
    # aggregate JSON
    agg_path = os.path.join(OUT_DIR, "retrieval_eval_aggregate.json")
    with open(agg_path, "w", encoding="utf-8") as fh:
        json.dump(agg, fh, ensure_ascii=False, indent=2)
    # human-readable report
    report_path = os.path.join(OUT_DIR, "retrieval_eval_report.md")
    _write_report(report_path, agg, rows)
    print(f"[eval] per-query  : {per_query_path}", flush=True)
    print(f"[eval] aggregate  : {agg_path}", flush=True)
    print(f"[eval] report     : {report_path}", flush=True)


def _write_report(path: str, agg: dict, rows: list[EvalRow]) -> None:
    L: list[str] = []
    L.append("# D-1 Retrieval-only Evaluation Report")
    L.append("")
    L.append("## Overall (standard 155 questions, fallback excluded)")
    o = agg["overall"]
    L.append(f"- top-1 URL exact match: **{o['top1_url_match']:.1%}**")
    for k in K_VALUES:
        L.append(f"- recall@{k}: **{o[f'recall@{k}']:.1%}**")
    L.append("")
    L.append("## Fallback (15 expected fallbacks)")
    f = agg["fallback"]
    L.append(f"- precision (TP / (TP+FP)) = {f['precision']:.1%}  (TP={f['tp']} FP={f['fp']})")
    L.append(f"- recall    (TP / (TP+FN)) = {f['recall']:.1%}    (TP={f['tp']} FN={f['fn']})")
    L.append(f"- standard triggered_fallback (FP rate): {f['fp']}/{f['n_standard']} ({f['fp']/max(1,f['n_standard']):.1%})")
    L.append("")
    L.append("## Per-domain recall (standard only)")
    L.append("| domain | n | recall@1 | recall@5 | recall@10 | recall@20 |")
    L.append("|---:|---:|---:|---:|---:|---:|")
    for d, st in sorted(agg["by_domain"].items()):
        L.append(f"| {d} | {st['n']} | {st['recall@1']:.1%} | {st['recall@5']:.1%} | {st['recall@10']:.1%} | {st['recall@20']:.1%} |")
    L.append("")
    # Bottom 5 worst standard cases (no expected url found in top-20)
    losses = [r for r in rows if (not r.is_fallback_expected) and not r.recall_at[20]]
    L.append(f"## Hard misses: standard cases with NO expected URL in top-20 ({len(losses)})")
    for r in losses[:20]:
        L.append(f"- [{r.domain}/{r.question_type}] **{r.question[:80]}**")
        L.append(f"    expected: {r.expected_urls}")
        L.append(f"    top-1: {r.retrieved_top[0]['title'] if r.retrieved_top else '(none)'} score={r.top_rerank_score:+.2f}")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def run() -> None:
    print("[eval] loading indices ...", flush=True)
    retriever = build_default()
    print(f"[eval] meta rows: {len(retriever.idx.meta)}", flush=True)
    qa_rows = load_eval()
    print(f"[eval] eval items: {len(qa_rows)}", flush=True)

    results: list[EvalRow] = []
    for i, qa in enumerate(qa_rows, 1):
        r = evaluate_one(retriever, qa)
        results.append(r)
        if i % 20 == 0:
            print(f"[eval] {i}/{len(qa_rows)}", flush=True)

    agg = aggregate(results)
    print("\n=== aggregate ===")
    print(json.dumps(agg["overall"], ensure_ascii=False, indent=2))
    print("fallback:", json.dumps(agg["fallback"], ensure_ascii=False))
    save_results(results, agg)


if __name__ == "__main__":
    run()
