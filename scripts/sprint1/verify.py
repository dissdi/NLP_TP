"""Sprint 1 Exit 검증 — corpus 양 측정 + §10-2 보정 + 리포트.

실행:
  python -m scripts.sprint1_verify

산출물:
  logs/sprint1/report.md      Sprint 1 결과 요약 (사용자에게 전달)
  logs/sprint1/coverage.json  카테고리별 청크·글자 수 (다음 단계로 핸드오프)

크롤링 후 무조건 1회 실행.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def load_chunks(day: str) -> list[dict]:
    paths = [
        os.path.join(_ROOT, "data", "sprint1", day, "chunks.jsonl"),
        os.path.join(_ROOT, "data", "sprint1", day, "attachments.jsonl"),
    ]
    out: list[dict] = []
    for p in paths:
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def main() -> int:
    days = ["day1", "day2", "day3", "day4", "day5"]
    all_chunks: list[dict] = []
    per_day: dict[str, list[dict]] = {}
    for d in days:
        cs = load_chunks(d)
        per_day[d] = cs
        all_chunks.extend(cs)

    total = sum(c.get("char_count", 0) for c in all_chunks)
    n = len(all_chunks)

    # 도메인 분포
    dom_chars: dict[int, int] = defaultdict(int)
    dom_count: Counter = Counter()
    for c in all_chunks:
        for d in c.get("domains", []):
            dom_chars[d] += c.get("char_count", 0)
            dom_count[d] += 1

    # 카테고리 분포
    cat_chars: dict[str, int] = defaultdict(int)
    for c in all_chunks:
        for cat in c.get("categories", []):
            cat_chars[cat] += c.get("char_count", 0)

    # source_type 분포
    type_count = Counter(c.get("source_type") for c in all_chunks)

    # 게시물 본문 분포 (T2)
    t2_lens = [c.get("char_count", 0) for c in all_chunks if c.get("source_type") == "T2"]
    t2_lens.sort()

    # 첨부 통계
    n_atch_posts = sum(
        1 for c in all_chunks
        if c.get("notes") and isinstance(c.get("notes"), str)
        and "attachments" in c.get("notes", "")
    )

    # § 10-2 보정 비교 (P0 추정 ~490k)
    estimated_p0 = 490000
    fill_pct = total / estimated_p0 * 100 if estimated_p0 else 0

    # ----- 리포트 markdown 작성 -----
    rep = []
    rep.append("# Sprint 1 Exit 리포트\n")
    rep.append(f"- 청크 총수: **{n:,}**개")
    rep.append(f"- 총 글자수: **{total:,}**자")
    rep.append(f"- §10-2 P0 추정 (490k) 대비: **{fill_pct:.0f}%**")
    rep.append(f"- 첨부 보유 게시물: {n_atch_posts}건\n")

    rep.append("## Day별 산출")
    for d in days:
        cs = per_day[d]
        tch = sum(c.get("char_count", 0) for c in cs)
        rep.append(f"- {d}: {len(cs):>4} 청크 / {tch:>8,}자")
    rep.append("")

    rep.append("## 도메인별 분포")
    rep.append("| 도메인 | 청크수 | 글자수 |")
    rep.append("|---|---|---|")
    for d in sorted(dom_chars.keys()):
        rep.append(f"| {d} | {dom_count[d]} | {dom_chars[d]:,} |")
    rep.append("")

    rep.append("## source_type 분포")
    for t, ct in type_count.most_common():
        rep.append(f"- {t}: {ct}건")
    rep.append("")

    if t2_lens:
        med = t2_lens[len(t2_lens) // 2]
        avg = sum(t2_lens) // len(t2_lens)
        short = sum(1 for x in t2_lens if x < 300)
        rep.append("## 게시물 본문 길이 (T2)")
        rep.append(f"- count: {len(t2_lens)}")
        rep.append(f"- avg: {avg}자  median: {med}자  min: {t2_lens[0]} max: {t2_lens[-1]}")
        rep.append(f"- 300자 미만 (첨부의존형 의심): {short}건 / {short*100//len(t2_lens)}%")
        rep.append("")

    rep.append("## 카테고리별 상위 12")
    top_cats = sorted(cat_chars.items(), key=lambda kv: -kv[1])[:12]
    rep.append("| 카테고리 | 글자수 |")
    rep.append("|---|---|")
    for cat, ch in top_cats:
        rep.append(f"| {cat} | {ch:,} |")
    rep.append("")

    rep.append("## Exit 판단")
    if fill_pct >= 70:
        rep.append("- ✓ §10-2 P0 추정의 70% 이상 확보 — Phase C(정제·청킹) 진입 OK")
    else:
        rep.append(f"- ⚠ {fill_pct:.0f}%만 확보 — 다음 중 점검:")
        rep.append("  - 백마광장 백본(5.4) 페이지 깊이가 충분한지 (pages 인자)")
        rep.append("  - 첨부 후처리 (sprint1_process_attachments) 실행했는지")
        rep.append("  - errors.json에 누락된 task 있는지")

    rep_text = "\n".join(rep) + "\n"
    out_md = os.path.join(_ROOT, "logs", "sprint1", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(rep_text)

    # JSON 핸드오프
    coverage = {
        "n_chunks": n,
        "total_chars": total,
        "fill_pct_vs_490k": fill_pct,
        "per_day": {
            d: {
                "n": len(per_day[d]),
                "chars": sum(c.get("char_count", 0) for c in per_day[d]),
            }
            for d in days
        },
        "per_domain": {str(k): {"n": dom_count[k], "chars": dom_chars[k]}
                       for k in sorted(dom_chars.keys())},
        "per_category": dict(sorted(cat_chars.items(), key=lambda kv: -kv[1])),
        "source_type": dict(type_count),
        "n_attachment_posts": n_atch_posts,
    }
    out_json = os.path.join(_ROOT, "logs", "sprint1", "coverage.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    print(rep_text)
    print(f"리포트: {out_md}")
    print(f"커버리지: {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
