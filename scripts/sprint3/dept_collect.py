"""scripts/sprint3_dept_collect.py — 학과정보 일괄 수집 (Sprint 3, D-통계 cover).

알리미 학과정보 진입점 (pubinfo0081) JSON API로 충남대 학과 104개 × 8 통계
일괄 수집. UbiReport viewer 우회, requests 기반 빠른 fetch.

D-통계 13문제 매핑:
  학사 5문제   → v1(신입생경쟁률) + v2(재학생수) + v4(입학정원)
  진로·취업 5문제 → v7(취업률)
  기숙사 3문제 → sprint3_dstat_collect.py로 별도 수집 (학교 단위)

산출물:
  data/sprint3/dept_info/{flag}_{svyYr}_all.json  flag별 모든 학과 통계
  data/sprint3/dept_info/dept_list_{svyYr}.json   학과 메타
  data/sprint3/dept_info/chunks.jsonl             RAG 청크 (Phase C 입력)
  data/sprint3/dept_info/manifest.json            수집 요약
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.adapters.g_dept_info import (  # noqa: E402
    DeptInfoAdapter, STAT_FLAGS, stat_to_chunks, DeptMeta, DeptStat,
)


SCHL_ID = "0000029"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--svy-yr", default="2026", help="조사연도 (기본 2026 - 최신 공시)")
    p.add_argument("--flags", default=None, help="수집할 flag (콤마, 기본 v1~v8)")
    p.add_argument("--limit", type=int, default=None, help="학과 N개만 시도 (디버그)")
    p.add_argument("--sleep", type=float, default=0.5)
    p.add_argument("--out-dir", default="data/sprint3/dept_info")
    args = p.parse_args()

    flags = args.flags.split(",") if args.flags else list(STAT_FLAGS.keys())
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"=== Sprint 3 학과정보 수집 ===")
    print(f"  schl_id={SCHL_ID}  svy_yr={args.svy_yr}")
    print(f"  flags={flags}")

    adapter = DeptInfoAdapter(schl_id=SCHL_ID, sleep_between=args.sleep)

    # 1) 학과 목록
    print(f"\n[1] selectMjrList.do (학과 메타)")
    depts = adapter.list_depts(svy_yr=args.svy_yr)
    if args.limit:
        depts = depts[:args.limit]
    print(f"  → {len(depts)} 학과")
    # 저장
    (out_dir / f"dept_list_{args.svy_yr}.json").write_text(
        json.dumps([asdict(d) for d in depts], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2) 각 학과 × 각 flag
    print(f"\n[2] fetch stats: {len(depts)} 학과 × {len(flags)} flag = "
          f"{len(depts)*len(flags)} 호출")
    all_stats: list[DeptStat] = []
    manifest = {
        "schl_id": SCHL_ID, "svy_yr": args.svy_yr, "flags": flags,
        "n_depts": len(depts),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "by_flag": {},
        "errors": [],
    }
    for di, dept in enumerate(depts, 1):
        for fi, flag in enumerate(flags, 1):
            stat = adapter.fetch_stat(dept, flag, svy_yr=args.svy_yr)
            all_stats.append(stat)
            if stat.error:
                manifest["errors"].append({
                    "dept": dept.mjr_nm, "flag": flag, "error": stat.error
                })
            if di % 10 == 0 and fi == 1:
                print(f"  [{di}/{len(depts)}] {dept.mjr_nm:20s} "
                      f"({sum(1 for s in all_stats if s.entries)} succ)")
            time.sleep(args.sleep)

    # 3) flag별 통계 정리
    print(f"\n[3] aggregate by flag")
    for flag in flags:
        flag_stats = [s for s in all_stats if s.flag == flag]
        non_empty = [s for s in flag_stats if s.entries]
        manifest["by_flag"][flag] = {
            "name": STAT_FLAGS.get(flag, {}).get("name", flag),
            "n_depts_attempted": len(flag_stats),
            "n_depts_with_data": len(non_empty),
        }
        # flag별 모든 학과 통계 저장 (entries 포함)
        flag_data = []
        for s in non_empty:
            flag_data.append({
                "dept": asdict(s.dept),
                "stat_name": s.stat_name,
                "svy_yr": s.svy_yr,
                "entries": s.entries,
            })
        (out_dir / f"{flag}_{args.svy_yr}_all.json").write_text(
            json.dumps(flag_data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  {flag} {STAT_FLAGS.get(flag, {}).get('name', flag):20s}: "
              f"{len(non_empty)}/{len(flag_stats)} 학과 데이터 OK")

    # 4) Chunks 변환
    print(f"\n[4] Chunk 변환")
    all_chunks = []
    for s in all_stats:
        all_chunks.extend(stat_to_chunks(s))
    print(f"  total chunks: {len(all_chunks)}")
    chunks_path = out_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(asdict(ch), ensure_ascii=False) + "\n")

    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["n_chunks_total"] = len(all_chunks)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n=== 완료 ===")
    print(f"  학과: {len(depts)}")
    print(f"  통계: {len(all_stats)} 호출 (성공 {sum(1 for s in all_stats if s.entries)})")
    print(f"  청크: {len(all_chunks)}")
    print(f"  manifest: {out_dir / 'manifest.json'}")
    print(f"  chunks:   {chunks_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
