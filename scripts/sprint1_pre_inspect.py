"""Sprint 1 사전 정비 — dorm/gymn/health CMS 확인 + 어댑터 셀렉터 검증.

용도: Sprint 1 진입 직전 1회 실행.

체크 항목:
  1. dorm.cnu.ac.kr — plus 같은 CMS인지 (#contents)
  2. gymn.cnu.ac.kr — jwxe (#jwxe_main_content)
  3. health.cnu.ac.kr — jwxe
  4. cnustudent.cnu.ac.kr — 자체 (.main_con_wrap)
  5. 어댑터 A의 CONTENT_CONTAINER_CANDIDATES가 위 4개를 모두 매칭하는지

실행:
  python -m scripts.sprint1_pre_inspect
  python -m scripts.sprint1_pre_inspect --verbose
"""

from __future__ import annotations

import argparse
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bs4 import BeautifulSoup  # noqa: E402
from crawler.http import HttpClient  # noqa: E402
from crawler.adapters.a_plus import (  # noqa: E402
    CONTENT_CONTAINER_CANDIDATES,
    inspect_page,
)


# 사전 inspect 대상 — Sprint 0 후속 검증
TARGETS = [
    {
        "label": "dorm 메인",
        "url": "https://dorm.cnu.ac.kr/html/kr/",
        "expect": "plus CMS 가능성 — #contents",
    },
    {
        "label": "dorm 알림마당",
        "url": "https://dorm.cnu.ac.kr/_prog/_board/?code=sub05_0501",
        "expect": "게시판 어댑터 B 동일 패턴",
    },
    {
        "label": "gymn 인트로",
        "url": "https://gymn.cnu.ac.kr/gymn/info/usage-fee.do",
        "expect": "jwxe — #jwxe_main_content",
    },
    {
        "label": "health 인덱스",
        "url": "https://health.cnu.ac.kr/health/index.do",
        "expect": "jwxe — #jwxe_main_content",
    },
    {
        "label": "health FAQ",
        "url": "https://health.cnu.ac.kr/health/info/faq.do",
        "expect": "jwxe FAQ — 시드 가치 확인",
    },
    {
        "label": "cnustudent 메인",
        "url": "https://cnustudent.cnu.ac.kr/",
        "expect": "자체 CMS — .main_con_wrap",
    },
]


def detect_cms(soup: BeautifulSoup) -> tuple[str, int]:
    """주요 컨테이너 매칭으로 CMS 추정. (cms명, 본문 길이) 반환."""
    checks = [
        ("plus", lambda s: s.find(attrs={"id": "contents"})),
        ("jwxe", lambda s: s.find(attrs={"id": "jwxe_main_content"})),
        ("library", lambda s: s.find(attrs={"id": "divContent"})),
        ("cnustudent", lambda s: s.find(attrs={"class": "main_con_wrap"})),
    ]
    for name, fn in checks:
        el = fn(soup)
        if el is not None:
            return name, len(el.get_text(" ", strip=True))
    return "unknown", 0


def main() -> int:
    p = argparse.ArgumentParser(description="Sprint 1 pre-inspect")
    p.add_argument("--verbose", action="store_true", help="inspect_page 풀 리포트 출력")
    p.add_argument(
        "--url", default=None,
        help="단일 URL만 검사 (기본은 TARGETS 전체)"
    )
    args = p.parse_args()

    client = HttpClient(sleep_between=0.5)

    targets = [{"label": "ad-hoc", "url": args.url, "expect": ""}] if args.url else TARGETS

    print(f"# Sprint 1 pre-inspect — {len(targets)}개 대상\n")
    print(f"어댑터 A CONTENT_CONTAINER_CANDIDATES = {len(CONTENT_CONTAINER_CANDIDATES)}개 등록\n")

    results = []
    for t in targets:
        url = t["url"]
        print(f"--- {t['label']}")
        print(f"  url   : {url}")
        print(f"  expect: {t['expect']}")
        try:
            resp = client.get(url)
            soup = BeautifulSoup(resp.text, "lxml")
            cms, body_len = detect_cms(soup)
            print(f"  CMS   : {cms}  body_len={body_len}")
            # 어댑터 A의 후보 셀렉터 매칭 결과
            matches = []
            for kind, key in CONTENT_CONTAINER_CANDIDATES:
                if kind == "id":
                    el = soup.find(attrs={"id": key})
                else:
                    el = soup.find(attrs={"class": key})
                if el is not None:
                    matches.append((kind, key, len(el.get_text(" ", strip=True))))
            print(f"  adapter-A hits ({len(matches)}):")
            for kind, key, n in matches[:4]:
                print(f"    {kind}={key}  ({n}자)")
            results.append({"label": t["label"], "url": url, "cms": cms,
                            "body_len": body_len, "matches": len(matches)})
            if args.verbose:
                rep = inspect_page(url, client=client)
                print("  --- inspect_page 헤딩 ---")
                print(f"    h1: {rep.h1_list[:3]}")
                print(f"    h2: {rep.h2_list[:3]}")
                print(f"  --- sample 200자 ---")
                print(f"    {rep.sample_text[:200]}")
        except Exception as e:
            print(f"  ✗ ERR: {type(e).__name__}: {e}")
            results.append({"label": t["label"], "url": url, "error": str(e)})
        print()

    # 요약
    print("# 요약")
    ok = sum(1 for r in results if "error" not in r)
    print(f"  접근 성공: {ok}/{len(results)}")
    if ok == len(results):
        unk = [r for r in results if r.get("cms") == "unknown"]
        if unk:
            print(f"  ⚠ unknown CMS {len(unk)}개 — 어댑터 A 셀렉터 보강 필요:")
            for r in unk:
                print(f"     - {r['label']}: {r['url']}")
        else:
            print("  ✓ 모든 대상이 어댑터 A 셀렉터로 매칭 가능 — Sprint 1 본격 진입 OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
