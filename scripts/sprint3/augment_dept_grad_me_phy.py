"""me + physics 재크롤 chunks → 16-필드 정규화 + 기존 corpus append + BM25 재빌드.

augment_dept_grad.py 의 me/phy 전용 fork. 차이점만 override:
  - RAW: data/sprint3/dept_grad_me_phy/chunks_raw.jsonl
  - notes 마커: dept_grad_me_phy
  - 기타 정책(1500/200 sliding, articleNo 제외, URL 중복 시 기존 chunk 제거)은 동일

사용:
  python -m scripts.sprint3.augment_dept_grad_me_phy --dry-run   # 미리보기
  python -m scripts.sprint3.augment_dept_grad_me_phy             # 실행 + BM25 재빌드
  python -m scripts.sprint3.augment_dept_grad_me_phy --no-bm25   # 파일만 쓰고 BM25 는 GPU 환경에서
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from scripts.sprint3 import augment_dept_grad as base  # noqa: E402

# Override paths
RAW = os.path.join(_ROOT, "data", "sprint3", "dept_grad_me_phy", "chunks_raw.jsonl")
ENRICHED = base.ENRICHED
META = base.META
BM25_DIR = base.BM25_DIR

DEPT_DOMS_ME_PHY = ["me.cnu.ac.kr", "physics.cnu.ac.kr"]


def patch_notes(rows: list[dict]) -> None:
    """notes 마커를 dept_grad_me_phy 로 교체."""
    for r in rows:
        n = r.get("notes") or ""
        if "dept_grad_10" in n:
            r["notes"] = n.replace("dept_grad_10", "dept_grad_me_phy")
        elif not n:
            r["notes"] = "dept_grad_me_phy"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-bm25", action="store_true",
                    help="BM25 재빌드 건너뛰기 (랩실/Colab에서 수행)")
    args = ap.parse_args()

    print(f"=== loading new raw chunks: {RAW}")
    raw = base.load_jsonl(RAW)
    print(f"  raw: {len(raw)}")

    if not raw:
        print("⚠ raw chunks 0건. me/physics 재크롤이 실패한 것 같음.")
        print("  dept_list_me_phy.json 의 direct_url 들을 사이트맵에서 직접 찾아 교체 후 재시도.")
        return 1

    print(f"=== loading existing enriched: {ENRICHED}")
    enr_exist = base.load_jsonl(ENRICHED)
    print(f"  existing enriched: {len(enr_exist)}")

    print(f"=== loading existing meta: {META}")
    meta_exist = base.load_jsonl(META)
    print(f"  existing meta: {len(meta_exist)}")

    new_enr, new_meta, stats = base.process_new_chunks(raw)
    patch_notes(new_enr)
    patch_notes(new_meta)

    print("\n=== process stats ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # 추가: 학과별 신규 chunk 분포
    by_dom = Counter()
    for r in new_enr:
        for d in DEPT_DOMS_ME_PHY:
            if d in r["source_url"]:
                by_dom[d] += 1
                break
    print("  new chunks by dept:")
    for d in DEPT_DOMS_ME_PHY:
        print(f"    {d}: {by_dom.get(d, 0)}")

    new_urls = {r["source_url"] for r in new_enr}
    enr_after, removed_e = base.diff_existing_urls(enr_exist, new_urls)
    meta_after, removed_m = base.diff_existing_urls(meta_exist, new_urls)
    print("\n=== URL 중복 제거 (기존 corpus에서 신규 URL과 겹치는 chunk 삭제) ===")
    print(f"  enriched: {len(enr_exist)} -> {len(enr_after)} (removed {removed_e})")
    print(f"  meta:     {len(meta_exist)} -> {len(meta_after)} (removed {removed_m})")

    final_enr = enr_after + new_enr
    final_meta = meta_after + new_meta
    print("\n=== 최종 ===")
    print(f"  enriched: {len(final_enr)} chunks")
    print(f"  meta:     {len(final_meta)} chunks")
    dist = Counter(r.get("label_5way") for r in final_enr)
    print(f"  label_5way dist: {dict(dist)}")

    me_old = sum(1 for r in enr_exist if "me.cnu.ac.kr" in r["source_url"])
    me_new = sum(1 for r in final_enr if "me.cnu.ac.kr" in r["source_url"])
    phy_old = sum(1 for r in enr_exist if "physics.cnu.ac.kr" in r["source_url"])
    phy_new = sum(1 for r in final_enr if "physics.cnu.ac.kr" in r["source_url"])
    print(f"  me.cnu.ac.kr chunks:      {me_old} -> {me_new}")
    print(f"  physics.cnu.ac.kr chunks: {phy_old} -> {phy_new}")

    if args.dry_run:
        print("\n[DRY-RUN] 파일 쓰기 생략. --dry-run 빼고 다시 실행.")
        return 0

    print("\n=== backup ===")
    print(f"  {base.backup(ENRICHED)}")
    print(f"  {base.backup(META)}")

    print("=== write enriched + meta ===")
    base.write_jsonl(ENRICHED, final_enr)
    base.write_jsonl(META, final_meta)
    print(f"  wrote {ENRICHED}")
    print(f"  wrote {META}")

    if args.no_bm25:
        print("\n[no-bm25] BM25 재빌드 생략. 랩실 GPU 또는 Colab에서 수행.")
        return 0

    print("\n=== BM25 rebuild ===")
    base.build_bm25(final_enr)
    print("\n✅ 완료.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
