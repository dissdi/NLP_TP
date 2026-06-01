"""Build bge-m3 FAISS index for the `general` track in Termproject submission.

Reads:  assets/index/03_enriched/general/chunks.jsonl  (1,151 in-scope chunks)
Writes: assets/index/04_index/faiss/bge-m3/general/{index.faiss,chunk_ids.json,embeddings.npy,build_meta.json}

Run-once on a machine with bge-m3 ready (GPU strongly preferred):

    # default — picks cuda:0 if available, else cpu
    python scripts/build_faiss.py

    # specify GPU index (when server has multiple)
    python scripts/build_faiss.py --gpu 1

    # or via env var (equivalent)
    CUDA_VISIBLE_DEVICES=1 python scripts/build_faiss.py

    # force CPU (slow)
    python scripts/build_faiss.py --gpu cpu

Dependencies: sentence-transformers, faiss-cpu, torch, numpy.
On GPU: bge-m3 encode for 1,151 chunks finishes in ~30s.
On CPU: ~3-5 min.

Loader (`src/crawler/phase_e/loader.py`) auto-detects the file. With FAISS
present, retrieval becomes hybrid (BM25 + dense + reranker). Without FAISS,
the pipeline falls back to BM25-only (~88.5% recall) but stays functional.
"""
from __future__ import annotations

import argparse
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


def load_chunks(path):
    rows = []
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _resolve_device(gpu_arg):
    """Resolve --gpu arg into a torch device string.

    Priority: explicit --gpu  >  cuda:0 if available  >  cpu.
    Accepts: '0', '1', 'cuda', 'cuda:2', 'cpu', or None.
    """
    import torch
    if gpu_arg is not None:
        s = str(gpu_arg).strip().lower()
        if s in ("cpu", "none", "-1"):
            return "cpu"
        if s.startswith("cuda"):
            return s
        if s.isdigit():
            return "cuda:" + s
    if torch.cuda.is_available():
        return "cuda:0"
    return "cpu"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--gpu",
        default=None,
        help="GPU index (0/1/...), 'cuda', 'cuda:N', or 'cpu'. "
             "Default: cuda:0 if available, else cpu. "
             "Equivalent to CUDA_VISIBLE_DEVICES=N.",
    )
    args = parser.parse_args()

    import torch
    from sentence_transformers import SentenceTransformer
    import faiss

    assert CHUNKS_PATH.exists(), "missing " + str(CHUNKS_PATH)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    device = _resolve_device(args.gpu)
    if device.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("requested " + device + " but CUDA not available")
        idx = int(device.split(":")[1]) if ":" in device else 0
        print("[faiss] device=" + device + " (" + torch.cuda.get_device_name(idx) + ")", flush=True)
    else:
        print("[faiss] device=cpu (encode will be slow, ~3-5 min)", flush=True)

    print("[faiss] loading model: " + MODEL_ID, flush=True)
    t0 = time.time()
    model = SentenceTransformer(MODEL_ID, device=device)
    print("[faiss] model loaded in {:.1f}s".format(time.time() - t0), flush=True)

    rows = load_chunks(CHUNKS_PATH)
    print("[faiss:" + TRACK + "] loaded " + str(len(rows)) + " chunks from " + str(CHUNKS_PATH), flush=True)

    chunk_ids = []
    passages = []
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
    print("[faiss:" + TRACK + "] encoded " + str(embs.shape) + " in {:.1f}s".format(time.time() - t1), flush=True)

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
        "device": device,
        "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": str(CHUNKS_PATH.relative_to(ROOT)).replace("\\", "/"),
    }
    with (OUT_DIR / "build_meta.json").open("w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print("[faiss] wrote: " + str(OUT_DIR), flush=True)
    print("[faiss] done", flush=True)


if __name__ == "__main__":
    main()
