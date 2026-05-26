"""Sprint 2 Exit 검증 — Sprint 2 신규 corpus + Sprint 1 합산 통계.

실행:
  python -m scripts.sprint2_verify

산출물:
  logs/sprint2/report.md       Sprint 2 결과 + Sprint 1 합산
  logs/sprint2/coverage.json   카테고리·도메인 분포 (Phase C 핸드오프)
  logs/sprint2/coverage_vs_eval.md  평가셋 168문제 매핑 점검표
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


# Sprint 2 가 산출하는 모든 jsonl
SPRINT2_FILES = [
    # day1
    ("day1", "chunks.jsonl"),
    ("day1", "attachments.jsonl"),
    ("day1", "rule_chunks.jsonl"),
    ("day1", "dept_grad_chunks.jsonl"),
    ("day1", "dstat", "dstat_chunks.jsonl"),
    # day2
    ("day2", "chunks.jsonl"),
    ("day2", "attachments.jsonl"),
    # day3
    ("day3", "chunks.jsonl"),
    ("day3", "attachments.jsonl"),
    ("day3", "cross_tag.jsonl"),
    ("day3", "faq_seeds.jsonl"),
    ("day3", "dorm_js.jsonl"),
]

# Sprint 1 산출
SPRINT1_DAYS = ["day1", "day2", "day3", "day4", "day5"]


def load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def load_sprint2() -> tuple[list[dict], dict[str, list[dict]]]:
    """전체 + day별 (faq_seeds 등 메타는 별도 키)."""
    all_chunks: list[dict] = []
    per_file: dict[str, list[dict]] = {}
    for parts in SPRINT2_FILES:
        rel = os.path.join(*parts)
        full = os.path.join(_ROOT, "data", "sprint2", rel)
        recs = load_jsonl(full)
        per_file[rel] = recs
        # faq_seeds 는 RAG corpus 가 아니라 D-1 입력이므로 합계에 포함 안 함
        if parts[-1] == "faq_seeds.jsonl":
            continue
        all_chunks.extend(recs)
    return all_chunks, per_file


def load_sprint1() -> tuple[list[dict], dict[str, list[dict]]]:
    all_chunks: list[dict] = []
    per_day: dict[str, list[dict]] = {}
    for d in SPRINT1_DAYS:
        recs: list[dict] = []
        for fn in ("chunks.jsonl", "attachments.jsonl"):
            recs.extend(load_jsonl(os.path.join(_ROOT, "data", "sprint1", d, fn)))
        per_day[d] = recs
        all_chunks.extend(recs)
    return all_chunks, per_day


def summarize(chunks: list[dict]) -> dict:
    total = sum(c.get("char_count", 0) for c in chunks)
    n = len(chunks)
    dom_chars: dict[int, int] = defaultdict(int)
    dom_count: Counter = Counter()
    for c in chunks:
        for d in c.get("domains", []):
            dom_chars[d] += c.get("char_count", 0)
            dom_count[d] += 1
    cat_chars: dict[str, int] = defaultdict(int)
    for c in chunks:
        for cat in c.get("categories", []):
            cat_chars[cat] += c.get("char_count", 0)
    type_count = Counter(c.get("source_type") for c in chunks)
    return {
        "n": n,
        "chars": total,
        "dom_count": dict(dom_count),
        "dom_chars": dict(dom_chars),
        "cat_chars": dict(cat_chars),
        "source_type": dict(type_count),
    }


# 평가셋 매트릭스 (project-nlp-tp-coverage 메모리)
EVAL_MATRIX = [
    # (도메인번호, 도메인명, A, B, C, D)
    (1, "학사",           10, 10, 5, 5),
    (2, "식생활",         10, 3,  3, 0),
    (3, "도서관",         10, 5,  3, 0),
    (4, "기숙사",         10, 5,  3, 3),
    (5, "학생활동·공지", 10, 3,  0, 0),
    (6, "장학금·등록금", 10, 5,  5, 0),
    (7, "진로·취업",     10, 3,  0, 5),
    (8, "행정·증명서",   10, 10, 0, 0),
    (9, "캠퍼스·시설",   10, 5,  0, 0),
]


def coverage_vs_eval(combined: dict) -> str:
    """corpus 가 평가셋 168문제 도메인을 얼마나 받쳐주는지 점검표."""
    lines = ["# Sprint 1+2 corpus 평가셋 매핑 점검표\n"]
    lines.append("| 도메인 | 명 | 평가합 | 청크수 | 글자수 | 비고 |")
    lines.append("|---|---|---|---|---|---|")
    for dom, name, a, b, c, d in EVAL_MATRIX:
        eval_n = a + b + c + d
        ck = combined["dom_count"].get(dom, 0)
        ch = combined["dom_chars"].get(dom, 0)
        flag = ""
        if ch < 2000:
            flag = "⚠ sparse"
        elif ch < 10000:
            flag = "·"
        else:
            flag = "✓"
        lines.append(f"| {dom} | {name} | {eval_n} | {ck} | {ch:,} | {flag} |")
    return "\n".join(lines) + "\n"


def main() -> int:
    s1_all, s1_per_day = load_sprint1()
    s2_all, s2_per_file = load_sprint2()
    combined = s1_all + s2_all

    s1 = summarize(s1_all)
    s2 = summarize(s2_all)
    co = summarize(combined)

    rep = []
    rep.append("# Sprint 2 Exit 리포트\n")
    rep.append(f"- Sprint 1 청크: **{s1['n']:,}** / {s1['chars']:,}자")
    rep.append(f"- Sprint 2 청크: **{s2['n']:,}** / {s2['chars']:,}자")
    rep.append(f"- **합산: {co['n']:,}** / **{co['chars']:,}**자\n")

    # Sprint 2 source file별
    rep.append("## Sprint 2 source 파일별 산출")
    for rel, recs in s2_per_file.items():
        tch = sum(r.get("char_count", 0) for r in recs)
        marker = " (시드, corpus 미포함)" if rel.endswith("faq_seeds.jsonl") else ""
        rep.append(f"- `data/sprint2/{rel}`: {len(recs)} 청크 / {tch:,}자{marker}")
    rep.append("")

    rep.append("## 합산 도메인별 분포")
    rep.append("| 도메인 | 청크수 | 글자수 |")
    rep.append("|---|---|---|")
    for d in sorted(co["dom_chars"].keys()):
        rep.append(f"| {d} | {co['dom_count'][d]} | {co['dom_chars'][d]:,} |")
    rep.append("")

    rep.append("## 합산 source_type")
    for t, ct in sorted(co["source_type"].items(), key=lambda kv: -kv[1]):
        rep.append(f"- {t}: {ct}건")
    rep.append("")

    rep.append("## 합산 카테고리 상위 20")
    rep.append("| 카테고리 | 글자수 |")
    rep.append("|---|---|")
    for cat, ch in sorted(co["cat_chars"].items(), key=lambda kv: -kv[1])[:20]:
        rep.append(f"| {cat} | {ch:,} |")
    rep.append("")

    # 평가셋 매핑
    rep.append("## 평가셋 도메인 커버 (Sprint 1+2)")
    rep.append(coverage_vs_eval(co))

    # Exit 판정
    s2_chars_only = s2["chars"]
    rep.append("## Exit 판정")
    if s2_chars_only >= 100_000:
        rep.append(f"- ✓ Sprint 2 신규 corpus {s2_chars_only:,}자 (≥100k 목표 달성) — Phase C 진입 OK")
    else:
        rep.append(f"- ⚠ Sprint 2 신규 corpus {s2_chars_only:,}자 (100k 미달)")
        rep.append("  점검: 학칙 RULE_HWP 동작·학과 졸업요건 candidates·D-통계 PDF URL")

    sparse_doms = [d for d, ch in co["dom_chars"].items() if ch < 2000]
    if sparse_doms:
        rep.append(f"- ⚠ sparse 도메인 {sparse_doms} — fallback 응답 정책 점검 필요")
    rep.append("")
    rep.append("## Phase C 핸드오프")
    rep.append("- 입력: `data/sprint{1,2}/<day>/{chunks,attachments,rule_chunks,dept_grad_chunks,cross_tag,dorm_js}.jsonl`")
    rep.append("- D-1 시드: `data/sprint2/day3/faq_seeds.jsonl`")
    rep.append("- 청크 분할 정책 결정 권장 (T3 페이지=청크 매핑이 너무 큼 — Sprint 1 메모 참조)")

    rep_text = "\n".join(rep) + "\n"
    out_md = os.path.join(_ROOT, "logs", "sprint2", "report.md")
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", encoding="utf-8") as f:
        f.write(rep_text)

    coverage = {
        "sprint1": s1, "sprint2": s2, "combined": co,
        "per_file_sprint2": {k: {"n": len(v), "chars": sum(r.get("char_count", 0) for r in v)}
                              for k, v in s2_per_file.items()},
    }
    out_json = os.path.join(_ROOT, "logs", "sprint2", "coverage.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(coverage, f, ensure_ascii=False, indent=2)

    eval_md = os.path.join(_ROOT, "logs", "sprint2", "coverage_vs_eval.md")
    with open(eval_md, "w", encoding="utf-8") as f:
        f.write(coverage_vs_eval(co))

    print(rep_text)
    print(f"리포트:   {out_md}")
    print(f"커버리지: {out_json}")
    print(f"평가매핑: {eval_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
