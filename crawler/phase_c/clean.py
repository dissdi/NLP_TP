"""01_clean: Phase C 1단계 — 정제·URL 정규화·중복 제거.

정책: docs/phase_c_plan.md §3.2, §3.3.
출력: data/phase_c/01_clean/{원본 미러}.jsonl + reports/duplicate_report.md + reports/dedup_aliases.jsonl
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from typing import Iterable
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from crawler.phase_c._report import write_clean_report

# ─── 정규화 패턴 ────────────────────────────────────────────────────────────
HWP_PLACEHOLDER_RE = re.compile(r"<(?:표|그림|도형|수식)>")
PAGE_NUMBER_RE = re.compile(r"\n\s*-\s*\d+\s*-\s*\n")
MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")
INTRA_SPACE_RE = re.compile(r"[ \t]+")
CTRL_RE = re.compile("[\x00\u200B\u200D\uFEFF]")  # NULL, ZWSP, ZWJ, BOM
NBSP_RE = re.compile(r"\xa0")

URL_DROP_QUERY_KEYS = {"GotoPage", "skey", "sval", "site_dvs"}
SOURCE_TYPE_PRIORITY = {"T1": 0, "T2": 1, "T3": 2, "T6": 3}
EXCLUDE_FILES = {"faq_seeds.jsonl", "dept_grad_candidates.jsonl"}
CROSS_TAG_FILENAME = "cross_tag.jsonl"


def clean_text(text: str) -> tuple[str, dict]:
    stats: dict[str, int] = {}
    if not text:
        return "", stats
    n = len(CTRL_RE.findall(text))
    if n: stats["ctrl"] = n; text = CTRL_RE.sub("", text)
    n = len(NBSP_RE.findall(text))
    if n: stats["nbsp"] = n; text = NBSP_RE.sub(" ", text)
    n = len(HWP_PLACEHOLDER_RE.findall(text))
    if n: stats["hwp_placeholder"] = n; text = HWP_PLACEHOLDER_RE.sub("", text)
    n = len(PAGE_NUMBER_RE.findall(text))
    if n: stats["page_number"] = n; text = PAGE_NUMBER_RE.sub("\n", text)
    text = MULTI_BLANK_LINE_RE.sub("\n\n", text)
    text = INTRA_SPACE_RE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n")).strip()
    return text, stats


def normalize_url(url: str) -> str:
    if not url:
        return url
    try:
        u = urlparse(url)
        pairs = parse_qsl(u.query, keep_blank_values=True)
        kept = [(k, v) for k, v in pairs if k not in URL_DROP_QUERY_KEYS and v != ""]
        return urlunparse((u.scheme, u.netloc, u.path, u.params, urlencode(kept), ""))
    except Exception:
        return url


def _priority_key(record: dict) -> tuple:
    st_rank = SOURCE_TYPE_PRIORITY.get(record.get("source_type", ""), 99)
    freshness_missing = 0 if record.get("freshness") else 1
    cc = -int(record.get("char_count") or len(record.get("text") or ""))
    return (st_rank, freshness_missing, cc)


def _better(new_r: dict, existing_r: dict) -> bool:
    return _priority_key(new_r) < _priority_key(existing_r)


def _iter_input_files(root: str) -> Iterable[str]:
    for sp in ("sprint1", "sprint2", "sprint3"):
        sp_dir = os.path.join(root, sp)
        if not os.path.isdir(sp_dir):
            continue
        for cur, _d, files in os.walk(sp_dir):
            for f in sorted(files):
                if not f.endswith(".jsonl") or f in EXCLUDE_FILES:
                    continue
                p = os.path.join(cur, f)
                if os.path.getsize(p) == 0:
                    continue
                yield p


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
    in_root: str = "data",
    out_root: str = "data/phase_c/01_clean",
    report_path: str = "data/phase_c/reports/duplicate_report.md",
) -> dict:
    files = list(_iter_input_files(in_root))
    cross_files = [f for f in files if os.path.basename(f) == CROSS_TAG_FILENAME]
    other_files = [f for f in files if os.path.basename(f) != CROSS_TAG_FILENAME]

    # 1) 정제
    cleaned: list[tuple[str, dict]] = []
    pattern_totals: Counter = Counter()
    in_total = empty_after_clean = char_before = char_after = 0

    for f in other_files:
        for r in _read_jsonl(f):
            in_total += 1
            orig = r.get("text") or ""
            char_before += len(orig)
            new_text, stats = clean_text(orig)
            for k, v in stats.items():
                pattern_totals[k] += v
            r["text"] = new_text
            r["source_url"] = normalize_url(r.get("source_url") or "")
            r["char_count"] = len(new_text)
            char_after += len(new_text)
            if not new_text:
                empty_after_clean += 1
                continue
            cleaned.append((f, r))

    aliases: dict[str, list[dict]] = defaultdict(list)
    def _alias(r: dict, in_file: str) -> dict:
        return {
            "source_url": r.get("source_url"),
            "parent_post_id": r.get("parent_post_id"),
            "chunk_id": r.get("chunk_id"),
            "source_type": r.get("source_type"),
            "source_file": os.path.relpath(in_file, in_root),
        }

    # 2) chunk_id dedup
    by_id: dict[str, tuple[str, dict]] = {}
    id_dup_keep_existing = id_dup_swap = 0
    for f, r in cleaned:
        cid = r.get("chunk_id")
        if not cid:
            by_id[f"__noid__{id(r)}"] = (f, r)
            continue
        if cid in by_id:
            ex_f, ex_r = by_id[cid]
            if _better(r, ex_r):
                aliases[cid].append(_alias(ex_r, ex_f))
                by_id[cid] = (f, r)
                id_dup_swap += 1
            else:
                aliases[cid].append(_alias(r, f))
                id_dup_keep_existing += 1
        else:
            by_id[cid] = (f, r)

    # 3) text SHA1 dedup
    by_hash: dict[str, tuple[str, dict]] = {}
    sha_dup_keep_existing = sha_dup_swap = 0
    sha_group_sizes: Counter = Counter()
    sha_group_winner: dict[str, dict] = {}
    for f, r in by_id.values():
        h = hashlib.sha1((r.get("text") or "").encode("utf-8")).hexdigest()
        sha_group_sizes[h] += 1
        if h in by_hash:
            ex_f, ex_r = by_hash[h]
            if _better(r, ex_r):
                aliases[r["chunk_id"]].append(_alias(ex_r, ex_f))
                if ex_r.get("chunk_id") in aliases and ex_r["chunk_id"] != r["chunk_id"]:
                    aliases[r["chunk_id"]].extend(aliases.pop(ex_r["chunk_id"]))
                by_hash[h] = (f, r)
                sha_group_winner[h] = r
                sha_dup_swap += 1
            else:
                aliases[ex_r["chunk_id"]].append(_alias(r, f))
                sha_dup_keep_existing += 1
        else:
            by_hash[h] = (f, r)
            sha_group_winner[h] = r

    # 4) 출력 미러링
    by_outfile: dict[str, list[dict]] = defaultdict(list)
    for f, r in by_hash.values():
        rel = os.path.relpath(f, in_root)
        by_outfile[os.path.join(out_root, rel)].append(r)

    cross_in_total = cross_empty = 0
    for f in cross_files:
        rel = os.path.relpath(f, in_root)
        out_path = os.path.join(out_root, rel)
        for r in _read_jsonl(f):
            cross_in_total += 1
            new_text, stats = clean_text(r.get("text") or "")
            for k, v in stats.items():
                pattern_totals[k] += v
            r["text"] = new_text
            r["source_url"] = normalize_url(r.get("source_url") or "")
            r["char_count"] = len(new_text)
            if not new_text:
                cross_empty += 1
                continue
            by_outfile[out_path].append(r)

    for path, rows in by_outfile.items():
        rows.sort(key=lambda x: (x.get("parent_post_id") or "", x.get("chunk_index") or 0, x.get("chunk_id") or ""))
        _write_jsonl(path, rows)

    out_total = sum(len(v) for v in by_outfile.values())

    # 5) alias 사이드카
    reports_dir = os.path.dirname(report_path)
    os.makedirs(reports_dir, exist_ok=True)
    alias_sidecar = os.path.join(reports_dir, "dedup_aliases.jsonl")
    alias_records = alias_total_urls = 0
    with open(alias_sidecar, "w", encoding="utf-8") as fp:
        for winner_cid, alist in sorted(aliases.items()):
            if not alist:
                continue
            alias_records += 1
            alias_total_urls += len(alist)
            fp.write(json.dumps({
                "winner_chunk_id": winner_cid,
                "alias_count": len(alist),
                "aliases": alist,
            }, ensure_ascii=False) + "\n")

    # 6) top SHA1 dup sample
    sha_samples = []
    for h, cnt in sha_group_sizes.most_common(8):
        if cnt < 2:
            continue
        w = sha_group_winner[h]
        sha_samples.append({
            "count": cnt,
            "char_count": w.get("char_count"),
            "winner_chunk_id": w.get("chunk_id"),
            "winner_source_url": w.get("source_url"),
            "preview": (w.get("text") or "")[:160].replace("\n", " "),
        })

    summary = {
        "input_files": len(files),
        "input_chunks_total": in_total + cross_in_total,
        "input_chunks_dedup_pool": in_total,
        "input_chunks_cross_tag": cross_in_total,
        "empty_after_clean": empty_after_clean,
        "cross_empty_after_clean": cross_empty,
        "id_dup_keep_existing": id_dup_keep_existing,
        "id_dup_swap": id_dup_swap,
        "sha_dup_keep_existing": sha_dup_keep_existing,
        "sha_dup_swap": sha_dup_swap,
        "output_chunks_total": out_total,
        "char_before_dedup_pool": char_before,
        "char_after_dedup_pool": char_after,
        "pattern_totals": dict(pattern_totals),
        "alias_records": alias_records,
        "alias_total_urls": alias_total_urls,
        "alias_sidecar": alias_sidecar,
        "sha_samples": sha_samples,
        "per_file": [(p, len(rows)) for p, rows in sorted(by_outfile.items())],
    }
    write_clean_report(report_path, summary)
    return summary


if __name__ == "__main__":
    s = run()
    safe = {k: v for k, v in s.items() if k not in ("per_file", "sha_samples")}
    print(json.dumps(safe, ensure_ascii=False, indent=2))
