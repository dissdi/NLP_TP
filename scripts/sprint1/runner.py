"""Sprint 1 Day별 통합 러너.

Day 1~5의 모든 작업을 sprint1_targets.json 에 정의해놓고, 이 스크립트는
day key를 받아 해당 day의 tasks를 순서대로 실행한다.

실행:
  python -m scripts.sprint1_runner day1
  python -m scripts.sprint1_runner day1 --only 1.1   # 특정 task만
  python -m scripts.sprint1_runner day2 --dry-run    # URL 목록만 확인
  python -m scripts.sprint1_runner all               # day1~day5 순차

출력:
  data/sprint1/<day>/chunks.jsonl  (Chunk JSON Lines)
  data/sprint1/<day>/tables/       (PDF에서 추출한 표 CSV)
  data/sprint1/<day>/hwp/          (HWP 다운로드본)
  data/sprint1/<day>/errors.json   (실패 step 모음)
  logs/sprint1/<day>.log
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts._common import DayRunner  # noqa: E402


TARGETS_PATH = os.path.join(_HERE, "sprint1_targets.json")

DAY_KEYS = {
    "day1": "_day1_domain1_2_4",
    "day2": "_day2_domain5_6_8",
    "day3": "_day3_domain3_7_9",
    "day4": "_day4_shuttle_faq_hwp",
    "day5": "_day5_graduation",
}


def load_targets() -> dict:
    with open(TARGETS_PATH, encoding="utf-8") as f:
        return json.load(f)


def run_day(day: str, *, only: Optional[str] = None, dry_run: bool = False) -> int:
    targets = load_targets()
    key = DAY_KEYS.get(day)
    if key is None:
        print(f"ERR: unknown day '{day}'. choose from {list(DAY_KEYS)}", file=sys.stderr)
        return 2
    block = targets[key]
    tasks = block["tasks"]
    if only:
        tasks = [t for t in tasks if t["id"] == only]
        if not tasks:
            print(f"ERR: no task with id={only} in {day}", file=sys.stderr)
            return 2

    print(f"\n### {day}: {block['label']}  ({len(tasks)} task)")

    if dry_run:
        for t in tasks:
            print(f"  [{t['adapter']}] {t['id']}  domains={t['domains']}  {t['url']}")
        return 0

    with DayRunner(day) as r:
        for t in tasks:
            adapter = t["adapter"]
            url = t["url"]
            domains = t["domains"]
            categories = t.get("categories")
            title = t.get("title")
            posted_at = t.get("posted_at")
            try:
                if adapter == "A" or adapter == "C" or adapter == "D":
                    # A/C/D 모두 어댑터 A 기반 (C·D는 wrapper)
                    r.run_a_static(
                        url, domains=domains,
                        categories=categories, title=title,
                    )
                elif adapter == "B":
                    pages = t.get("pages", 5)
                    max_total = t.get("max_total")
                    r.run_b_paginate(
                        url, domains=domains, categories=categories,
                        pages=pages, max_total=max_total,
                    )
                elif adapter == "PDF":
                    r.run_pdf(
                        url, domains=domains, categories=categories,
                        title=title, posted_at=posted_at,
                    )
                elif adapter == "HWP":
                    r.run_hwp(
                        url, domains=domains, categories=categories,
                        title=title,
                    )
                else:
                    print(f"  [skip] unknown adapter {adapter} for {t['id']}")
            except Exception as e:
                print(f"  [task {t['id']}] err={type(e).__name__}: {e}")
        r.dump()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Sprint 1 Day runner")
    p.add_argument("day", choices=list(DAY_KEYS) + ["all"])
    p.add_argument("--only", default=None, help="특정 task id만 실행")
    p.add_argument("--dry-run", action="store_true", help="URL 목록만 출력")
    args = p.parse_args()

    if args.day == "all":
        rc = 0
        for d in DAY_KEYS:
            r = run_day(d, dry_run=args.dry_run)
            if r != 0:
                rc = r
        return rc
    return run_day(args.day, only=args.only, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
