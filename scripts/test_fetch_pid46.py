"""scripts/test_fetch_pid46.py - paramItemId=46 진단 단독 스크립트.

sprint3_dstat_collect.py에 의존하지 않고 어댑터 fetch_report만 직접 호출.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.adapters.f_ubireport import UbiReportAdapter


def main():
    targets = [
        ("9", "paramItemId=9 baseline (PoC success)"),
        ("46", "paramItemId=46 D-통계 (졸업생 취업 현황)"),
    ]
    for pid, note in targets:
        print(f"\n{'=' * 50}")
        print(f"=== pid={pid} : {note} ===")
        with UbiReportAdapter(headless=True) as a:
            r = a.fetch_report("0000029", pid, "2025", label=note)
        print(f"  raw_xml: {len(r.raw_xml):,} B")
        print(f"  cells:   {len(r.cells)}")
        print(f"  records: {len(r.records)}")
        print(f"  errors:  {r.errors}")
        if r.raw_xml:
            print(f"  xml head: {r.raw_xml[:200]!r}")


if __name__ == "__main__":
    main()
