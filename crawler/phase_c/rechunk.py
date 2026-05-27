"""02_rechunked: Phase C 2단계 — 거대 청크 분할 + 초소형 청크 병합 + 알리미 학과 병합.

정책 (docs/phase_c_plan.md §3.1):
  - char_count > 2,000 → 분할
      * 학칙 (제○조 패턴 N≥3 이상 등장) → 조문 단위 분할 우선
      * 일반 → 빈 줄(\\n\\n) / numbered list 구분자 우선
      * fallback: 1,500자 sliding window (overlap 200)
  - char_count < 50 → 같은 parent_post_id + 인접 chunk_index 누적 병합
      * T6 dept_info 셀은 별도 처리 (학과 단위 dense 인덱스용 청크 추가 생성)
  - 50 ≤ char_count ≤ 2,000 → 그대로 통과

출력:
  data/phase_c/02_rechunked/{원본 미러}.jsonl
  data/phase_c/02_rechunked/sprint3/dept_info/dept_merged.jsonl  ← 학과 단위 dense용
  data/phase_c/reports/rechunk_report.md
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict

from crawler.phase_c._report import write_rechunk_report

MAX_CHARS = 2000
MIN_CHARS = 50
WINDOW_CHARS = 1500
WINDOW_OVERLAP = 200

# 학칙 조문 패턴: "제1조", "제22조의2" 등
ARTICLE_RE = re.compile(r"(?=\n?\s*제\s*\d+\s*조(?:의\s*\d+)?\s*[\(（])")
# 일반 분할 우선 구분자
PARA_RE = re.compile(r"\n{2,}")
NUMBERED_RE = re.compile(r"(?=\n\s*\d{1,2}[.)]\s)")


def _split_school_rule(text: str) -> list[str]:
    """학칙: 조문 단위로 분할. 각 조각이 MAX_CHARS 초과하면 sliding window로 재분할."""
    parts = ARTICLE_RE.split(text)
    parts = [p.strip() for p in parts if p.strip()]
    # 조문이 충분히 잡혔는지 검사 — 너무 적으면 fallback
    if len(parts) < 3:
        return _split_by_window(text)
    out: list[str] = []
    for p in parts:
        if len(p) <= MAX_CHARS:
            out.append(p)
        else:
            out.extend(_split_by_window(p))
    return out


def _split_general(text: str) -> tuple[list[str], str]:
    """일반 청크: 빈 줄 → numbered → window 순. (조각 리스트, 사용된 전략)."""
    # 1) 빈 줄 분할
    paras = [p.strip() for p in PARA_RE.split(text) if p.strip()]
    if len(paras) >= 2 and all(len(p) <= MAX_CHARS for p in paras):
        return paras, "separator"
    # 빈 줄로 자른 후에도 큰 게 있으면 더 쪼개기
    if len(paras) >= 2:
        out: list[str] = []
        for p in paras:
            if len(p) <= MAX_CHARS:
                out.append(p)
            else:
                # numbered list 시도
                nums = [x.strip() for x in NUMBERED_RE.split(p) if x.strip()]
                if len(nums) >= 2 and all(len(x) <= MAX_CHARS for x in nums):
                    out.extend(nums)
                else:
                    out.extend(_split_by_window(p))
        return out, "separator"
    # 2) numbered
    nums = [x.strip() for x in NUMBERED_RE.split(text) if x.strip()]
    if len(nums) >= 2 and all(len(x) <= MAX_CHARS for x in nums):
        return nums, "separator"
    # 3) window fallback
    return _split_by_window(text), "window"


def _split_by_window(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out: list[str] = []
    start = 0
    step = WINDOW_CHARS - WINDOW_OVERLAP
    while start < len(text):
        end = min(start + WINDOW_CHARS, len(text))
        out.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return out


def _new_chunk_id(orig_id: str, suffix: str) -> str:
    h = hashlib.sha1(f"{orig_id}|{suffix}".encode("utf-8")).hexdigest()[:16]
    return h


def _split_record(r: dict) -> tuple[list[dict], dict]:
    """거대 청크 1개를 N개로 분할. 메타데이터는 상속. (조각 list, 사용 전략 카운터)"""
    text = r.get("text") or ""
    strat: dict[str, int] = {}
    if len(text) <= MAX_CHARS:
        return [r], strat

    # 학칙 판정 — 제○조 패턴이 3개 이상이면 학칙
    article_count = len(ARTICLE_RE.findall("\n" + text))
    if article_count >= 3:
        pieces = _split_school_rule(text)
        strat["article"] = 1
    else:
        pieces, used = _split_general(text)
        if used == "separator":
            strat["separator"] = 1
        else:
            strat["window"] = 1

    out: list[dict] = []
    orig_id = r.get("chunk_id") or ""
    for i, piece in enumerate(pieces):
        new_r = dict(r)
        new_r["text"] = piece
        new_r["char_count"] = len(piece)
        new_r["chunk_id"] = _new_chunk_id(orig_id, f"p{i:02d}")
        # chunk_index 도 새로 부여
        new_r["chunk_index"] = i
        # 부모 추적용
        new_r["parent_post_id"] = r.get("parent_post_id") or orig_id
        new_r["notes"] = _append_note(new_r.get("notes"), f"split_from={orig_id}")
        out.append(new_r)
    return out, strat


def _append_note(existing: str | None, addition: str) -> str:
    if not existing:
        return addition
    return f"{existing} | {addition}"


def _merge_small_chunks(rows: list[dict]) -> tuple[list[dict], int, int, int]:
    """초소형(<50) 청크를 같은 parent_post_id의 인접 chunk_index와 누적 병합.
    반환: (처리 후 rows, 병합 대상 수, 병합 결과 수, 단독 유지된 작은 청크 수)
    """
    # parent_post_id 별로 chunk_index 정렬 후 sliding 병합
    by_parent: dict[str, list[dict]] = defaultdict(list)
    no_parent: list[dict] = []
    for r in rows:
        pp = r.get("parent_post_id")
        if pp:
            by_parent[pp].append(r)
        else:
            no_parent.append(r)

    out: list[dict] = list(no_parent)
    merge_src = 0
    merge_out = 0
    orphans = 0
    for pp, group in by_parent.items():
        group.sort(key=lambda x: (x.get("chunk_index") or 0))
        # 누적 병합: 한 청크의 char_count 가 MIN_CHARS 미달이면 다음(또는 직전) 청크와 합침
        buf: list[dict] = []
        for r in group:
            buf.append(r)
        # 단일 패스: 왼→오 누적
        merged_group: list[dict] = []
        i = 0
        while i < len(buf):
            cur = buf[i]
            cc = cur.get("char_count", 0)
            if cc < MIN_CHARS and len(buf) == 1:
                # 동반자 없음 → 단독 유지 (orphan)
                orphans += 1
                merged_group.append(cur)
                i += 1
                continue
            if cc >= MIN_CHARS:
                merged_group.append(cur)
                i += 1
                continue
            # cc < MIN_CHARS — 다음 청크와 병합 (있으면)
            merge_src += 1
            if i + 1 < len(buf):
                nxt = buf[i + 1]
                merged = _merge_two(cur, nxt)
                buf[i + 1] = merged
                i += 1
            else:
                # 마지막인데 작음 → 직전과 병합
                if merged_group:
                    prev = merged_group.pop()
                    merged = _merge_two(prev, cur)
                    merged_group.append(merged)
                    i += 1
                else:
                    orphans += 1
                    merged_group.append(cur)
                    i += 1
        # 병합 결과 카운트
        # (단순화: input N개, output M개, 차이 = N - M = 병합 진행 횟수, merge_src 와 일치)
        merge_out += len(merged_group)
        out.extend(merged_group)
    return out, merge_src, merge_out, orphans


def _merge_two(a: dict, b: dict) -> dict:
    new_r = dict(a)
    glue = "\n\n" if not a["text"].endswith("\n") else ""
    new_r["text"] = a["text"] + glue + b["text"]
    new_r["char_count"] = len(new_r["text"])
    new_r["chunk_id"] = _new_chunk_id(a.get("chunk_id") or "", f"m+{b.get('chunk_id') or ''}")
    # domains/categories union
    new_r["domains"] = sorted(set((a.get("domains") or []) + (b.get("domains") or [])))
    new_r["categories"] = sorted(set((a.get("categories") or []) + (b.get("categories") or [])))
    new_r["notes"] = _append_note(a.get("notes"), f"merged_with={b.get('chunk_id')}")
    return new_r


def _build_dept_merged(cells: list[dict]) -> list[dict]:
    """알리미 dept_info 셀들을 단과대학>학과 단위로 묶어 dense용 청크 생성."""
    by_dept: dict[str, list[dict]] = defaultdict(list)
    for r in cells:
        sp = r.get("section_path") or ""
        parts = [p.strip() for p in sp.split(">")]
        dept_key = " > ".join(parts[:2]) if len(parts) >= 2 else sp
        by_dept[dept_key].append(r)

    out: list[dict] = []
    for dept_key, group in sorted(by_dept.items()):
        # 같은 학과 내 셀 정렬 (section_path 알파벳 순으로 안정)
        group.sort(key=lambda x: (x.get("section_path") or "", x.get("chunk_id") or ""))
        combined_text = f"[{dept_key}]\n" + "\n".join(r["text"] for r in group)
        if len(combined_text) > MAX_CHARS:
            combined_text = combined_text[:MAX_CHARS]
        cid = _new_chunk_id(dept_key, "dept_merged")
        first = group[0]
        out.append({
            "chunk_id": cid,
            "chunk_index": 0,
            "parent_post_id": f"dept_merged_{cid}",
            "source_url": first.get("source_url"),
            "source_title": f"대학알리미 학과정보 - {dept_key}",
            "source_type": "T6",
            "section_path": dept_key,
            "text": combined_text,
            "char_count": len(combined_text),
            "lang": "ko",
            "posted_at": first.get("posted_at"),
            "crawled_at": first.get("crawled_at"),
            "freshness": first.get("freshness"),
            "domains": sorted({d for r in group for d in (r.get("domains") or [])}),
            "categories": sorted({c for r in group for c in (r.get("categories") or [])}),
            "notes": f"dept_merged from {len(group)} cells",
        })
    return out


def _read_jsonl(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _write_jsonl(path: str, rows: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fp:
        for r in rows:
            fp.write(json.dumps(r, ensure_ascii=False) + "\n")


def run(
    in_root: str = "data/phase_c/01_clean",
    out_root: str = "data/phase_c/02_rechunked",
    report_path: str = "data/phase_c/reports/rechunk_report.md",
) -> dict:
    # 입력 파일 수집
    in_files: list[str] = []
    for cur, _d, files in os.walk(in_root):
        for f in sorted(files):
            if f.endswith(".jsonl"):
                in_files.append(os.path.join(cur, f))

    total_in = 0
    avg_in_sum = 0
    max_in = 0
    split_src = 0
    split_result = 0
    strat_counts: Counter = Counter()
    merge_src_total = merge_out_total = orphans_total = 0
    output_chunks = 0
    avg_out_sum = 0
    max_out = 0
    under_50_after = over_2000_after = 0

    domain_in: Counter = Counter()
    domain_out: Counter = Counter()
    per_file: dict[str, tuple[int, int]] = {}
    almi_cells_kept = 0
    almi_dept_chunks = 0

    for in_path in in_files:
        rel = os.path.relpath(in_path, in_root)
        out_path = os.path.join(out_root, rel)
        rows = _read_jsonl(in_path)
        n_in = len(rows)
        total_in += n_in
        for r in rows:
            cc = r.get("char_count", 0)
            avg_in_sum += cc
            max_in = max(max_in, cc)
            for d in (r.get("domains") or []):
                domain_in[d] += 1

        # 1) 분할 (모든 청크에 대해)
        after_split: list[dict] = []
        for r in rows:
            pieces, strat = _split_record(r)
            if len(pieces) > 1:
                split_src += 1
                split_result += len(pieces)
                for k, v in strat.items():
                    strat_counts[k] += v
            after_split.extend(pieces)

        # 2) 병합 — 단, T6 dept_info 는 셀 단위 보존이 정책
        is_dept_info = "dept_info" in in_path
        if is_dept_info:
            after_merge = after_split  # 셀 단위 그대로
            almi_cells_kept = len(after_merge)
        else:
            after_merge, ms, mo, mp = _merge_small_chunks(after_split)
            merge_src_total += ms
            merge_out_total += mo
            orphans_total += mp

        # 3) 출력
        _write_jsonl(out_path, after_merge)
        output_chunks += len(after_merge)
        for r in after_merge:
            cc = r.get("char_count", 0)
            avg_out_sum += cc
            max_out = max(max_out, cc)
            if cc < MIN_CHARS:
                under_50_after += 1
            if cc > MAX_CHARS:
                over_2000_after += 1
            for d in (r.get("domains") or []):
                domain_out[d] += 1
        per_file[rel] = (n_in, len(after_merge))

        # 4) 알리미 dept_info → 학과 단위 dense 청크 추가 파일 생성
        if is_dept_info:
            merged_dept = _build_dept_merged(after_merge)
            merged_path = os.path.join(os.path.dirname(out_path), "dept_merged.jsonl")
            _write_jsonl(merged_path, merged_dept)
            almi_dept_chunks = len(merged_dept)
            output_chunks += len(merged_dept)
            for r in merged_dept:
                cc = r.get("char_count", 0)
                avg_out_sum += cc
                max_out = max(max_out, cc)
                for d in (r.get("domains") or []):
                    domain_out[d] += 1
            per_file[os.path.relpath(merged_path, out_root)] = (0, len(merged_dept))

    summary = {
        "input_chunks": total_in,
        "avg_in": avg_in_sum / max(1, total_in),
        "max_in": max_in,
        "split_source_chunks": split_src,
        "split_by_article": strat_counts.get("article", 0),
        "split_by_separator": strat_counts.get("separator", 0),
        "split_by_window": strat_counts.get("window", 0),
        "split_result_chunks": split_result,
        "merge_source_chunks": merge_src_total,
        "merge_result_chunks": merge_out_total,
        "merge_orphans": orphans_total,
        "almi_cells_kept": almi_cells_kept,
        "almi_dept_chunks": almi_dept_chunks,
        "output_chunks": output_chunks,
        "avg_out": avg_out_sum / max(1, output_chunks),
        "max_out": max_out,
        "under_50_after": under_50_after,
        "over_2000_after": over_2000_after,
        "domain_in_out": {d: (domain_in.get(d, 0), domain_out.get(d, 0)) for d in sorted(set(list(domain_in.keys()) + list(domain_out.keys())))},
        "per_file": per_file,
    }
    write_rechunk_report(report_path, summary)
    return summary


if __name__ == "__main__":
    s = run()
    safe = {k: v for k, v in s.items() if k not in ("per_file", "domain_in_out")}
    safe["domain_summary"] = {d: list(io) for d, io in (s.get("domain_in_out") or {}).items()}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
