"""scripts/sprint3_dstat_collect.py — Sprint 3 D-통계 일괄 수집.

Phase B Sprint 2에서 sparse로 남겨졌던 D-통계 13문제 영역을 알리미 UbiReport
어댑터(crawler.adapters.f_ubireport)로 자동 수집.

D-통계 13문제 매핑 (coverage-plan.md §5 + spike_almi_ubireport list_page.html 스캔):
  학사 5문제 (신입생 등):       paramItemId 27, 29, 30, 31, 37
  기숙사 3문제 (생활관):         paramItemId 193, 262, 266, 278
  진로·취업 5문제 (취업률 등):    paramItemId 39, 46, 290

대상 연도: 2025 (최신). 필요 시 2024/2023도 추가 수집.

사용:
  python scripts/sprint3_dstat_collect.py             # 모든 target 수집 (rate-limit 적용)
  python scripts/sprint3_dstat_collect.py --dry-run   # 매핑 출력만
  python scripts/sprint3_dstat_collect.py --pid 46    # 특정 paramItemId만
  python scripts/sprint3_dstat_collect.py --year 2024 # 다른 연도

산출물:
  data/sprint3/dstat/{schl_id}_pid{N}_{year}.xml         원본 XML
  data/sprint3/dstat/{schl_id}_pid{N}_{year}.csv         표 (Excel 호환)
  data/sprint3/dstat/{schl_id}_pid{N}_{year}_records.json  레코드 리스트
  data/sprint3/dstat/chunks.jsonl                          RAG 청크 (Phase C 입력)
  data/sprint3/dstat/manifest.json                         수집 요약
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# 어댑터 import
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from crawler.adapters.f_ubireport import (  # noqa: E402
    UbiReportAdapter,
    records_to_chunks,
    ButtonInfo,
)


# ============================================================================
# D-통계 13문제 매핑 (coverage-plan.md §5)
# ============================================================================
SCHL_ID = "0000029"  # 충남대
DEFAULT_YEAR = "2025"

# 각 target: (domain, category, paramItemId, label_hint)
# label_hint는 list 페이지 스캔 결과로 자동 보강됨
DSTAT_TARGETS: list[dict] = [
    # 학사 (도메인 1) — 5문제: 신입생/충원/재적/출신고교
    {"domain": 1, "category": "1.7", "pid": "27", "hint": "신입생 충원 현황"},
    {"domain": 1, "category": "1.7", "pid": "29", "hint": "학생 충원 현황(편입학 포함)"},
    {"domain": 1, "category": "1.7", "pid": "30", "hint": "학생 충원 현황(편입학 포함)"},
    {"domain": 1, "category": "1.7", "pid": "31", "hint": "재적 학생 현황"},
    {"domain": 1, "category": "1.7", "pid": "37", "hint": "신입생 출신 고등학교 유형별"},
    # 기숙사 (도메인 4) — 3문제: 생활관 현황
    {"domain": 4, "category": "4.3", "pid": "193", "hint": "기숙사 현황"},
    {"domain": 4, "category": "4.3", "pid": "262", "hint": "기숙사 현황"},
    {"domain": 4, "category": "4.3", "pid": "266", "hint": "기숙사 현황"},
    {"domain": 4, "category": "4.3", "pid": "278", "hint": "기숙사 현황"},
    # 진로·취업 (도메인 7) — 5문제: 졸업생/취업/진학
    {"domain": 7, "category": "7.5", "pid": "39", "hint": "졸업생 현황"},
    {"domain": 7, "category": "7.5", "pid": "46", "hint": "졸업생의 취업 현황"},
    {"domain": 7, "category": "7.5", "pid": "290", "hint": "졸업생의 진학 현황"},
]

# 추가: D-통계 외에도 알리미가 가진 풍부한 통계가 있으니, 보너스로 수집할 ID
# (사용자 결정 — 일단 D-통계만, 더 필요하면 BONUS_TARGETS 풀어쓰기)
BONUS_TARGETS: list[dict] = []


# ============================================================================
# 보조 함수
# ============================================================================
def find_label(buttons: list[ButtonInfo], pid: str, year: str) -> str:
    """list 스캔 결과에서 (pid, year)에 매칭되는 라벨 찾기."""
    for b in buttons:
        if b.param_item_id == pid and b.year == year:
            return b.label
    # 같은 pid의 다른 year라도 있으면 그 라벨 사용 (라벨은 보통 연도 무관)
    for b in buttons:
        if b.param_item_id == pid:
            return b.label
    return ""


# ============================================================================
# 메인
# ============================================================================
def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--year", default=DEFAULT_YEAR, help="조사연도 (기본 2025)")
    p.add_argument("--pid", help="특정 paramItemId만 수집 (콤마 구분 가능)")
    p.add_argument("--dry-run", action="store_true", help="매핑 출력만")
    p.add_argument("--sleep", type=float, default=3.0, help="요청 사이 sleep 초 (기본 3.0)")
    p.add_argument("--out-dir", default="data/sprint3/dstat")
    p.add_argument("--no-scan", action="store_true", help="list 페이지 스캔 생략 (라벨 hint 사용)")
    args = p.parse_args()

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    # target 필터
    targets = DSTAT_TARGETS + BONUS_TARGETS
    if args.pid:
        wanted = set(args.pid.split(","))
        filtered = [t for t in targets if t["pid"] in wanted]
        # 매핑에 없는 pid도 ad-hoc target으로 허용 (디버그용)
        mapped_pids = {t["pid"] for t in filtered}
        for w in wanted:
            if w not in mapped_pids:
                # domain=9 (캠퍼스·시설, valid 범위 1~9 안에서 안전한 catch-all)
                filtered.append({"domain": 9, "category": "adhoc", "pid": w, "hint": f"ad-hoc pid={w}"})
        targets = filtered
    if not targets:
        print("[FATAL] no targets to collect")
        return 2

    print(f"=== Sprint 3 D-통계 수집 ===")
    print(f"schl_id={SCHL_ID} year={args.year} targets={len(targets)}")
    for t in targets:
        print(f"  D{t['domain']} cat={t['category']} pid={t['pid']:>3s}  {t['hint']}")

    if args.dry_run:
        print("\n(dry-run) 종료")
        return 0

    # ---------------------------------------------------------------
    # Playwright Adapter 실행
    # ---------------------------------------------------------------
    manifest = {
        "schl_id": SCHL_ID,
        "year": args.year,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "targets": targets,
        "results": [],
    }
    all_chunks = []

    with UbiReportAdapter(headless=True) as adapter:
        # 1) list 페이지 스캔 (라벨 보강)
        buttons: list[ButtonInfo] = []
        if not args.no_scan:
            print(f"\n[1] Scanning list page (학교 {SCHL_ID}, year {args.year}) ...")
            try:
                buttons = adapter.scan_list_page(SCHL_ID, args.year)
                print(f"    found {len(buttons)} buttons")
                # 저장
                (out_dir / "_list_scan.json").write_text(
                    json.dumps([asdict(b) for b in buttons], ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception as e:
                print(f"    [WARN] scan failed: {e}")

        # 2) 각 target 수집
        for ti, t in enumerate(targets, 1):
            pid = t["pid"]
            domain = t["domain"]
            category = t["category"]
            label = find_label(buttons, pid, args.year) or t["hint"]

            print(f"\n[{ti}/{len(targets)}] fetch D{domain} pid={pid} year={args.year}")
            print(f"    label: {label}")

            try:
                report = adapter.fetch_report(SCHL_ID, pid, args.year, label=label)
            except Exception as e:
                print(f"    [ERROR] fetch exception: {e}")
                manifest["results"].append({
                    "pid": pid, "year": args.year, "domain": domain, "category": category,
                    "label": label, "ok": False, "error": str(e),
                })
                continue

            print(f"    xml={len(report.raw_xml):,}B cells={len(report.cells)} "
                  f"grid={len(report.grid)}r×{len(report.grid[0]) if report.grid else 0}c "
                  f"records={len(report.records)} errors={len(report.errors)}")

            # 저장
            stem = f"{SCHL_ID}_pid{pid}_{args.year}"
            if report.raw_xml:
                (out_dir / f"{stem}.xml").write_text(report.raw_xml, encoding="utf-8")
            if report.records:
                (out_dir / f"{stem}_records.json").write_text(
                    json.dumps(report.records, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                # CSV (Excel 호환)
                import csv
                with (out_dir / f"{stem}.csv").open("w", encoding="utf-8-sig", newline="") as f:
                    w = csv.writer(f)
                    for row in report.grid:
                        w.writerow(row)

            # Chunk 변환
            chunks = records_to_chunks(report, domain=domain, category=category)
            print(f"    → {len(chunks)} chunks (RAG-ready)")
            all_chunks.extend(chunks)

            manifest["results"].append({
                "pid": pid, "year": args.year, "domain": domain, "category": category,
                "label": label, "ok": bool(report.records) and not report.errors,
                "n_cells": len(report.cells), "n_records": len(report.records),
                "n_chunks": len(chunks), "title": report.meta.title,
                "errors": report.errors,
            })

            # rate limit
            if ti < len(targets):
                time.sleep(args.sleep)

    # ---------------------------------------------------------------
    # 결과 저장
    # ---------------------------------------------------------------
    manifest["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["n_chunks_total"] = len(all_chunks)
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # chunks.jsonl (Phase C 입력 호환)
    chunks_path = out_dir / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(asdict(ch), ensure_ascii=False) + "\n")

    print(f"\n=== 수집 완료 ===")
    print(f"  total chunks: {len(all_chunks)}")
    ok_count = sum(1 for r in manifest["results"] if r["ok"])
    print(f"  success: {ok_count}/{len(targets)}")
    print(f"  manifest: {out_dir / 'manifest.json'}")
    print(f"  chunks:   {chunks_path}")

    return 0 if ok_count == len(targets) else 1

if __name__ == "__main__":
    sys.exit(main() or 0)
