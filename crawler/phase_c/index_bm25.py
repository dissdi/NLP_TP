"""Phase C - 04_index BM25 builder.

Two BM25 tracks:
  - general:   data/phase_c/03_enriched/general/chunks.jsonl    (1279 chunks)
  - almi_cell: data/phase_c/03_enriched/almi_cell/chunks.jsonl  (2235 chunks)

Tokenizer: kiwipiepy morphological analyzer, keeping content POS tags only.
Per-track outputs (data/phase_c/04_index/bm25/<track>/):
  - bm25.pkl       : pickled (BM25Okapi instance, tokenized_corpus reference)
  - chunk_ids.json : ordered list mapping bm25 row index -> chunk_id
  - tokens.jsonl   : per-chunk token list (one JSON array per line) for debug / re-build

Also writes data/phase_c/04_index/meta/chunks.jsonl: 16-field metadata for all corpus chunk_ids (lookup index).
"""
from __future__ import annotations

import glob
import json
import os
import pickle
import time
from typing import Iterable

from kiwipiepy import Kiwi
from rank_bm25 import BM25Okapi

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_DIR = os.path.join(ROOT, "data", "phase_c", "03_enriched")
OUT_DIR = os.path.join(ROOT, "data", "phase_c", "04_index")

# Content POS tags to keep (drop josa/eomi/punct/etc.)
KEEP_POS = {
    "NNG", "NNP", "NNB", "NR", "NP",       # nouns / pronouns / numerals
    "VV", "VA", "VX", "VCP", "VCN",        # verbs / adjectives / copulas
    "XR",                                   # roots
    "SL", "SN", "SH",                       # latin / digits / chinese
}

TRACKS = ["general", "almi_cell"]


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def load_chunks(jsonl_path: str) -> list[dict]:
    rows: list[dict] = []
    with open(jsonl_path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def tokenize_with_kiwi(kiwi: Kiwi, text: str) -> list[str]:
    """Morphological tokenize; keep content POS only; lower ASCII tokens."""
    out: list[str] = []
    for tok in kiwi.tokenize(text or ""):
        if tok.tag in KEEP_POS and tok.form:
            form = tok.form
            # latin lowercased; korean stays as-is
            if form.isascii():
                form = form.lower()
            # drop single-char content tokens that are likely noise
            if len(form) == 1 and tok.tag in {"SN"}:
                continue
            out.append(form)
    return out


def build_track(kiwi: Kiwi, track: str) -> dict:
    in_path = os.path.join(IN_DIR, track, "chunks.jsonl")
    out_dir = os.path.join(OUT_DIR, "bm25", track)
    ensure_dir(out_dir)

    rows = load_chunks(in_path)
    print(f"[bm25:{track}] loaded {len(rows)} chunks", flush=True)

    chunk_ids: list[str] = []
    tokenized_corpus: list[list[str]] = []
    tokens_jsonl_path = os.path.join(out_dir, "tokens.jsonl")
    t0 = time.time()
    with open(tokens_jsonl_path, "w", encoding="utf-8") as tf:
        for i, r in enumerate(rows):
            cid = r["chunk_id"]
            chunk_ids.append(cid)
            text = r.get("_text_for_bm25") or r.get("_passage") or r.get("text") or ""
            toks = tokenize_with_kiwi(kiwi, text)
            tokenized_corpus.append(toks)
            tf.write(json.dumps({"chunk_id": cid, "tokens": toks}, ensure_ascii=False) + "\n")
            if (i + 1) % 500 == 0:
                print(f"[bm25:{track}] tokenized {i+1}/{len(rows)} ({time.time()-t0:.1f}s)", flush=True)
    elapsed_tok = time.time() - t0
    print(f"[bm25:{track}] tokenize done in {elapsed_tok:.1f}s", flush=True)

    # Build BM25Okapi (default k1=1.5, b=0.75)
    t0 = time.time()
    bm25 = BM25Okapi(tokenized_corpus)
    elapsed_idx = time.time() - t0
    print(f"[bm25:{track}] BM25Okapi built in {elapsed_idx:.2f}s", flush=True)

    with open(os.path.join(out_dir, "bm25.pkl"), "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)
    with open(os.path.join(out_dir, "chunk_ids.json"), "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)

    # Stats
    token_counts = [len(t) for t in tokenized_corpus]
    avg_tok = sum(token_counts) / max(1, len(token_counts))
    return {
        "track": track,
        "n_chunks": len(rows),
        "tokenize_seconds": round(elapsed_tok, 1),
        "build_seconds": round(elapsed_idx, 2),
        "tokens_total": sum(token_counts),
        "tokens_avg": round(avg_tok, 1),
        "tokens_min": min(token_counts) if token_counts else 0,
        "tokens_max": max(token_counts) if token_counts else 0,
        "out_dir": os.path.relpath(out_dir, ROOT).replace("\\", "/"),
    }


def build_meta_lookup() -> int:
    """Write 16-field metadata for every chunk in the corpus (chunk_id-keyed lookup)."""
    meta_dir = os.path.join(OUT_DIR, "meta")
    ensure_dir(meta_dir)
    src = os.path.join(IN_DIR, "corpus", "all.jsonl")
    dst = os.path.join(meta_dir, "chunks.jsonl")
    SCHEMA_16 = [
        "text", "source_type", "source_url", "source_title", "domains",
        "chunk_index", "categories", "freshness", "posted_at", "parent_post_id",
        "section_path", "notes", "lang", "chunk_id", "char_count", "crawled_at",
    ]
    EXTRA = ["_retrieval_group", "_canonical_url", "_alias_urls"]
    n = 0
    with open(src, "r", encoding="utf-8") as fh, open(dst, "w", encoding="utf-8") as out:
        for line in fh:
            d = json.loads(line)
            keep = {k: d.get(k) for k in SCHEMA_16 + EXTRA}
            out.write(json.dumps(keep, ensure_ascii=False) + "\n")
            n += 1
    print(f"[bm25] meta lookup written: {n} rows -> {dst}", flush=True)
    return n


def write_report(stats: list[dict], n_meta: int) -> None:
    report_path = os.path.join(ROOT, "data", "phase_c", "reports", "index_bm25_report.md")
    ensure_dir(os.path.dirname(report_path))
    L = ["# Phase C - 04_index BM25 Report", ""]
    L.append("## Tokenizer")
    L.append("- kiwipiepy 0.23 (Korean morphological analyzer)")
    L.append("- kept POS: " + ", ".join(sorted(KEEP_POS)))
    L.append("- ASCII tokens lowercased; single-digit SN drops")
    L.append("")
    L.append("## Tracks")
    L.append("| track | chunks | tokens(total) | tokens(avg/min/max) | tok sec | build sec |")
    L.append("|---|---:|---:|---|---:|---:|")
    for s in stats:
        L.append(
            f"| `{s['track']}` | {s['n_chunks']} | {s['tokens_total']} | "
            f"{s['tokens_avg']} / {s['tokens_min']} / {s['tokens_max']} | "
            f"{s['tokenize_seconds']} | {s['build_seconds']} |"
        )
    L.append("")
    L.append("## Output files")
    for s in stats:
        L.append(f"- `{s['out_dir']}/bm25.pkl`")
        L.append(f"- `{s['out_dir']}/chunk_ids.json`")
        L.append(f"- `{s['out_dir']}/tokens.jsonl`")
    L.append("")
    L.append("## Metadata lookup")
    L.append(f"- `data/phase_c/04_index/meta/chunks.jsonl`: {n_meta} rows (16 schema fields + 3 derived)")
    L.append("")
    L.append("## Policy notes")
    L.append("- general track = dense+sparse hybrid candidate pool")
    L.append("- almi_cell track = sparse-only; dense side uses almi_dept (FAISS phase)")
    L.append("- BM25 hyperparams: default k1=1.5, b=0.75 (rank_bm25 defaults)")
    L.append("- queries at retrieval time must be tokenized with the SAME function")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[bm25] report: {report_path}", flush=True)


def run() -> None:
    kiwi = Kiwi()
    print("[bm25] kiwipiepy loaded", flush=True)
    stats = []
    for track in TRACKS:
        stats.append(build_track(kiwi, track))
    n_meta = build_meta_lookup()
    write_report(stats, n_meta)
    print("[bm25] done", flush=True)


if __name__ == "__main__":
    run()
