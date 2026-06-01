"""Shuttle tool: 충남대 셔틀버스 정보 실시간 fetch.

Strategy:
  1) 정적 안내 페이지(시간표·노선): plus.cnu.ac.kr/html/kr/sub05/sub05_050403.html
  2) 최신 셔틀 운영 변경 공지(통제/단축/임시): 백마광장 게시판 sub07_0701
     '셔틀' 키워드 포함 게시물 최근 N건만.

Reasoning:
  Static page → 평상시 시간표·노선 답변에 활용.
  최신 공지   → "이번 주 운행해?" / "오늘 운휴인가?" 같은 동적 질의에 활용.

키워드:
  셔틀, 셔틀버스, 통학버스, 캠퍼스순환, 교내순환, 보운 셔틀, 운행 시간(셔틀+컨텍스트)
"""
from __future__ import annotations

import re
import time
from typing import Optional

STATIC_URL = "https://plus.cnu.ac.kr/html/kr/sub05/sub05_050403.html"
NOTICE_LIST_URL = "https://plus.cnu.ac.kr/_prog/_board/?code=sub07_0701&site_dvs_cd=kr"

KEYWORDS = [
    "셔틀", "셔틀버스", "통학버스",
    "캠퍼스순환", "교내순환", "보운 셔틀",
]
EXCLUDE = [
    "셔틀콕",  # 배드민턴 등 동음이의 회피
]


class ShuttleTool:
    name = "shuttle_info"
    _cache: dict = {}
    _cache_ttl_s = 300

    def matches(self, query: str) -> bool:
        if not query:
            return False
        if any(x in query for x in EXCLUDE):
            return False
        return any(k in query for k in KEYWORDS)

    def _fetch(self, url: str, key: str) -> str:
        import requests
        now = time.time()
        c = self._cache.get(key)
        if c and (now - c[0] < self._cache_ttl_s):
            return c[1]
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            r.encoding = "utf-8"
            html = r.text
        except Exception as e:
            print(f"[shuttle] fetch {key} failed: {e}", flush=True)
            html = ""
        self._cache[key] = (now, html)
        return html

    @staticmethod
    def _extract_main_text(html: str, max_len: int = 3000) -> str:
        """Pull main body text from the static info page."""
        if not html:
            return ""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            # Prefer #contents or .contents body if present
            body = soup.select_one("#contents") or soup.select_one(".contents") or soup.body or soup
            txt = body.get_text("\n", strip=True)
        except Exception:
            txt = re.sub(r"<[^>]+>", " ", html)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        return txt[:max_len].strip()

    @staticmethod
    def _extract_recent_notices(html: str, k: int = 5) -> list[dict]:
        """Parse the board list page for the latest k posts whose title mentions
        a shuttle keyword."""
        if not html:
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        rows = soup.select("table tr") or soup.select("tr")
        out: list[dict] = []
        for tr in rows:
            text = tr.get_text(" ", strip=True)
            if not text or not any(k_ in text for k_ in ("셔틀", "통학")):
                continue
            a = tr.find("a")
            url = ""
            if a and a.get("href"):
                href = a["href"]
                if href.startswith("?"):
                    url = "https://plus.cnu.ac.kr/_prog/_board/" + href
                elif href.startswith("/"):
                    url = "https://plus.cnu.ac.kr" + href
                else:
                    url = href
            date_m = re.search(r"\d{4}-\d{2}-\d{2}|\d{4}\.\d{2}\.\d{2}", text)
            out.append({
                "title": (a.get_text(" ", strip=True) if a else text)[:120],
                "url": url,
                "date": date_m.group(0) if date_m else "",
            })
            if len(out) >= k:
                break
        return out

    def run(self, query: str) -> Optional[dict]:
        static_html = self._fetch(STATIC_URL, "static")
        notice_html = self._fetch(NOTICE_LIST_URL, "notice_list")
        main_text = self._extract_main_text(static_html)
        notices = self._extract_recent_notices(notice_html, k=5)

        if not main_text and not notices:
            return None

        blocks = []
        if main_text:
            blocks.append(
                f"[출처] 셔틀버스 안내 (정적 페이지) — {STATIC_URL}\n\n{main_text}"
            )
        if notices:
            lines = ["[출처] 최신 셔틀 관련 공지 — " + NOTICE_LIST_URL]
            for n in notices:
                line = f"- ({n['date']}) {n['title']}"
                if n["url"]:
                    line += f"  <{n['url']}>"
                lines.append(line)
            blocks.append("\n".join(lines))
        context_block = "\n\n".join(blocks)

        sources = [{
            "chunk_id": "tool:shuttle",
            "title": "충남대 셔틀버스 안내 (plus.cnu 실시간)",
            "source_url": STATIC_URL,
            "rerank_score": 1.0,
        }]
        for n in notices[:3]:
            if n["url"]:
                sources.append({
                    "chunk_id": "tool:shuttle:notice",
                    "title": n["title"],
                    "source_url": n["url"],
                    "rerank_score": 0.95,
                })
        return {"context": context_block, "sources": sources}
