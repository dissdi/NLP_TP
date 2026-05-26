"""PDF 파이프라인 — 텍스트 + 표 추출.

§8-4 결정: pdfplumber 기반.
T3 (PDF 문서) + T6 (표/구조화 데이터) 동시 처리.

검증 기준 (§8-4):
  - 텍스트 추출: pdfplumber.pages[i].extract_text()
  - 표 추출   : pdfplumber.pages[i].extract_tables() → CSV/JSON 정제
  - 페이지/장·절 단위 청크 분할

CLI:
  inspect URL_OR_PATH       # PDF 구조 진단 (페이지 수, 페이지별 text/table 카운트)
  crawl   URL_OR_PATH ...   # 텍스트 청크 + 표 CSV 저장
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urlparse

import pdfplumber

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402


# --------------------------------------------------------------------------- #
# 다운로드 / 캐시
# --------------------------------------------------------------------------- #

def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _safe_filename(url: str) -> str:
    """URL에서 안전한 파일명 추출."""
    name = os.path.basename(urlparse(url).path) or "downloaded.pdf"
    name = re.sub(r"[^\w\-_.가-힣]", "_", name)
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    return name


def download_pdf(url: str, save_dir: str = "data/sprint0", client: Optional[HttpClient] = None) -> str:
    """PDF 다운로드 후 로컬 경로 반환. 이미 있으면 캐시 사용."""
    client = client or HttpClient()
    os.makedirs(save_dir, exist_ok=True)
    fname = _safe_filename(url)
    path = os.path.join(save_dir, fname)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[cache] {path}")
        return path
    data = client.get_bytes(url)
    with open(path, "wb") as f:
        f.write(data)
    print(f"[downloaded] {len(data)} bytes → {path}")
    return path


# --------------------------------------------------------------------------- #
# inspect 모드
# --------------------------------------------------------------------------- #

@dataclass
class PdfInspectReport:
    source: str               # url 또는 path
    local_path: str
    n_pages: int
    page_text_lens: list[int] # 페이지별 문자 수
    page_table_counts: list[int]  # 페이지별 표 개수
    total_text_len: int
    total_tables: int
    metadata: dict            # PDF 메타데이터
    sample_text: str          # 첫 페이지 첫 600자
    sample_table: Optional[list[list[Optional[str]]]] = None  # 첫 표 미리보기


def inspect_pdf(source: str, client: Optional[HttpClient] = None) -> PdfInspectReport:
    """PDF 구조 진단. URL이면 다운로드 후 분석, 경로면 직접 분석."""
    local_path = download_pdf(source, client=client) if _is_url(source) else source
    with pdfplumber.open(local_path) as pdf:
        n = len(pdf.pages)
        page_text_lens: list[int] = []
        page_table_counts: list[int] = []
        sample_text = ""
        sample_table: Optional[list[list[Optional[str]]]] = None
        total_text = 0
        total_tables = 0
        for i, page in enumerate(pdf.pages):
            t = page.extract_text() or ""
            page_text_lens.append(len(t))
            total_text += len(t)
            tables = page.extract_tables() or []
            page_table_counts.append(len(tables))
            total_tables += len(tables)
            if i == 0:
                sample_text = t[:600]
                if tables:
                    sample_table = tables[0][:5]
        meta = pdf.metadata or {}

    return PdfInspectReport(
        source=source,
        local_path=local_path,
        n_pages=n,
        page_text_lens=page_text_lens,
        page_table_counts=page_table_counts,
        total_text_len=total_text,
        total_tables=total_tables,
        metadata={k: str(v) for k, v in meta.items()},
        sample_text=sample_text,
        sample_table=sample_table,
    )


def print_pdf_inspect(rep: PdfInspectReport) -> None:
    print(f"SOURCE     : {rep.source}")
    print(f"LOCAL      : {rep.local_path}")
    print(f"PAGES      : {rep.n_pages}")
    print(f"TOTAL_TEXT : {rep.total_text_len} chars")
    print(f"TOTAL_TBLS : {rep.total_tables}")
    print(f"METADATA   : {rep.metadata}")
    print("--- 페이지별 text/table ---")
    for i, (tl, tc) in enumerate(zip(rep.page_text_lens, rep.page_table_counts)):
        print(f"  p{i+1}: text={tl} tables={tc}")
    print("--- sample text (p1, 첫 600자) ---")
    print(rep.sample_text)
    if rep.sample_table:
        print("--- sample table (p1, 첫 표 5행) ---")
        for row in rep.sample_table:
            print(f"  {row}")
    else:
        print("--- sample table : (없음) ---")


# --------------------------------------------------------------------------- #
# crawl 모드 — 텍스트 청크 + 표 CSV 저장
# --------------------------------------------------------------------------- #

def crawl_pdf(
    source: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    client: Optional[HttpClient] = None,
    source_title: Optional[str] = None,
    posted_at: Optional[str] = None,
    table_csv_dir: str = "data/sprint0/tables",
) -> tuple[list[Chunk], list[str]]:
    """PDF → 텍스트 청크(페이지 단위) + 표 CSV 파일들.

    Returns:
        (chunks, table_csv_paths)
    """
    local_path = download_pdf(source, client=client) if _is_url(source) else source
    os.makedirs(table_csv_dir, exist_ok=True)
    title = source_title or os.path.basename(local_path)
    source_url = source if _is_url(source) else f"file://{os.path.abspath(local_path)}"

    chunks: list[Chunk] = []
    csv_paths: list[str] = []

    with pdfplumber.open(local_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            # 텍스트 청크 — 페이지 단위
            text = page.extract_text() or ""
            text = text.strip()
            if len(text) >= 30:
                chunks.append(
                    Chunk(
                        text=text,
                        source_type="T3",
                        source_url=source_url,
                        source_title=title,
                        domains=domains,
                        chunk_index=i,
                        categories=categories or [],
                        freshness="dated" if posted_at else "static",
                        posted_at=posted_at,
                        section_path=f"page:{i}",
                    )
                )
            # 표 추출 → CSV (T6)
            tables = page.extract_tables() or []
            for ti, table in enumerate(tables, start=1):
                csv_name = f"{_safe_filename(local_path).replace('.pdf','')}_p{i}_t{ti}.csv"
                csv_path = os.path.join(table_csv_dir, csv_name)
                with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    for row in table:
                        writer.writerow(["" if cell is None else cell for cell in row])
                csv_paths.append(csv_path)

    return chunks, csv_paths


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="PDF Pipeline (T3 + T6)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_i = sub.add_parser("inspect", help="PDF 구조 진단 (페이지·텍스트·표 카운트)")
    p_i.add_argument("source", help="PDF URL 또는 로컬 경로")

    p_c = sub.add_parser("crawl", help="텍스트 청크 + 표 CSV 저장")
    p_c.add_argument("source", help="PDF URL 또는 로컬 경로")
    p_c.add_argument("--domains", default="4", help="콤마 구분 도메인 (기본 4: 기숙사)")
    p_c.add_argument("--categories", default="")
    p_c.add_argument("--posted-at", default=None, help="게시일 (YYYY-MM-DD)")
    p_c.add_argument("--out", default="data/sprint0/pdf_chunks.jsonl")
    p_c.add_argument("--tables-dir", default="data/sprint0/tables")

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "inspect":
        rep = inspect_pdf(args.source, client=client)
        print_pdf_inspect(rep)
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks, csv_paths = crawl_pdf(
            args.source,
            domains=domains,
            categories=categories,
            client=client,
            posted_at=args.posted_at,
            table_csv_dir=args.tables_dir,
        )
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total = sum(c.char_count for c in chunks)
        print(f"OK: {n} text chunks → {args.out}")
        print(f"     {len(csv_paths)} table CSVs → {args.tables_dir}")
        print(f"     total_chars = {total}")
        for c in chunks[:2]:
            print(f"--- {c.section_path} ({c.char_count}자)")
            print(c.text[:200])
        for path in csv_paths[:3]:
            print(f"[csv] {path}")
            with open(path, encoding="utf-8-sig") as f:
                for j, line in enumerate(f):
                    if j >= 3:
                        print("  ...")
                        break
                    print(f"  {line.rstrip()}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
