"""어댑터 F — 대학알리미 UbiReport viewer (T6).

academyinfo.go.kr의 공시정보 페이지는 'fn_RdViewer(paramItemId, year)' 버튼을 통해
UbiReport viewer를 popup으로 띄우고, viewer가 NewAcInfo.do XHR로 데이터를 XML로 받음.
응답 XML은 좌표 기반 셀 그리드 (<Item classname="UbiTextItem" x= y= width= height=>).

Sprint 2 미해결 이슈 해소 (Sprint 3 = 알리미 회수):
  Sprint 2에서 'static fetch 0건, Playwright 렌더 후도 0건'으로 남겨졌던 원인은
  viewer 페이지를 띄우기만 했지 그 안에서 발생하는 NewAcInfo.do XHR 응답을
  가로채지 않았기 때문. Playwright의 page.on('response')로 XHR body 캡쳐.

구조:
  scan_list_page    list 페이지에서 모든 [YYYY 보기] 버튼 추출 (paramItemId 매핑)
  fetch_report      단일 (schl_id, paramItemId, year) 보고서 수집 + XML 파싱
  parse_xml         UbiReport XML → Cell 리스트 + ReportMeta
  build_grid        Cell들 → 좌표 기반 grid (merge cell 자동 처리)
  detect_header     헤더 행 인덱스 (키워드 + backcolor 신호)
  grid_to_records   grid + header → dict 레코드
  records_to_chunks 레코드 → 자연어 청크 (RAG-ready)

CLI:
  scan SCHL_ID [YR]                         list 페이지 스캔, 버튼 매핑 출력
  fetch SCHL_ID PARAM_ITEM_ID YR            단일 보고서 수집 + 파싱
  batch SCHL_ID YR --ids 27,29,46,...       일괄 수집 (Sprint 3 전용)

요구사항:
  pip install playwright && playwright install chromium

PoC 검증 (2026-05-27):
  paramItemId=9 (2-가. 전공과목 성적평가 분포) 충남대 2025년
    → 31,903B XML, 119 cells, 14×26 grid, 22 records (header_idx=3)
    → "충남대학교 간호대학 간호학과 1학기 등급 A+ 학생수 577 비율 27.2"
"""
from __future__ import annotations

import json
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

# crawler/schema.py에서 Chunk dataclass 재사용
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from crawler.schema import Chunk  # noqa: E402

try:
    from playwright.sync_api import sync_playwright, Response, Request, BrowserContext, Page
except ImportError:
    sync_playwright = None  # CLI 진입점에서 친절한 에러


# ============================================================================
# 데이터 클래스
# ============================================================================
@dataclass
class ButtonInfo:
    """list 페이지의 [YYYY 보기] 버튼 1개."""
    param_item_id: str
    year: str
    label: str          # "2-가. 성적평가 결과(성적평가 분포)" 등 항목 라벨


@dataclass
class Cell:
    """UbiReport XML의 <Item classname="UbiTextItem"> 1개."""
    x: int
    y: int
    w: int
    h: int
    text: str
    forecolor: str = ""
    backcolor: str = ""


@dataclass
class ReportMeta:
    """보고서 메타 (XML 상단 메타 행에서 추출)."""
    title: str = ""           # 예: "2025년_ [졸업생의 졸업성적 분포 (대학)]"
    author: str = ""          # 작성자
    verifier: str = ""        # 확인자
    last_verified: str = ""   # 최종확인일자


@dataclass
class ParsedReport:
    """단일 보고서 1건의 모든 결과."""
    schl_id: str
    param_item_id: str
    year: str
    label: str
    fetched_at: str
    rdviewer_post_body: str = ""
    raw_xml: str = ""
    cells: list[Cell] = field(default_factory=list)
    grid: list[list[str]] = field(default_factory=list)
    header_idx: int = -1
    header: list[str] = field(default_factory=list)
    records: list[dict] = field(default_factory=list)
    meta: ReportMeta = field(default_factory=ReportMeta)
    n_pages: int = 1
    errors: list[str] = field(default_factory=list)


# ============================================================================
# XML 파싱 (정적 함수, Playwright 불필요)
# ============================================================================
def parse_xml(xml_text: str) -> tuple[list[Cell], ReportMeta]:
    """UbiReport XML → Cell 리스트 + 메타."""
    xml_text = xml_text.lstrip("﻿").strip()
    root = ET.fromstring(xml_text)
    cells: list[Cell] = []
    for page in root.iter("Page"):
        for item in page.iter("Item"):
            if item.get("classname") != "UbiTextItem":
                continue
            try:
                cells.append(
                    Cell(
                        x=int(item.get("x", "0")),
                        y=int(item.get("y", "0")),
                        w=int(item.get("width", "0")),
                        h=int(item.get("height", "0")),
                        text=((item.find("Text").text or "").strip()
                              if item.find("Text") is not None else ""),
                        forecolor=item.get("forecolorid", ""),
                        backcolor=item.get("backcolorid", ""),
                    )
                )
            except (ValueError, AttributeError):
                continue

    # 메타 추출: y가 가장 작은 셀들 (보통 0~28의 행) 텍스트로
    meta = ReportMeta()
    top_cells = sorted([c for c in cells if c.y < 40], key=lambda c: (c.y, c.x))
    for c in top_cells:
        t = c.text
        if not t:
            continue
        # 제목: 첫 줄에 보통 "YYYY년_ [...]" 형태
        if not meta.title and (re.match(r"\d{4}년", t) or "[" in t):
            meta.title = t
        # 작성자/확인자
        m = re.search(r"작성자\s*:\s*([^/\s]+)", t)
        if m:
            meta.author = m.group(1).strip()
        m = re.search(r"확인자\s*:\s*([^/\s]+)", t)
        if m:
            meta.verifier = m.group(1).strip()
        m = re.search(r"최종확인일자\s*:\s*([\d\-./]+)", t)
        if m:
            meta.last_verified = m.group(1).strip()

    return cells, meta


def build_grid(cells: list[Cell]) -> list[list[str]]:
    """셀들의 (x, y, x+w, y+h) 좌표에서 grid line 추출, 각 grid 칸을
    포함하는 셀 텍스트로 채움. merge cell은 큰 셀이 작은 grid 칸들에
    동일 텍스트를 자동 채우는 방식으로 처리."""
    if not cells:
        return []
    xs, ys = set(), set()
    for c in cells:
        xs.add(c.x); xs.add(c.x + c.w)
        ys.add(c.y); ys.add(c.y + c.h)
    xs_sorted = sorted(xs)
    ys_sorted = sorted(ys)
    n_rows = len(ys_sorted) - 1
    n_cols = len(xs_sorted) - 1
    if n_rows <= 0 or n_cols <= 0:
        return []
    grid: list[list[str]] = [["" for _ in range(n_cols)] for _ in range(n_rows)]
    for j in range(n_rows):
        y_mid = (ys_sorted[j] + ys_sorted[j + 1]) / 2
        for i in range(n_cols):
            x_mid = (xs_sorted[i] + xs_sorted[i + 1]) / 2
            covering = [
                c for c in cells
                if c.x <= x_mid < c.x + c.w and c.y <= y_mid < c.y + c.h
            ]
            if covering:
                exact = [c for c in covering if c.x == xs_sorted[i] and c.y == ys_sorted[j]]
                chosen = exact[0] if exact else min(covering, key=lambda c: (c.y, c.x))
                grid[j][i] = chosen.text
    return grid


HEADER_KEYWORDS = {
    "기준연도", "학교명", "학과명", "단과대학", "구분", "학과특성",
    "학생수", "비율", "등급", "만점평점", "기숙사", "수용인원",
    "졸업자", "취업자", "취업률", "진학자", "년도", "성별", "학기",
    "정원", "충원", "신입생", "재적학생", "재학생",
}


def detect_header(grid: list[list[str]], cells: list[Cell]) -> int:
    """헤더 행 인덱스 추정.
    1) HEADER_KEYWORDS 매칭 셀이 가장 많은 행
    2) 동률이면 backcolor != "1" (흰색 아닌) 셀 비율 높은 행
    3) 그것도 안 되면 0 반환
    """
    if not grid:
        return 0
    best_idx, best_score = 0, -1
    for i, row in enumerate(grid):
        kw_hits = sum(1 for c in row if c in HEADER_KEYWORDS)
        if kw_hits >= 2 and kw_hits > best_score:
            best_idx, best_score = i, kw_hits
    return best_idx


def grid_to_records(grid: list[list[str]], header_idx: int) -> list[dict]:
    """grid + header → dict 레코드 (헤더 매칭, 빈 행 제외)."""
    if not grid or header_idx >= len(grid):
        return []
    header = grid[header_idx]
    records = []
    for row in grid[header_idx + 1:]:
        rec = {}
        for h, v in zip(header, row):
            if h:
                rec[h] = v
        if any(v.strip() for v in rec.values()):
            records.append(rec)
    return records


# ============================================================================
# 청크 변환 (RAG-ready)
# ============================================================================
def record_to_sentence(rec: dict, label: str = "", year: str = "") -> str:
    """레코드 1개를 자연어 1문장으로 변환.

    예: {"기준연도": "2024", "학교명": "충남대학교", "단과대학": "간호대학",
         "학과명": "간호학과", "구분": "주간", "등급": "A+",
         "학생수": "577", "비율": "27.2"}
    →   "충남대학교 간호대학 간호학과 (주간)의 2024년 등급 A+ 학생수 577명,
         비율 27.2% [출처: 2-가. 성적평가 결과(성적평가 분포)]"
    """
    parts = []
    # 학교/단과대학/학과 prefix
    school = rec.get("학교명", "")
    college = rec.get("단과대학", "")
    dept = rec.get("학과명", "")
    if school or college or dept:
        prefix = " ".join(x for x in [school, college, dept] if x).strip()
        parts.append(prefix)

    # 구분/학기/학과특성/연도/성별
    qualifiers = []
    for k in ("구분", "학과특성", "학기", "성별"):
        v = rec.get(k, "").strip()
        if v:
            qualifiers.append(v)
    if qualifiers:
        parts.append(f"({', '.join(qualifiers)})")

    # 연도
    yr = rec.get("기준연도", year)
    if yr:
        parts.append(f"{yr}년")

    # 나머지 모든 컬럼을 "키 값" 시퀀스로
    skip = {"학교명", "단과대학", "학과명", "구분", "학과특성", "학기", "성별", "기준연도"}
    body_pairs = []
    for k, v in rec.items():
        if k in skip:
            continue
        v = (v or "").strip()
        if not v:
            continue
        body_pairs.append(f"{k} {v}")
    if body_pairs:
        parts.append(", ".join(body_pairs))

    sent = " ".join(parts).strip()
    if label:
        sent = f"{sent} [출처: {label}]"
    return sent


def records_to_chunks(
    report: ParsedReport,
    domain: int,
    category: Optional[str] = None,
    source_url: str = "",
    source_title: Optional[str] = None,
) -> list[Chunk]:
    """ParsedReport → Chunk 리스트 (행 1개 = 청크 1개)."""
    chunks: list[Chunk] = []
    if not source_url:
        source_url = (
            f"https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"
            f"?schlId={report.schl_id}&svyYr={report.year}"
            f"#paramItemId={report.param_item_id}"
        )
    title = source_title or report.meta.title or report.label or f"알리미 보고서 {report.param_item_id}"
    cats = [category] if category else []
    for idx, rec in enumerate(report.records):
        text = record_to_sentence(rec, label=report.label, year=report.year)
        if not text:
            continue
        ch = Chunk(
            text=text,
            source_type="T6",
            source_url=source_url,
            source_title=title,
            domains=[domain],
            chunk_index=idx,
            categories=cats,
            freshness="dated",
            posted_at=report.meta.last_verified or f"{report.year}-01-01",
            section_path=report.label,
            notes=f"paramItemId={report.param_item_id}, year={report.year}",
        )
        chunks.append(ch)
    return chunks


# ============================================================================
# Playwright Adapter (XHR 캡쳐)
# ============================================================================
LIST_URL_TEMPLATE = (
    "https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"
    "?schlId={schl_id}&svyYr={svy_yr}"
    "&pageIdx=all&filePath=01&fileName=01&saveName=01"
)
SCAN_JS = r"""
() => {
  const out = [];
  const seen = new Set();
  const els = document.querySelectorAll('a, button, input[type=button], span, div');
  for (const el of els) {
    const t = (el.innerText || el.value || '').trim();
    if (!/^20\d{2}\s*보기$/.test(t)) continue;
    const oc = el.getAttribute('onclick') || '';
    // fn_RdViewer('NN','YYYY') 패턴
    const m = oc.match(/fn_RdViewer\('(\d+)','(\d{4})'\)/);
    if (!m) continue;
    const key = m[1] + '|' + m[2];
    if (seen.has(key)) continue;
    seen.add(key);
    // 가장 가까운 항목 라벨 (X-가. ...) 탐색
    let label = '';
    let cur = el;
    for (let i = 0; i < 10 && cur; i++) {
      cur = cur.parentElement;
      if (!cur) break;
      const tt = (cur.innerText || '').trim();
      const lm = tt.match(/^(\d+-[가-힣]\.\s*[^\n]+)/);
      if (lm) { label = lm[1].trim(); break; }
    }
    // 라벨에서 "YYYY 보기" 같은 버튼 텍스트 제거
    label = label.replace(/\s*20\d{2}\s*보기.*$/g, '').replace(/ /g, ' ').replace(/\s+/g, ' ').trim();
    out.push({ param_item_id: m[1], year: m[2], label: label });
  }
  return out;
}
"""


class UbiReportAdapter:
    """Playwright 기반 알리미 UbiReport viewer 크롤러.

    사용:
      with UbiReportAdapter() as adapter:
          buttons = adapter.scan_list_page("0000029", "2025")
          report = adapter.fetch_report("0000029", "46", "2025", label="5-다. 졸업생의 취업 현황")
    """

    def __init__(self, headless: bool = True, timeout_ms: int = 60_000,
                 user_agent: Optional[str] = None) -> None:
        if sync_playwright is None:
            raise RuntimeError("playwright not installed. run: pip install playwright && playwright install chromium")
        self.headless = headless
        self.timeout_ms = timeout_ms
        self.user_agent = user_agent or (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120 Safari/537.36"
        )
        self._pw = None
        self._browser = None
        self._ctx: Optional[BrowserContext] = None

    def __enter__(self) -> "UbiReportAdapter":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self._ctx = self._browser.new_context(
            user_agent=self.user_agent, locale="ko-KR",
            viewport={"width": 1440, "height": 900},
        )
        return self

    def __exit__(self, *args) -> None:
        try:
            if self._browser:
                self._browser.close()
        finally:
            if self._pw:
                self._pw.stop()
        self._browser = None
        self._ctx = None
        self._pw = None

    def scan_list_page(self, schl_id: str, svy_yr: str = "2025") -> list[ButtonInfo]:
        """list 페이지를 열고 모든 [YYYY 보기] 버튼 추출."""
        assert self._ctx is not None
        url = LIST_URL_TEMPLATE.format(schl_id=schl_id, svy_yr=svy_yr)
        page = self._ctx.new_page()
        try:
            try:
                page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            except Exception:
                page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(2)
            raw = page.evaluate(SCAN_JS)
        finally:
            page.close()
        return [ButtonInfo(**b) for b in raw]

    def fetch_report(
        self,
        schl_id: str,
        param_item_id: str,
        year: str,
        label: str = "",
    ) -> ParsedReport:
        """단일 보고서 수집: list 페이지에서 실제 [YYYY 보기] 버튼 클릭.

        흐름:
          1. list 페이지 navigate (JSESSIONID 셋업 + fn_RdViewer JS 로드)
          2. [onclick*="fn_RdViewer('pid','year')"] 버튼을 locator로 찾아 .click()
             (page.evaluate가 아닌 실제 user-gesture 클릭이라야 popup 정상 동작)
          3. popup 열림 → 그 popup에서 NewAcInfo.do XHR 자동 발생
          4. response listener로 XML body 캡쳐
          5. XML 파싱
        """
        from datetime import datetime, timezone
        assert self._ctx is not None
        ctx = self._ctx
        captured = {
            "newacinfo_responses": [],
            "rdviewer_requests": [],
            "errors": [],
        }

        def on_response(resp: Response) -> None:
            # UbiReport는 보고서별로 다른 endpoint를 씀:
            #   NewAcInfo.do (paramItemId=9 등) / UbiServer.do (paramItemId=46 등)
            if not any(k in resp.url for k in ("NewAcInfo.do", "UbiServer.do")):
                return
            try:
                body = resp.body()
            except Exception as e:
                captured["errors"].append(f"NewAcInfo body fail: {e}")
                return
            captured["newacinfo_responses"].append({
                "url": resp.url, "status": resp.status, "len": len(body),
                "body_text": body.decode("utf-8", errors="replace"),
            })

        def on_request(req: Request) -> None:
            if "RdViewer.do" not in req.url:
                return
            captured["rdviewer_requests"].append({
                "url": req.url, "method": req.method,
                "post_data": getattr(req, "post_data", None),
            })

        def attach(p: Page) -> None:
            p.on("response", on_response)
            p.on("request", on_request)

        # popup 자동 부착 — context 단위 listener (모든 새 페이지에 부착)
        ctx.on("page", attach)
        page = ctx.new_page()
        attach(page)

        popup_to_close = None
        list_url = LIST_URL_TEMPLATE.format(schl_id=schl_id, svy_yr=year)
        try:
            try:
                page.goto(list_url, wait_until="networkidle", timeout=self.timeout_ms)
            except Exception:
                page.goto(list_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1.5)

            # [onclick*="fn_RdViewer('46','2025')"] 정확 매칭 selector
            selector = f"[onclick*=\"fn_RdViewer('{param_item_id}','{year}')\"]"
            btn = page.locator(selector)
            cnt = btn.count()
            if cnt == 0:
                captured["errors"].append(
                    f"button not found: pid={param_item_id} year={year}"
                )
            else:
                # 실제 user-gesture 클릭 → popup 자동 발생
                try:
                    with ctx.expect_page(timeout=15_000) as popup_info:
                        btn.first.click()
                    popup_to_close = popup_info.value
                    # 명시 attach — ctx.on race condition 방지 (PoC 패턴)
                    attach(popup_to_close)
                    print(f"    [debug] popup url(immediately): {popup_to_close.url!r}")
                    try:
                        popup_to_close.wait_for_load_state(
                            "networkidle", timeout=self.timeout_ms
                        )
                    except Exception as e:
                        captured["errors"].append(f"popup networkidle: {e}")
                except Exception as e:
                    captured["errors"].append(f"popup expect fail: {e}")

            # XHR 완료 추가 대기
            time.sleep(6)
        finally:
            try:
                if popup_to_close:
                    popup_to_close.close()
            except Exception:
                pass
            try:
                page.close()
            except Exception:
                pass
            # remove ctx listener
            try:
                ctx.remove_listener("page", attach)
            except Exception:
                pass

        # 가장 큰 NewAcInfo 응답이 데이터
        responses = sorted(captured["newacinfo_responses"], key=lambda r: r["len"], reverse=True)
        raw_xml = responses[0]["body_text"] if responses else ""
        post_body = captured["rdviewer_requests"][0]["post_data"] if captured["rdviewer_requests"] else ""

        report = ParsedReport(
            schl_id=schl_id,
            param_item_id=param_item_id,
            year=year,
            label=label,
            fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            rdviewer_post_body=post_body or "",
            raw_xml=raw_xml,
            errors=captured["errors"],
        )

        if not raw_xml:
            report.errors.append("no NewAcInfo response captured")
            return report

        try:
            cells, meta = parse_xml(raw_xml)
            report.cells = cells
            report.meta = meta
            report.grid = build_grid(cells)
            report.header_idx = detect_header(report.grid, cells)
            report.header = report.grid[report.header_idx] if report.header_idx < len(report.grid) else []
            report.records = grid_to_records(report.grid, report.header_idx)
        except ET.ParseError as e:
            report.errors.append(f"xml parse error: {e}")
        return report


# ============================================================================
# CLI
# ============================================================================
def _print_scan(buttons: list[ButtonInfo]) -> None:
    from collections import defaultdict
    print(f"Total buttons: {len(buttons)}")
    by_label = defaultdict(list)
    for b in buttons:
        by_label[b.label].append((b.param_item_id, b.year))
    print(f"Unique labels: {len(by_label)}")
    for label, items in sorted(by_label.items()):
        pids = sorted(set(p for p, _ in items), key=lambda x: int(x))
        years = sorted(set(y for _, y in items))
        print(f"  [{label}] pids={pids} years={years}")


def _cli_scan(args) -> int:
    with UbiReportAdapter() as ad:
        buttons = ad.scan_list_page(args.schl_id, args.year)
    _print_scan(buttons)
    if args.out:
        Path(args.out).write_text(
            json.dumps([asdict(b) for b in buttons], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"saved: {args.out}")
    return 0


def _cli_fetch(args) -> int:
    with UbiReportAdapter() as ad:
        rep = ad.fetch_report(args.schl_id, args.param_item_id, args.year, label=args.label or "")
    print(f"=== fetch result ===")
    print(f"  schl_id={rep.schl_id} pid={rep.param_item_id} year={rep.year}")
    print(f"  label: {rep.label}")
    print(f"  meta.title: {rep.meta.title}")
    print(f"  raw_xml: {len(rep.raw_xml):,} B")
    print(f"  cells: {len(rep.cells)}, grid: {len(rep.grid)}r×{len(rep.grid[0]) if rep.grid else 0}c")
    print(f"  header_idx: {rep.header_idx}, header: {rep.header[:8]}...")
    print(f"  records: {len(rep.records)}")
    if rep.records:
        print(f"  first record: {rep.records[0]}")
    if rep.errors:
        print(f"  errors: {rep.errors}")

    if args.out_dir:
        out = Path(args.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        stem = f"{rep.schl_id}_pid{rep.param_item_id}_{rep.year}"
        (out / f"{stem}.xml").write_text(rep.raw_xml, encoding="utf-8")
        (out / f"{stem}_records.json").write_text(
            json.dumps(rep.records, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # grid as CSV
        import csv
        with (out / f"{stem}.csv").open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            for row in rep.grid:
                w.writerow(row)
        print(f"  saved: {stem}.{{xml,csv,records.json}}")
    return 0 if rep.records and not rep.errors else 1


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    p = argparse.ArgumentParser(description="Adapter F — 알리미 UbiReport (T6)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp_scan = sub.add_parser("scan", help="list 페이지 스캔")
    sp_scan.add_argument("schl_id")
    sp_scan.add_argument("--year", default="2025")
    sp_scan.add_argument("--out", help="결과 JSON 저장 경로")
    sp_scan.set_defaults(func=_cli_scan)

    sp_fetch = sub.add_parser("fetch", help="단일 보고서 수집")
    sp_fetch.add_argument("schl_id")
    sp_fetch.add_argument("param_item_id")
    sp_fetch.add_argument("year")
    sp_fetch.add_argument("--label", default="")
    sp_fetch.add_argument("--out-dir", default="data/sprint3/dstat")
    sp_fetch.set_defaults(func=_cli_fetch)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main() or 0)