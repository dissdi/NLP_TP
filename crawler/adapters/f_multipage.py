"""crawler/adapters/f_multipage.py — UbiReport multi-page XML 처리 helper.

f_ubireport.py의 parse_xml은 모든 <Page>의 셀을 한 리스트로 합쳐서
build_grid에 넘기는데, 페이지마다 같은 (x, y) 좌표를 쓰는 보고서(예:
pagecount=7인 paramItemId=46)는 그리드가 깨짐.

여기서는 페이지별로 cells를 분리 추출 → 페이지별 build_grid →
페이지별 records 추출 후 모두 합침.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from typing import Optional

from crawler.adapters.f_ubireport import (
    Cell,
    ReportMeta,
    ParsedReport,
    build_grid,
    detect_header,
    grid_to_records,
    parse_xml,  # 메타 추출용
)


def parse_xml_per_page(xml_text: str) -> list[list[Cell]]:
    """페이지별 cells 분리."""
    xml_text = xml_text.lstrip("﻿").strip()
    root = ET.fromstring(xml_text)
    pages_cells: list[list[Cell]] = []
    for page in root.iter("Page"):
        cells: list[Cell] = []
        for item in page.iter("Item"):
            if item.get("classname") != "UbiTextItem":
                continue
            try:
                cells.append(
                    Cell(
                        x=int(item.get("x", "0")),
                        y=int(item.get("y", "0")),
                        w=int(item.get("width", "0")),
                        h=int(item.get("height", "0")),
                        text=(
                            (item.find("Text").text or "").strip()
                            if item.find("Text") is not None
                            else ""
                        ),
                        forecolor=item.get("forecolorid", ""),
                        backcolor=item.get("backcolorid", ""),
                    )
                )
            except (ValueError, AttributeError):
                continue
        pages_cells.append(cells)
    return pages_cells


def enrich_report_multipage(report: ParsedReport) -> ParsedReport:
    """기존 ParsedReport의 raw_xml을 페이지별로 다시 처리하여
    records를 모든 페이지에서 합친 결과로 갱신.

    어댑터 fetch_report 직후 이 함수에 통과시키면 multi-page 보고서도
    완전한 records 추출됨. 기존 cells/grid/header는 첫 페이지 기준 유지.
    """
    if not report.raw_xml:
        return report
    try:
        pages_cells = parse_xml_per_page(report.raw_xml)
    except ET.ParseError as e:
        report.errors.append(f"multipage parse error: {e}")
        return report

    report.n_pages = len(pages_cells)
    all_cells: list[Cell] = []
    all_records: list[dict] = []
    first_grid: list[list[str]] = []
    first_hi: int = -1
    first_header: list[str] = []

    for pi, pc in enumerate(pages_cells):
        if not pc:
            continue
        all_cells.extend(pc)
        grid = build_grid(pc)
        hi = detect_header(grid, pc)
        recs = grid_to_records(grid, hi)
        all_records.extend(recs)
        if pi == 0:
            first_grid = grid
            first_hi = hi
            first_header = grid[hi] if 0 <= hi < len(grid) else []

    report.cells = all_cells
    report.grid = first_grid
    report.header_idx = first_hi
    report.header = first_header
    report.records = all_records
    return report
