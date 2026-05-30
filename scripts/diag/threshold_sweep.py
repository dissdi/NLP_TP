"""Fallback threshold sweep — top_rerank_score 분포로 안전한 threshold 결정.

목적: 170 qa의 top_rerank_score, is_fallback_expected, expected_source_urls,
sources, judge_score를 결합하여 threshold 후보별 trade-off 추정.

각 threshold T에 대해 측정:
  - n_currently_fallback: 기존에 used_fallback=True 였던 qa
  - n_would_unblock(T):   T 적용 시 fallback 해제될 qa (top_rerank_score >= T)
  - among unblocked:
      n_recovery_candidate: expected_source_urls가 sources에 들어있고
                            현재 judge_score=0 — 답변 시 회수 가능성
      n_regression_risk:    is_fallback_expected=True (답변하면 안 되는 케이스가
                            새로 답변 가능) — 회귀 위험
      n_neutral:            나머지

또한 추천 threshold (회수 - 회귀)를 최대화하는 값 출력.

사용:
  python -m scripts.diag.threshold_sweep \\
      --answers eval/results/full_eval_answers.jsonl \\
      --judged  eval/results/full_eval_judged.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys


def _normalize_url(u: str) -> str:
    u = (u or "").strip()
    if u.endswith("/"):
        u = u[:-1]
    return u


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--answers", default="eval/results/full_eval_answers.jsonl")
    ap.add_argument("--judged", default="eval/results/full_eval_judged.jsonl")
    ap.add_argument("--candidates", default="0.01,0.03,0.05,0.07,0.10,0.12,0.15,0.18,0.20,0.25,0.30",
                    help="threshold 후보 (콤마 구분)")
    ap.add_argument("--list-current-fallbacks", action="store_true",
                    help="현재 fallback 발생한 qa 목록 + 점수 출력")
    args = ap.parse_args()

    # 1) answers 로드
    answers: dict[str, dict] = {}
    with open(args.answers, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            answers[d["qa_id"]] = d

    # 2) judged 로드 (judge_score)
    judged: dict[str, dict] = {}
    with open(args.judged, encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            judged[d["qa_id"]] = d

    # 3) 모든 qa에 대해 join
    rows: list[dict] = []
    for qa_id, a in answers.items():
        j = judged.get(qa_id, {})
        sources = a.get("sources") or []
        src_urls = {_normalize_url(s.get("source_url") or "") for s in sources if isinstance(s, dict)}
        exp_urls = {_normalize_url(u) for u in (a.get("expected_source_urls") or [])}
        gold_in_sources = bool(exp_urls & src_urls) or any(
            any((eu and (eu in su or su in eu)) for su in src_urls) for eu in exp_urls
        )
        rows.append({
            "qa_id": qa_id,
            "question": a.get("question", "")[:80],
            "top_rerank_score": float(a.get("top_rerank_score") or 0.0),
            "used_fallback": bool(a.get("used_fallback", False)),
            "is_fallback_expected": bool(a.get("is_fallback_expected", False)),
            "gold_in_sources": gold_in_sources,
            "judge_score": j.get("judge_score"),
        })

    n_total = len(rows)
    n_current_fb = sum(1 for r in rows if r["used_fallback"])
    n_expected_fb = sum(1 for r in rows if r["is_fallback_expected"])
    n_score0 = sum(1 for r in rows if r["judge_score"] == 0)

    print(f"# Threshold Sweep Report")
    print(f"## Inputs")
    print(f"- answers: {args.answers}  ({n_total} qa)")
    print(f"- judged:  {args.judged}")
    print(f"- 현재 used_fallback=True: {n_current_fb}")
    print(f"- is_fallback_expected=True: {n_expected_fb}")
    print(f"- judge_score=0: {n_score0}")
    print()

    # 4) Threshold sweep
    thresholds = [float(x) for x in args.candidates.split(",")]
    print(f"## Threshold sweep")
    print(f"| T | unblock | recovery候 | regression候 | net |")
    print(f"|---|---|---|---|---|")
    for T in thresholds:
        unblocked = [r for r in rows if r["used_fallback"] and r["top_rerank_score"] >= T]
        # recovery: 현재 fallback되어 0점인데 정답 URL이 sources에 있던 qa
        recovery = [r for r in unblocked
                    if r["judge_score"] == 0 and r["gold_in_sources"]]
        # regression: 현재 fallback되어 0점이지만 is_fallback_expected=True (답하면 안 됨)
        regression = [r for r in unblocked if r["is_fallback_expected"]]
        net = len(recovery) - len(regression)
        print(f"| {T:.2f} | {len(unblocked)} | {len(recovery)} | {len(regression)} | {net:+d} |")

    print()
    print(f"## 컬럼 정의")
    print(f"- unblock: T 적용 시 fallback 해제될 qa 수")
    print(f"- recovery候: unblock 중 (judge_score=0 AND 정답 URL이 sources에 들어있던 것) — 회수 가능성")
    print(f"- regression候: unblock 중 is_fallback_expected=True — 답하면 안 되는 케이스가 답하게 됨")
    print(f"- net: recovery - regression")
    print()

    # 5) 현재 fallback 발생 qa 상세
    print(f"## 현재 used_fallback=True qa 상세")
    cur_fb = sorted([r for r in rows if r["used_fallback"]], key=lambda x: x["top_rerank_score"])
    print(f"| qa_id | top_rerank_score | judge | gold_in_sources | is_fb_expected | question |")
    print(f"|---|---|---|---|---|---|")
    for r in cur_fb:
        print(f"| {r['qa_id']} | {r['top_rerank_score']:.4f} | {r['judge_score']} | {r['gold_in_sources']} | {r['is_fallback_expected']} | {r['question'][:50]} |")

    print()
    # 6) score 분포 요약 (used_fallback=False 그룹은 항상 답변한 거)
    answered = [r for r in rows if not r["used_fallback"]]
    print(f"## 답변(used_fallback=False) qa 의 top_rerank_score 통계")
    if answered:
        scores = sorted(r["top_rerank_score"] for r in answered)
        n = len(scores)
        def pct(p):
            i = max(0, min(n - 1, int(n * p / 100)))
            return scores[i]
        print(f"- n: {n}, min={scores[0]:.4f}, p10={pct(10):.4f}, p25={pct(25):.4f}, "
              f"median={pct(50):.4f}, p75={pct(75):.4f}, max={scores[-1]:.4f}")
        below_03 = [s for s in scores if s < 0.3]
        print(f"- 답변한 qa 중 score<0.3 인 것: {len(below_03)} ({len(below_03)/n:.1%})")


if __name__ == "__main__":
    main()
