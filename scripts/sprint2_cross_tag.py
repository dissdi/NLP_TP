"""Sprint 1 청크에 cross-domain 태그 추가 (신규 크롤 없음).

§11 "한 번 크롤링, 다중 태그" 원칙. Sprint 2 Day 3에서 처리:

  8.3 학적변동       ← Sprint 1 day1 1.5 청크에 domains+={8}, categories+={"8.3"}
  2.4 식당 비교       ← Sprint 1 day1 2.1·2.2 청크에 categories+={"2.4"}
  6.6 장학금 간 비교   ← Sprint 1 day2 6.1~6.4 청크에 categories+={"6.6"}

입력:  data/sprint1/<day>/chunks.jsonl, data/sprint1/<day>/attachments.jsonl
출력:  data/sprint2/day3/cross_tag.jsonl  (cross-tag된 청크의 *copy*)
       (Sprint 1 원본은 건드리지 않음. RAG 적재 단계에서 union하면 됨.)

실행:
  python -m scripts.sprint2_cross_tag
"""

from __future__ import annotations

import json
import os
import sys
from typing import Iterable

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


# 규칙: (입력 day, 매칭 카테고리 prefix, 추가 도메인, 추가 카테고리, label)
RULES = [
    # 8.3: 1.5 청크 → +domain 8 +category 8.3
    ("day1", "1.5", [8], ["8.3"], "8.3 학적변동 (1.5 cross)"),
    # 2.4: 2.1·2.2 청크 → +category 2.4
    ("day1", "2.1", [], ["2.4"], "2.4 식당 비교 (2.1 cross)"),
    ("day1", "2.2", [], ["2.4"], "2.4 식당 비교 (2.2 cross)"),
    # 6.6: 6.1~6.4 청크 → +category 6.6
    ("day2", "6.1", [], ["6.6"], "6.6 장학금 비교 (6.1 cross)"),
    ("day2", "6.2", [], ["6.6"], "6.6 장학금 비교 (6.2 cross)"),
    ("day2", "6.3", [], ["6.6"], "6.6 장학금 비교 (6.3 cross)"),
    ("day2", "6.4", [], ["6.6"], "6.6 장학금 비교 (6.4 cross)"),
]


def iter_chunks(day: str) -> Iterable[dict]:
    """sprint1 의 chunks.jsonl + attachments.jsonl 통합 iter."""
    for fname in ("chunks.jsonl", "attachments.jsonl"):
        path = os.path.join(_ROOT, "data", "sprint1", day, fname)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def main() -> int:
    out_records: list[dict] = []
    summary: list[str] = []

    for day, cat_prefix, add_domains, add_cats, label in RULES:
        n = 0
        chars = 0
        for d in iter_chunks(day):
            cats = d.get("categories", []) or []
            if not any(c == cat_prefix or c.startswith(cat_prefix + ".") for c in cats):
                continue
            # 청크의 도메인·카테고리 확장 (set union)
            new_doms = sorted(set(d.get("domains", []) or []) | set(add_domains))
            new_cats = sorted(set(cats) | set(add_cats))
            new_d = dict(d)
            new_d["domains"] = new_doms
            new_d["categories"] = new_cats
            new_d["section_path"] = "cross_tag/" + (d.get("section_path") or "")
            existing_notes = d.get("notes") or ""
            cross_note = f"cross_tag: +domain={add_domains} +cat={add_cats}"
            new_d["notes"] = cross_note if not existing_notes else f"{existing_notes} | {cross_note}"
            out_records.append(new_d)
            n += 1
            chars += int(d.get("char_count") or 0)
        summary.append(f"  {label:<40} -> {n:>4} 청크 / {chars:>7,}자")

    out = os.path.join(_ROOT, "data", "sprint2", "day3", "cross_tag.jsonl")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print("=== cross-tag 결과 ===")
    for line in summary:
        print(line)
    print(f"\nOK: 총 {len(out_records)} 청크 → {out}")
    print("  (Sprint 1 원본은 변경 없음. RAG 적재 시 union 가능.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
