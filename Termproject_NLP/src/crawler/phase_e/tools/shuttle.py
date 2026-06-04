"""Shuttle tool: 충남대 셔틀버스 정보 (정적 시간표 + 실시간 변경 공지).

Strategy:
  1) 정적 시간표·노선: STATIC_FALLBACK 상수 (학기간 거의 안 바뀜).
  2) 실시간 fetch: 안내 페이지(JS 렌더 가능성)와 백마광장 게시판의 셔틀 관련 공지.
     fetch가 풍부히 들어오면 보조 자료로 동봉, 비면 정적 시간표만으로도 답변 가능.

키워드: 셔틀, 셔틀버스, 통학버스, 캠퍼스순환, 교내순환, 보운 셔틀
EXCLUDE: 셔틀콕 (배드민턴)
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
    "셔틀콕",
]

STATIC_FALLBACK = """충남대학교 학교셔틀버스 운영 안내 (2026학년도)

운영 기준:
- 학기 중 평일 주간 운영
- 평일 야간, 주말, 공휴일, 방학, 수학능력시험일(10시 이전) 미운영
- 운행시간은 학사일정·교통상황 등에 따라 변경될 수 있음 (5분 내외 오차)

운행 노선:
1) 교내순환 (대덕캠퍼스 내)
2) 캠퍼스 순환 (대덕캠퍼스 ↔ 보운캠퍼스)

[교내순환 시간표]
오전: 08:20(월평역 등교), 08:30, 09:30, 09:40, 10:30, 11:30
오후: 13:30, 14:30, 15:30, 16:30, 17:30
첫차 08:30 · 막차 17:30 · 1일 10회 운행

교내순환 노선:
정심화 국제문화회관 → 사회과학대학 입구(한누리회관 뒤) → 서문(공동실험실습관 앞) →
음악2호관 앞 → 공동동물실험센터(회차) → 체육관 입구 → 예술대학 앞 →
도서관 앞(대학본부 옆 농대방향) → 학생생활관 3거리 → 농업생명과학대학 앞 →
동문주차장 → 농업생명과학대학 앞 → 도서관 앞(도서관삼거리 방향) → 예술대학 앞 →
서문 → 사회과학대학 입구 → 산학연교육연구관 앞 → 정심화 국제문화회관
※ 오전(등교) 1회만 월평역 출발

[캠퍼스 순환 시간표]
오전: 08:10(대덕 출발, 골프연습장), 08:50(보운 회차)
오후: 미운영
1일 1회(회차)

캠퍼스 순환 노선:
①골프연습장 출발(08:10) → ②중앙도서관(08:11) → ③산학연교육연구관(08:12) →
④충남대학교입구 버스정류장(홈플러스유성점 방면)(08:13) → ⑤월평역(08:15) →
⑥보운캠퍼스(회차, 08:50) → ⑦다솔아파트 건너편 → 제2학생회관 →
중앙도서관 → 골프연습장 도착

문의: 총괄(5052), 총무과(배차·운행) 042-821-5115
"""


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
        # Colab 네트워크에서 plus.cnu.ac.kr 8s 타임아웃 빈번. 20s + 1회 재시도.
        html = ""
        for attempt in range(2):
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                r.encoding = "utf-8"
                html = r.text
                break
            except Exception as e:
                print("[shuttle] fetch " + key + " try " + str(attempt + 1) + " failed: " + str(e), flush=True)
                if attempt == 0:
                    time.sleep(1.5)
        self._cache[key] = (now, html)
        return html

    @staticmethod
    def _extract_main_text(html: str, max_len: int = 3000) -> str:
        if not html:
            return ""
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header"]):
                tag.decompose()
            body = soup.select_one("#contents") or soup.select_one(".contents") or soup.body or soup
            txt = body.get_text("\n", strip=True)
        except Exception:
            txt = re.sub(r"<[^>]+>", " ", html)
        txt = re.sub(r"\n{3,}", "\n\n", txt)
        return txt[:max_len].strip()

    @staticmethod
    def _extract_recent_notices(html: str, k: int = 5) -> list:
        if not html:
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        rows = soup.select("table tr") or soup.select("tr")
        out = []
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

        blocks = []
        # 정적 시간표 항상 동봉 — 학기간 거의 안 바뀜.
        blocks.append("[출처] 충남대 셔틀버스 안내 (운영 시간표·노선)\n\n" + STATIC_FALLBACK)
        # 실시간 fetch는 보조 자료. "시간표" 키워드가 포함된 충실한 텍스트일 때만 추가.
        if main_text and "시간표" in main_text and len(main_text) > 500:
            blocks.append("[출처 보조] 실시간 페이지 발췌 — " + STATIC_URL + "\n\n" + main_text)
        if notices:
            lines = ["[출처] 최신 셔틀 관련 공지 — " + NOTICE_LIST_URL]
            for n in notices:
                line = "- (" + n["date"] + ") " + n["title"]
                if n["url"]:
                    line += "  <" + n["url"] + ">"
                lines.append(line)
            blocks.append("\n".join(lines))
        context_block = "\n\n".join(blocks)

        sources = [{
            "chunk_id": "tool:shuttle",
            "title": "충남대 셔틀버스 안내 (운영 시간표·노선)",
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
