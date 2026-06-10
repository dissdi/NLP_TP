"""me + physics 사이트맵 탐색 — 실제 URL을 찾아낸다.

3단계:
  A) home 페이지의 모든 <a href> 덤프 (sub-domain 안의 .do 만)
  B) 추정 URL 후보들을 HEAD/GET 으로 status 확인
  C) home 에 있는 sub-menu 페이지 1단계 따라가 그 안에서도 졸업요건/교육과정 키워드 anchor 검색

랩실/dev PC에서 실행:
  python -m scripts.sprint3.probe_me_phy_urls

산출:
  콘솔에 후보 URL + 텍스트 출력. 사용자가 골라 dept_list_me_phy.json 의 direct_url 에 붙여넣음.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

UA = "Mozilla/5.0 (compatible; cnu-corpus-probe/1.0)"
TIMEOUT = 10

SITES = [
    ("me", "https://me.cnu.ac.kr/me/index.do", "https://me.cnu.ac.kr/"),
    ("physics", "https://physics.cnu.ac.kr/physics/index.do", "https://physics.cnu.ac.kr/"),
]

KW = re.compile(
    r"졸업|이수|학위|교과|교육과정|커리큘럼|curriculum|graduation|requirement|학사|학부|학과\s*소개",
    re.I,
)
BAD = re.compile(r"인사말|연혁|찾아오는|위치|로그인|articleNo=", re.I)


def fetch(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=TIMEOUT, allow_redirects=True)
        return r
    except Exception as e:
        print(f"  ⚠ fetch fail {url}: {type(e).__name__}: {e}")
        return None


def is_same_host(url: str, host: str) -> bool:
    try:
        return urlparse(url).hostname == host
    except Exception:
        return False


def collect_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """(href_abs, text) 목록. 같은 호스트만, javascript:/mailto:/# 제외."""
    soup = BeautifulSoup(html, "lxml")
    host = urlparse(base_url).hostname
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        href = a["href"]
        if isinstance(href, list):
            href = href[0] if href else ""
        if not href or href.startswith(("javascript:", "mailto:", "#", "tel:")):
            continue
        full = urljoin(base_url, href)
        if not is_same_host(full, host):
            continue
        if full in seen:
            continue
        seen.add(full)
        text = a.get_text(" ", strip=True)
        out.append((full, text))
    return out


def filter_candidate(text: str, url: str) -> bool:
    if BAD.search(text or "") or BAD.search(url):
        return False
    return bool(KW.search(text or "") or KW.search(url))


def stage_A_home_links(label: str, home: str) -> list[tuple[str, str]]:
    print(f"\n=== [{label}] STAGE A — home={home} ===")
    r = fetch(home)
    if not r or r.status_code >= 400:
        print(f"  home fetch fail: {r.status_code if r else 'no resp'}")
        return []
    print(f"  status={r.status_code} bytes={len(r.text)}")
    links = collect_links(r.text, home)
    print(f"  total links: {len(links)}")
    # 후보(키워드 매칭)
    cands = [(u, t) for (u, t) in links if filter_candidate(t, u)]
    print(f"  keyword-matched: {len(cands)}")
    for u, t in cands[:30]:
        print(f"    [HOME] {t[:50]!s:50s} -> {u}")
    return links


def stage_B_probe_paths(label: str, base: str, paths: list[str]) -> None:
    print(f"\n=== [{label}] STAGE B — common path probe ===")
    for p in paths:
        url = base.rstrip("/") + p
        r = fetch(url)
        if not r:
            continue
        title = ""
        try:
            soup = BeautifulSoup(r.text, "lxml")
            t = soup.find("title")
            if t:
                title = t.get_text(strip=True)[:60]
        except Exception:
            pass
        sz = len(r.text)
        flag = ""
        if r.status_code == 200 and sz > 5000:
            flag = "  ⭐ 가능성 높음"
        print(f"  [{r.status_code}] size={sz:>7}  title={title!s:60s}  {url}{flag}")


def stage_C_followup(label: str, home_links: list[tuple[str, str]], home: str) -> None:
    """home 의 sub-menu (학사/학부/교육 등 anchor) 한 단계 따라가서 그 안에서 키워드 anchor 재검색."""
    print(f"\n=== [{label}] STAGE C — follow sub-menus 1 hop ===")
    SUB_KW = re.compile(r"학부|학과|학사|교육|전공|커리|학생|graduate|undergrad|edu|bachelor", re.I)
    seeds = [(u, t) for (u, t) in home_links if SUB_KW.search(t or "") or SUB_KW.search(u)]
    print(f"  sub-menu seeds: {len(seeds)}")
    seen_pages: set[str] = set()
    for u, t in seeds[:15]:
        if u in seen_pages:
            continue
        seen_pages.add(u)
        r = fetch(u)
        if not r or r.status_code >= 400:
            continue
        sub_links = collect_links(r.text, u)
        cands = [(uu, tt) for (uu, tt) in sub_links if filter_candidate(tt, uu)]
        if cands:
            print(f"  via [{t[:30]!s:30s}] {u}")
            for uu, tt in cands[:10]:
                print(f"    [SUB] {tt[:50]!s:50s} -> {uu}")


ME_PROBE_PATHS = [
    # 가장 흔한 패턴들 (다른 학과들로부터)
    "/me/sub01/sub01_01.do",  # 학과소개
    "/me/sub02/sub02_01.do",
    "/me/sub03/sub03_01.do",
    "/me/sub04/sub04_01.do",
    "/me/sub05/sub05_01.do",
    "/me/sub06/sub06_01.do",
    "/me/edu/edu01.do",
    "/me/edu/edu02.do",
    "/me/edu/edu03.do",
    "/me/edu/sub01.do",
    "/me/edu/sub02.do",
    "/me/edu/curri01.do",
    "/me/edu/curri02.do",
    "/me/edu/grad01.do",
    "/me/edu/grad02.do",
    "/me/edu/req01.do",
    "/me/data/curri01.do",
    "/me/data/curri02.do",
    "/me/data/curri03.do",
    "/me/data/grad01.do",
    "/me/data/req01.do",
    "/me/data/learn01.do",
    "/me/info/intro01.do",
    "/me/info/intro02.do",
    "/me/info/intro03.do",
    "/me/info/intro04.do",
    "/me/info/grad01.do",
    "/me/info/curri01.do",
    "/me/curri/curri.do",
    "/me/curri/under.do",
    "/me/curri/undergrad.do",
    "/me/under/curri.do",
    "/me/under/req.do",
]

PHY_PROBE_PATHS = [
    "/physics/sub01/sub01_01.do",
    "/physics/sub02/sub02_01.do",
    "/physics/sub03/sub03_01.do",
    "/physics/sub04/sub04_01.do",
    "/physics/sub05/sub05_01.do",
    "/physics/edu/edu01.do",
    "/physics/edu/edu02.do",
    "/physics/edu/curri01.do",
    "/physics/edu/sub01.do",
    "/physics/data/curri.do",
    "/physics/data/curri01.do",
    "/physics/data/grad01.do",
    "/physics/info/intro01.do",
    "/physics/info/intro02.do",
    "/physics/info/curri01.do",
    "/physics/curri/curri.do",
    "/physics/curri/under.do",
    "/physics/curri/undergrad.do",
    "/physics/under/curri.do",
    "/physics/under/req.do",
    "/physics/department/under_curri.do",
    "/physics/department/grad_curri.do",
    "/physics/learn/curri.do",
    "/physics/learn/grad.do",
]


def main() -> int:
    for label, index, base in SITES:
        print("\n" + "#" * 60)
        print(f"# {label}  base={base}")
        print("#" * 60)
        home_links = stage_A_home_links(label, index)
        paths = ME_PROBE_PATHS if label == "me" else PHY_PROBE_PATHS
        stage_B_probe_paths(label, base, paths)
        stage_C_followup(label, home_links, index)
    print("\n=== 끝 ===")
    print("위 출력에서 ⭐ 표시 또는 '졸업/이수/교육과정/curriculum' 키워드 있는 URL 을")
    print("scripts/sprint2/dept_list_me_phy.json 의 direct_url 배열에 붙여넣은 뒤")
    print("bash scripts/sprint3/run_dept_grad_me_phy.sh crawl 재실행.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
