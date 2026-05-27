"""Phase C - 04_index FAISS dense builder (default model: BAAI/bge-m3).

Two dense tracks:
  - general:   data/phase_c/03_enriched/general/chunks.jsonl    (1279 chunks)
  - almi_dept: data/phase_c/03_enriched/almi_dept/chunks.jsonl  (101 chunks)

For each track:
  - encode _passage (model-agnostic) with sentence-transformers
  - L2-normalize and build IndexFlatIP (cosine similarity)
  - persist FAISS index + chunk_ids.json + embeddings.npy (for re-use without re-encoding)

Outputs (data/phase_c/04_index/faiss/bge-m3/<track>/):
  - index.faiss
  - chunk_ids.json
  - embeddings.npy
  - build_meta.json
"""
from __future__ import annotations

import json
import os
import time
from typing import Iterable

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_DIR = os.path.join(ROOT, "data", "phase_c", "03_enriched")
OUT_DIR = os.path.join(ROOT, "data", "phase_c", "04_index", "faiss")

DEFAULT_MODEL_ID = "BAAI/bge-m3"
DEFAULT_MODEL_TAG = "bge-m3"
TRACKS = ["general", "almi_dept"]

# Optional model-specific prefix to prepend to each passage at encode time.
# bge-m3: no prefix required.
# e5 family: prefix passages with "passage: " and queries with "query: ".
MODEL_PASSAGE_PREFIX = {
    "BAAI/bge-m3": "",
    "intfloat/multilingual-e5-large": "passage: ",
    "jhgan/ko-sroberta-multitask": "",
}


def ensure_dir(p: str) -> None:
    os.makedirs(p, exist_ok=True)


def load_chunks(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def encode_passages(model, passages: list[str], batch_size: int = 8) -> np.ndarray:
    """Encode passages with the given sentence-transformer model. L2-normalized."""
    embs = model.encode(
        passages,
        batch_size=batch_size,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    return embs.astype("float32")


def build_track(model, model_id: str, track: str) -> dict:
    import faiss  # imported here so report writer can run without faiss

    in_path = os.path.join(IN_DIR, track, "chunks.jsonl")
    out_dir = os.path.join(OUT_DIR, DEFAULT_MODEL_TAG, track)
    ensure_dir(out_dir)

    rows = load_chunks(in_path)
    print(f"[faiss:{track}] loaded {len(rows)} chunks", flush=True)

    prefix = MODEL_PASSAGE_PREFIX.get(model_id, "")
    chunk_ids: list[str] = []
    passages: list[str] = []
    for r in rows:
        chunk_ids.append(r["chunk_id"])
        p = r.get("_passage") or r.get("text") or ""
        if prefix:
            p = prefix + p
        passages.append(p)

    t0 = time.time()
    embs = encode_passages(model, passages, batch_size=8)
    enc_secs = time.time() - t0
    print(f"[faiss:{track}] encoded {embs.shape} in {enc_secs:.1f}s", flush=True)

    dim = int(embs.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    np.save(os.path.join(out_dir, "embeddings.npy"), embs)
    faiss.write_index(index, os.path.join(out_dir, "index.faiss"))
    with open(os.path.join(out_dir, "chunk_ids.json"), "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)

    return {
        "track": track,
        "n_chunks": len(rows),
        "dim": dim,
        "encode_seconds": round(enc_secs, 1),
        "out_dir": os.path.relpath(out_dir, ROOT).replace("\\", "/"),
    }


def write_report(model_id: str, stats: list[dict]) -> None:
    rp = os.path.join(ROOT, "data", "phase_c", "reports", "index_faiss_report.md")
    ensure_dir(os.path.dirname(rp))
    L = ["# Phase C - 04_index FAISS Report", ""]
    L.append("## Model")
    L.append(f"- id: `{model_id}`")
    L.append(f"- passage prefix: `{MODEL_PASSAGE_PREFIX.get(model_id, '')!r}`")
    L.append("- index: IndexFlatIP over L2-normalized embeddings (cosine sim)")
    L.append("")
    L.append("## Tracks")
    L.append("| track | chunks | dim | encode sec |")
    L.append("|---|---:|---:|---:|")
    for s in stats:
        L.append(f"| `{s['track']}` | {s['n_chunks']} | {s['dim']} | {s['encode_seconds']} |")
    L.append("")
    L.append("## Output files")
    for s in stats:
        L.append(f"- `{s['out_dir']}/index.faiss`")
        L.append(f"- `{s['out_dir']}/chunk_ids.json`")
        L.append(f"- `{s['out_dir']}/embeddings.npy` (re-usable for re-indexing)")
    L.append("")
    L.append("## Policy notes")
    L.append("- general track = dense+sparse hybrid (paired with bm25/general)")
    L.append("- almi_dept track = dense-only for dept-level dense retrieval (cell-level BM25 in bm25/almi_cell)")
    L.append("- At retrieval time, queries must be encoded with the SAME model and (if applicable) prepended with the same prefix from MODEL_PASSAGE_PREFIX (queries use 'query: ' instead of 'passage: ' for e5).")
    with open(rp, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"[faiss] report: {rp}", flush=True)


def write_build_meta(model_id: str, stats: list[dict]) -> None:
    bm_path = os.path.join(OUT_DIR, DEFAULT_MODEL_TAG, "build_meta.json")
    ensure_dir(os.path.dirname(bm_path))
    obj = {
        "model_id": model_id,
        "model_tag": DEFAULT_MODEL_TAG,
        "passage_prefix": MODEL_PASSAGE_PREFIX.get(model_id, ""),
        "tracks": stats,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(bm_path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print(f"[faiss] build_meta: {bm_path}", flush=True)


def run(model_id: str = DEFAULT_MODEL_ID) -> None:
    # Lazy imports so the script's import surface fails clearly
    from sentence_transformers import SentenceTransformer
    print(f"[faiss] loading model: {model_id}", flush=True)
    t0 = time.time()
    model = SentenceTransformer(model_id)
    print(f"[faiss] model loaded in {time.time()-t0:.1f}s", flush=True)
    stats = []
    for track in TRACKS:
        stats.append(build_track(model, model_id, track))
    write_build_meta(model_id, stats)
    write_report(model_id, stats)
    print("[faiss] done", flush=True)


if __name__ == "__main__":
    import sys
    model_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MODEL_ID
    run(model_id)
