"""Notice tool: 충남대 백마광장 / 학사공지 게시판 실시간 fetch.

Strategy:
  학사공지 sub07_0702 + 일반공지 sub07_0701 두 게시판 상위 N건을 합쳐
  최신 공지 리스트와 (선택) 첫 게시물 본문 일부를 LLM context로 제공.

활성 키워드: "공지", "공지사항", "최근", "최신", "오늘 공지" 등 + 학사일정 신호.
"""
from __future__ import annotations

import re
import time
from typing import Optional

NOTICE_BOARDS = [
    {"name": "일반공지(백마광장)",
     "code": "sub07_0701",
     "url": "https://plus.cnu.ac.kr/_prog/_board/?code=sub07_0701&site_dvs_cd=kr"},
    {"name": "학사공지",
     "code": "sub07_0702",
     "url": "https://plus.cnu.ac.kr/_prog/_board/?code=sub07_0702&site_dvs_cd=kr"},
]

KEYWORDS = [
    "공지", "공지사항", "알림",
    "최근 공지", "최신 공지", "오늘 공지",
    "최근 알림", "최신 알림",
    "새 공지", "새로운 공지",
]
# 학사일정 신호 — '언제' 같은 동적 시간 질의 + 명사
ACADEMIC_TIME_KEYWORDS = [
    "수강신청", "수강 정정", "성적 정정", "휴학", "복학",
    "등록금", "졸업식", "입학식", "방학", "개강",
    "시험", "기말", "중간",
]
EXCLUDE = [
    "장학",  # 장학공지는 별도 라우팅 영역 (학생복지 페이지)
]


class NoticeTool:
    name = "notice_recent"
    _cache: dict = {}
    _cache_ttl_s = 300

    def matches(self, query: str) -> bool:
        if not query:
            return False
        if any(x in query for x in EXCLUDE):
            return False
        if any(k in query for k in KEYWORDS):
            return True
        # 학사일정 키워드 + 동적 시간 cue
        if any(k in query for k in ACADEMIC_TIME_KEYWORDS) and \
           any(c in query for c in ("언제", "기간", "일정", "며칠", "몇 일")):
            return True
        return False

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
            print(f"[notice] fetch {key} failed: {e}", flush=True)
            html = ""
        self._cache[key] = (now, html)
        return html

    @staticmethod
    def _extract_list(html: str, k: int = 8) -> list[dict]:
        if not html:
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        rows = soup.select("table tr")
        out: list[dict] = []
        for tr in rows:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["td", "th"])]
            if len(cells) < 2:
                continue
            a = tr.find("a")
            if not a:
                continue
            title = a.get_text(" ", strip=True)
            if not title or len(title) < 3:
                continue
            href = a.get("href", "")
            if href.startswith("?"):
                url = "https://plus.cnu.ac.kr/_prog/_board/" + href
            elif href.startswith("/"):
                url = "https://plus.cnu.ac.kr" + href
            else:
                url = href
            text = " | ".join(cells)
            date_m = re.search(r"20\d{2}-\d{2}-\d{2}|20\d{2}\.\d{2}\.\d{2}", text)
            out.append({
                "title": title[:140],
                "url": url,
                "date": date_m.group(0) if date_m else "",
            })
            if len(out) >= k:
                break
        return out

    def run(self, query: str) -> Optional[dict]:
        all_items: list[dict] = []
        for b in NOTICE_BOARDS:
            html = self._fetch(b["url"], b["code"])
            items = self._extract_list(html, k=5)
            for it in items:
                it["board"] = b["name"]
            all_items.extend(items)
        if not all_items:
            return None

        # Sort by date desc when available, then keep top 8
        all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
        top = all_items[:8]

        lines = ["[출처] 충남대 최신 공지 (실시간)"]
        for it in top:
            lines.append(f"- [{it['board']}] ({it['date']}) {it['title']}  <{it['url']}>")
        context_block = "\n".join(lines)

        sources = []
        for it in top[:5]:
            sources.append({
                "chunk_id": "tool:notice",
                "title": it["title"],
                "source_url": it["url"],
                "rerank_score": 1.0,
            })
        return {"context": context_block, "sources": sources}
