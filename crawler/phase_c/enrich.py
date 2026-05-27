"""Phase C — 03_enriched. 정책은 phase_c_plan.md §3 참조."""
from __future__ import annotations

import glob
import json
import os
import re
from collections import Counter, defaultdict
from typing import Iterable

from ._report import write_enrich_report

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_DIR = os.path.join(ROOT, "data", "phase_c", "02_rechunked")
OUT_DIR = os.path.join(ROOT, "data", "phase_c", "03_enriched")
REPORT_DIR = os.path.join(ROOT, "data", "phase_c", "reports")
ALIAS_PATH = os.path.join(REPORT_DIR, "dedup_aliases.jsonl")

SCHEMA_16 = [
    "text", "source_type", "source_url", "source_title", "domains",
    "chunk_index", "categories", "freshness", "posted_at", "parent_post_id",
    "section_path", "notes", "lang", "chunk_id", "char_count", "crawled_at",
]
DERIVED_5 = ["_passage", "_alias_urls", "_retrieval_group", "_canonical_url", "_text_for_bm25"]


def iter_input_files() -> list[str]:
    files = sorted(glob.glob(os.path.join(IN_DIR, "**", "*.jsonl"), recursive=True))
    return [f for f in files if os.path.getsize(f) > 0]


def classify(path: str) -> str:
    rel = os.path.relpath(path, IN_DIR).replace("\\", "/")
    if rel == "sprint3/dept_info/chunks.jsonl":
        return "almi_cell"
    if rel == "sprint3/dept_info/dept_merged.jsonl":
        return "almi_dept"
    return "general"


def load_alias_map() -> dict[str, list[str]]:
    m: dict[str, list[str]] = {}
    if not os.path.exists(ALIAS_PATH):
        return m
    with open(ALIAS_PATH, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            d = json.loads(line)
            wid = d.get("winner_chunk_id")
            aliases = d.get("aliases") or []
            urls = [a.get("source_url") for a in aliases if a.get("source_url")]
            seen: set = set()
            ordered: list[str] = []
            for u in urls:
                if u not in seen:
                    seen.add(u)
                    ordered.append(u)
            if wid and ordered:
                m[wid] = ordered
    return m


_TRAIL_BREADCRUMB = re.compile(
    r"\s*(?:>\s*충남대학교\s*$|>\s*부서홈페이지\s*$|>\s*대학생활\s*$|>\s*Home\s*$)",
    re.IGNORECASE,
)
_MULTI_SPACE = re.compile(r"[ \t]+")
_ARTICLE = re.compile(r"^제\s*\d+\s*조")
_ASCII_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_]+")


def normalize_title(title) -> str:
    if not title:
        return ""
    t = title.strip()
    for _ in range(4):
        new = _TRAIL_BREADCRUMB.sub("", t).rstrip()
        if new == t:
            break
        t = new
    t = _MULTI_SPACE.sub(" ", t)
    if len(t) > 200:
        t = t[:200].rstrip()
    return t


def build_passage(d: dict) -> str:
    title = normalize_title(d.get("source_title"))
    section = (d.get("section_path") or "").strip()
    text = d.get("text") or ""
    rg = d.get("_retrieval_group")
    if rg in ("almi_cell", "almi_dept"):
        return text.strip()
    if section and _ARTICLE.match(section):
        return (f"{section} | {title}\n{text}" if title else f"{section}\n{text}").strip()
    head_parts = [p for p in (title, section if section and section.lower() != "body" else None) if p]
    head = " | ".join(head_parts)
    return (f"{head}\n{text}" if head else text).strip()


def build_bm25_text(passage: str) -> str:
    return _ASCII_TOKEN.sub(lambda m: m.group(0).lower(), passage)


def enrich_chunk(d: dict, group: str, alias_map: dict) -> dict:
    out = {k: d.get(k) for k in SCHEMA_16}
    out["_retrieval_group"] = group
    out["_alias_urls"] = alias_map.get(d.get("chunk_id"), [])
    out["_canonical_url"] = (d.get("source_url") or "").strip()
    passage = build_passage({**d, "_retrieval_group": group})
    out["_passage"] = passage
    out["_text_for_bm25"] = build_bm25_text(passage)
    return out


def merge_cross_tag_dups(rows: list[dict]):
    """general 트랙 내 chunk_id 중복(cross_tag 페어)을 합집합 merge로 통합."""
    by_cid: dict = {}
    for r in rows:
        by_cid.setdefault(r["chunk_id"], []).append(r)
    merged: list[dict] = []
    n_merged = 0
    for cid, recs in by_cid.items():
        if len(recs) == 1:
            merged.append(recs[0])
            continue
        n_merged += 1
        base = next(
            (r for r in recs if "cross_tag" in (r.get("section_path") or "")),
            recs[0],
        )
        out = dict(base)
        all_doms: list = []
        seen_d: set = set()
        all_cats: list = []
        seen_c: set = set()
        notes_parts: list = []
        sections: list = []
        for r in recs:
            for x in r.get("domains") or []:
                if x not in seen_d:
                    seen_d.add(x)
                    all_doms.append(x)
            for x in r.get("categories") or []:
                if x not in seen_c:
                    seen_c.add(x)
                    all_cats.append(x)
            n = r.get("notes")
            if n and n not in notes_parts:
                notes_parts.append(n)
            sp = r.get("section_path") or ""
            if sp and sp not in sections:
                sections.append(sp)
        out["domains"] = all_doms
        out["categories"] = all_cats
        short_sections = sorted({sp.replace("cross_tag/", "", 1) for sp in sections})
        out["section_path"] = " | ".join(short_sections) if short_sections else (base.get("section_path") or "")
        out["notes"] = " | ".join(notes_parts) if notes_parts else None
        merged.append(out)
    return merged, n_merged


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def write_jsonl(path: str, rows: Iterable[dict]) -> int:
    ensure_dir(os.path.dirname(path))
    n = 0
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def run() -> dict:
    alias_map = load_alias_map()
    files = iter_input_files()
    print(f"[enrich] input files: {len(files)}", flush=True)
    print(f"[enrich] alias_map winners: {len(alias_map)}", flush=True)

    bucket: dict = defaultdict(list)
    n_in = 0
    n_with_alias = 0
    passage_lens: list = []
    domain_counter: Counter = Counter()
    group_per_file: list = []
    seen_ids: set = set()
    dup_ids: list = []

    for f in files:
        group = classify(f)
        fn = 0
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                missing = [k for k in SCHEMA_16 if k not in d]
                if missing:
                    raise RuntimeError(f"missing 16-schema fields {missing} in {f}")
                cid = d.get("chunk_id")
                if cid in seen_ids:
                    dup_ids.append(cid)
                else:
                    seen_ids.add(cid)
                enriched = enrich_chunk(d, group, alias_map)
                bucket[group].append(enriched)
                if enriched["_alias_urls"]:
                    n_with_alias += 1
                passage_lens.append(len(enriched["_passage"]))
                for dom in enriched.get("domains") or []:
                    domain_counter[dom] += 1
                n_in += 1
                fn += 1
        group_per_file.append((os.path.relpath(f, IN_DIR).replace("\\", "/"), group, fn))

    n_general_in = len(bucket.get("general", []))
    merged_general, n_merged_pairs = merge_cross_tag_dups(bucket.get("general", []))
    bucket["general"] = merged_general
    print(
        f"[enrich] cross_tag merge: general {n_general_in} -> {len(merged_general)} (pairs: {n_merged_pairs})",
        flush=True,
    )

    out_files: list = []
    for group, rows in bucket.items():
        out_path = os.path.join(OUT_DIR, group, "chunks.jsonl")
        n = write_jsonl(out_path, rows)
        out_files.append((os.path.relpath(out_path, ROOT).replace("\\", "/"), n))
        print(f"[enrich] wrote {out_path}  ({n})", flush=True)

    all_rows: list = []
    for group in ("general", "almi_cell", "almi_dept"):
        all_rows.extend(bucket.get(group, []))
    corpus_path = os.path.join(OUT_DIR, "corpus", "all.jsonl")
    n_corpus = write_jsonl(corpus_path, all_rows)
    print(f"[enrich] wrote {corpus_path}  ({n_corpus})", flush=True)

    stats = {
        "n_in": n_in,
        "n_with_alias": n_with_alias,
        "n_alias_winners": len(alias_map),
        "dup_ids_in_input": dup_ids,
        "n_general_in": n_general_in,
        "n_general_out": len(merged_general),
        "n_merged_pairs": n_merged_pairs,
        "passage_min": min(passage_lens) if passage_lens else 0,
        "passage_max": max(passage_lens) if passage_lens else 0,
        "passage_avg": sum(passage_lens) // len(passage_lens) if passage_lens else 0,
        "domain_counter": dict(domain_counter),
        "group_per_file": group_per_file,
        "out_files": out_files,
        "corpus_size": n_corpus,
    }
    write_enrich_report(os.path.join(REPORT_DIR, "enrich_report.md"), stats, SCHEMA_16, DERIVED_5)
    print(f"[enrich] report written", flush=True)
    return stats


if __name__ == "__main__":
    run()
