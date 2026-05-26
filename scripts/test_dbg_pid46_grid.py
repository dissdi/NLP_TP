"""scripts/test_dbg_pid46_grid.py — paramItemId=46의 grid 상세 진단.

raw XML 저장 + grid 행별 비어있지 않은 셀 개수/내용 출력.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from crawler.adapters.f_ubireport import UbiReportAdapter, parse_xml, build_grid


def main():
    pid = "46"
    print(f"=== diagnose pid={pid} ===")
    with UbiReportAdapter(headless=True) as a:
        r = a.fetch_report("0000029", pid, "2025", label="졸업생의 취업 현황")

    # raw XML 파일 저장
    save_dir = ROOT / "data" / "spike_ubireport"
    save_dir.mkdir(parents=True, exist_ok=True)
    xml_path = save_dir / f"pid{pid}_raw.xml"
    xml_path.write_text(r.raw_xml, encoding="utf-8")
    print(f"raw XML saved: {xml_path}  ({len(r.raw_xml):,}B)")

    if not r.raw_xml:
        print(f"errors: {r.errors}")
        return

    # 단일 page 처리 (어댑터 기본)
    cells = r.cells
    grid = r.grid
    print(f"\ncells: {len(cells)}, grid: {len(grid)}r x {len(grid[0]) if grid else 0}c")
    print(f"current header_idx={r.header_idx}")
    print(f"current header: {r.header}")

    # 모든 행의 non-empty 셀 갯수와 첫 6개 텍스트
    print(f"\n=== all grid rows ===")
    for i, row in enumerate(grid):
        non_empty = [v for v in row if v.strip()]
        if not non_empty:
            continue
        preview = [v.replace("\n", "↵")[:25] for v in non_empty[:6]]
        print(f"  row{i:>3d}: {len(non_empty):>3d}ne | {preview}")

    # 헤더 후보 검출: '학과' 또는 '졸업자' 포함된 행 모두 출력
    print(f"\n=== header candidates (포함: '학과명' or '졸업자' 등) ===")
    KW_LOOSE = ("학과", "졸업자", "취업자", "취업률", "기준", "단과대")
    for i, row in enumerate(grid):
        hits = [v for v in row if any(kw in v for kw in KW_LOOSE)]
        if len(hits) >= 2:
            preview = [v.replace("\n", "↵")[:20] for v in row if v.strip()]
            print(f"  row{i:>3d}: hits={len(hits)} | {preview[:8]}")


if __name__ == "__main__":
    main()
