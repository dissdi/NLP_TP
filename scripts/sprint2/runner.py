"""Sprint 2 Day별 통합 러너 (sprint1_runner.py 패턴 그대로).

Day 1: 학칙 HWP + D-통계 + 학과 졸업요건 (이월 + P1)
Day 2: 학생활동·진로·도서관·캠퍼스 보강 (P1 11개)
Day 3: 행정·식당·장학 cross + dorm JS + FAQ 시드 (P1 8개 + 이월 1)
Day 4: Exit (코드 없음, sprint2_verify.py 호출)

실행:
  python -m scripts.sprint2_runner day1
  python -m scripts.sprint2_runner day1 --only 1.3_rule_list
  python -m scripts.sprint2_runner day2 --dry-run
  python -m scripts.sprint2_runner all

신규/특수 어댑터 모드:
  RULE_HWP   → DayRunner.run_rule_hwp (어댑터 E)
  DEPT_GRAD  → 별도 스크립트 sprint2_dept_grad.py 안내 (skip + 메시지)
  ALIMI_PDF  → 별도 스크립트 sprint2_dstat.py 안내 (skip + 메시지)
  CROSS_TAG  → 별도 스크립트 sprint2_cross_tag.py 안내
  FAQ_SEED   → 별도 스크립트 sprint2_faq_seed.py 안내
  JS_FALLBACK → 별도 스크립트 sprint2_dorm_js.py 안내
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


TARGETS_PATH = os.path.join(_HERE, "sprint2_targets.json")

DAY_KEYS = {
    "day1": "_day1_carryover_and_dstat",
    "day2": "_day2_activity_career_lib_campus",
    "day3": "_day3_admin_food_scholar_cross",
    "day4": "_day4_exit_verify",
}

# adapter id → DayRunner 메서드명 매핑 (기본 어댑터)
ADAPTER_MAP = {
    "A": "run_a_static",
    "B": "run_b_paginate",
    "C": "run_a_static",   # Spring .do도 어댑터 A wrapper
    "D": "run_a_static",   # 도서관 webcontent도 어댑터 A wrapper
    "PDF": "run_pdf",
    "HWP": "run_hwp",
    "RULE_HWP": "run_rule_hwp",
}

# 별도 스크립트로 처리하는 모드 → runner 는 안내 메시지만
DEFERRED_MODES = {
    "DEPT_GRAD":   "python -m scripts.sprint2_dept_grad discover --dept-list scripts/sprint2_dept_list.json && python -m scripts.sprint2_dept_grad crawl --candidates data/sprint2/day1/dept_grad_candidates.jsonl",
    "ALIMI_PDF":   "python -m scripts.sprint2_dstat spike-alimi   (그 다음 fetch-pdf URL 직접)",
    "CROSS_TAG":   "python -m scripts.sprint2_cross_tag",
    "FAQ_SEED":    "python -m scripts.sprint2_faq_seed",
    "JS_FALLBACK": "python -m scripts.sprint2_dorm_js",
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

    if not tasks:
        print(f"  (no task — '{day}' 는 별도 스크립트로 처리)")
        return 0

    with DayRunner(day, sprint="sprint2") as r:
        for t in tasks:
            adapter = t["adapter"]
            url = t["url"]
            domains = t["domains"]
            categories = t.get("categories")
            title = t.get("title")
            posted_at = t.get("posted_at")
            tid = t["id"]

            # 별도 스크립트로 처리하는 모드는 안내만
            if adapter in DEFERRED_MODES:
                cmd = DEFERRED_MODES[adapter]
                r._log(f"\n[deferred] {tid} ({adapter}) — 별도 실행 필요:")
                r._log(f"  $ {cmd}")
                continue

            method_name = ADAPTER_MAP.get(adapter)
            if method_name is None:
                r._log(f"  [skip] unknown adapter {adapter} for {tid}")
                continue

            try:
                if adapter in ("A", "C", "D"):
                    r.run_a_static(url, domains=domains, categories=categories, title=title)
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
                    r.run_hwp(url, domains=domains, categories=categories, title=title)
                elif adapter == "RULE_HWP":
                    max_items = t.get("max_items", 30)
                    r.run_rule_hwp(
                        url, domains=domains, categories=categories,
                        max_items=max_items,
                    )
            except Exception as e:
                r._log(f"  [task {tid}] err={type(e).__name__}: {e}")
        r.dump()
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Sprint 2 Day runner")
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
