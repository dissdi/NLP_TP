"""Load BM25 + FAISS indices and chunk metadata.

Submission packaging:
  ROOT is Termproject_NLP/.
  Indices ship under assets/index/ (BM25 always; FAISS optional).
  RAG_INDEX_DIR / RAG_REPORT_DIR env vars override paths.
"""
from __future__ import annotations

import json
import os
import pickle
from dataclasses import dataclass, field
from typing import Any

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
_DEFAULT_INDEX = os.path.join(ROOT, "assets", "index", "04_index")
_DEFAULT_REPORT = os.path.join(ROOT, "assets", "index", "reports")
INDEX_DIR = os.environ.get("RAG_INDEX_DIR", _DEFAULT_INDEX)
REPORT_DIR = os.environ.get("RAG_REPORT_DIR", _DEFAULT_REPORT)


@dataclass
class BM25Track:
    name: str
    bm25: Any
    chunk_ids: list


@dataclass
class FaissTrack:
    name: str
    index: Any
    chunk_ids: list
    dim: int


@dataclass
class RetrievalIndex:
    bm25_tracks: list
    faiss_tracks: list
    meta: dict = field(default_factory=dict)
    alias_map: dict = field(default_factory=dict)


def load_bm25(track):
    path = os.path.join(INDEX_DIR, "bm25", track, "bm25.pkl")
    with open(path, "rb") as f:
        d = pickle.load(f)
    return BM25Track(name=track, bm25=d["bm25"], chunk_ids=d["chunk_ids"])


def load_faiss(track, model_tag="bge-m3"):
    import faiss
    base = os.path.join(INDEX_DIR, "faiss", model_tag, track)
    index = faiss.read_index(os.path.join(base, "index.faiss"))
    with open(os.path.join(base, "chunk_ids.json"), "r", encoding="utf-8") as f:
        cids = json.load(f)
    return FaissTrack(name=track, index=index, chunk_ids=cids, dim=index.d)


def load_meta():
    path = os.path.join(INDEX_DIR, "meta", "chunks.jsonl")
    meta = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            d = json.loads(line)
            meta[d["chunk_id"]] = d
    return meta


def load_alias_map():
    path = os.path.join(REPORT_DIR, "dedup_aliases.jsonl")
    m = {}
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


def _load_bm25_safe(track):
    path = os.path.join(INDEX_DIR, "bm25", track, "bm25.pkl")
    if not os.path.exists(path):
        return None
    return load_bm25(track)


def _load_faiss_safe(track, model_tag="bge-m3"):
    base = os.path.join(INDEX_DIR, "faiss", model_tag, track)
    if not os.path.exists(os.path.join(base, "index.faiss")):
        return None
    return load_faiss(track, model_tag)


def load_all(model_tag="bge-m3"):
    bm25 = [t for t in (_load_bm25_safe("general"), _load_bm25_safe("almi_cell")) if t is not None]
    fa = [t for t in (_load_faiss_safe("general", model_tag), _load_faiss_safe("almi_dept", model_tag)) if t is not None]
    if not bm25 and not fa:
        raise RuntimeError(
            f"No retrieval tracks loaded from {INDEX_DIR}. "
            "Set RAG_INDEX_DIR or build indices."
        )
    meta = load_meta()
    aliases = load_alias_map()
    return RetrievalIndex(bm25_tracks=bm25, faiss_tracks=fa, meta=meta, alias_map=aliases)
