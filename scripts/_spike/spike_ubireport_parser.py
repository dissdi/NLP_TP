"""
scripts/spike_ubireport_parser.py
UbiReport XML → 표(rows×cols) 재구성 PoC

목적
----
spike_almi_ubireport.py가 캡쳐한 newacinfo_*.xml 파일의
<Item classname="UbiTextItem" x= y= width= height=> 셀들을
좌표 기반으로 그룹화하여 사람이 읽기 좋은 표/JSON으로 변환.

UbiReport는 merge cell을 좌표(width/height)로 표현 ─ 일반 셀보다
큰 height/width를 가진 셀이 여러 행/열을 차지한다.

성공 기준
---------
- 파싱된 셀 개수 == XML 내 UbiTextItem 개수
- 헤더 행이 첫 번째 행으로 분리됨
- "충남대학교" / "경상대학" / "경제학과" 등 알려진 데이터가 정상 텍스트로 추출됨
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterator
import xml.etree.ElementTree as ET


@dataclass
class Cell:
    x: int
    y: int
    w: int
    h: int
    text: str
    forecolor: str = ""
    backcolor: str = ""


def parse_xml(xml_text: str) -> list[Cell]:
    """UbiReport XML 파싱 → Cell 리스트."""
    # UbiReport 응답은 BOM이나 prolog 문제가 있을 수 있어 약간 정리
    xml_text = xml_text.lstrip("﻿").strip()
    root = ET.fromstring(xml_text)
    cells: list[Cell] = []
    for page in root.iter("Page"):
        for item in page.iter("Item"):
            if item.get("classname") != "UbiTextItem":
                continue
            try:
                x = int(item.get("x", "0"))
                y = int(item.get("y", "0"))
                w = int(item.get("width", "0"))
                h = int(item.get("height", "0"))
            except ValueError:
                continue
            text_el = item.find("Text")
            text = (text_el.text or "").strip() if text_el is not None else ""
            cells.append(
                Cell(
                    x=x, y=y, w=w, h=h, text=text,
                    forecolor=item.get("forecolorid", ""),
                    backcolor=item.get("backcolorid", ""),
                )
            )
    return cells


def detect_grid(cells: list[Cell]) -> tuple[list[int], list[int]]:
    """
    셀들의 (x, y, x+w, y+h) 좌표에서 고유 grid line 추출.
    표의 열 경계와 행 경계를 결정한다.
    """
    xs = set()
    ys = set()
    for c in cells:
        xs.add(c.x)
        xs.add(c.x + c.w)
        ys.add(c.y)
        ys.add(c.y + c.h)
    return sorted(xs), sorted(ys)


def build_table(cells: list[Cell]) -> list[list[str]]:
    """
    좌표 기반 표 재구성.
    각 grid 셀(x_i ~ x_{i+1}, y_j ~ y_{j+1})에 해당하는
    UbiTextItem 셀의 텍스트를 채워넣음. merge cell 자연 처리.
    """
    if not cells:
        return []
    xs, ys = detect_grid(cells)
    n_rows = len(ys) - 1
    n_cols = len(xs) - 1
    grid: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]

    # 각 grid 셀의 중점을 포함하는 UbiTextItem 찾기
    for j in range(n_rows):
        y_mid = (ys[j] + ys[j + 1]) / 2
        for i in range(n_cols):
            x_mid = (xs[i] + xs[i + 1]) / 2
            # 이 좌표를 포함하는 셀 (가장 좌상단이 작은 = 가장 큰 merge cell 우선)
            covering = [
                c for c in cells
                if c.x <= x_mid < c.x + c.w and c.y <= y_mid < c.y + c.h
            ]
            if covering:
                # 좌상단 좌표가 정확히 (xs[i], ys[j])인 셀이 있으면 그것 (정확 매칭)
                exact = [c for c in covering if c.x == xs[i] and c.y == ys[j]]
                chosen = exact[0] if exact else min(covering, key=lambda c: (c.y, c.x))
                grid[j][i] = chosen.text
    return grid


def detect_header_row(grid: list[list[str]]) -> int:
    """
    헤더 행 인덱스 추정.
    UbiReport는 보통 헤더가 backcolor != 1(흰색)으로 표시되지만
    여기선 단순히 "기준연도/학교명/학과명" 같은 키워드로 판정.
    """
    header_kws = {"기준연도", "학교명", "학과", "단과대학", "구분", "연도", "항목"}
    for i, row in enumerate(grid):
        if sum(1 for c in row if c in header_kws) >= 2:
            return i
    return 0


def grid_to_records(grid: list[list[str]], header_idx: int = 0) -> list[dict]:
    """
    헤더 + 데이터 행을 dict 레코드로 변환.
    merge cell로 같은 텍스트가 여러 행에 반복되는 케이스 그대로 둠 (원본 보존).
    """
    if not grid or header_idx >= len(grid):
        return []
    header = grid[header_idx]
    # 빈 헤더는 무시
    records = []
    for row in grid[header_idx + 1:]:
        rec = {}
        for h, v in zip(header, row):
            if h:
                rec[h] = v
        # 모두 빈 값인 행 제외
        if any(rec.values()):
            records.append(rec)
    return records


# ----------------------------------------------------------------------------
# 실행
# ----------------------------------------------------------------------------
def main() -> int:
    root = Path(__file__).resolve().parent.parent
    spike_dir = root / "data" / "spike_ubireport"
    xml_files = sorted(spike_dir.glob("newacinfo_*.xml"))
    if not xml_files:
        print(f"[FATAL] no newacinfo_*.xml in {spike_dir}")
        print(f"        run spike_almi_ubireport.py first")
        return 2

    for xml_path in xml_files:
        size = xml_path.stat().st_size
        if size < 500:
            print(f"\n=== {xml_path.name} (size={size}B, skipped: too small) ===")
            continue

        print(f"\n=== {xml_path.name} (size={size:,}B) ===")
        xml_text = xml_path.read_text(encoding="utf-8")

        # 빠른 정합성 체크
        n_items_raw = xml_text.count('<Item classname="UbiTextItem"')
        try:
            cells = parse_xml(xml_text)
        except ET.ParseError as e:
            print(f"  [PARSE ERROR] {e}")
            # 시작 100자 출력
            print(f"  start: {xml_text[:200]!r}")
            continue

        print(f"  UbiTextItem cells (raw count vs parsed): {n_items_raw} vs {len(cells)}")
        if len(cells) != n_items_raw:
            print(f"  [WARN] count mismatch")

        # grid 추출
        xs, ys = detect_grid(cells)
        print(f"  grid: {len(xs)} x-lines, {len(ys)} y-lines → max {len(xs)-1} cols × {len(ys)-1} rows")

        # 표 재구성
        grid = build_table(cells)
        header_idx = detect_header_row(grid)
        print(f"  estimated header row index: {header_idx}")
        if header_idx < len(grid):
            print(f"  header preview: {grid[header_idx][:12]}")
        # 처음 3 데이터 행 미리보기
        print(f"  first 3 data rows:")
        for i, row in enumerate(grid[header_idx + 1 : header_idx + 4]):
            non_empty = [(j, v) for j, v in enumerate(row) if v]
            print(f"    row {i}: {non_empty[:8]}")

        # 레코드 변환
        records = grid_to_records(grid, header_idx)
        print(f"  records extracted: {len(records)}")
        if records:
            print(f"  first record: {records[0]}")

        # 결과 저장
        out_csv = spike_dir / xml_path.name.replace(".xml", ".csv")
        out_json = spike_dir / xml_path.name.replace(".xml", "_records.json")
        # CSV
        import csv as csv_mod
        with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv_mod.writer(f)
            for row in grid:
                w.writerow(row)
        # JSON records
        out_json.write_text(
            json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"  saved: {out_csv.name}, {out_json.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
