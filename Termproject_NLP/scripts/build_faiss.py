"""Build bge-m3 FAISS index for the `general` track in Termproject submission.

Reads:  assets/index/03_enriched/general/chunks.jsonl  (1,151 in-scope chunks)
Writes: assets/index/04_index/faiss/bge-m3/general/{index.faiss,chunk_ids.json,embeddings.npy,build_meta.json}

Run-once on a machine with bge-m3 ready (GPU strongly preferred):

    python Termproject_NLP/scripts/build_faiss.py

Dependencies: sentence-transformers, faiss-cpu, torch, numpy.
On GPU: bge-m3 encode for 1,151 chunks finishes in ~30s.
On CPU: ~3-5 min.

Loader (`src/crawler/phase_e/loader.py`) auto-detects the file. With FAISS
present, retrieval becomes hybrid (BM25 + dense + reranker). Without FAISS,
the pipeline falls back to BM25-only (~88.5% recall) but stays functional.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent  # Termproject_NLP/

CHUNKS_PATH = ROOT / "assets" / "index" / "03_enriched" / "general" / "chunks.jsonl"
OUT_DIR = ROOT / "assets" / "index" / "04_index" / "faiss" / "bge-m3" / "general"

MODEL_ID = "BAAI/bge-m3"
MODEL_TAG = "bge-m3"
TRACK = "general"


def load_chunks(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def main() -> None:
    from sentence_transformers import SentenceTransformer
    import faiss

    assert CHUNKS_PATH.exists(), f"missing {CHUNKS_PATH}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"[faiss] loading model: {MODEL_ID}", flush=True)
    t0 = time.time()
    model = SentenceTransformer(MODEL_ID)
    print(f"[faiss] model loaded in {time.time()-t0:.1f}s", flush=True)

    rows = load_chunks(CHUNKS_PATH)
    print(f"[faiss:{TRACK}] loaded {len(rows)} chunks from {CHUNKS_PATH}", flush=True)

    chunk_ids: list[str] = []
    passages: list[str] = []
    for r in rows:
        chunk_ids.append(r["chunk_id"])
        p = r.get("_passage") or r.get("text") or ""
        passages.append(p)

    t1 = time.time()
    embs = model.encode(
        passages,
        batch_size=8,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype("float32")
    print(f"[faiss:{TRACK}] encoded {embs.shape} in {time.time()-t1:.1f}s", flush=True)

    dim = int(embs.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    np.save(OUT_DIR / "embeddings.npy", embs)
    faiss.write_index(index, str(OUT_DIR / "index.faiss"))
    with (OUT_DIR / "chunk_ids.json").open("w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)

    meta = {
        "model_id": MODEL_ID,
        "model_tag": MODEL_TAG,
        "track": TRACK,
        "n_chunks": len(rows),
        "dim": dim,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(CHUNKS_PATH.relative_to(ROOT)).replace("\\", "/"),
    }
    with (OUT_DIR / "build_meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[faiss] wrote: {OUT_DIR}", flush=True)
    print("[faiss] done", flush=True)


if __name__ == "__main__":
    main()
