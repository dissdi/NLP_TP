"""학과 졸업요건 페이지 자동 발견 + 크롤.

Sprint 1 이월: ``*/intro/intro01.do`` 가 학과 인사말이라 졸업요건 누락 (35자).

전략:
  1) (discover) 학과 홈 URL 받아서 메뉴 링크 스캔 → 졸업요건 후보 URL 추출
  2) (crawl)    후보 URL을 어댑터 A로 크롤 → chunks

매뉴 키워드 (한국어 대학 사이트 통례):
  졸업요건, 졸업, 이수, 교육과정, 교과과정, 학위, 학과교육과정,
  curriculum, graduation, requirements, course

CLI:
  discover --dept-list scripts/sprint2_dept_list.json --out data/sprint2/day1/dept_grad_candidates.jsonl
  crawl    --candidates data/sprint2/day1/dept_grad_candidates.jsonl --out data/sprint2/day1/dept_grad_chunks.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup, Tag

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import Chunk, write_jsonl  # noqa: E402
from crawler.adapters.a_plus import crawl_page  # noqa: E402


# 졸업요건 키워드: 우선순위 순. 첫 매치된 그룹의 점수가 높을수록 좋은 후보.
KEYWORD_GROUPS = [
    # (score, regex)
    (10, re.compile(r"졸업\s*요건|졸업요건", re.I)),
    (9,  re.compile(r"이수\s*기준|학위\s*수여|학위수여", re.I)),
    (8,  re.compile(r"교육\s*과정|교과\s*과정|교과과정", re.I)),
    (7,  re.compile(r"graduation|requirement", re.I)),
    (6,  re.compile(r"curriculum|coursework", re.I)),
    (5,  re.compile(r"학과\s*교육|전공\s*과목", re.I)),
]
# 제외 키워드 (인사말·연혁 등)
BAD_KEYWORDS = re.compile(r"인사말|연혁|역사|소개|찾아오는|위치", re.I)


def score_link(text: str) -> int:
    """링크 텍스트를 키워드 매칭으로 점수화. 0이면 후보 아님."""
    if not text:
        return 0
    if BAD_KEYWORDS.search(text):
        return 0
    for score, rx in KEYWORD_GROUPS:
        if rx.search(text):
            return score
    return 0


def discover_grad_links(home_url: str, client: HttpClient, *, max_depth: int = 1) -> list[dict]:
    """학과 홈 페이지의 메뉴를 스캔해서 졸업요건 후보 URL 추출.

    max_depth=1: 홈 페이지만. depth=2이면 후보 페이지에서 한 단계 더 탐색.
    """
    try:
        resp = client.get(home_url)
    except Exception as e:
        print(f"  [skip] {home_url} fetch fail: {type(e).__name__}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    seen: set[str] = set()
    cands: list[dict] = []

    for a in soup.find_all("a", href=True):
        if not isinstance(a, Tag):
            continue
        text = a.get_text(" ", strip=True)
        s = score_link(text)
        if s == 0:
            continue
        href = a["href"]
        if href.startswith(("javascript:", "mailto:", "#")):
            continue
        full = urljoin(home_url, href)
        if full in seen:
            continue
        seen.add(full)
        cands.append({
            "score": s,
            "text": text[:80],
            "url": full,
        })

    cands.sort(key=lambda r: -r["score"])
    return cands


def load_dept_list(path: str) -> list[dict]:
    """학과 리스트 로드. 형식:
        [
          {"name": "컴퓨터공학과", "home": "https://cse.cnu.ac.kr/"},
          {"name": "경영학부",     "home": "https://biz.cnu.ac.kr/"},
          ...
        ]
    """
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def cmd_discover(args) -> int:
    client = HttpClient(sleep_between=1.2)
    depts = load_dept_list(args.dept_list)
    print(f"[discover] {len(depts)}개 학과 — 키워드 매칭 메뉴 스캔")

    out_records: list[dict] = []
    for d in depts:
        name = d["name"]
        home = d["home"]
        print(f"  · {name}  {home}")
        cands = discover_grad_links(home, client=client)
        if not cands:
            print(f"      ⚠ 후보 0건 — 메뉴 명칭 다를 가능성, 학과 홈 직접 조사 필요")
            out_records.append({
                "dept_name": name,
                "home": home,
                "candidates": [],
                "status": "no_candidate",
            })
            continue
        top = cands[:3]
        for c in top:
            print(f"      [score={c['score']}] {c['text']}  →  {c['url']}")
        out_records.append({
            "dept_name": name,
            "home": home,
            "candidates": top,
            "status": "ok",
        })

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in out_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n_ok = sum(1 for r in out_records if r["status"] == "ok")
    print(f"\n[discover] {n_ok}/{len(out_records)} 학과 후보 확보 → {args.out}")
    return 0


def cmd_crawl(args) -> int:
    client = HttpClient(sleep_between=1.2)
    records: list[dict] = []
    with open(args.candidates, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"[crawl] {len(records)} 학과")

    all_chunks: list[Chunk] = []
    for rec in records:
        name = rec["dept_name"]
        cands = rec.get("candidates") or []
        if not cands:
            print(f"  · {name}: 후보 없음 — skip")
            continue
        # 최고 점수 후보 1개 (필요시 args.top_n으로 확장)
        top = cands[:args.top_n]
        print(f"  · {name}: {len(top)} 후보 크롤")
        for c in top:
            try:
                chunks = crawl_page(
                    c["url"],
                    domains=[1],
                    categories=["1.2"],
                    client=client,
                )
                for ch in chunks:
                    # 학과명을 source_title에 prepend 해서 청크 식별 용이하게
                    ch.source_title = f"[{name}] {ch.source_title or c['text']}"
                all_chunks.extend(chunks)
                tch = sum(ch.char_count for ch in chunks)
                print(f"      [score={c['score']}] {len(chunks)} chunk / {tch}자  {c['url']}")
            except Exception as e:
                print(f"      [fail] {c['url']}: {type(e).__name__}: {e}")

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    n = write_jsonl(all_chunks, args.out)
    total = sum(c.char_count for c in all_chunks)
    print(f"\n[crawl] OK {n} chunks / {total}자 → {args.out}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="학과 졸업요건 발견·크롤")
    sub = p.add_subparsers(dest="mode", required=True)

    p_d = sub.add_parser("discover", help="학과 메뉴 스캔 → 후보 URL")
    p_d.add_argument("--dept-list", required=True, help="JSON [{name, home}, ...]")
    p_d.add_argument("--out", default="data/sprint2/day1/dept_grad_candidates.jsonl")

    p_c = sub.add_parser("crawl", help="후보 URL을 어댑터 A로 크롤")
    p_c.add_argument("--candidates", required=True)
    p_c.add_argument("--out", default="data/sprint2/day1/dept_grad_chunks.jsonl")
    p_c.add_argument("--top-n", type=int, default=1)

    args = p.parse_args()
    if args.mode == "discover":
        return cmd_discover(args)
    if args.mode == "crawl":
        return cmd_crawl(args)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
