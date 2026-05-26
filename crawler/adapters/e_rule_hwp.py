"""어댑터 E — 학칙·규정 (plus.cnu.ac.kr/_prog/rule/).

Sprint 1 이월 이슈:
  리스트 페이지의 행이 ``<a href="javascript:void(0)" onclick="...">`` 패턴이라
  어댑터 B의 행→상세 추출이 작동하지 않음. onclick 핸들러에서 ``ntt_no`` 같은
  파라미터를 파싱해서 상세 페이지 URL 또는 첨부 다운로드 URL을 합성한다.

샌드박스에서 라이브 페이지를 보기 어려우므로 가설을 여러 개 잡고 시도:

  가설 G1: ``onclick="fn_egov_select_ruleView('123')"``   → ntt_no=123
  가설 G2: ``onclick="fnLink('view','123')"``              → ntt_no=123
  가설 G3: ``onclick="javascript:goView('123','456')"``    → ntt_no=123 (1st arg)
  가설 G4: ``onclick="...; ntt_no=123 ..."``               → 정규식 ntt_no=\d+
  가설 G5: ``data-ntt-no``/``data-no``/``data-seq`` 속성 직접
  가설 G6: form 제출형 ``onclick="goView(this, '123')"``

확정된 ntt_no로 두 가지 URL을 시도:

  방식 1 (상세 페이지): ``{base}?mode=view&site_dvs_cd=kr&menu_dvs_cd=0703&ntt_no=123``
                       → HTML 본문 추출 + 첨부 링크 추가 다운로드
  방식 2 (직접 다운로드): ``{site}/_prog/_board/common/download.php?code=rule&ntt_no=123``
                       → HWP 직접

CLI:
  inspect URL                # 리스트 구조 + onclick 패턴 + ntt_no 후보 진단
  crawl   URL [--max N]      # 리스트 N개 → 상세/첨부 → Chunk
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse, urlencode, parse_qs

from bs4 import BeautifulSoup, Tag

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402
from crawler.hwp_pipeline import crawl_hwp, download_hwp, _is_valid_hwp  # noqa: E402


# --------------------------------------------------------------------------- #
# onclick → ntt_no 파싱
# --------------------------------------------------------------------------- #

# G1~G4 통합: 따옴표 안 첫 번째 숫자 인자 (대다수 한국 정부/대학 CMS 패턴)
_ONCLICK_FIRST_ARG = re.compile(r"""['"](\d{3,})['"]""")
# G4 폴백: 자유 형식 ntt_no=123
_NTT_NO_FREE = re.compile(r"""ntt_?no\s*[=:]\s*['"]?(\d{3,})['"]?""", re.I)
# 페이지네이션·검색 폼 안의 GotoPage 등은 제외하기 위한 negative 단어
_BAD_NUM_CONTEXT = re.compile(r"(GotoPage|page_no|searchCnt)", re.I)


def parse_ntt_no_from_onclick(onclick: str) -> Optional[str]:
    """onclick 문자열에서 ntt_no 후보 1개 추출. 못 찾으면 None."""
    if not onclick:
        return None
    if _BAD_NUM_CONTEXT.search(onclick):
        return None
    m = _NTT_NO_FREE.search(onclick)
    if m:
        return m.group(1)
    m = _ONCLICK_FIRST_ARG.search(onclick)
    if m:
        return m.group(1)
    return None


def parse_ntt_no_from_tag(tag: Tag) -> Optional[str]:
    """G5: data-ntt-no / data-no / data-seq 속성, 또는 onclick."""
    for attr in ("data-ntt-no", "data-ntt_no", "data-no", "data-seq", "data-id"):
        v = tag.get(attr)
        if v and re.fullmatch(r"\d{3,}", v):
            return v
    onclick = tag.get("onclick") or ""
    return parse_ntt_no_from_onclick(onclick)


# --------------------------------------------------------------------------- #
# 리스트 페이지 진단 + 행 추출
# --------------------------------------------------------------------------- #

@dataclass
class RuleListReport:
    url: str
    status: int
    title: Optional[str]
    n_table_rows: int
    n_onclick_rows: int
    ntt_no_samples: list[dict]          # [{title, ntt_no, onclick}, ...]
    has_javascript_void: bool
    raw_len: int


def inspect_rule_list(url: str, client: Optional[HttpClient] = None) -> RuleListReport:
    client = client or HttpClient()
    resp = client.get(url)
    html = resp.text
    soup = BeautifulSoup(html, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else None
    has_void = "javascript:void" in html

    rows: list[dict] = []
    n_table_rows = 0
    n_onclick_rows = 0

    # 1) <table><tr> 우선
    for table in soup.find_all("table"):
        body = table.find("tbody") or table
        for tr in body.find_all("tr"):
            tds = tr.find_all("td")
            if not tds:
                continue
            n_table_rows += 1
            # tr 또는 안의 a 태그에서 ntt_no
            ntt = parse_ntt_no_from_tag(tr)
            a = tr.find("a")
            if not ntt and a is not None:
                ntt = parse_ntt_no_from_tag(a)
            if ntt:
                n_onclick_rows += 1
                row_title = (a.get_text(" ", strip=True) if a else tr.get_text(" ", strip=True))[:120]
                rows.append({
                    "title": row_title,
                    "ntt_no": ntt,
                    "onclick": (a.get("onclick") if a else None) or tr.get("onclick"),
                })

    # 2) <ul>/<li> 폴백
    if not rows:
        for a in soup.find_all("a"):
            if not isinstance(a, Tag):
                continue
            ntt = parse_ntt_no_from_tag(a)
            if ntt:
                n_onclick_rows += 1
                rows.append({
                    "title": a.get_text(" ", strip=True)[:120],
                    "ntt_no": ntt,
                    "onclick": a.get("onclick"),
                })

    return RuleListReport(
        url=url,
        status=resp.status_code,
        title=title,
        n_table_rows=n_table_rows,
        n_onclick_rows=n_onclick_rows,
        ntt_no_samples=rows[:12],
        has_javascript_void=has_void,
        raw_len=len(html),
    )


def print_rule_inspect(rep: RuleListReport) -> None:
    print(f"URL    : {rep.url}")
    print(f"STATUS : {rep.status}  RAW: {rep.raw_len}")
    print(f"TITLE  : {rep.title}")
    print(f"JS void: {rep.has_javascript_void}")
    print(f"Rows   : table={rep.n_table_rows}, with_ntt_no={rep.n_onclick_rows}")
    print("--- ntt_no 후보 (최대 12개) ---")
    for r in rep.ntt_no_samples:
        oc = (r.get("onclick") or "")[:80]
        print(f"  ntt={r['ntt_no']:>6}  {r['title'][:60]!r}")
        if oc:
            print(f"           onclick={oc!r}")


# --------------------------------------------------------------------------- #
# ntt_no → 상세/첨부 URL 합성
# --------------------------------------------------------------------------- #

def build_view_url(list_url: str, ntt_no: str, *, mode: str = "view") -> str:
    """리스트 URL 기준으로 상세 페이지 URL 생성.

    plus CMS 통상 패턴: 동일 endpoint에 ``&mode=view&ntt_no=...`` 추가.
    """
    pu = urlparse(list_url)
    qs = parse_qs(pu.query, keep_blank_values=True)
    qs["mode"] = [mode]
    qs["ntt_no"] = [ntt_no]
    return f"{pu.scheme}://{pu.netloc}{pu.path}?{urlencode(qs, doseq=True)}"


def build_download_candidates(list_url: str, ntt_no: str) -> list[str]:
    """첨부 직접 다운로드 후보 URL 여러 개.

    plus·dorm 공통: ``{site}/_prog/_board/common/download.php?code=...&ntt_no=...&atch_no=1``
    학칙은 ``code=rule`` 또는 리스트 URL의 ``menu_dvs_cd``에서 추정.
    """
    pu = urlparse(list_url)
    qs = parse_qs(pu.query, keep_blank_values=True)
    code_candidates: list[str] = []
    for key in ("code", "menu_dvs_cd"):
        if key in qs and qs[key]:
            code_candidates.append(qs[key][0])
    if not code_candidates:
        code_candidates = ["rule"]

    out: list[str] = []
    for code in code_candidates:
        for atch_no in (1, 2):
            q = urlencode({"code": code, "ntt_no": ntt_no, "atch_no": atch_no})
            out.append(f"{pu.scheme}://{pu.netloc}/_prog/_board/common/download.php?{q}")
    return out


NOISE_SELECTORS = [
    "header", "footer", "nav",
    ".gnb", ".lnb", ".snb", ".breadcrumb",
    "#header", "#footer", "#gnb", "#lnb", "#snb",
    "script", "style", "noscript",
]


@dataclass
class ViewExtract:
    text: str
    attachments: list[dict]              # [{name, url, ext, kind}]


# 첨부 link in 상세 page
_ATCH_RE = re.compile(r"download\.php\?", re.I)
_EXT_RE = re.compile(r"\.([a-zA-Z0-9]{1,5})(?:$|[?#])")


def extract_view_page(html: str, base_url: str) -> ViewExtract:
    """상세 페이지 HTML → 본문 텍스트 + 첨부 링크."""
    soup_raw = BeautifulSoup(html, "lxml")
    # 첨부는 NOISE 제거 전에
    attachments: list[dict] = []
    seen: set[str] = set()
    for a in soup_raw.find_all("a", href=True):
        href = a["href"]
        is_endpoint = bool(_ATCH_RE.search(href)) or "download" in href.lower()
        if not is_endpoint:
            continue
        full = urljoin(base_url, href)
        if full in seen:
            continue
        seen.add(full)
        name = a.get_text(" ", strip=True) or os.path.basename(urlparse(full).path)
        m = _EXT_RE.search(name) or _EXT_RE.search(href)
        ext = (m.group(1).lower() if m else "")
        kind = (
            "hwp" if ext in ("hwp", "hwpx")
            else "pdf" if ext == "pdf"
            else "other"
        )
        attachments.append({"name": name[:160], "url": full, "ext": ext, "kind": kind})

    soup = BeautifulSoup(html, "lxml")
    for sel in NOISE_SELECTORS:
        for tag in soup.select(sel):
            tag.decompose()
    container = (
        soup.find(attrs={"id": "txt"})
        or soup.find(attrs={"id": "contents"})
        or soup.find(attrs={"id": "content"})
        or soup.find(attrs={"class": "detail_con"})
        or soup.find("article")
        or soup.body
    )
    text = container.get_text("\n", strip=True) if container else ""
    return ViewExtract(text=text, attachments=attachments)


# --------------------------------------------------------------------------- #
# crawl — 리스트 N개 → Chunk 리스트
# --------------------------------------------------------------------------- #

def crawl_rule_list(
    list_url: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    max_items: int = 30,
    hwp_save_dir: str = "data/sprint2/day1/hwp",
    client: Optional[HttpClient] = None,
    verbose: bool = True,
) -> list[Chunk]:
    """학칙 리스트 N개 처리 → 본문 + HWP 텍스트 Chunk."""
    client = client or HttpClient()
    rep = inspect_rule_list(list_url, client=client)
    if not rep.ntt_no_samples:
        if verbose:
            print(f"[skip] ntt_no 후보 0건 — list={list_url}")
        return []

    chunks: list[Chunk] = []
    ntt_list = rep.ntt_no_samples[:max_items]
    if verbose:
        print(f"[rule] list rows={len(ntt_list)} (sampled top {max_items})")

    os.makedirs(hwp_save_dir, exist_ok=True)
    for i, r in enumerate(ntt_list, 1):
        ntt = r["ntt_no"]
        title = r["title"]
        view_url = build_view_url(list_url, ntt)
        if verbose:
            print(f"  [{i:>2}/{len(ntt_list)}] ntt={ntt}  {title[:50]}")

        # 1) 상세 페이지 시도
        try:
            resp = client.get(view_url)
            view = extract_view_page(resp.text, base_url=view_url)
        except Exception as e:
            if verbose:
                print(f"      view fetch fail: {type(e).__name__}: {e}")
            view = ViewExtract(text="", attachments=[])

        # 본문이 30자 이상이면 본문 chunk 추가
        if view.text and len(view.text) >= 30:
            chunks.append(Chunk(
                text=view.text,
                source_type="T2",
                source_url=view_url,
                source_title=title,
                domains=domains,
                categories=categories or [],
                freshness="static",
                parent_post_id=ntt,
                section_path="rule_view",
            ))

        # 첨부 후보 결정: 상세에서 발견한 link 우선, 없으면 download.php 후보 추측
        attachments = view.attachments
        if not attachments:
            for cand in build_download_candidates(list_url, ntt):
                attachments.append({"name": f"rule_{ntt}.hwp", "url": cand, "ext": "hwp", "kind": "hwp"})

        # 2) HWP 다운로드 + hwp_pipeline.crawl_hwp
        for atch in attachments:
            if atch["kind"] not in ("hwp", "pdf"):
                continue
            try:
                if atch["kind"] == "hwp":
                    new_chunks = crawl_hwp(
                        atch["url"],
                        domains=domains,
                        categories=categories or [],
                        source_title=f"{title} ({atch['name']})",
                        save_dir=hwp_save_dir,
                        client=client,
                    )
                    for c in new_chunks:
                        c.parent_post_id = ntt
                        c.section_path = "rule_attachment"
                    chunks.extend(new_chunks)
                    if verbose and new_chunks:
                        print(f"      + HWP {len(new_chunks)} chunk / {sum(c.char_count for c in new_chunks)}자")
                elif atch["kind"] == "pdf":
                    # PDF는 pdf_pipeline 호출
                    from crawler.pdf_pipeline import crawl_pdf  # type: ignore
                    new_chunks, _ = crawl_pdf(
                        atch["url"], domains=domains, categories=categories or [],
                        source_title=f"{title} ({atch['name']})",
                        client=client, table_csv_dir=None,
                    )
                    for c in new_chunks:
                        c.parent_post_id = ntt
                        c.section_path = "rule_attachment_pdf"
                    chunks.extend(new_chunks)
                    if verbose and new_chunks:
                        print(f"      + PDF {len(new_chunks)} chunk / {sum(c.char_count for c in new_chunks)}자")
            except Exception as e:
                if verbose:
                    print(f"      atch fail ({atch['url'][:80]}): {type(e).__name__}: {e}")
                continue

    return chunks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="Adapter E (rule HWP)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_i = sub.add_parser("inspect", help="리스트 페이지 + onclick 패턴 진단")
    p_i.add_argument("url")

    p_c = sub.add_parser("crawl", help="리스트 N개 → Chunks")
    p_c.add_argument("url")
    p_c.add_argument("--domains", default="1")
    p_c.add_argument("--categories", default="1.3")
    p_c.add_argument("--max", type=int, default=30)
    p_c.add_argument("--out", default="data/sprint2/day1/rule_chunks.jsonl")
    p_c.add_argument("--hwp-dir", default="data/sprint2/day1/hwp")

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "inspect":
        rep = inspect_rule_list(args.url, client=client)
        print_rule_inspect(rep)
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks = crawl_rule_list(
            args.url, domains=domains, categories=categories,
            max_items=args.max, hwp_save_dir=args.hwp_dir, client=client,
        )
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total = sum(c.char_count for c in chunks)
        print(f"OK: {n} chunks → {args.out}  total_chars={total}")
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
