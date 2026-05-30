"""Retrieval pipeline 단계별 진단.

목적: D-1 score=0 오답의 정답 chunk가 retrieval pipeline의 어느 단계에서
top-k 밖으로 떨어지는지 확인한다.

단계별 출력:
  1. BM25 raw scores (모든 BM25 track 통합) — gold chunk rank/score
  2. Dense raw scores (모든 FAISS track 통합) — gold chunk rank/score
  3. RRF fused — gold chunk rank/score
  4. Reranker top-k 적용 후 — gold chunk rank/score

사용 예:
  # 단일 쿼리 + 정답 URL
  python -m scripts.diag.retrieval_debug \\
      --query "제1학생회관 1층의 제1학생식당에서는 어떤 종류의 메뉴를 판매하나요?" \\
      --expected-url "https://plus.cnu.ac.kr/html/kr/sub05/sub05_05050101.html"

  # eval-generated.jsonl에서 qa_id 일괄 진단
  python -m scripts.diag.retrieval_debug \\
      --eval-file eval/eval-generated.jsonl \\
      --qa-ids G260528102,G260528111,G260528112,G260528124

  # reranker 모델 지정 (default: BAAI/bge-reranker-v2-m3)
  python -m scripts.diag.retrieval_debug --qa-ids G260528111 \\
      --reranker dragonkue/bge-reranker-v2-m3-ko

  # query expansion (aliases.json) 적용
  python -m scripts.diag.retrieval_debug --qa-ids G260528111 --expand
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.phase_e.retriever import build_default, HybridRetriever  # noqa: E402
from crawler.phase_e.tokenizer import tokenize  # noqa: E402
from crawler.phase_e.encoder import encode_query  # noqa: E402

EVAL_FILE_DEFAULT = os.path.join(_ROOT, "eval", "eval-generated.jsonl")
ALIASES_FILE_DEFAULT = os.path.join(_ROOT, "crawler", "phase_e", "aliases.json")


# ---------------------------------------------------------------------------- #
# 정답 chunk_id lookup
# ---------------------------------------------------------------------------- #

def _normalize_url(u: str) -> str:
    """URL 비교용 정규화: trailing slash 제거, query 정렬은 안 함 (mng_no 보존)."""
    u = (u or "").strip()
    if u.endswith("/"):
        u = u[:-1]
    return u


def find_gold_chunk_ids(
    expected_urls: list[str],
    meta: dict[str, dict],
    alias_winners: dict[str, str] | None = None,
) -> list[tuple[str, str]]:
    """expected URL list로부터 매칭되는 chunk_id 목록 추출.

    Returns: [(chunk_id, matched_url), ...]
    """
    norm_targets = {_normalize_url(u) for u in expected_urls}
    out: list[tuple[str, str]] = []
    for cid, m in meta.items():
        src = _normalize_url(m.get("source_url") or "")
        if not src:
            continue
        # 1) 완전 일치
        if src in norm_targets:
            out.append((cid, src))
            continue
        # 2) menu_dvs_cd 등 일부 변형 매칭: substring (단순)
        for t in norm_targets:
            if t and (t in src or src in t):
                out.append((cid, src))
                break
    return out


# ---------------------------------------------------------------------------- #
# Query expansion
# ---------------------------------------------------------------------------- #

def expand_query(query: str, aliases: dict[str, str]) -> str:
    extra_terms: list[str] = []
    for short, full in aliases.items():
        if short.startswith("_"):
            continue
        if short in query:
            extra_terms.append(full)
    if extra_terms:
        return f"{query} {' '.join(extra_terms)}"
    return query


# ---------------------------------------------------------------------------- #
# Per-query diagnosis
# ---------------------------------------------------------------------------- #

def diagnose_query(
    retriever: HybridRetriever,
    query: str,
    expected_urls: list[str],
    *,
    bm25_pool: int = 200,
    dense_pool: int = 200,
    rrf_k: int = 60,
    rerank_top_n: int = 50,
    reranker_id: Optional[str] = None,
    show_top: int = 5,
) -> dict:
    """단계별 retrieval 결과 + gold chunk rank 진단."""
    idx = retriever.idx
    meta = idx.meta

    gold_pairs = find_gold_chunk_ids(expected_urls, meta)
    gold_ids = {cid for cid, _ in gold_pairs}

    report: dict = {
        "query": query,
        "expected_urls": expected_urls,
        "gold_chunk_count": len(gold_ids),
        "gold_pairs_sample": gold_pairs[:5],
    }
    if not gold_ids:
        report["error"] = "정답 chunk 0건 — expected URL이 corpus에 없음"
        return report

    # 1) BM25
    q_tokens = tokenize(query)
    bm25_map = retriever._bm25_scores(q_tokens)
    bm25_ranked = retriever._to_ranked(bm25_map)
    bm25_rank = {cid: (rk, sc, src) for cid, rk, sc, src in bm25_ranked}

    gold_bm = []
    for cid in gold_ids:
        if cid in bm25_rank:
            rk, sc, src = bm25_rank[cid]
            gold_bm.append({"chunk_id": cid, "rank": rk, "score": round(sc, 4), "track": src})
    gold_bm.sort(key=lambda x: x["rank"])
    report["bm25"] = {
        "total_scored_chunks": len(bm25_ranked),
        "tokens": q_tokens,
        "gold_hits": gold_bm,
        "best_gold_rank": gold_bm[0]["rank"] if gold_bm else None,
        "top_passages": [
            {"rank": rk, "chunk_id": cid, "score": round(sc, 4),
             "title": (meta.get(cid, {}).get("source_title") or "")[:50]}
            for cid, rk, sc, _ in bm25_ranked[:show_top]
        ],
    }

    # 2) Dense
    import numpy as np  # noqa
    q_emb = encode_query(query, model_id=retriever.model_id)
    dense_map = retriever._dense_scores(q_emb, top_per_track=dense_pool)
    dense_ranked = retriever._to_ranked(dense_map)
    dense_rank = {cid: (rk, sc, src) for cid, rk, sc, src in dense_ranked}

    gold_de = []
    for cid in gold_ids:
        if cid in dense_rank:
            rk, sc, src = dense_rank[cid]
            gold_de.append({"chunk_id": cid, "rank": rk, "score": round(sc, 4), "track": src})
    gold_de.sort(key=lambda x: x["rank"])
    report["dense"] = {
        "pool_per_track": dense_pool,
        "total_scored_chunks": len(dense_ranked),
        "gold_hits": gold_de,
        "best_gold_rank": gold_de[0]["rank"] if gold_de else None,
        "top_passages": [
            {"rank": rk, "chunk_id": cid, "score": round(sc, 4),
             "title": (meta.get(cid, {}).get("source_title") or "")[:50]}
            for cid, rk, sc, _ in dense_ranked[:show_top]
        ],
    }

    # 3) RRF — 실제 production retrieve()를 큰 top_k로 호출
    fused_results = retriever.retrieve(
        query, top_k=rerank_top_n, bm25_pool=bm25_pool, dense_pool=dense_pool, rrf_k=rrf_k
    )
    fused_ids = [r.chunk_id for r in fused_results]
    gold_rrf = []
    for cid in gold_ids:
        if cid in fused_ids:
            rk = fused_ids.index(cid) + 1
            r = fused_results[rk - 1]
            gold_rrf.append({"chunk_id": cid, "rank": rk, "rrf_score": round(r.rrf_score, 4),
                             "bm25_rank": r.bm25_rank, "dense_rank": r.dense_rank})
    gold_rrf.sort(key=lambda x: x["rank"])
    report["rrf"] = {
        "pool": rerank_top_n,
        "gold_hits": gold_rrf,
        "best_gold_rank": gold_rrf[0]["rank"] if gold_rrf else None,
        "top_passages": [
            {"rank": i + 1, "chunk_id": r.chunk_id, "rrf": round(r.rrf_score, 4),
             "title": (r.meta.get("source_title") or "")[:50] if r.meta else "",
             "bm25_rank": r.bm25_rank, "dense_rank": r.dense_rank}
            for i, r in enumerate(fused_results[:show_top])
        ],
    }

    # 4) Reranker
    if reranker_id:
        # text field가 meta에 있어야 reranker가 동작
        for r in fused_results:
            if r.meta and "text" not in r.meta:
                pass  # loader.load_meta()가 이미 text 포함 가정
        from crawler.phase_e.reranker import rerank as do_rerank
        reranked = do_rerank(query, fused_results, top_k=rerank_top_n, model_id=reranker_id)
        rer_ids = [r.chunk_id for r in reranked]
        gold_rer = []
        for cid in gold_ids:
            if cid in rer_ids:
                rk = rer_ids.index(cid) + 1
                r = reranked[rk - 1]
                gold_rer.append({"chunk_id": cid, "rank": rk,
                                 "score": round(r.meta.get("_rerank_score", 0.0), 4)})
        gold_rer.sort(key=lambda x: x["rank"])
        report["reranker"] = {
            "model": reranker_id,
            "input_pool": len(fused_results),
            "gold_hits": gold_rer,
            "best_gold_rank": gold_rer[0]["rank"] if gold_rer else None,
            "top_passages": [
                {"rank": i + 1, "chunk_id": r.chunk_id,
                 "score": round(r.meta.get("_rerank_score", 0.0), 4),
                 "title": (r.meta.get("source_title") or "")[:50] if r.meta else ""}
                for i, r in enumerate(reranked[:show_top])
            ],
        }

    return report


def _fmt_report(rep: dict) -> str:
    lines: list[str] = []
    lines.append("=" * 80)
    lines.append(f"Q: {rep['query'][:120]}")
    lines.append(f"Expected URLs: {rep['expected_urls']}")
    lines.append(f"Gold chunk count: {rep['gold_chunk_count']}")
    if rep.get("error"):
        lines.append(f"  ERROR: {rep['error']}")
        return "\n".join(lines)

    for stage in ("bm25", "dense", "rrf", "reranker"):
        if stage not in rep:
            continue
        s = rep[stage]
        lines.append(f"\n[{stage.upper()}]")
        if stage == "bm25":
            lines.append(f"  tokens: {s.get('tokens')}")
        if stage == "reranker":
            lines.append(f"  model: {s.get('model')}, pool: {s.get('input_pool')}")
        best = s.get("best_gold_rank")
        lines.append(f"  best gold rank: {best}")
        for g in s.get("gold_hits", [])[:5]:
            lines.append(f"    gold #{g['rank']} :: {g}")
        lines.append("  Top passages:")
        for t in s.get("top_passages", []):
            lines.append(f"    {t}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------------------- #

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--query", help="단일 쿼리")
    ap.add_argument("--expected-url", action="append", default=[],
                    help="정답 URL (여러 번 사용 가능)")
    ap.add_argument("--eval-file", default=EVAL_FILE_DEFAULT,
                    help="eval-generated.jsonl 경로")
    ap.add_argument("--qa-ids", help="콤마 구분 qa_id 목록 (eval-file에서 lookup)")
    ap.add_argument("--reranker", default="dragonkue/bge-reranker-v2-m3-ko",
                    help="reranker 모델 ID. 빈 문자열이면 skip")
    ap.add_argument("--no-reranker", action="store_true", help="reranker 단계 skip")
    ap.add_argument("--expand", action="store_true",
                    help="aliases.json으로 query expand")
    ap.add_argument("--aliases-file", default=ALIASES_FILE_DEFAULT)
    ap.add_argument("--bm25-pool", type=int, default=200)
    ap.add_argument("--dense-pool", type=int, default=200)
    ap.add_argument("--rerank-top-n", type=int, default=50,
                    help="RRF 단계에서 reranker에 넘길 top-N")
    ap.add_argument("--show-top", type=int, default=5,
                    help="각 단계 top passage 몇 개 출력")
    ap.add_argument("--rrf-k", type=int, default=60)
    ap.add_argument("--json", action="store_true", help="JSON으로 출력")
    ap.add_argument("--out", help="결과 JSONL 저장 경로")
    args = ap.parse_args()

    # 1) qa list 수집
    queries: list[tuple[str, str, list[str]]] = []  # (qa_id, question, expected_urls)
    if args.qa_ids:
        wanted = set(args.qa_ids.split(","))
        with open(args.eval_file, encoding="utf-8") as f:
            for line in f:
                d = json.loads(line)
                if d.get("qa_id") in wanted:
                    queries.append((
                        d["qa_id"],
                        d["question"],
                        d.get("expected_source_urls") or [],
                    ))
    elif args.query:
        queries.append(("(adhoc)", args.query, list(args.expected_url)))
    else:
        ap.error("--query 또는 --qa-ids 중 하나 필요")

    # 2) aliases
    aliases: dict[str, str] = {}
    if args.expand:
        with open(args.aliases_file, encoding="utf-8") as f:
            aliases = json.load(f)

    # 3) retriever 로드
    print(f"[diag] loading retrieval index ...", file=sys.stderr, flush=True)
    retriever = build_default()
    print(f"[diag] bm25 tracks: {[t.name for t in retriever.idx.bm25_tracks]}", file=sys.stderr)
    print(f"[diag] dense tracks: {[t.name for t in retriever.idx.faiss_tracks]}", file=sys.stderr)
    print(f"[diag] meta rows: {len(retriever.idx.meta)}", file=sys.stderr)

    reranker_id = None if args.no_reranker else (args.reranker or None)

    out_f = open(args.out, "w", encoding="utf-8") if args.out else None
    try:
        for qa_id, question, urls in queries:
            q_for_retrieval = expand_query(question, aliases) if aliases else question
            rep = diagnose_query(
                retriever,
                q_for_retrieval,
                urls,
                bm25_pool=args.bm25_pool,
                dense_pool=args.dense_pool,
                rrf_k=args.rrf_k,
                rerank_top_n=args.rerank_top_n,
                reranker_id=reranker_id,
                show_top=args.show_top,
            )
            rep["qa_id"] = qa_id
            rep["raw_question"] = question
            if q_for_retrieval != question:
                rep["expanded_query"] = q_for_retrieval

            if args.json:
                print(json.dumps(rep, ensure_ascii=False))
            else:
                print(f"\n\n###### qa_id={qa_id}")
                print(_fmt_report(rep))

            if out_f:
                out_f.write(json.dumps(rep, ensure_ascii=False) + "\n")
    finally:
        if out_f:
            out_f.close()
            print(f"\n[diag] wrote results to {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
