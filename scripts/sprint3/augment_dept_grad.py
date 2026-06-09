"""신규 dept_grad_10 chunks → 16-필드 정규화 + 기존 corpus append + BM25 재빌드.

입력:
  data/sprint3/dept_grad_10/chunks_raw.jsonl  (24 raw chunks)

처리:
  1) articleNo= URL 제외
  2) char_count > 2000 → 1500/200 sliding window 분할 (phase_c.rechunk 정책)
  3) URL이 기존 corpus와 중복인 chunk → 기존 corpus 측 chunk 모두 제거 (신규로 교체)
  4) 16-필드 + 4 라벨필드 + _passage/_text_for_bm25/_canonical_url/_alias_urls 정규화
  5) 기존 chunks.jsonl backup → 새 corpus 덮어쓰기
  6) meta/chunks.jsonl 도 동일 처리 (_passage/_text_for_bm25 제외)
  7) BM25 재빌드 (kiwipiepy)

출력:
  Termproject_NLP/assets/index/03_enriched/general/chunks.jsonl  (덮어쓰기)
  Termproject_NLP/assets/index/04_index/meta/chunks.jsonl        (덮어쓰기)
  Termproject_NLP/assets/index/04_index/bm25/general/{bm25.pkl, chunk_ids.json, tokens.jsonl}
  .bak.YYYYMMDD-HHMM 백업 동시 생성

사용:
  python -m scripts.sprint3.augment_dept_grad --dry-run     # 미리보기
  python -m scripts.sprint3.augment_dept_grad               # 실행
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pickle
import shutil
import sys
import time
from collections import Counter
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

RAW = os.path.join(ROOT, "data", "sprint3", "dept_grad_10", "chunks_raw.jsonl")
ENRICHED = os.path.join(ROOT, "Termproject_NLP", "assets", "index", "03_enriched", "general", "chunks.jsonl")
META = os.path.join(ROOT, "Termproject_NLP", "assets", "index", "04_index", "meta", "chunks.jsonl")
BM25_DIR = os.path.join(ROOT, "Termproject_NLP", "assets", "index", "04_index", "bm25", "general")

MAX_CHARS = 2000
WINDOW_CHARS = 1500
WINDOW_OVERLAP = 200


def load_jsonl(path: str) -> list[dict]:
    rows: list[dict] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: str, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def split_by_window(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    out: list[str] = []
    start = 0
    step = WINDOW_CHARS - WINDOW_OVERLAP
    while start < len(text):
        end = min(start + WINDOW_CHARS, len(text))
        out.append(text[start:end])
        if end >= len(text):
            break
        start += step
    return out


def new_chunk_id(orig: str, suffix: str) -> str:
    return hashlib.sha1(f"{orig}|{suffix}".encode("utf-8")).hexdigest()[:16]


def normalize_chunk(r: dict, *, piece_text: str, piece_idx: int, total_pieces: int, orig_id: str) -> dict:
    """16-필드 + 4 라벨 + _passage/_text_for_bm25 정규화."""
    src_title = r.get("source_title") or ""
    text = piece_text
    # _passage = title + "\n" + text (기존 corpus 규칙)
    passage = (src_title + "\n" + text) if src_title else text

    chunk_id = orig_id if total_pieces == 1 else new_chunk_id(orig_id, f"p{piece_idx:02d}")
    notes = None
    if total_pieces > 1:
        notes = f"split_from={orig_id}|dept_grad_10"
    else:
        notes = "dept_grad_10"

    out = {
        "text": text,
        "source_type": r.get("source_type", "T1"),
        "source_url": r["source_url"],
        "source_title": src_title,
        "domains": r.get("domains", [1]),
        "chunk_index": piece_idx,
        "categories": r.get("categories", ["1.2"]),
        "freshness": r.get("freshness", "static"),
        "posted_at": r.get("posted_at"),
        "parent_post_id": orig_id if total_pieces > 1 else None,
        "section_path": r.get("section_path", "body"),
        "notes": notes,
        "lang": r.get("lang", "ko"),
        "chunk_id": chunk_id,
        "char_count": len(text),
        "crawled_at": r.get("crawled_at"),
        # enriched extra
        "_retrieval_group": "general",
        "_alias_urls": [],
        "_canonical_url": r["source_url"],
        "_passage": passage,
        "_text_for_bm25": passage,
        # 5-cat labels
        "label_5way": 0,                 # 졸업요건
        "is_oos": False,
        "label_confidence": "high",
        "label_reason": "kw:grad",
    }
    return out


def to_meta(enriched_row: dict) -> dict:
    """meta/chunks.jsonl 스키마: _passage/_text_for_bm25 제외."""
    out = dict(enriched_row)
    out.pop("_passage", None)
    out.pop("_text_for_bm25", None)
    return out


def process_new_chunks(raw_rows: list[dict]) -> tuple[list[dict], list[dict], dict]:
    """raw 24개 → 정규화된 enriched + meta rows.
    반환: (enriched_rows, meta_rows, stats)
    """
    excluded_noise = 0
    kept = []
    for r in raw_rows:
        if "articleNo=" in r.get("source_url", ""):
            excluded_noise += 1
            continue
        kept.append(r)

    enriched_out: list[dict] = []
    meta_out: list[dict] = []
    split_total = 0
    for r in kept:
        text = r.get("text") or ""
        orig_id = r["chunk_id"]
        if len(text) <= MAX_CHARS:
            pieces = [text]
        else:
            pieces = split_by_window(text)
            split_total += 1
        for i, p in enumerate(pieces):
            enr = normalize_chunk(r, piece_text=p, piece_idx=i, total_pieces=len(pieces), orig_id=orig_id)
            enriched_out.append(enr)
            meta_out.append(to_meta(enr))

    stats = {
        "raw_in": len(raw_rows),
        "excluded_noise": excluded_noise,
        "after_filter": len(kept),
        "split_sources": split_total,
        "enriched_out": len(enriched_out),
        "total_chars": sum(r["char_count"] for r in enriched_out),
    }
    return enriched_out, meta_out, stats


def diff_existing_urls(existing_rows: list[dict], new_urls: set[str]) -> tuple[list[dict], int]:
    """기존 corpus에서 신규 URL과 중복인 chunk 제거."""
    kept = [r for r in existing_rows if r["source_url"] not in new_urls]
    return kept, len(existing_rows) - len(kept)


def backup(path: str) -> str:
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    bak = f"{path}.bak.{ts}"
    shutil.copy2(path, bak)
    return bak


def build_bm25(enriched_rows: list[dict]) -> None:
    """kiwipiepy로 토크나이즈 → BM25 재빌드 → 3파일 생성."""
    from kiwipiepy import Kiwi
    from rank_bm25 import BM25Okapi

    KEEP_POS = {
        "NNG", "NNP", "NNB", "NR", "NP",
        "VV", "VA", "VX", "VCP", "VCN",
        "XR", "SL", "SN", "SH",
    }
    kiwi = Kiwi()

    def tok(text: str) -> list[str]:
        out: list[str] = []
        for t in kiwi.tokenize(text or ""):
            if t.tag in KEEP_POS and t.form:
                f = t.form
                if f.isascii():
                    f = f.lower()
                if len(f) == 1 and t.tag == "SN":
                    continue
                out.append(f)
        return out

    print(f"[bm25] tokenize {len(enriched_rows)} chunks ...")
    t0 = time.time()
    tokenized: list[list[str]] = []
    chunk_ids: list[str] = []
    for i, r in enumerate(enriched_rows):
        toks = tok(r.get("_text_for_bm25") or r.get("text") or "")
        tokenized.append(toks)
        chunk_ids.append(r["chunk_id"])
        if (i + 1) % 500 == 0:
            print(f"  {i+1}/{len(enriched_rows)}  ({time.time()-t0:.1f}s)")
    print(f"[bm25] tokenize done in {time.time()-t0:.1f}s")

    print("[bm25] building BM25Okapi ...")
    t1 = time.time()
    bm25 = BM25Okapi(tokenized)
    print(f"[bm25] build done in {time.time()-t1:.1f}s")

    os.makedirs(BM25_DIR, exist_ok=True)
    # backup old
    pkl = os.path.join(BM25_DIR, "bm25.pkl")
    ids_path = os.path.join(BM25_DIR, "chunk_ids.json")
    tok_path = os.path.join(BM25_DIR, "tokens.jsonl")
    for p in (pkl, ids_path, tok_path):
        if os.path.exists(p):
            backup(p)

    # NOTE: loader 가 d["bm25"] / d["chunk_ids"] 로 읽음. dict로 wrap 필수.
    with open(pkl, "wb") as f:
        pickle.dump({"bm25": bm25, "chunk_ids": chunk_ids}, f)
    with open(ids_path, "w", encoding="utf-8") as f:
        json.dump(chunk_ids, f, ensure_ascii=False)
    with open(tok_path, "w", encoding="utf-8") as f:
        for toks in tokenized:
            f.write(json.dumps(toks, ensure_ascii=False) + "\n")
    print(f"[bm25] wrote {pkl}")
    print(f"[bm25] wrote {ids_path}")
    print(f"[bm25] wrote {tok_path}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-bm25", action="store_true", help="BM25 재빌드 건너뛰기 (랩실/Colab에서 수행)")
    args = ap.parse_args()

    print(f"=== loading new raw chunks: {RAW}")
    raw = load_jsonl(RAW)
    print(f"  raw: {len(raw)}")

    print(f"=== loading existing enriched: {ENRICHED}")
    enr_exist = load_jsonl(ENRICHED)
    print(f"  existing enriched: {len(enr_exist)}")

    print(f"=== loading existing meta: {META}")
    meta_exist = load_jsonl(META)
    print(f"  existing meta: {len(meta_exist)}")

    new_enr, new_meta, stats = process_new_chunks(raw)
    print(f"\n=== process stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    new_urls = {r["source_url"] for r in new_enr}
    enr_after, removed_e = diff_existing_urls(enr_exist, new_urls)
    meta_after, removed_m = diff_existing_urls(meta_exist, new_urls)
    print(f"\n=== URL 중복 제거 ===")
    print(f"  enriched: {len(enr_exist)} -> {len(enr_after)} (removed {removed_e})")
    print(f"  meta:     {len(meta_exist)} -> {len(meta_after)} (removed {removed_m})")

    final_enr = enr_after + new_enr
    final_meta = meta_after + new_meta
    print(f"\n=== 최종 ===")
    print(f"  enriched: {len(final_enr)} chunks")
    print(f"  meta:     {len(final_meta)} chunks")
    # label dist 변화
    dist = Counter(r.get("label_5way") for r in final_enr)
    print(f"  label_5way dist: {dict(dist)}")

    # 학과 도메인 chunk 변화
    DEPT_DOMS = ['computer.cnu.ac.kr','me.cnu.ac.kr','medicine.cnu.ac.kr','pharm.cnu.ac.kr','nursing.cnu.ac.kr','ee.cnu.ac.kr','ceac.cnu.ac.kr','math.cnu.ac.kr','stat.cnu.ac.kr','physics.cnu.ac.kr']
    dept_old = sum(1 for r in enr_exist if any(d in r['source_url'] for d in DEPT_DOMS))
    dept_new = sum(1 for r in final_enr if any(d in r['source_url'] for d in DEPT_DOMS))
    print(f"  10-dept chunks: {dept_old} -> {dept_new}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일 쓰기 생략. --dry-run 빼고 다시 실행.")
        return 0

    print(f"\n=== backup ===")
    print(f"  {backup(ENRICHED)}")
    print(f"  {backup(META)}")

    print(f"=== write enriched + meta ===")
    write_jsonl(ENRICHED, final_enr)
    write_jsonl(META, final_meta)
    print(f"  wrote {ENRICHED}")
    print(f"  wrote {META}")

    if args.no_bm25:
        print("\n[no-bm25] BM25 재빌드 생략. 랩실 GPU 또는 Colab에서 수행.")
        return 0

    print(f"\n=== BM25 rebuild ===")
    build_bm25(final_enr)
    print("\n✅ 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
