"""백마광장 게시판 청크에서 FAQ 시드 추출 (Phase D-1 입력용).

Sprint 1 day2 의 5.4 백마광장 백본 청크 중 FAQ 패턴 (Q: ... A: ...) 또는 질문형
제목 (?로 끝남, "문의", "어떻게", "어디서" 등 키워드) 매칭 → seeds.jsonl.

Phase D-1 LLM Q&A 생성 시 이 시드를 입력으로 받아 평가셋용 합성 Q&A를 생성한다.

실행:
  python -m scripts.sprint2_faq_seed
  python -m scripts.sprint2_faq_seed --src data/sprint1/day4/chunks.jsonl --out X.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# 질문성 시그널
QUESTION_TITLE = re.compile(r"\?$|어떻게|어디서|문의|FAQ|Q\.|Q:|얼마|언제|무엇|왜")
# 본문 안의 Q&A 패턴
QA_BODY = re.compile(r"(Q\.|Q:|문\s*:|문의\s*:).{5,200}?(A\.|A:|답\s*:)", re.S)


def is_faq_candidate(d: dict) -> tuple[bool, str]:
    """(is_candidate, reason). reason 으로 분류 통계."""
    title = d.get("source_title") or ""
    body = d.get("text") or ""
    if QUESTION_TITLE.search(title):
        return True, "title_question"
    if QA_BODY.search(body):
        return True, "body_qa_pattern"
    # 짧은 본문 + 질문어 (게시판 단답형 Q&A) — overfit 위험 있으니 conservative
    if len(body) < 600 and QUESTION_TITLE.search(body[:200]):
        return True, "short_body_question"
    return False, ""


SOURCES = [
    # (sprint, day, 파일명)
    ("sprint1", "day2", "chunks.jsonl"),
    ("sprint1", "day2", "attachments.jsonl"),
    ("sprint1", "day4", "chunks.jsonl"),
    ("sprint1", "day4", "attachments.jsonl"),
    ("sprint2", "day2", "chunks.jsonl"),
    ("sprint2", "day3", "chunks.jsonl"),
]


def iter_default_sources():
    for sprint, day, fn in SOURCES:
        path = os.path.join(_ROOT, "data", sprint, day, fn)
        if os.path.exists(path):
            yield path


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--src", action="append", default=[],
                   help="입력 jsonl (반복 가능). 없으면 Sprint 1/2 기본 소스")
    p.add_argument("--out", default="data/sprint2/day3/faq_seeds.jsonl")
    args = p.parse_args()

    sources = args.src or list(iter_default_sources())
    if not sources:
        print("ERR: 입력 소스 없음", file=sys.stderr)
        return 2

    print(f"[faq_seed] 입력 {len(sources)} 파일")

    seeds: list[dict] = []
    reasons: dict[str, int] = {}

    for path in sources:
        n = 0
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                ok, reason = is_faq_candidate(d)
                if not ok:
                    continue
                seeds.append({
                    "source_url": d.get("source_url"),
                    "source_title": d.get("source_title"),
                    "text": (d.get("text") or "")[:1500],
                    "domains": d.get("domains", []),
                    "categories": d.get("categories", []),
                    "seed_reason": reason,
                    "src_path": os.path.relpath(path, _ROOT),
                })
                reasons[reason] = reasons.get(reason, 0) + 1
                n += 1
        print(f"  {path}  -> {n} seed")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for s in seeds:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\nOK: {len(seeds)} seed → {args.out}")
    print("--- reason 분포 ---")
    for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {r:<25} {n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
