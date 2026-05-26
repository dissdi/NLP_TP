"""
scripts/spike_almi_ubireport.py
대학알리미 UbiReport viewer NewAcInfo.do XHR 캡쳐 PoC

목적
----
충남대(schlId=0000029) 알리미 공시정보 페이지에서 [YYYY 보기] 버튼을 자동 클릭하여
viewer 내부에서 발생하는 NewAcInfo.do XHR 응답(UbiReport XML)을 캡쳐.

검증 항목 (Phase B Sprint 3 진입 전)
-----------------------------------
B. Playwright의 page.on('response')로 XHR body 캡쳐 가능?
C. driver.get만으로 트리거 vs 버튼 클릭 필요? (정찰상 클릭 필요)
K. 페이지 스크래핑으로 paramItemId 매핑 자동 추출 가능?

성공 기준
---------
- NewAcInfo.do XHR 응답 본문 ≥ 5 KB
- 응답 XML 내 <Item classname="UbiTextItem" 셀 개수 ≥ 50개

요구사항
--------
pip install playwright
playwright install chromium

실행
----
python scripts/spike_almi_ubireport.py
결과: data/spike_ubireport/{captures.json, newacinfo_*.xml, list_page.html}
"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, Response, Request
except ImportError:
    print("[FATAL] playwright not installed. run:")
    print("        pip install playwright && playwright install chromium")
    sys.exit(2)

# ----------------------------------------------------------------------------
# 설정
# ----------------------------------------------------------------------------
SCHL_ID = "0000029"  # 충남대
SVY_YR = "2025"
# 전체목록 페이지 (학생/교육여건 등 모든 항목이 한 화면에 — 사용자 첫 스크린샷)
LIST_URL = (
    f"https://www.academyinfo.go.kr/pubinfo/pubinfo0020/list.do"
    f"?schlId={SCHL_ID}&svyYr={SVY_YR}"
    f"&pageIdx=all&filePath=01&fileName=01&saveName=01"
)
TARGET_YEAR_BTN = "2025 보기"  # 첫 클릭 대상 (어떤 항목이든 첫 번째 [2025 보기])

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "spike_ubireport"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# 캡쳐 상태
# ----------------------------------------------------------------------------
captured: dict = {
    "newacinfo_responses": [],
    "rdviewer_requests": [],
    "page_buttons": [],
    "errors": [],
}


def on_response(resp: Response) -> None:
    """모든 response 중 NewAcInfo.do만 body 캡쳐."""
    url = resp.url
    if "NewAcInfo.do" not in url:
        return
    try:
        body = resp.body()
    except Exception as e:
        captured["errors"].append(f"NewAcInfo body read fail: {e}")
        return
    captured["newacinfo_responses"].append(
        {
            "url": url,
            "status": resp.status,
            "len": len(body),
            "body_text": body.decode("utf-8", errors="replace"),
        }
    )
    print(f"  [CAPTURE] NewAcInfo.do {len(body)}B status={resp.status}")


def on_request(req: Request) -> None:
    """RdViewer.do POST 요청의 form 파라미터 캡쳐."""
    if "RdViewer.do" not in req.url:
        return
    try:
        post_data = req.post_data
    except Exception as e:
        post_data = None
        captured["errors"].append(f"RdViewer post_data fail: {e}")
    captured["rdviewer_requests"].append(
        {"url": req.url, "method": req.method, "post_data": post_data}
    )
    print(f"  [CAPTURE] RdViewer.do {req.method} body={(post_data or '')[:200]!r}")


# ----------------------------------------------------------------------------
# JS: 페이지 내 [YYYY 보기] 버튼 모두 스캔
# ----------------------------------------------------------------------------
SCAN_JS = r"""
() => {
  const results = [];
  const seen = new Set();
  const all = document.querySelectorAll('a, button, input[type=button], span, div');
  for (const el of all) {
    const text = (el.innerText || el.value || '').trim();
    if (/^20\d{2}\s*보기$/.test(text)) {
      // 중복 제거 (같은 노드 두 번 안 잡히게)
      const key = (el.outerHTML || '').slice(0, 200);
      if (seen.has(key)) continue;
      seen.add(key);
      // 부모/조상의 항목 라벨 추정 (li, dt, h3, h4 등)
      let label = '';
      let cur = el;
      for (let i = 0; i < 6 && cur; i++) {
        cur = cur.parentElement;
        if (!cur) break;
        const tt = (cur.innerText || '').trim();
        // 라벨이 "X-X. ..." 형태 시작이면 그 부분만
        const m = tt.match(/^(\d+-[가-힣]\.\s*[^\n]+)/);
        if (m) { label = m[1]; break; }
      }
      results.push({
        tag: el.tagName,
        text: text,
        onclick: el.getAttribute('onclick') || '',
        href: el.getAttribute('href') || '',
        class: el.className || '',
        label: label,
      });
    }
  }
  return results;
}
"""


def extract_param_ids(button_info: list[dict]) -> set[str]:
    """버튼 onclick에서 paramItemId 추출 시도."""
    ids: set[str] = set()
    for b in button_info:
        oc = b.get("onclick", "") or ""
        # 다양한 패턴 매칭
        for m in re.finditer(r"paramItemId[\s'\":=,(]+(\d+)", oc):
            ids.add(m.group(1))
        # 단순 숫자 인자도 (fn_view(12, ...) 식)
        if "view" in oc.lower() or "open" in oc.lower():
            for m in re.finditer(r"\b(\d{1,3})\b", oc):
                ids.add(m.group(1))
    return ids


# ----------------------------------------------------------------------------
# main
# ----------------------------------------------------------------------------
def main() -> int:
    print(f"[1] Playwright launch (headless=True)")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120 Safari/537.36"
            ),
            locale="ko-KR",
            viewport={"width": 1440, "height": 900},
        )

        def attach_listeners(page) -> None:
            page.on("response", on_response)
            page.on("request", on_request)
            page.on(
                "console",
                lambda m: None,  # 필요 시 콘솔 로깅
            )

        ctx.on("page", attach_listeners)  # popup 새 창 자동 부착
        page = ctx.new_page()
        attach_listeners(page)

        print(f"[2] Navigate to list page")
        print(f"    URL: {LIST_URL}")
        try:
            page.goto(LIST_URL, wait_until="networkidle", timeout=60_000)
        except Exception as e:
            print(f"    [WARN] goto networkidle timeout: {e}")
            print(f"    falling back to domcontentloaded")
            page.goto(LIST_URL, wait_until="domcontentloaded", timeout=30_000)

        # 페이지 렌더 추가 대기 (JS 트리거 후 항목 렌더링)
        time.sleep(3)

        # list 페이지 HTML 저장 (오프라인 검사용)
        list_html = page.content()
        (OUT_DIR / "list_page.html").write_text(list_html, encoding="utf-8")
        print(f"    list page HTML saved ({len(list_html):,} chars)")

        print(f"[3] Scan page for [YYYY 보기] buttons")
        button_info = page.evaluate(SCAN_JS)
        captured["page_buttons"] = button_info
        print(f"    found {len(button_info)} [YYYY 보기]-style buttons")
        for b in button_info[:6]:
            oc = b.get("onclick", "")[:120]
            print(f"      {b['tag']:6s} '{b['text']}' label='{b['label'][:30]}' onclick='{oc}'")

        param_ids = extract_param_ids(button_info)
        print(f"    paramItemId candidates from onclick: {sorted(param_ids)[:20]}")

        # ------------------------------------------------------------------
        # 첫 [2025 보기] 버튼 클릭 (popup 새 창 가능성 대비)
        # ------------------------------------------------------------------
        print(f"[4] Locate & click first '{TARGET_YEAR_BTN}' button")
        # Playwright locator: 정확히 그 텍스트만
        locator = page.get_by_text(TARGET_YEAR_BTN, exact=True)
        cnt = locator.count()
        print(f"    {cnt} elements match '{TARGET_YEAR_BTN}'")
        if cnt == 0:
            print(f"    [FAIL] no '{TARGET_YEAR_BTN}' button — page may not have loaded properly")
            captured["errors"].append(f"no target button: {TARGET_YEAR_BTN}")
        else:
            # 클릭 — popup 또는 same-tab navigation 모두 대응
            popup_page = None
            try:
                with ctx.expect_page(timeout=8_000) as popup_info:
                    locator.first.click()
                popup_page = popup_info.value
                attach_listeners(popup_page)
                print(f"    popup opened: {popup_page.url}")
                try:
                    popup_page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception as e:
                    print(f"    popup networkidle timeout (ok if XHR still going): {e}")
            except Exception:
                # popup 안 뜸 → same-tab일 가능성
                print(f"    no popup. checking same-tab navigation...")
                try:
                    page.wait_for_load_state("networkidle", timeout=30_000)
                except Exception as e:
                    print(f"    same-tab networkidle timeout: {e}")

        # XHR 완료 추가 대기
        print(f"[5] Sleep 8s for XHR completion")
        time.sleep(8)

        browser.close()

    # ------------------------------------------------------------------
    # 결과 저장 & 판정
    # ------------------------------------------------------------------
    print(f"\n[6] Save captures")
    summary = {
        "list_url": LIST_URL,
        "rdviewer_requests": captured["rdviewer_requests"],
        "page_buttons_count": len(captured["page_buttons"]),
        "page_buttons_sample": captured["page_buttons"][:20],
        "newacinfo_responses_meta": [
            {k: v for k, v in r.items() if k != "body_text"}
            for r in captured["newacinfo_responses"]
        ],
        "errors": captured["errors"],
    }
    (OUT_DIR / "captures.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"    summary: {OUT_DIR / 'captures.json'}")

    for i, r in enumerate(captured["newacinfo_responses"]):
        xml_path = OUT_DIR / f"newacinfo_{i:02d}_{r['len']}B.xml"
        xml_path.write_text(r["body_text"], encoding="utf-8")
        print(f"    XML #{i}: {xml_path.name} ({r['len']:,}B)")

    print(f"\n[7] Verdict")
    print(f"    NewAcInfo.do responses captured: {len(captured['newacinfo_responses'])}")
    print(f"    RdViewer.do requests seen     : {len(captured['rdviewer_requests'])}")
    print(f"    Buttons on list page          : {len(captured['page_buttons'])}")

    if not captured["newacinfo_responses"]:
        print(f"    ✗ FAIL — no NewAcInfo.do captured")
        return 1

    biggest = max(captured["newacinfo_responses"], key=lambda r: r["len"])
    n_cells = biggest["body_text"].count('<Item classname="UbiTextItem"')
    has_doc_tag = "<Doc" in biggest["body_text"]
    print(f"    biggest response: {biggest['len']:,} B, UbiTextItem cells: {n_cells}, has <Doc>: {has_doc_tag}")

    if biggest["len"] >= 5_000 and n_cells >= 50 and has_doc_tag:
        print(f"    ✓ PASS — XHR capture works, UbiReport XML extracted")
        return 0
    elif biggest["len"] >= 1_000:
        print(f"    △ PARTIAL — response captured but smaller than expected")
        print(f"      (check {biggest['len']}B XML in newacinfo_*.xml for content)")
        return 0
    else:
        print(f"    ✗ FAIL — response too small (likely error or empty)")
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
