"""어댑터 D — library.cnu.ac.kr webcontent.

URL 패턴: ``library.cnu.ac.kr/webcontent/info/{ID}`` 형식.
도서관 사이트 자체 CMS. 정적 HTML 응답이라 어댑터 A의 정적 처리 로직 재사용.
FAQ 페이지(``/faqlib/faq?code=all``)는 Q&A 쌍 추출이 필요 — Sprint 1에서 별도 처리.

이 모듈은 a_plus의 inspect_page/crawl_page를 재활용하는 가벼운 wrapper.
도서관 CMS 특유의 셀렉터가 필요하면 여기서 보강한다.
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
    p = argparse.ArgumentParser(description="Adapter D (library webcontent)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_i = sub.add_parser("inspect", help="페이지 구조 진단")
    p_i.add_argument("url")

    p_c = sub.add_parser("crawl", help="청크 추출 → JSON Lines")
    p_c.add_argument("url")
    p_c.add_argument("--domains", default="3", help="콤마 구분 도메인 (기본 3: 도서관)")
    p_c.add_argument("--categories", default="")
    p_c.add_argument("--out", default="data/sprint0/d_library_chunks.jsonl")

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
