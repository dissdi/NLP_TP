"""어댑터 A — plus.cnu.ac.kr 정적 HTML.

대상 URL 패턴: ``https://plus.cnu.ac.kr/_html/kr/sub05/sub05_05020101_01.html``
URL 패턴 (A): 정적 페이지, 페이지네이션 없음, 일반적으로 학사 안내·정책 텍스트.

두 모드:
  --inspect URL : 페이지 구조 진단 (h1/h2/h3, 본문 컨테이너 후보, 추정 본문 길이)
  --crawl URL   : 실제 청크 추출 → JSON Lines 저장

Sprint 0에서는 inspect를 먼저 돌려 셀렉터를 확정한 뒤 crawl로 넘어간다.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from typing import Optional

from bs4 import BeautifulSoup, Tag

# 패키지 경로 보정 (로컬 실행 시 `python crawler/adapters/a_plus.py` 도 동작하도록)
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402


# 본문 컨테이너 후보 (우선순위 순)
# Sprint 0 검증: 충남대는 적어도 4가지 CMS 혼용 — plus / jwxe / 도서관 자체 / cnustudent 자체
# 각 CMS 1순위 컨테이너를 모두 등록해 자동 매칭 → 다른 사이트 첫 inspect 비용 절감
CONTENT_CONTAINER_CANDIDATES = [
    # plus CMS
    ("id", "contents"),
    ("id", "content"),
    # jwxe (Spring 기반) — job/dorm/gymn/health 일부에서 가능성
    ("id", "jwxe_main_content"),
    ("class_", "detail_con"),
    # 도서관 자체 CMS
    ("id", "divContent"),
    ("class_", "guideW"),
    # cnustudent 자체 CMS
    ("class_", "main_con_wrap"),
    # 일반 fallback
    ("class_", "contents"),
    ("class_", "content"),
    ("class_", "sub_contents"),
    ("class_", "sub_content"),
    ("class_", "sub_con"),
    ("class_", "al_box"),
]

# 명백히 본문이 아닌 영역 (제거 대상)
NOISE_SELECTORS = [
    "header", "footer", "nav",
    ".gnb", ".lnb", ".snb", ".breadcrumb",
    ".header", ".footer", ".nav",
    "#header", "#footer", "#gnb", "#lnb", "#snb",
    ".btn_top", ".sns", ".util",
    "script", "style", "noscript",
]


# --------------------------------------------------------------------------- #
# inspect 모드
# --------------------------------------------------------------------------- #

@dataclass
class InspectReport:
    url: str
    status: int
    encoding: Optional[str]
    raw_len: int
    title: Optional[str]
    h1_list: list[str]
    h2_list: list[str]
    h3_list: list[str]
    container_candidates: list[dict]  # 가설 셀렉터별 텍스트 길이
    top_text_divs: list[dict]         # 실제 모든 div의 text_len 상위 N개
    body_text_len: int                # NOISE 제거 후 body 텍스트 길이
    sample_text: str                  # 본문 후보 첫 600자

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        return d


def _div_selector(tag: Tag) -> str:
    """div 식별용 셀렉터 문자열 생성 (#id 우선, 없으면 .class, 없으면 ancestor:tag)."""
    if tag.get("id"):
        return f"#{tag.get('id')}"
    classes = tag.get("class") or []
    if classes:
        return "." + ".".join(classes)
    # 부모 id/class 기반 경로
    parent = tag.parent
    ph = ""
    if parent and parent.name and parent.name != "[document]":
        if parent.get("id"):
            ph = f"#{parent.get('id')}>"
        elif parent.get("class"):
            ph = "." + ".".join(parent.get("class")) + ">"
    return f"{ph}<{tag.name}>"


def inspect_page(url: str, client: Optional[HttpClient] = None) -> InspectReport:
    client = client or HttpClient()
    resp = client.get(url)
    html = resp.text
    soup = BeautifulSoup(html, "lxml")

    # 노이즈 제거 (제목/구조 파악에는 살려두는 게 낫지만 본문 길이 추정용 사본 따로)
    soup_clean = BeautifulSoup(html, "lxml")
    for sel in NOISE_SELECTORS:
        for tag in soup_clean.select(sel):
            tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else None
    h1 = [t.get_text(" ", strip=True) for t in soup.find_all("h1")]
    h2 = [t.get_text(" ", strip=True) for t in soup.find_all("h2")]
    h3 = [t.get_text(" ", strip=True) for t in soup.find_all("h3")]

    # 본문 컨테이너 후보 평가
    cand_reports: list[dict] = []
    for kind, key in CONTENT_CONTAINER_CANDIDATES:
        if kind == "id":
            els = soup.find_all(attrs={"id": key})
        else:
            els = soup.find_all(attrs={"class": key})
        for el in els:
            txt = el.get_text(" ", strip=True)
            cand_reports.append({
                "selector": f"{kind}={key}",
                "tag": el.name,
                "text_len": len(txt),
                "n_h2": len(el.find_all("h2")),
                "n_h3": len(el.find_all("h3")),
            })

    body_text = soup_clean.get_text(" ", strip=True)
    body_len = len(body_text)
    sample = body_text[:600]

    # --- 자동 본문 탐지: 모든 div의 text_len 상위 N + link_ratio ---
    # 메뉴/네비는 보통 link_ratio가 높고, 본문은 낮음 → 본문 식별 휴리스틱
    div_reports: list[dict] = []
    for div in soup_clean.find_all("div"):
        if not isinstance(div, Tag):
            continue
        txt = div.get_text(" ", strip=True)
        if len(txt) < 100:
            continue
        link_text_len = sum(
            len(a.get_text(" ", strip=True)) for a in div.find_all("a")
        )
        link_ratio = link_text_len / max(1, len(txt))
        n_h2 = len(div.find_all("h2"))
        n_h3 = len(div.find_all("h3"))
        n_p = len(div.find_all("p"))
        n_li = len(div.find_all("li"))
        div_reports.append({
            "selector": _div_selector(div),
            "text_len": len(txt),
            "link_ratio": round(link_ratio, 2),
            "n_h2": n_h2,
            "n_h3": n_h3,
            "n_p": n_p,
            "n_li": n_li,
        })
    # 정렬: text_len 큰 순 (단 link_ratio 0.8 이상은 후순위 — 메뉴 가능성)
    div_reports.sort(
        key=lambda d: (d["link_ratio"] > 0.8, -d["text_len"])
    )
    top_text_divs = div_reports[:15]

    return InspectReport(
        url=url,
        status=resp.status_code,
        encoding=resp.encoding,
        raw_len=len(html),
        title=title,
        h1_list=h1[:10],
        h2_list=h2[:20],
        h3_list=h3[:30],
        container_candidates=cand_reports,
        top_text_divs=top_text_divs,
        body_text_len=body_len,
        sample_text=sample,
    )


def print_inspect(rep: InspectReport) -> None:
    print(f"URL        : {rep.url}")
    print(f"STATUS     : {rep.status}  ENC: {rep.encoding}  RAW: {rep.raw_len}")
    print(f"TITLE      : {rep.title}")
    print(f"H1 ({len(rep.h1_list)}): {rep.h1_list}")
    print(f"H2 ({len(rep.h2_list)}): {rep.h2_list}")
    print(f"H3 ({len(rep.h3_list)}): {rep.h3_list}")
    print(f"BODY_TEXT  : {rep.body_text_len} chars (NOISE 제거 후)")
    print("--- 가설 container candidates ---")
    for c in rep.container_candidates:
        print(f"  {c}")
    print("--- 실제 div text_len top 15 (link_ratio 낮은 게 본문 후보) ---")
    for c in rep.top_text_divs:
        print(f"  {c}")
    print("--- sample (first 600 chars of body_text) ---")
    print(rep.sample_text)


# --------------------------------------------------------------------------- #
# crawl 모드 (1차 가설 — inspect 결과 보고 보정)
# --------------------------------------------------------------------------- #

def _pick_container(soup: BeautifulSoup) -> Optional[Tag]:
    """본문 컨테이너 자동 선택 (CONTENT_CONTAINER_CANDIDATES 우선순위)."""
    for kind, key in CONTENT_CONTAINER_CANDIDATES:
        if kind == "id":
            el = soup.find(attrs={"id": key})
        else:
            el = soup.find(attrs={"class": key})
        if el:
            return el
    # fallback: <main> → <article> → <body>
    return soup.find("main") or soup.find("article") or soup.body


def _split_into_sections(container: Tag) -> list[tuple[str, str]]:
    """h2/h3 절 단위로 분할. (section_path, text) 리스트 반환.

    h2가 없으면 전체를 단일 섹션으로 묶는다.
    """
    # NOISE 제거
    for sel in NOISE_SELECTORS:
        for tag in container.select(sel):
            tag.decompose()

    sections: list[tuple[str, str]] = []
    h2_blocks = container.find_all("h2")
    if not h2_blocks:
        # h2 없으면 단일 청크
        txt = container.get_text("\n", strip=True)
        if txt:
            sections.append(("body", txt))
        return sections

    # h2별로 순회하며 다음 h2까지 sibling 수집
    for h2 in h2_blocks:
        h2_title = h2.get_text(" ", strip=True)
        # h3 sub-section 모음
        # 현재 h2 ~ 다음 h2 사이의 element 순회
        buf_lines: list[str] = []
        current_h3: Optional[str] = None
        sub_sections: dict[str, list[str]] = {}

        for sib in h2.next_siblings:
            if isinstance(sib, Tag) and sib.name == "h2":
                break
            if isinstance(sib, Tag) and sib.name == "h3":
                # flush prior sub
                if current_h3 is None and buf_lines:
                    sub_sections.setdefault("", []).extend(buf_lines)
                    buf_lines = []
                elif current_h3 is not None:
                    sub_sections.setdefault(current_h3, []).extend(buf_lines)
                    buf_lines = []
                current_h3 = sib.get_text(" ", strip=True)
                continue
            txt = sib.get_text("\n", strip=True) if isinstance(sib, Tag) else str(sib).strip()
            if txt:
                buf_lines.append(txt)

        # flush 마지막
        if current_h3 is None and buf_lines:
            sub_sections.setdefault("", []).extend(buf_lines)
        elif current_h3 is not None:
            sub_sections.setdefault(current_h3, []).extend(buf_lines)

        if not sub_sections:
            continue

        for h3_title, lines in sub_sections.items():
            body = "\n".join(lines).strip()
            if not body:
                continue
            path = f"h2:{h2_title}" + (f" > h3:{h3_title}" if h3_title else "")
            sections.append((path, body))

    return sections


def crawl_page(
    url: str,
    *,
    domains: list[int],
    categories: Optional[list[str]] = None,
    client: Optional[HttpClient] = None,
) -> list[Chunk]:
    """plus 정적 페이지 1개 → Chunk 리스트.

    호출자가 도메인·카테고리를 명시한다. 어댑터는 도메인 매핑을 모름.
    """
    client = client or HttpClient()
    resp = client.get(url)
    soup = BeautifulSoup(resp.text, "lxml")

    title = soup.title.get_text(strip=True) if soup.title else url
    container = _pick_container(soup)
    if container is None:
        return []

    sections = _split_into_sections(container)
    chunks: list[Chunk] = []
    for idx, (section_path, body) in enumerate(sections):
        if len(body) < 30:
            continue  # 너무 짧은 노이즈 섹션 스킵
        chunks.append(
            Chunk(
                text=body,
                source_type="T1",
                source_url=url,
                source_title=title,
                domains=domains,
                chunk_index=idx,
                categories=categories or [],
                freshness="static",
                section_path=section_path,
            )
        )
    return chunks


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def main() -> int:
    p = argparse.ArgumentParser(description="Adapter A (plus.cnu.ac.kr 정적)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_inspect = sub.add_parser("inspect", help="페이지 구조 진단")
    p_inspect.add_argument("url")
    p_inspect.add_argument("--json", action="store_true", help="JSON으로 출력")

    p_crawl = sub.add_parser("crawl", help="실제 청크 추출")
    p_crawl.add_argument("url")
    p_crawl.add_argument(
        "--domains", default="1",
        help="콤마 구분 도메인 정수 (예: 1 또는 1,8)",
    )
    p_crawl.add_argument(
        "--categories", default="",
        help="콤마 구분 카테고리 코드 (선택)",
    )
    p_crawl.add_argument(
        "--out", default="data/sprint0/a_plus_chunks.jsonl",
        help="JSON Lines 출력 경로",
    )

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "inspect":
        rep = inspect_page(args.url, client=client)
        if args.json:
            print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
        else:
            print_inspect(rep)
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks = crawl_page(args.url, domains=domains, categories=categories, client=client)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total_chars = sum(c.char_count for c in chunks)
        print(f"OK: {n} chunks → {args.out}")
        print(f"total_chars = {total_chars}")
        for c in chunks[:3]:
            print("---", c.section_path, f"({c.char_count}자)")
            print(c.text[:200])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
