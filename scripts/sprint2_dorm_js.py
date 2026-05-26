"""4.1 dorm.cnu.ac.kr 메인 페이지 JS 렌더링 시도 + fallback.

Sprint 1 이월: ``https://dorm.cnu.ac.kr/html/kr/`` 가 어댑터 A로 body_len=0.
JS-render 가능성 → Playwright 로 시도. 실패하면 4.2 공지로 fallback documenting.

Playwright 가 설치되지 않은 경우 즉시 skip + fallback 안내.

실행:
  python -m scripts.sprint2_dorm_js
  python -m scripts.sprint2_dorm_js --url https://dorm.cnu.ac.kr/html/kr/
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from crawler.schema import Chunk, write_jsonl  # noqa: E402


def try_playwright(url: str, *, wait_sec: int = 5) -> tuple[bool, str]:
    """Playwright 로 페이지 렌더 후 body text 반환. 실패 시 (False, reason)."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError:
        return False, "playwright not installed (pip install playwright; playwright install chromium)"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx = browser.new_context(user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            ))
            page = ctx.new_page()
            page.goto(url, timeout=30_000)
            page.wait_for_load_state("networkidle", timeout=wait_sec * 1000)
            body = page.evaluate("() => document.body && document.body.innerText")
            browser.close()
            return True, (body or "")[:50_000]
    except Exception as e:
        return False, f"playwright error: {type(e).__name__}: {e}"


def fallback_message(url: str) -> None:
    print(
        f"[fallback] {url} JS 렌더 실패 → 4.1 dorm 메인은 미커버. "
        "평가 영향: 5문제 중 일부는 Sprint 1 day3 4.2 공지로 부분 커버. "
        "RAG fallback 응답으로 'dorm.cnu.ac.kr 공지사항/생활관 안내 페이지를 참조해주세요' 안내."
    )


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="https://dorm.cnu.ac.kr/html/kr/")
    p.add_argument("--out", default="data/sprint2/day3/dorm_js.jsonl")
    p.add_argument("--wait", type=int, default=5)
    args = p.parse_args()

    print(f"[dorm_js] try Playwright: {args.url}")
    ok, payload = try_playwright(args.url, wait_sec=args.wait)
    if not ok:
        print(f"[skip] {payload}")
        fallback_message(args.url)
        # 빈 jsonl 이라도 작성해서 runner 가 일관되게 처리하도록
        os.makedirs(os.path.dirname(args.out), exist_ok=True)
        write_jsonl([], args.out)
        return 0

    body = payload.strip()
    if len(body) < 50:
        print(f"[skip] body too short: {len(body)}자")
        fallback_message(args.url)
        write_jsonl([], args.out)
        return 0

    chunk = Chunk(
        text=body,
        source_type="T4",  # JS 렌더
        source_url=args.url,
        source_title="기숙사 메인 (JS rendered)",
        domains=[4],
        categories=["4.1"],
        freshness="static",
        section_path="dorm_main_js",
        notes="rendered_by=playwright_chromium",
    )
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    write_jsonl([chunk], args.out)
    print(f"OK: 1 chunk / {chunk.char_count}자 → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
