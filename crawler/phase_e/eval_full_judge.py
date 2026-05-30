"""LLM-as-judge for D-1 full RAG evaluation.

Input:  eval/results/full_eval_answers.jsonl  (from eval_full.py)
Output: eval/results/full_eval_judged.jsonl   (per-query score + reason)
        eval/results/full_eval_judged_agg.json
        eval/results/full_eval_judged_report.md

Judge model: same Qwen2.5-14B-Instruct 4-bit (self-judge — self-bias possible,
but acceptable for our 50% LLM-as-judge eval protocol per project doc).

Scoring (3-point):
  2 = core facts (numbers/articles/dates) ALL correct vs gold
  1 = partial: some facts match, some missing/vague
  0 = wrong / hallucinated facts conflicting with gold

Fallback cases scored automatically (no LLM call needed):
  is_fallback_expected=True  + used_fallback=True  -> 2  (correct refusal)
  is_fallback_expected=True  + used_fallback=False -> 0  (hallucination risk)
  is_fallback_expected=False + used_fallback=True  -> 0  (over-refusal)
  is_fallback_expected=False + used_fallback=False -> LLM judge

Resumable: skips qa_id already in output.
"""
from __future__ import annotations

import json
import os
import re
import time
from collections import defaultdict
from typing import Optional

from .llm import DEFAULT_LLM, chat

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_DIR = os.path.join(ROOT, "eval", "results")
_TAG = os.environ.get("EVAL_TAG", "")
_SUFFIX = f"_{_TAG}" if _TAG else ""
ANS_PATH = os.path.join(OUT_DIR, f"full_eval_answers{_SUFFIX}.jsonl")
JUDGE_PATH = os.path.join(OUT_DIR, f"full_eval_judged{_SUFFIX}.jsonl")
AGG_PATH = os.path.join(OUT_DIR, f"full_eval_judged_agg{_SUFFIX}.json")
REPORT_PATH = os.path.join(OUT_DIR, f"full_eval_judged_report{_SUFFIX}.md")


_JUDGE_SYS = """너는 RAG 시스템의 답변 정확성 평가자다.
주어진 [질문]에 대해 [정답]과 [생성답변]이 같은 핵심 사실을 말하는지 평가한다.

평가 기준:
1. 핵심 사실(숫자/조항번호/날짜/기간/대상/금액)이 [정답]과 일치하는지가 가장 중요하다.
2. 표현의 자연스러움·길이·말투는 평가하지 않는다.
3. [정답]에 없는 추가 정보가 있어도 [생성답변]의 핵심 사실이 [정답]과 모순되지 않으면 감점하지 않는다.
4. 핵심 사실이 모순되거나 [정답]에 없는 숫자/날짜를 만들어내면 0점.

점수 (정수 하나):
- 2: 핵심 사실이 모두 [정답]과 일치
- 1: 부분 일치 (일부 사실 맞고 일부 누락·모호)
- 0: 사실 모순·환각

출력 형식 (엄수):
- 첫 줄: 숫자만 (0 또는 1 또는 2)
- 두 번째 줄부터: 이유를 한국어 한 문장으로 (50자 이내)
다른 텍스트, 머리말, markdown 절대 금지.
"""


def load_answers() -> list[dict]:
    rows: list[dict] = []
    with open(ANS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_judged() -> dict[str, dict]:
    out: dict[str, dict] = {}
    if not os.path.exists(JUDGE_PATH):
        return out
    with open(JUDGE_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
                out[d["qa_id"]] = d
            except Exception:
                pass
    return out


def parse_score(text: str) -> tuple[int, str]:
    if not text:
        return -1, ""
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    score = -1
    if lines:
        m = re.search(r"\b([012])\b", lines[0])
        if m:
            score = int(m.group(1))
    reason = " ".join(lines[1:]).strip()[:200]
    return score, reason


def auto_score(row: dict) -> Optional[tuple[int, str]]:
    """Score fallback cases without calling LLM. Return None for LLM-judged path."""
    exp = bool(row.get("is_fallback_expected"))
    used = bool(row.get("used_fallback"))
    if exp and used:
        return 2, "정답 거절 (fallback expected + triggered)"
    if exp and not used:
        return 0, "거절해야 할 케이스에 답변함 (FN)"
    if not exp and used:
        return 0, "답변해야 할 케이스를 거절함 (FP)"
    return None  # standard non-fallback: LLM judge


def judge_one(row: dict, model_id: str = DEFAULT_LLM) -> tuple[int, str, str]:
    """Return (score, reason, raw_output)."""
    user_msg = (
        f"[질문]\n{row['question']}\n\n"
        f"[정답]\n{row.get('answer_gold','')}\n\n"
        f"[생성답변]\n{row.get('generated_answer','')}"
    )
    out = chat(
        user_msg=user_msg,
        system_msg=_JUDGE_SYS,
        model_id=model_id,
        max_new_tokens=128,
        temperature=0.0,
    )
    score, reason = parse_score(out)
    return score, reason, out


def run_judge() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    answers = load_answers()
    done = load_judged()
    print(f"[judge] total {len(answers)}  done {len(done)}", flush=True)

    n_new = 0
    t_global = time.time()
    n_to_do = sum(1 for r in answers if r["qa_id"] not in done)
    with open(JUDGE_PATH, "a", encoding="utf-8") as out:
        for i, row in enumerate(answers, 1):
            qid = row["qa_id"]
            if qid in done:
                continue
            t0 = time.time()
            auto = auto_score(row)
            if auto is not None:
                score, reason = auto
                raw = ""
                source = "auto"
            else:
                score, reason, raw = judge_one(row)
                source = "llm"
            res = {
                "qa_id": qid,
                "domain": row.get("domain", 0),
                "question_type": row.get("question_type", ""),
                "is_fallback_expected": row.get("is_fallback_expected", False),
                "used_fallback": row.get("used_fallback", False),
                "judge_score": score,
                "judge_reason": reason,
                "judge_source": source,
                "judge_raw": raw,
                "elapsed_s": round(time.time() - t0, 2),
            }
            out.write(json.dumps(res, ensure_ascii=False) + "\n")
            out.flush()
            n_new += 1
            if n_new % 10 == 0 or n_new == 1:
                eta = (time.time() - t_global) / n_new * (n_to_do - n_new)
                print(f"[judge] {i}/{len(answers)} (+{n_new})  last={res['elapsed_s']}s  ETA={eta/60:.1f}m", flush=True)
    print(f"[judge] done. new judgments: {n_new}", flush=True)


def aggregate() -> dict:
    rows: list[dict] = []
    with open(JUDGE_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))

    n = len(rows)
    valid = [r for r in rows if r["judge_score"] >= 0]
    n_invalid = n - len(valid)

    def _avg(items): return (sum(r["judge_score"] for r in items) / len(items)) if items else 0.0
    def _correct(items): return (sum(1 for r in items if r["judge_score"] == 2) / len(items)) if items else 0.0

    # by domain
    by_domain: dict[int, dict] = {}
    for d in sorted({r["domain"] for r in valid}):
        sub = [r for r in valid if r["domain"] == d]
        by_domain[d] = {
            "n": len(sub),
            "avg_score": round(_avg(sub), 3),
            "correct_rate": round(_correct(sub), 3),
            "score_2": sum(1 for r in sub if r["judge_score"] == 2),
            "score_1": sum(1 for r in sub if r["judge_score"] == 1),
            "score_0": sum(1 for r in sub if r["judge_score"] == 0),
        }
    # by source (auto vs llm)
    by_source = {}
    for s in sorted({r["judge_source"] for r in valid}):
        sub = [r for r in valid if r["judge_source"] == s]
        by_source[s] = {"n": len(sub), "avg_score": round(_avg(sub), 3), "correct_rate": round(_correct(sub), 3)}
    # by question_type
    by_qt = {}
    for qt in sorted({r["question_type"] for r in valid}):
        sub = [r for r in valid if r["question_type"] == qt]
        by_qt[qt] = {"n": len(sub), "avg_score": round(_avg(sub), 3), "correct_rate": round(_correct(sub), 3)}

    return {
        "n_total": n,
        "n_invalid_parse": n_invalid,
        "overall_avg_score": round(_avg(valid), 3),
        "overall_correct_rate_score2": round(_correct(valid), 3),
        "by_domain": by_domain,
        "by_source": by_source,
        "by_question_type": by_qt,
    }


def write_report(agg: dict) -> None:
    rows = []
    with open(JUDGE_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                rows.append(json.loads(line))
    L = ["# D-1 LLM-as-judge Report", ""]
    L.append(f"- judged total: {agg['n_total']}")
    L.append(f"- invalid parse: {agg['n_invalid_parse']}")
    L.append(f"- **overall avg score: {agg['overall_avg_score']:.3f} / 2.0**")
    L.append(f"- **overall correct rate (score=2): {agg['overall_correct_rate_score2']:.1%}**")
    L.append("")
    L.append("## By judge source (auto: fallback rules / llm: standard cases)")
    L.append("| source | n | avg | correct rate |")
    L.append("|---|---:|---:|---:|")
    for s, st in agg["by_source"].items():
        L.append(f"| {s} | {st['n']} | {st['avg_score']:.3f} | {st['correct_rate']:.1%} |")
    L.append("")
    L.append("## By domain")
    L.append("| domain | n | avg | correct(score=2) | s2 | s1 | s0 |")
    L.append("|---:|---:|---:|---:|---:|---:|---:|")
    for d, st in sorted(agg["by_domain"].items()):
        L.append(f"| {d} | {st['n']} | {st['avg_score']:.3f} | {st['correct_rate']:.1%} | {st['score_2']} | {st['score_1']} | {st['score_0']} |")
    L.append("")
    L.append("## By question_type")
    L.append("| type | n | avg | correct rate |")
    L.append("|---|---:|---:|---:|")
    for qt, st in agg["by_question_type"].items():
        L.append(f"| {qt} | {st['n']} | {st['avg_score']:.3f} | {st['correct_rate']:.1%} |")
    L.append("")
    L.append("## Low-score (score=0) cases — review priority")
    losses = [r for r in rows if r.get("judge_score") == 0]
    L.append(f"Total: {len(losses)}")
    for r in losses[:30]:
        L.append(f"- [d{r['domain']}/{r['question_type']}] qa_id={r['qa_id']}  fb_exp={r['is_fallback_expected']}  used_fb={r['used_fallback']}")
        L.append(f"    reason: {r['judge_reason']}")
    with open(REPORT_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print(f"[judge] report: {REPORT_PATH}", flush=True)


def main() -> None:
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("judge", "all"):
        run_judge()
    if cmd in ("metrics", "all"):
        agg = aggregate()
        with open(AGG_PATH, "w", encoding="utf-8") as fh:
            json.dump(agg, fh, ensure_ascii=False, indent=2)
        write_report(agg)
        print(f"[judge] aggregate: {AGG_PATH}")
        print(json.dumps({k: agg[k] for k in ("overall_avg_score", "overall_correct_rate_score2", "n_invalid_parse")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
