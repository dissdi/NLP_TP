"""Dormitory (생활관) cafeteria menu tool.

dorm.cnu.ac.kr is client-rendered (Sprint 2 confirmed), so requests/urllib
return empty body. We fetch via Playwright (already a dependency for adapter F).

Activates on dorm-specific keywords ONLY so it does not collide with the
student-union cafeteria tool. TOOLS list places this tool BEFORE the regular
cafeteria so dorm queries match first.
"""
from __future__ import annotations

import time
from typing import Optional

DORM_URL = "https://dorm.cnu.ac.kr/html/kr/sub04/sub04_040301.html"

KEYWORDS = [
    "기숙사 식당",
    "기숙사 메뉴",
    "기숙사 식사",
    "기숙사 밥",
    "관식",
    "생활관 식당",
    "생활관 메뉴",
    "생활관 밥",
    "생활관 식사",
    "기숙사식당",
    "생활관식당",
]


class DormCafeteriaTool:
    name = "dorm_cafeteria_menu"
    _cache: dict = {}
    _cache_ttl_s = 600  # 10 min

    def matches(self, query: str) -> bool:
        if not query:
            return False
        return any(k in query for k in KEYWORDS)

    def _fetch_via_playwright(self) -> str:
        # cache
        now = time.time()
        cached = self._cache.get("text")
        if cached and (now - cached[0] < self._cache_ttl_s):
            return cached[1]
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("[dorm_cafeteria] playwright not installed", flush=True)
            return ""
        text = ""
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    context = browser.new_context(
                        user_agent=(
                            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                        ),
                        locale="ko-KR",
                    )
                    page = context.new_page()
                    page.goto(DORM_URL, wait_until="networkidle", timeout=20000)
                    # Best-effort: get the main content area, fall back to full body
                    body_text = page.inner_text("body")
                    text = body_text or ""
                finally:
                    browser.close()
        except Exception as e:
            print(f"[dorm_cafeteria] playwright error: {e}", flush=True)
            return ""
        # cache
        self._cache["text"] = (now, text)
        return text

    def run(self, query: str) -> Optional[dict]:
        text = self._fetch_via_playwright()
        if not text or len(text.strip()) < 50:
            # Graceful fallback: external link guidance
            context_block = (
                f"[출처] 충남대 기숙사 식당 메뉴 — {DORM_URL}\n\n"
                f"기숙사 식당의 일별 메뉴는 위 페이지에서 직접 확인하세요. "
                f"본 시스템은 해당 페이지의 실시간 식단을 자동으로 가져오지 못했습니다."
            )
        else:
            # Trim to a reasonable size for LLM context (4k chars)
            trimmed = text.strip()[:4000]
            context_block = (
                f"[출처] 충남대 기숙사 식당 메뉴 (실시간) — {DORM_URL}\n\n{trimmed}"
            )
        sources = [{
            "chunk_id": "tool:dorm_cafeteria",
            "title": "충남대 기숙사 식당 메뉴 (dorm.cnu.ac.kr 실시간)",
            "source_url": DORM_URL,
            "rerank_score": 1.0,
        }]
        return {"context": context_block, "sources": sources}
