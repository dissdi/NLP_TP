"""물리 교육과정 페이지 (JS 렌더링) 우회 시도.

지금 상황:
  GET https://physics.cnu.ac.kr/physics/intro/curriculum.do
  → 200 응답이지만 본문 0 chunks (JS 렌더 후에야 표가 채워지는 듯).

전략:
  1) ?layout=print / ?_layout=ajax / ?layout=text 같은 흔한 cnu 패턴 시도
  2) Mobile User-Agent 로 재요청 (mobile 라우트가 SSR 인 경우 있음)
  3) raw HTML 내의 <iframe>/<script src>/fetch(...)/XMLHttpRequest 호출 분석
  4) 사이트맵/robots.txt 점검

콘솔에 status + size + 본문 keyword hit("학점","전공","교양") 보고.
"""
from __future__ import annotations

import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

URL = "https://physics.cnu.ac.kr/physics/intro/curriculum.do"
BASE = "https://physics.cnu.ac.kr"

UA_DESKTOP = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
UA_MOBILE = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

KW = ["학점", "전공", "교양", "교과목", "이수", "필수", "선택"]

LAYOUT_VARIANTS = [
    "",                  # baseline
    "?layout=print",
    "?layout=text",
    "?layout=ajax",
    "?_layout=print",
    "?print=1",
    "?print=true",
    "?mode=print",
    "?mode=text",
    "?show=text",
    "?format=text",
    "?ajax=1",
    "?_format=json",
]


def probe(url: str, ua: str, label: str) -> str | None:
    try:
        r = requests.get(url, headers={"User-Agent": ua, "Accept": "text/html,*/*"}, timeout=15)
    except Exception as e:
        print(f"  [{label}] FAIL: {type(e).__name__}: {e}")
        return None
    text = r.text
    soup = BeautifulSoup(text, "lxml")
    body_text = soup.get_text(" ", strip=True)
    hits = {k: body_text.count(k) for k in KW if k in body_text}
    flag = ""
    if sum(hits.values()) >= 5 and len(body_text) > 1500:
        flag = "  ⭐ 본문 회수 가능성!"
    print(f"  [{label}] status={r.status_code}  bytes={len(text):>6}  body_chars={len(body_text):>6}  kw_hits={hits}{flag}")
    return text


def analyze_iframe_ajax(html: str) -> None:
    print("\n--- HTML 구조 분석 ---")
    soup = BeautifulSoup(html, "lxml")

    iframes = soup.find_all("iframe")
    print(f"  <iframe> {len(iframes)}개:")
    for f in iframes:
        src = f.get("src") or ""
        if src:
            print(f"    iframe src= {urljoin(BASE, src)}")

    scripts = soup.find_all("script")
    src_scripts = [s.get("src") for s in scripts if s.get("src")]
    print(f"  <script src> {len(src_scripts)}개 (정적 JS)")
    for s in src_scripts[:5]:
        print(f"    {s}")
    print(f"    ... 외 {max(0, len(src_scripts)-5)}개")

    inline_text = "\n".join(s.get_text() for s in scripts if not s.get("src"))
    ajax_urls: set[str] = set()
    for pat in [
        r"""url\s*[:=]\s*['"]([^'"]+\.do[^'"]*)['"]""",
        r"""\$\.get\(\s*['"]([^'"]+)['"]""",
        r"""\$\.post\(\s*['"]([^'"]+)['"]""",
        r"""fetch\(\s*['"]([^'"]+)['"]""",
        r"""ajax\(\s*\{?\s*[^}]*url\s*:\s*['"]([^'"]+)['"]""",
        r"""XMLHttpRequest[^}]+open\([^,]+,\s*['"]([^'"]+)['"]""",
    ]:
        for m in re.finditer(pat, inline_text):
            ajax_urls.add(m.group(1))
    if ajax_urls:
        print(f"  inline JS 내 AJAX/fetch URL {len(ajax_urls)}개:")
        for u in sorted(ajax_urls)[:20]:
            full = urljoin(URL, u)
            print(f"    {full}")
    else:
        print("  inline JS 내 AJAX URL 미발견")

    forms = soup.find_all("form")
    if forms:
        print(f"  <form> {len(forms)}개:")
        for f in forms[:5]:
            print(f"    action={f.get('action')}  method={f.get('method')}")


def stage_robots_sitemap() -> None:
    print("\n--- robots.txt / sitemap ---")
    for path in ["/robots.txt", "/sitemap.xml"]:
        url = BASE + path
        try:
            r = requests.get(url, headers={"User-Agent": UA_DESKTOP}, timeout=10)
            print(f"  [{path}] status={r.status_code}  bytes={len(r.text)}")
            if r.status_code == 200:
                snippet = r.text[:400].replace("\n", " | ")
                print(f"    head: {snippet}")
        except Exception as e:
            print(f"  [{path}] FAIL: {type(e).__name__}: {e}")


def main() -> int:
    print(f"### Probe target: {URL}\n")

    print("=== STAGE 1: layout 변형 (desktop UA) ===")
    baseline_html = None
    for q in LAYOUT_VARIANTS:
        u = URL + q
        h = probe(u, UA_DESKTOP, f"DT {q or 'baseline'}")
        if q == "":
            baseline_html = h

    print("\n=== STAGE 2: mobile UA ===")
    probe(URL, UA_MOBILE, "MB baseline")

    if baseline_html:
        analyze_iframe_ajax(baseline_html)

    stage_robots_sitemap()

    print("\n=== 끝 ===")
    print("⭐ 표시 또는 kw_hits 풍부한 URL 을 dept_list_me_phy.json 에 추가하거나,")
    print("AJAX URL 이 발견되면 그 URL 을 dept_list 에 직접 등록.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
