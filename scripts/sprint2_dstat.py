"""D-통계 PDF raw 추출 헬퍼.

대상:
  1.7 신입생수    — 대학알리미 충남대 (univ_no=000007)
  7.5 취업률      — 대학알리미 충남대 (같은 사이트)
  4.7 기숙사 경쟁률 — dorm.cnu.ac.kr 알림마당 게시판 첨부 PDF

대학알리미 (www.academyinfo.go.kr) 는 항목별 popup endpoint를 갖는데, 실제 PDF URL은
페이지 HTML 안에 있을 수도(직접 link) JS 후처리로 생성될 수도 있어서 spike 필요.

CLI:
  spike-alimi --univ-no 000007  # 충남대 알리미 페이지에서 PDF·CSV link 후보 출력
  fetch-pdf URL --out PATH      # PDF 단건 다운로드 + pdfplumber 표 추출 → CSV 모음

대학알리미 결과는 사용자가 확인 후 sprint2_targets.json 의 PDF task 로 옮긴다.
기숙사 4.7 은 sprint2_runner day1 에서 어댑터 B 로 게시판 fetch → 첨부 후처리에서 PDF
다운로드 + 표 추출이 자동으로 됨.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402


ALIMI_BASE = "https://www.academyinfo.go.kr"

# 대학알리미 공시 항목 (univ_no 충남대=000007 가정)
# 각 항목별 popup endpoint 후보. 실제 동작은 spike 결과로 확정.
ALIMI_CANDIDATES = [
    # (label, url_template, ctype hint)
    ("신입생수",       "{base}/popup/disclosure5.do?univ_no={univ_no}",              "freshman"),
    ("취업률",         "{base}/popup/disclosure5.do?univ_no={univ_no}&item_no=43",  "employment"),
    ("재학생수",       "{base}/popup/disclosure5.do?univ_no={univ_no}&item_no=42",  "enrollment"),
    ("학과별정원",     "{base}/popup/disclosure5.do?univ_no={univ_no}&item_no=10",  "quota"),
]


def spike_alimi(univ_no: str, *, client: Optional[HttpClient] = None) -> list[dict]:
    """대학알리미 popup endpoint들을 fetch 해서 PDF/CSV link 후보 출력."""
    client = client or HttpClient(sleep_between=1.2)
    results: list[dict] = []
    for label, tmpl, hint in ALIMI_CANDIDATES:
        url = tmpl.format(base=ALIMI_BASE, univ_no=univ_no)
        print(f"\n=== {label} ({hint}) ===")
        print(f"  url: {url}")
        try:
            resp = client.get(url)
        except Exception as e:
            print(f"  ✗ fetch fail: {type(e).__name__}: {e}")
            continue
        soup = BeautifulSoup(resp.text, "lxml")
        pdf_links: list[str] = []
        csv_links: list[str] = []
        excel_links: list[str] = []
        for a in soup.find_all("a", href=True):
            if not isinstance(a, Tag):
                continue
            href = a["href"]
            lower = href.lower()
            if ".pdf" in lower:
                pdf_links.append(urljoin(url, href))
            if ".csv" in lower:
                csv_links.append(urljoin(url, href))
            if ".xls" in lower:
                excel_links.append(urljoin(url, href))

        # 동적 popup의 경우 onclick="fnDownload(...)" 패턴도 점검
        onclick_dl: list[str] = []
        for a in soup.find_all("a"):
            if not isinstance(a, Tag):
                continue
            oc = a.get("onclick") or ""
            if re.search(r"download|excel|pdf|fnPrint", oc, re.I):
                onclick_dl.append(oc[:120])

        print(f"  HTTP {resp.status_code}  RAW={len(resp.text)}")
        print(f"  PDF link : {len(pdf_links)}")
        for u in pdf_links[:5]:
            print(f"    {u}")
        print(f"  CSV link : {len(csv_links)}")
        for u in csv_links[:5]:
            print(f"    {u}")
        print(f"  XLS link : {len(excel_links)}")
        for u in excel_links[:5]:
            print(f"    {u}")
        if onclick_dl:
            print(f"  onclick download 후보 ({len(onclick_dl)}):")
            for oc in onclick_dl[:5]:
                print(f"    {oc!r}")

        results.append({
            "label": label,
            "url": url,
            "status": resp.status_code,
            "pdf_links": pdf_links,
            "csv_links": csv_links,
            "excel_links": excel_links,
            "onclick_dl_count": len(onclick_dl),
        })

    print("\n=== 요약 ===")
    print("PDF·CSV·XLS link 가 발견된 endpoint 만 sprint2_targets.json 의 PDF task 로 옮긴다.")
    print("아무 link 도 못 찾았다면 알리미 popup 이 JS 후처리이거나 form 제출형 →")
    print("이 경우 브라우저로 직접 열어서 다운로드 URL 확보 후 PDF task 에 명시.")
    return results


def fetch_pdf(url: str, out_dir: str, *, title: Optional[str] = None) -> int:
    """PDF 단건 다운로드 + pdfplumber 표 추출 → CSV 모음.

    pdf_pipeline.crawl_pdf 재사용. 표 CSV 는 ``{out_dir}/tables/`` 에.
    """
    from crawler.pdf_pipeline import crawl_pdf  # type: ignore
    from crawler.schema import write_jsonl

    client = HttpClient(sleep_between=1.2)
    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "tables"), exist_ok=True)
    chunks, csvs = crawl_pdf(
        url, domains=[1, 7], categories=["1.7", "7.5"],
        source_title=title or "대학알리미 PDF",
        client=client,
        table_csv_dir=os.path.join(out_dir, "tables"),
    )
    out_jsonl = os.path.join(out_dir, f"dstat_chunks.jsonl")
    n = write_jsonl(chunks, out_jsonl)
    total = sum(c.char_count for c in chunks)
    print(f"OK {n} chunks / {total}자  표 CSV {len(csvs)}개")
    print(f"  → {out_jsonl}")
    return 0


def scan_pubinfo_list(list_url: str, *, client: Optional[HttpClient] = None) -> list[dict]:
    """대학알리미 pubinfo1690/list.do 페이지에서 항목 link 자동 발견.

    사용자가 발견한 URL: https://www.academyinfo.go.kr/popup/pubinfo1690/list.do?schlId=0000029
    이 페이지는 학교별 공시정보 목록이라 각 항목 link · onclick 패턴 다양.
    스캔 결과를 출력해서 사용자가 신입생수/취업률에 해당하는 항목 URL 선택.
    """
    client = client or HttpClient(sleep_between=1.0)
    print(f"=== scan-pubinfo-list ===\n  url: {list_url}")
    try:
        resp = client.get(list_url)
    except Exception as e:
        print(f"  ✗ fetch fail: {type(e).__name__}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    print(f"  HTTP {resp.status_code}  RAW={len(resp.text)}")
    title = soup.title.get_text(strip=True) if soup.title else None
    print(f"  TITLE: {title}")

    # 모든 a 태그 + onclick 추출
    items: list[dict] = []
    for a in soup.find_all("a"):
        if not isinstance(a, Tag):
            continue
        text = a.get_text(" ", strip=True)
        if not text:
            continue
        href = a.get("href") or ""
        oc = a.get("onclick") or ""
        # 키워드 필터: 신입생/취업/충원/졸업/재학 등 D-통계 관련
        keywords = re.search(
            r"신입생|충원|취업|진학|졸업생|재학생|학과별\s*정원|정원|등록금",
            text, re.I,
        )
        if not keywords and not re.search(r"신입생|취업|진학|충원|정원", oc, re.I):
            continue
        items.append({
            "text": text[:80],
            "href": href if href else None,
            "onclick": oc[:120] if oc else None,
        })

    print(f"\n--- 키워드 매칭 항목 ({len(items)}) ---")
    for it in items[:30]:
        print(f"  · {it['text']}")
        if it["href"]:
            print(f"      href:    {it['href']}")
        if it["onclick"]:
            print(f"      onclick: {it['onclick']!r}")

    print("\n--- 다음 ---")
    print("  1) 위 항목 중 신입생수·취업률에 해당하는 행의 href 또는 onclick에서 URL 추출")
    print("  2) fetch-pdf <URL> --title \"신입생수\" 등으로 실행")
    return items


def main() -> int:
    p = argparse.ArgumentParser(description="D-통계 PDF raw 추출")
    sub = p.add_subparsers(dest="mode", required=True)

    p_s = sub.add_parser("spike-alimi", help="대학알리미 popup endpoint 진단 (예전 가설)")
    p_s.add_argument("--univ-no", default="000007", help="충남대=000007")
    p_s.add_argument("--out", default="data/sprint2/day1/alimi_spike.json")

    p_l = sub.add_parser("scan-list", help="알리미 pubinfo list.do에서 항목 자동 발견 (권장)")
    p_l.add_argument("--url", default="https://www.academyinfo.go.kr/popup/pubinfo1690/list.do?schlId=0000029",
                     help="사용자 확인 URL (충남대 schlId=0000029)")
    p_l.add_argument("--out", default="data/sprint2/day1/alimi_list_scan.json")

    p_f = sub.add_parser("fetch-pdf", help="PDF 단건 다운로드 + 표 CSV 추출")
    p_f.add_argument("url")
    p_f.add_argument("--out-dir", default="data/sprint2/day1/dstat")
    p_f.add_argument("--title", default=None)

    args = p.parse_args()
    if args.mode == "spike-alimi":
        res = spike_alimi(args.univ_no)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"\n→ {args.out}")
        return 0
    if args.mode == "scan-list":
        res = scan_pubinfo_list(args.url)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=2)
        print(f"\n-> {args.out}")
        return 0
    if args.mode == "fetch-pdf":
        return fetch_pdf(args.url, args.out_dir, title=args.title)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
