"""Phase C report helpers (ASCII-only to avoid Write tool multi-byte truncation)."""
from __future__ import annotations
import os


def _ensure(p: str) -> None:
    os.makedirs(os.path.dirname(p), exist_ok=True)


def write_clean_report(path: str, s: dict) -> None:
    _ensure(path)
    L = ["# Phase C - 01_clean Report", ""]
    L.append("## Input")
    L.append(f"- files: {s.get('input_files')}")
    L.append(f"- chunks (dedup pool): {s.get('input_chunks_dedup_pool')}")
    L.append(f"- chunks (cross_tag, excl. dedup): {s.get('input_chunks_cross_tag')}")
    L.append(f"- chunks total: {s.get('input_chunks_total')}")
    L.append("")
    L.append("## Noise patterns removed")
    pt = s.get("pattern_totals") or {}
    if not pt:
        L.append("- (no change)")
    else:
        for k, v in sorted(pt.items(), key=lambda x: -x[1]):
            L.append(f"- `{k}`: {v}")
    L.append("")
    L.append("## Dedup")
    L.append(f"- empty after clean (pool): {s.get('empty_after_clean')}")
    L.append(f"- empty after clean (cross_tag): {s.get('cross_empty_after_clean')}")
    L.append(f"- chunk_id dup (keep existing): {s.get('id_dup_keep_existing')}")
    L.append(f"- chunk_id dup (swap to new): {s.get('id_dup_swap')}")
    L.append(f"- SHA1 dup (keep existing): {s.get('sha_dup_keep_existing')}")
    L.append(f"- SHA1 dup (swap to new): {s.get('sha_dup_swap')}")
    L.append("")
    L.append("## Output")
    L.append(f"- total chunks: {s.get('output_chunks_total')}")
    cb, ca = s.get("char_before_dedup_pool", 0), s.get("char_after_dedup_pool", 0)
    if cb:
        L.append(f"- char size (pool): {cb} -> {ca} ({(ca-cb)/cb*100:+.2f}%)")
    L.append("")
    L.append("## Dedup alias sidecar")
    L.append(f"- file: `{s.get('alias_sidecar')}`")
    L.append(f"- winners: {s.get('alias_records', 0)}")
    L.append(f"- total alias urls: {s.get('alias_total_urls', 0)}")
    L.append("")
    L.append("## Per-file output")
    L.append("| file | chunks |")
    L.append("|---|---:|")
    for p, n in s.get("per_file") or []:
        L.append(f"| `{p}` | {n} |")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")


def write_rechunk_report(path: str, s: dict) -> None:
    _ensure(path)
    L = ["# Phase C - 02_rechunked Report", ""]
    L.append("## Input")
    L.append(f"- chunks: {s.get('input_chunks')}")
    L.append(f"- avg/max char_count: {s.get('avg_in', 0):.0f} / {s.get('max_in')}")
    L.append("")
    L.append("## Split (char_count > 2000)")
    L.append(f"- source chunks: {s.get('split_source_chunks')}")
    L.append(f"  - article-based: {s.get('split_by_article')}")
    L.append(f"  - separator-based: {s.get('split_by_separator')}")
    L.append(f"  - 1500 sliding window: {s.get('split_by_window')}")
    L.append(f"- result chunks: {s.get('split_result_chunks')}")
    L.append("")
    L.append("## Merge (char_count < 50, except almi cells)")
    L.append(f"- source: {s.get('merge_source_chunks')}")
    L.append(f"- result: {s.get('merge_result_chunks')}")
    L.append(f"- orphans: {s.get('merge_orphans')}")
    L.append("")
    L.append("## Almi (T6 dept_info)")
    L.append(f"- cells kept (BM25): {s.get('almi_cells_kept')}")
    L.append(f"- dept_merged (dense): {s.get('almi_dept_chunks')}")
    L.append("")
    L.append("## Output")
    L.append(f"- total: {s.get('output_chunks')}")
    L.append(f"- avg/max: {s.get('avg_out', 0):.0f} / {s.get('max_out')}")
    L.append(f"- under_50: {s.get('under_50_after')} | over_2000: {s.get('over_2000_after')}")
    L.append("")
    L.append("## Domain in -> out")
    L.append("| domain | in | out | delta |")
    L.append("|---|---:|---:|---:|")
    for dom, (i, o) in sorted((s.get("domain_in_out") or {}).items(), key=lambda x: -x[1][1]):
        L.append(f"| {dom} | {i} | {o} | {o-i:+d} |")
    L.append("")
    L.append("## Per file")
    L.append("| file | in | out |")
    L.append("|---|---:|---:|")
    for p, (i, o) in sorted((s.get("per_file") or {}).items()):
        L.append(f"| `{p}` | {i} | {o} |")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")


def write_enrich_report(path: str, s: dict, schema_16: list, derived_5: list) -> None:
    _ensure(path)
    L = ["# Phase C - 03_enriched Report", ""]
    L.append("## Input")
    L.append(f"- files: {len(s['group_per_file'])}")
    L.append(f"- chunks: {s['n_in']}")
    L.append(f"- chunk_id dup in input: {len(s['dup_ids_in_input'])}")
    if s["dup_ids_in_input"]:
        L.append(f"  - sample: {s['dup_ids_in_input'][:5]}")
    L.append("")
    L.append("## Output (retrieval_group split)")
    for p, n in s["out_files"]:
        L.append(f"- `{p}`: {n}")
    L.append(f"- `data/phase_c/03_enriched/corpus/all.jsonl`: {s['corpus_size']}")
    L.append("")
    L.append("## cross_tag merge (general track)")
    L.append(f"- in: {s['n_general_in']}  ->  out: {s['n_general_out']}")
    L.append(f"- merged pairs: {s['n_merged_pairs']}")
    L.append("- policy: cross_tag copies merged by chunk_id; domains/categories union, notes join, section_path strips cross_tag/ prefix.")
    L.append("")
    L.append("## Enrichment stats")
    L.append(f"- chunks with _alias_urls: {s['n_with_alias']} (winner pool: {s['n_alias_winners']})")
    L.append(f"- _passage length: min {s['passage_min']} / avg {s['passage_avg']} / max {s['passage_max']}")
    L.append("")
    L.append("## Domain distribution (multi-tag sum)")
    for k in sorted(s["domain_counter"]):
        L.append(f"- {k}: {s['domain_counter'][k]}")
    L.append("")
    L.append("## Per-file retrieval_group classification")
    for rel, group, n in s["group_per_file"]:
        L.append(f"- `{rel}` -> **{group}** ({n})")
    L.append("")
    L.append("## Schema (per chunk)")
    L.append("- original 16 fields: " + ", ".join(schema_16))
    L.append("- derived 5 fields (with `_` prefix): " + ", ".join(derived_5))
    L.append("")
    L.append("## Policy notes")
    L.append("- original 16 fields are NEVER mutated.")
    L.append("- _passage is model-agnostic; 04_index encoder adds model-specific prefix (e.g. e5 passage:).")
    L.append("- almi_cell track is BM25-only, almi_dept track is dense-only at 04_index.")
    L.append("- _alias_urls supports retrieval recall against evaluation expected_source_urls (Phase E).")
    with open(path, "w", encoding="utf-8") as fp:
        fp.write("\n".join(L) + "\n")
