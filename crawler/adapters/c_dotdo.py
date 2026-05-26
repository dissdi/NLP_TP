"""어댑터 C — Spring .do (job.cnu.ac.kr 등).

URL 패턴 C: ``job.cnu.ac.kr/job/intro/intro01.do`` 같은 Spring 컨트롤러 응답.
일반적으로 정적 HTML 응답(서버 렌더링)이라 어댑터 A의 정적 처리 로직과 본질적으로 동일.
사이트별 컨테이너 셀렉터 차이는 inspect_page의 자동 div 탐지(top_text_divs)로 흡수.

이 모듈은 a_plus의 inspect_page/crawl_page를 재활용하는 가벼운 wrapper.
job.cnu.ac.kr 특유의 셀렉터가 필요해지면 여기서 보강한다.
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.http import HttpClient  # noqa: E402
from crawler.schema import write_jsonl  # noqa: E402
from crawler.adapters.a_plus import (  # noqa: E402
    inspect_page, crawl_page, print_inspect,
)


def main() -> int:
    p = argparse.ArgumentParser(description="Adapter C (Spring .do)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_i = sub.add_parser("inspect", help="페이지 구조 진단")
    p_i.add_argument("url")

    p_c = sub.add_parser("crawl", help="청크 추출 → JSON Lines")
    p_c.add_argument("url")
    p_c.add_argument("--domains", default="7", help="콤마 구분 도메인 (기본 7: 진로·취업)")
    p_c.add_argument("--categories", default="")
    p_c.add_argument("--out", default="data/sprint0/c_dotdo_chunks.jsonl")

    args = p.parse_args()
    client = HttpClient()

    if args.mode == "inspect":
        rep = inspect_page(args.url, client=client)
        print_inspect(rep)
        return 0

    if args.mode == "crawl":
        domains = [int(d) for d in args.domains.split(",") if d.strip()]
        categories = [c for c in args.categories.split(",") if c.strip()]
        chunks = crawl_page(args.url, domains=domains, categories=categories, client=client)
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        n = write_jsonl(chunks, args.out)
        total = sum(c.char_count for c in chunks)
        print(f"OK: {n} chunks → {args.out}")
        print(f"total_chars = {total}")
        for c in chunks[:3]:
            print("---", c.section_path, f"({c.char_count}자)")
            print(c.text[:200])
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
