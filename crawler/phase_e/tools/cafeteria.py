"""Cafeteria menu tool: fetch today's menu from mobileadmin.cnu.ac.kr.

The page renders a table of 5 cafeterias x (조식/중식/석식) x (직원/학생).
We fetch HTML, parse the table, and return a Markdown-ish text block that the
LLM can ground its answer on.

Activates on keywords: 학식, 메뉴, 식단, 학생회관, 생활과학, 1학, 2학, 3학, 4학,
조식, 중식, 석식, 아침, 점심, 저녁 ...
"""
from __future__ import annotations

import re
import time
from typing import Optional

MENU_URL = "https://mobileadmin.cnu.ac.kr/food/index.jsp"

# Precise keywords only — "1학" alone causes false matches with "1학기", "1학년".
# We require either dining-context words OR specific compound forms.
KEYWORDS = [
    "학식", "식단", "학생회관 식당", "학생회관 메뉴",
    "1학 메뉴", "2학 메뉴", "3학 메뉴", "4학 메뉴",
    "1학 식당", "2학 식당", "3학 식당", "4학 식당",
    "1학식당", "2학식당", "3학식당", "4학식당",
    "1학생회관", "2학생회관", "3학생회관", "4학생회관",
    "제1학생회관", "제2학생회관", "제3학생회관", "제4학생회관",
    "구내식당", "오늘 점심", "오늘 저녁", "오늘 아침", "오늘 학식",
    "조식 메뉴", "중식 메뉴", "석식 메뉴",
]
# Words that should EXCLUDE the cafeteria tool (academic-period false matches)
EXCLUDE_IF_PRESENT = ["1학기", "2학기", "1학년", "2학년", "3학년", "4학년", "장학", "학점", "휴학", "복학"]



class CafeteriaTool:
    name = "cafeteria_menu"
    _cache: dict = {}  # crude TTL cache so multiple queries in the same minute don't refetch
    _cache_ttl_s = 300  # 5 min

    def matches(self, query: str) -> bool:
        if not query:
            return False
        if any(neg in query for neg in EXCLUDE_IF_PRESENT):
            return False
        return any(k in query for k in KEYWORDS)

    def _fetch_html(self) -> str:
        import requests
        # cache
        now = time.time()
        cached = self._cache.get("html")
        if cached and (now - cached[0] < self._cache_ttl_s):
            return cached[1]
        r = requests.get(MENU_URL, timeout=8)
        r.encoding = "utf-8"
        html = r.text
        self._cache["html"] = (now, html)
        return html

    @staticmethod
    def _parse_menu(html: str) -> str:
        """Parse the menu table out of mobileadmin.cnu HTML.

        Strategy: rely on the simple, stable structure of the page —
        first `table.menu_div` (if class) or first table after a `요일별` marker.
        Fall back to extracting all <td> cells in order.
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            # Fallback: regex strip tags
            text = re.sub(r"<[^>]+>", " ", html)
            text = re.sub(r"\s+", " ", text)
            return text.strip()[:4000]

        # Try to find the date header e.g. "금요일 2026.05.29"
        date_match = re.search(r"\d{4}\.\d{2}\.\d{2}", html)
        date_str = date_match.group(0) if date_match else ""

        tables = soup.find_all("table")
        if not tables:
            return ""

        # Prefer the largest table (assumed to be the menu matrix)
        menu_table = max(tables, key=lambda t: len(t.find_all("td")))
        rows = []
        for tr in menu_table.find_all("tr"):
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if not any(cells):
                continue
            rows.append(" | ".join(cells))
        text = "\n".join(rows)
        if date_str:
            text = f"[조회 날짜] {date_str}\n\n" + text
        return text.strip()

    def run(self, query: str) -> Optional[dict]:
        html = self._fetch_html()
        if not html:
            return None
        menu_text = self._parse_menu(html)
        if not menu_text:
            return None
        # Format context for the LLM
        context_block = (
            "[출처] 충남대 식당 메뉴 (실시간) — " + MENU_URL + "\n\n"
            + menu_text
        )
        sources = [{
            "chunk_id": "tool:cafeteria",
            "title": "충남대 학식 메뉴 (mobileadmin 실시간)",
            "source_url": MENU_URL,
            "rerank_score": 1.0,  # synthetic, tool source is authoritative
        }]
        return {"context": context_block, "sources": sources}
