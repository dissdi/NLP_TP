"""어댑터 B — 백마광장 게시판 (T2).

대상 URL 패턴: ``https://plus.cnu.ac.kr/_prog/_board/?code=sub07_0702``
2단계 fetch:
  1) 리스트 페이지: 게시물 row(제목/작성일/상세 URL) 추출 + 페이지네이션
  2) 상세 페이지: 게시물 본문 → 청크 1개

Sprint 0 검증 절차:
  --mode inspect-list URL    # 리스트 페이지 구조 진단
  --mode crawl URL --max N   # 리스트 1페이지 + 상세 N개 → JSON Lines 저장
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse, parse_qs

from bs4 import BeautifulSoup, Tag

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402


NOISE_SELECTORS = [
    "header", "footer", "nav",
    ".gnb", ".lnb", ".snb", ".breadcrumb",
    ".header", ".footer", ".nav",
    "#header", "#footer", "#gnb", "#lnb", "#snb",
    ".btn_top", ".sns", ".util",
    "script", "style", "noscript",
]


# --------------------------------------------------------------------------- #
# inspect-list 모드
# --------------------------------------------------------------------------- #

@dataclass
class ListInspectReport:
    url: str
    status: int
    encoding: Optional[str]
    raw_len: int
    title: Optional[str]
    # 행(row) 후보: 테이블/리스트 패턴 자동 탐색
    table_candidates: list[dict]   # <table>의 row 수 + 첫 row 텍스트
    list_candidates: list[dict]    # <ul>/<ol>의 li 수 + 첫 li 텍스트
    # 페이지네이션 후보
    pagination_candidates: list[dict]
    # 본문 컨테이너 후보 (어댑터 A와 유사 — 같은 CMS면 동일 패턴 기대)
    container_candidates: list[dict]
    # 게시물 후보 row 5개 미리보기 (제목/날짜/링크)
    preview_rows: list[dict]


def _row_text_sample(tag: Tag) -> str:
    return " | ".join(tag.get_text(" ", strip=True).split())[:120]


def _is_pagination_block(tag: Tag) -> bool:
    cls = " ".join(tag.get("class", []) or [])
    idn = tag.get("id", "") or ""
    pat = re.compile(r"paging|pagination|paginate|page_nav|num_pg|board_paging", re.I)
    return bool(pat.search(cls) or pat.search(idn))


def _extract_preview_rows(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """게시판 리스트의 첫 5~10개 행을 다양한 가설로 시도해 추출."""
    rows: list[dict] = []

    # 가설 1: <table><tbody><tr>
    for table in soup.find_all("table"):
        body = table.find("tbody") or table
        tr_list = body.find_all("tr")
        if len(tr_list) < 3:
            continue
        for tr in tr_list[:8]:
            tds = tr.find_all(["td", "th"])
            if not tds:
                continue
            a = tr.find("a", href=True)
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            href = urljoin(base_url, a["href"])
            cols = [td.get_text(" ", strip=True) for td in tds]
            rows.append({
                "source": "table",
                "title": title[:80],
                "href": href,
                "cols": cols[:6],
            })
        if rows:
            return rows

    # 가설 2: <ul class="board_list">
    for ul in soup.find_all(["ul", "ol"]):
        cls = " ".join(ul.get("class", []) or [])
        if not re.search(r"board|list|article", cls, re.I):
            continue
        li_list = ul.find_all("li")
        if len(li_list) < 3:
            continue
        for li in li_list[:8]:
            a = li.find("a", href=True)
            if not a:
                continue
            rows.append({
                "source": f"ul.{cls}",
                "title": a.get_text(" ", strip=True)[:80],
                "href": urljoin(base_url, a["href"]),
                "cols": [li.get_text(" ", strip=True)[:80]],
            })
        if rows:
            return rows

    return rows


def inspect_list(url: str, client: Optional[HttpClient] = None) -> ListInspectReport:
    client = client or HttpClient()
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else None

    # 테이블 후보
    table_cands: list[dict] = []
    for table in soup.find_all("table"):
        body = table.find("tbody") or table
        tr_list = body.find_all("tr")
        if not tr_list:
            continue
        cls = " ".join(table.get("class", []) or [])
        table_cands.append({
            "selector": f"table.{cls}" if cls else "<table>",
            "n_rows": len(tr_list),
            "first_row": _row_text_sample(tr_list[0]) if tr_list else "",
        })

    # 리스트(ul/ol) 후보
    list_cands: list[dict] = []
    for ul in soup.find_all(["ul", "ol"]):
        cls = " ".join(ul.get("class", []) or [])
        li_list = ul.find_all("li", recursive=False) or ul.find_all("li")
        if len(li_list) < 3:
            continue
        if not re.search(r"board|list|article|item|notice", cls, re.I):
            continue
        list_cands.append({
            "selector": f"{ul.name}.{cls}" if cls else f"<{ul.name}>",
            "n_li": len(li_list),
            "first_li": _row_text_sample(li_list[0]) if li_list else "",
        })

    # 페이지네이션 후보
    pagi_cands: list[dict] = []
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if _is_pagination_block(tag):
            a_list = tag.find_all("a", href=True)
            pagi_cands.append({
                "selector": (
                    f"{tag.name}#{tag.get('id')}" if tag.get("id")
                    else f"{tag.name}.{'.'.join(tag.get('class', []))}"
                ),
                "n_links": len(a_list),
                "hrefs": [a["href"] for a in a_list[:8]],
            })

    # 본문 컨테이너 후보 (plus CMS 동일 패턴)
    container_cands: list[dict] = []
    for sel in ["contents", "container", "content"]:
        el = soup.find(attrs={"id": sel})
        if el:
            container_cands.append({
                "selector": f"#{sel}",
                "text_len": len(el.get_text(" ", strip=True)),
            })

    # 게시물 행 미리보기
    preview = _extract_preview_rows(soup, base_url=url)

    return ListInspectReport(
        url=url,
        status=resp.status_code,
        encoding=resp.encoding,
        raw_len=len(resp.text),
        title=title,
        table_candidates=table_cands[:6],
        list_candidates=list_cands[:6],
        pagination_candidates=pagi_cands[:4],
        container_candidates=container_cands,
        preview_rows=preview[:8],
    )


def print_list_inspect(rep: ListInspectReport) -> None:
    print(f"URL    : {rep.url}")
    print(f"STATUS : {rep.status}  ENC: {rep.encoding}  RAW: {rep.raw_len}")
    print(f"TITLE  : {rep.title}")
    print("--- 본문 container candidates ---")
    for c in rep.container_candidates:
        print(f"  {c}")
    print(f"--- table candidates ({len(rep.table_candidates)}) ---")
    for c in rep.table_candidates:
        print(f"  {c}")
    print(f"--- list candidates ({len(rep.list_candidates)}) ---")
    for c in rep.list_candidates:
        print(f"  {c}")
    print(f"--- pagination candidates ({len(rep.pagination_candidates)}) ---")
    for c in rep.pagination_candidates:
        print(f"  {c}")
    print(f"--- preview rows ({len(rep.preview_rows)}) ---")
    for r in rep.preview_rows:
        print(f"  src={r['source']}")
        print(f"    title: {r['title']}")
        print(f"    href : {r['href']}")
        print(f"    cols : {r['cols']}")


# --------------------------------------------------------------------------- #
# crawl 모드 (1차 가설 — inspect-list 결과 보고 보정)
# --------------------------------------------------------------------------- #

def _extract_post_id_from_url(url: str) -> Optional[str]:
    """상세 URL의 쿼리에서 게시물 ID 추정 (seq, board_seq, no, idx 중 첫 매칭)."""
    qs = parse_qs(urlparse(url).query)
    # plus CMS: 'no' / 일부 사이트: 'seq' / 'board_seq' / 'bbs_seq' / 'idx' / 'board_no'
    for key in ("no", "board_seq", "seq", "bbs_seq", "idx", "board_no"):
        if key in qs and qs[key][0]:
            return qs[key][0]
    return None


def crawl_post(
    url: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    client: Optional[HttpClient] = None,
    list_title: Optional[str] = None,
    list_posted_at: Optional[str] = None,
) -> Optional[Chunk]:
    """게시물 상세 페이지 1개 → Chunk."""
    client = client or HttpClient()
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    # NOISE 제거
    for sel in NOISE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()

    # plus CMS 본문: #contents > #txt 가 가장 깨끗 (어댑터 A 검증 결과)
    container = (
        soup.find(attrs={"id": "txt"})
        or soup.find(attrs={"id": "contents"})
        or soup.find(attrs={"class": "content"})
        or soup.find("article")
        or soup.body
    )
    if container is None:
        return None

    title = (
        list_title
        or (soup.title.get_text(strip=True) if soup.title else url)
    )
    body = container.get_text("\n", strip=True)
    if len(body) < 30:
        return None

    post_id = _extract_post_id_from_url(url)
    return Chunk(
        text=body,
        source_type="T2",
        source_url=url,
        source_title=title,
        domains=domains,
        categories=categories or [],
        freshness="dated",
        posted_at=list_posted_at,
        parent_post_id=post_id,
        section_path="post_body",
    )


def crawl_list_and_posts(
    list_url: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    max_posts: int = 3,
    client: Optional[HttpClient] = None,
) -> list[Chunk]:
    """리스트 1페이지 → 처음 N개 상세 fetch → Chunk 리스트."""
    client = client or HttpClient()
    list_rep = inspect_list(list_url, client=client)
    chunks: list[Chunk] = []
    for r in list_rep.preview_rows[:max_posts]:
        href = r["href"]
        title = r["title"]
        # cols 중 날짜 후보 (YYYY-MM-DD 또는 YYYY.MM.DD 패턴)
        posted_at = None
        for c in r.get("cols", []):
            m = re.search(r"(\d{4})[-./](\d{2})[-./](\d{2})", c)
            if m:
                posted_at = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
                break
        chunk = crawl_post(
            href,
            domains=domains,
            categories=categories,
            client=client,
            list_title=title,
            list_posted_at=posted_at,
        )
        if chunk:
            chunks.append(chunk)
    return chunks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="Adapter B (게시판 T2)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_il = sub.add_parser("inspect-list", help="리스트 페이지 구조 진단")
    p_il.add_argument("url")

    p_crawl = sub.add_parser("crawl", help="리스트 1페이지 + 상세 N개 → JSON Lines")
    p_crawl.add_argument("url")
    p_crawl.add_argument("--domains", default="5", help="콤마 구분 도메인 (예: 5 또는 5,1)")
    p_crawl.add_argument("--categories", default="", help="콤마 구분 카테고리 코드")
    p_crawl.add_argument("--max", type=int, default=3, help="상세 fetch 최대 개수")
    p_crawl.add_argument("--out", default="data/sprint0/b_board_chunks.jsonl")

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "inspect-list":
        rep = inspect_list(args.url, client=client)
        print_list_inspect(rep)
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks = crawl_list_and_posts(
            args.url,
            domains=domains,
            categories=categories,
            max_posts=args.max,
            client=client,
        )
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total = sum(c.char_count for c in chunks)
        print(f"OK: {n} chunks → {args.out}")
        print(f"total_chars = {total}")
        for c in chunks[:3]:
            print(f"--- post_id={c.parent_post_id} posted_at={c.posted_at} ({c.char_count}자)")
            print(c.text[:200])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
