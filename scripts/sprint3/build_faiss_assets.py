"""Termproject_NLP/assets/index/ 경로로 FAISS bge-m3 인덱스 빌드.

기존 phase_c.index_faiss는 data/phase_c/03_enriched 를 보지만,
실제 운영 corpus는 Termproject_NLP/assets/index 로 옮겨졌으므로 경로만 갈아끼운 빌더.

사용 (랩실 GPU):
  pip install sentence-transformers faiss-cpu  # 또는 faiss-gpu
  python -m scripts.sprint3.build_faiss_assets

출력:
  Termproject_NLP/assets/index/04_index/faiss/bge-m3/general/{index.faiss, chunk_ids.json, embeddings.npy}
  Termproject_NLP/assets/index/04_index/faiss/bge-m3/build_meta.json
"""
from __future__ import annotations

import json
import os
import time

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IN_DIR = os.path.join(ROOT, "Termproject_NLP", "assets", "index", "03_enriched")
OUT_DIR = os.path.join(ROOT, "Termproject_NLP", "assets", "index", "04_index", "faiss")

MODEL_ID = "BAAI/bge-m3"
MODEL_TAG = "bge-m3"
TRACKS = ["general"]   # almi_dept 트랙은 본 corpus에 없음 — general 하나만


def load_chunks(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def build_track(model, track: str) -> dict:
    import faiss
    in_path = os.path.join(IN_DIR, track, "chunks.jsonl")
    out_dir = os.path.join(OUT_DIR, MODEL_TAG, track)
    os.makedirs(out_dir, exist_ok=True)

    rows = load_chunks(in_path)
    print(f"[faiss:{track}] loaded {len(rows)} chunks", flush=True)

    chunk_ids = [r["chunk_id"] for r in rows]
    passages = [(r.get("_passage") or r.get("text") or "") for r in rows]

    t0 = time.time()
    embs = model.encode(
        passages,
        batch_size=8,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=True,
    ).astype("float32")
    secs = time.time() - t0
    print(f"[faiss:{track}] encoded {embs.shape} in {secs:.1f}s", flush=True)

    dim = int(embs.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(embs)

    np.save(os.path.join(out_dir, "embeddings.npy"), embs)
    faiss.write_index(index, os.path.join(out_dir, "index.faiss"))
    with open(os.path.join(out_dir, "chunk_ids.json"), "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)
    print(f"[faiss:{track}] wrote {out_dir}", flush=True)

    return {
        "track": track,
        "n_chunks": len(rows),
        "dim": dim,
        "encode_seconds": round(secs, 1),
    }


def main() -> int:
    from sentence_transformers import SentenceTransformer
    print(f"[faiss] loading {MODEL_ID} ...", flush=True)
    t0 = time.time()
    model = SentenceTransformer(MODEL_ID)
    print(f"[faiss] model loaded in {time.time()-t0:.1f}s", flush=True)

    stats = []
    for tr in TRACKS:
        stats.append(build_track(model, tr))

    bm_path = os.path.join(OUT_DIR, MODEL_TAG, "build_meta.json")
    os.makedirs(os.path.dirname(bm_path), exist_ok=True)
    with open(bm_path, "w", encoding="utf-8") as f:
        json.dump({
            "model_id": MODEL_ID,
            "model_tag": MODEL_TAG,
            "passage_prefix": "",
            "tracks": stats,
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }, f, ensure_ascii=False, indent=2)
    print(f"[faiss] build_meta: {bm_path}", flush=True)
    print("\n✅ FAISS bge-m3 빌드 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
