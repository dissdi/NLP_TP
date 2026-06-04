"""Notice tool: 충남대 백마광장 / 학사공지 게시판 실시간 fetch + 학사일정 fallback.

Strategy:
  - 학사공지 sub07_0702 + 일반공지 sub07_0701 두 게시판 상위 N건 수집.
  - 학사일정 키워드(수강신청·시험·휴학 등)면 학사일정 정적 fallback도 함께 제공.
  - 학사일정 키워드면 게시물 제목에 그 키워드 포함된 건만 우선 노출.

활성 키워드: "공지", "공지사항", "최근/최신", "오늘 공지" 등 + 학사일정 신호.
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
ACADEMIC_CAL_URL = "https://plus.cnu.ac.kr/_prog/academic_calendar/?menu_dvs_cd=05020101"

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

# 학사일정 정적 fallback — 학기간 거의 안 바뀜.
# 출처: plus.cnu.ac.kr/_prog/academic_calendar/?menu_dvs_cd=05020101 (Phase C 크롤링본)
ACADEMIC_CAL_FALLBACK = """충남대학교 2026학년도 학사일정 (대학 일정)

[1학기]
01.26(월)~01.28(수) 2026학년도 제1학기 예비수강신청
01.29(목)~02.04(수) 학사학위취득 유예 신청
02.02(월)~02.06(금) 2026학년도 제1학기 수강신청
02.02(월)~02.27(금) 휴학 및 복학 신청
02.24(화)~02.27(금) 제1학기 재학생 등록금 납부
02.27(금) 입학식(2026학년도)
03.03(화) 제1학기 개강일
03.03(화)~03.09(월) 수강신청 확인 및 변경
03.23(월)~03.26(목) 수강신청 취소
03.30(월)~04.03(금) 2025학년도 후기 조기졸업 신청
05.07(목)~05.11(월) 하기 계절학기 수강신청
06.22(월) 하기방학 / 하기 계절학기 시작
07.10(금) 제1학기 성적발표

[2학기]
07.27(월)~07.29(수) 제2학기 예비수강신청
08.03(월)~08.07(금) 제2학기 수강신청
08.03(월)~08.31(월) 휴학 및 복학 신청

[성적·등록 관련]
01.13(화) 제2학기 성적발표
01.20(화) 동기 계절학기 성적발표
02.25(수) 2025학년도 전기 학위수여식
07.20(월) 하기 계절학기 성적발표

문의: 학사지원과 042-821-5025 (수강신청·성적), 재무과(등록금)
"""


def _filter_by_keyword(items: list, keyword: str) -> list:
    """제목에 keyword 포함된 항목만 추림. 결과 비면 원본 그대로 리턴."""
    if not keyword:
        return items
    hit = [it for it in items if keyword in it.get("title", "")]
    return hit if hit else items


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
        if any(k in query for k in ACADEMIC_TIME_KEYWORDS) and \
           any(c in query for c in ("언제", "기간", "일정", "며칠", "몇 일")):
            return True
        return False

    def _matched_academic_keyword(self, query: str) -> str:
        """query에 들어 있는 ACADEMIC_TIME_KEYWORDS의 첫 매칭 반환."""
        for k in ACADEMIC_TIME_KEYWORDS:
            if k in query:
                return k
        return ""

    def _fetch(self, url: str, key: str) -> str:
        import requests
        now = time.time()
        c = self._cache.get(key)
        if c and (now - c[0] < self._cache_ttl_s):
            return c[1]
        # Colab 환경에서 plus.cnu.ac.kr 응답이 8s 안에 못 끝나는 경우 다수 관측 →
        # RAG 폴백으로 빠지면 q005 같은 학사공지 질의에서 컨텍스트 폭증 + OOM.
        # 타임아웃 20s + 1회 재시도(짧은 backoff)로 견고화.
        html = ""
        for attempt in range(2):
            try:
                r = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
                r.encoding = "utf-8"
                html = r.text
                break
            except Exception as e:
                print("[notice] fetch " + key + " try " + str(attempt + 1) + " failed: " + str(e), flush=True)
                if attempt == 0:
                    time.sleep(1.5)
        self._cache[key] = (now, html)
        return html

    @staticmethod
    def _extract_list(html: str, k: int = 8) -> list:
        if not html:
            return []
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        rows = soup.select("table tr")
        out = []
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
        all_items = []
        for b in NOTICE_BOARDS:
            html = self._fetch(b["url"], b["code"])
            items = self._extract_list(html, k=8)
            for it in items:
                it["board"] = b["name"]
            all_items.extend(items)

        # 학사일정 키워드 매칭 시 해당 키워드로 게시물 필터 + 학사일정 fallback 동봉
        academic_key = self._matched_academic_keyword(query)
        if academic_key:
            all_items = _filter_by_keyword(all_items, academic_key)

        if not all_items and not academic_key:
            return None

        # Sort by date desc
        all_items.sort(key=lambda x: x.get("date", ""), reverse=True)
        top = all_items[:8]

        blocks = []
        if academic_key:
            blocks.append("[출처] 충남대 학사일정 — " + ACADEMIC_CAL_URL + "\n\n" + ACADEMIC_CAL_FALLBACK)

        if top:
            lines = ["[출처] 충남대 최신 공지 (실시간)"]
            for it in top:
                lines.append("- [" + it["board"] + "] (" + it["date"] + ") " + it["title"] + "  <" + it["url"] + ">")
            blocks.append("\n".join(lines))

        context_block = "\n\n".join(blocks)

        sources = []
        if academic_key:
            sources.append({
                "chunk_id": "tool:notice:academic_cal",
                "title": "충남대 학사일정 (2026학년도)",
                "source_url": ACADEMIC_CAL_URL,
                "rerank_score": 1.0,
            })
        for it in top[:5]:
            sources.append({
                "chunk_id": "tool:notice",
                "title": it["title"],
                "source_url": it["url"],
                "rerank_score": 1.0,
            })
        return {"context": context_block, "sources": sources}
