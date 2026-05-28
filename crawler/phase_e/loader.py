"""Load BM25 + FAISS indices and chunk metadata.

Layout (built in Phase C):
  data/phase_c/04_index/
    bm25/{general,almi_cell}/{bm25.pkl, chunk_ids.json}
    faiss/bge-m3/{general,almi_dept}/{index.faiss, chunk_ids.json}
    meta/chunks.jsonl
  data/phase_c/reports/dedup_aliases.jsonl  (winner -> alias urls)
"""
from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, field
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INDEX_DIR = os.path.join(ROOT, "data", "phase_c", "04_index")
REPORT_DIR = os.path.join(ROOT, "data", "phase_c", "reports")


@dataclass
class BM25Track:
    name: str
    bm25: Any
    chunk_ids: list[str]


@dataclass
class FaissTrack:
    name: str
    index: Any            # faiss.Index
    chunk_ids: list[str]
    dim: int


@dataclass
class RetrievalIndex:
    bm25_tracks: list[BM25Track]
    faiss_tracks: list[FaissTrack]
    meta: dict[str, dict] = field(default_factory=dict)
    alias_map: dict[str, list[str]] = field(default_factory=dict)


def load_bm25(track: str) -> BM25Track:
    path = os.path.join(INDEX_DIR, "bm25", track, "bm25.pkl")
    with open(path, "rb") as f:
        d = pickle.load(f)
    return BM25Track(name=track, bm25=d["bm25"], chunk_ids=d["chunk_ids"])


def load_faiss(track: str, model_tag: str = "bge-m3") -> FaissTrack:
    import faiss
    base = os.path.join(INDEX_DIR, "faiss", model_tag, track)
    index = faiss.read_index(os.path.join(base, "index.faiss"))
    with open(os.path.join(base, "chunk_ids.json"), "r", encoding="utf-8") as f:
        cids = json.load(f)
    return FaissTrack(name=track, index=index, chunk_ids=cids, dim=index.d)


def load_meta() -> dict[str, dict]:
    path = os.path.join(INDEX_DIR, "meta", "chunks.jsonl")
    meta: dict[str, dict] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            meta[d["chunk_id"]] = d
    return meta


def load_alias_map() -> dict[str, list[str]]:
    """winner_chunk_id -> [alias_url, ...] for retrieval recall against eval set."""
    path = os.path.join(REPORT_DIR, "dedup_aliases.jsonl")
    m: dict[str, list[str]] = {}
    if not os.path.exists(path):
        return m
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            wid = d.get("winner_chunk_id")
            aliases = d.get("aliases") or []
            urls = [a.get("source_url") for a in aliases if a.get("source_url")]
            if wid and urls:
                m[wid] = urls
    return m


def load_all(model_tag: str = "bge-m3") -> RetrievalIndex:
    """Load all tracks and meta in one shot."""
    bm25 = [load_bm25("general"), load_bm25("almi_cell")]
    fa = [load_faiss("general", model_tag), load_faiss("almi_dept", model_tag)]
    meta = load_meta()
    aliases = load_alias_map()
    return RetrievalIndex(bm25_tracks=bm25, faiss_tracks=fa, meta=meta, alias_map=aliases)
