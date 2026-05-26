"""scripts/test_multipage_pid46.py — multi-page 처리 후 paramItemId=46 records 확인."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.adapters.f_ubireport import UbiReportAdapter
from crawler.adapters.f_multipage import enrich_report_multipage


def main():
    targets = [
        ("9", "baseline pagecount=1"),
        ("46", "졸업생 취업 현황 pagecount=7"),
    ]
    for pid, note in targets:
        print(f"\n{'=' * 50}")
        print(f"=== pid={pid} : {note} ===")
        with UbiReportAdapter(headless=True) as a:
            r = a.fetch_report("0000029", pid, "2025", label=note)
        # 어댑터 결과 (단일 페이지 처리)
        before_records = len(r.records)
        before_cells = len(r.cells)
        # multi-page enrich
        enrich_report_multipage(r)
        print(f"  raw_xml: {len(r.raw_xml):,}B  n_pages: {r.n_pages}")
        print(f"  cells:   {before_cells} (단일) → {len(r.cells)} (multi)")
        print(f"  records: {before_records} (단일) → {len(r.records)} (multi)")
        print(f"  errors:  {r.errors}")
        if r.records:
            print(f"  first record:  {r.records[0]}")
            print(f"  last record:   {r.records[-1]}")
        # 학과 unique 카운트 (취업 보고서일 경우)
        depts = set()
        for rec in r.records:
            d = rec.get("학과명", "").strip()
            if d:
                depts.add(d)
        if depts:
            print(f"  unique 학과명 count: {len(depts)} (sample 5: {sorted(depts)[:5]})")


if __name__ == "__main__":
    main()
