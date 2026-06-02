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
    # 자연어 — 학생식당 / N학 메뉴 / 식당 메뉴
    "학생식당", "학생 식당", "교내식당",
    "점심 메뉴", "저녁 메뉴", "아침 메뉴",
    "오늘 메뉴", "오늘 식단",
    "1학 메뉴", "2학 메뉴", "3학 메뉴", "4학 메뉴",
    "1학 식당", "2학 식당", "3학 식당", "4학 식당",
    "1학식당", "2학식당", "3학식당", "4학식당",
    "1학생회관", "2학생회관", "3학생회관", "4학생회관",
    "제1학생회관", "제2학생회관", "제3학생회관", "제4학생회관",
    "구내식당", "오늘 점심", "오늘 저녁", "오늘 아침", "오늘 학식",
    "조식 메뉴", "중식 메뉴", "석식 메뉴",
]
# Words that should EXCLUDE the cafeteria tool.
# 1) academic-period false matches
# 2) static facility-info queries — tool only returns "today's menu" and cannot
#    answer building-layout / shop-list questions even though "학생회관" matches.
#    Confirmed via D-1 G260528111/112 regression analysis (2026-05-31).
EXCLUDE_IF_PRESENT = [
    "1학기", "2학기", "1학년", "2학년", "3학년", "4학년",
    "장학", "학점", "휴학", "복학",
    # static facility-info signals
    "편의시설", "어떤 식당", "어떤 종류", "어떤 메뉴",
    "복지시설", "편의점", "은행", "카페", "층에",
]



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
        """Parse mobileadmin.cnu menu table with rowspan-aware grid construction.

        Returns a column-labeled string like:
          [조회 날짜] 2026.06.02
          [제1학생회관] 조식·중식·석식: 메뉴운영내역 (상인 운영)
          [제2학생회관]
            - 조식/학생: 정식(1000) 삼계닭죽 ...
            - 중식/직원: 정식(6000) 취나물밥 ...
          ...
        """
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return ""

        date_m = re.search(r"\d{4}\.\d{2}\.\d{2}", html)
        date_str = date_m.group(0) if date_m else ""

        tables = soup.find_all("table")
        if not tables:
            return ""
        menu_table = max(tables, key=lambda t: len(t.find_all("td")))

        # Build 2D grid with rowspan/colspan expansion
        trs = menu_table.find_all("tr")
        grid: list = []
        occupied = {}  # (r, c) -> True if filled by rowspan from prior row
        max_cols = 0
        for r, tr in enumerate(trs):
            row = []
            cells = tr.find_all(["td", "th"])
            c = 0
            for cell in cells:
                while (r, c) in occupied:
                    row.append(occupied[(r, c)])
                    c += 1
                text = cell.get_text(" ", strip=True)
                rs = int(cell.get("rowspan", 1))
                cs = int(cell.get("colspan", 1))
                for dc in range(cs):
                    row.append(text)
                    for dr in range(1, rs):
                        occupied[(r + dr, c + dc)] = text
                    c += 1
            # Drain any trailing rowspan'd cells
            while (r, c) in occupied:
                row.append(occupied[(r, c)])
                c += 1
            grid.append(row)
            max_cols = max(max_cols, len(row))

        if len(grid) < 3:
            return ""

        # Header row: find row containing "학생회관" or "학생회관"-related labels
        header_idx = -1
        for i, row in enumerate(grid):
            joined = " ".join(row)
            if "학생회관" in joined or "생활과학" in joined:
                header_idx = i
                break
        if header_idx < 0:
            return ""

        header = grid[header_idx]
        # Filter cafeteria columns: skip empty + duplicated header labels (구분/직원/학생).
        # "구분" repeats due to colspan=2 over 구분+직원/학생 sub-columns.
        HEADER_NOISE = {"구분", "직원", "학생", "조식", "중식", "석식", ""}
        seen = set()
        cafeteria_names = []
        cafeteria_cols = []  # column indices in grid corresponding to each cafeteria
        for col_idx, c in enumerate(header):
            if not c or c.strip() in HEADER_NOISE:
                continue
            name = c.strip()
            if name in seen:
                continue
            seen.add(name)
            cafeteria_names.append(name)
            cafeteria_cols.append(col_idx)
        if len(cafeteria_names) < 2:
            return ""

        # Data rows: after the header. Each data row format expected:
        #   [meal_label, target_label, cafe1_menu, cafe2_menu, ...]
        # Where meal_label may repeat (rowspan from 조식/중식/석식).
        # Determine first meal-row index and parse meal/target/menus.
        data_rows = grid[header_idx + 1:]

        # Group menus per cafeteria
        cafe_entries: dict = {name: [] for name in cafeteria_names}
        for row in data_rows:
            # Expected first two cols: meal (조식/중식/석식), target (직원/학생)
            if len(row) < 2:
                continue
            meal = row[0].strip() if row[0] else ""
            target = row[1].strip() if len(row) > 1 and row[1] else ""
            if meal not in ("조식", "중식", "석식"):
                continue
            if target not in ("직원", "학생"):
                continue
            for name, col_idx in zip(cafeteria_names, cafeteria_cols):
                menu = row[col_idx] if col_idx < len(row) else ""
                menu_text = (menu or "").strip()
                if not menu_text:
                    continue
                # Skip uninformative cells but keep "운영안함" as info
                cafe_entries[name].append((meal, target, menu_text))

        # Format output
        lines = []
        if date_str:
            lines.append(f"[조회 날짜] {date_str}")
            lines.append("")
        for name in cafeteria_names:
            entries = cafe_entries.get(name, [])
            lines.append(f"[{name}]")
            # Special handling: if every entry is "메뉴운영내역" → 상인 운영
            unique_menus = set(e[2] for e in entries)
            if entries and unique_menus == {"메뉴운영내역"}:
                lines.append("- 푸드코트 형식 (라면·양식·스낵·한식·일식·중식 코너별 단품 주문, 정해진 정식 없음)")
            elif not entries:
                lines.append("- 정보 없음")
            else:
                for meal, target, menu in entries:
                    lines.append(f"- {meal}/{target}: {menu}")
            lines.append("")
        text = "\n".join(lines).strip()
        # Require non-trivial content
        if "정식" not in text and "메뉴운영내역" not in text:
            return ""
        return text


    def run(self, query: str) -> Optional[dict]:
        html = self._fetch_html()
        menu_text = self._parse_menu(html) if html else ""

        # 항상 동봉되는 운영 안내 (LLM이 grounded 답변을 만들 anchor).
        OPERATIONAL_INFO = (
            "충남대학교 학생식당 운영 정보:\n"
            "운영 식당 5곳 — 제1학생회관, 제2학생회관, 제3학생회관, 제4학생회관, 생활과학대학 식당.\n"
            "참고: 제1학생회관은 푸드코트 형식(라면·양식·스낵·한식·일식·중식 코너별 단품 주문)이라 정해진 정식 메뉴가 없습니다.\n"
            "운영 시간: 학기 중 평일 정상 운영 / 주말·공휴일·방학 미운영 또는 단축 운영.\n"
            "당일 점심·저녁 상세 메뉴는 실시간 모바일 페이지에서 확인: " + MENU_URL
        )

        # Context 구성: 메뉴(있을 때 우선) → 운영 안내(항상 보조)
        parts = []
        if menu_text and len(menu_text) >= 100:
            parts.append("[오늘의 메뉴 — 실시간 fetch]\n" + menu_text)
        parts.append(OPERATIONAL_INFO)
        body = "\n\n".join(parts)

        context_block = (
            "[출처] 충남대 식당 메뉴 (실시간) — " + MENU_URL + "\n\n"
            + body
        )
        sources = [{
            "chunk_id": "tool:cafeteria",
            "title": "충남대 학식 메뉴 (mobileadmin 실시간)",
            "source_url": MENU_URL,
            "rerank_score": 1.0,
        }]
        return {"context": context_block, "sources": sources}
